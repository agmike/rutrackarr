"""Tracked topics: RuTracker topics RuTrackarr follows.

- **Tracked by hand** (Search page / topic URL): RuTrackarr adds the topic's torrent to
  qBittorrent itself, in the tracking category (`tracking.category`, e.g. `rutrackarr/tracked`,
  which no Sonarr/Radarr client asks for) — Sonarr/Radarr know nothing about it. RuTrackarr owns
  that torrent: a Sonarr grab of the topic reuses it without moving it, and Sonarr removing its
  release never deletes it.
- **Tracked because Sonarr/Radarr grabbed it** (`tracking.auto_track`): their torrent, in their
  categories, as before — tracking only follows it.

Tracked topics take part in every Sonarr/Radarr search like RuTracker's own results (so they're
offered even when RuTracker's search misses them); the first search that matches one links it
to that series/film and season.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from rutrackarr.activity import Activity
from rutrackarr.db.models import TrackedRow
from rutrackarr.qbit import topics
from rutrackarr.qbit.upstream import Qbit
from rutrackarr.releases.language import assess
from rutrackarr.releases.naming import file_tag, release_name
from rutrackarr.releases.sections import classify
from rutrackarr.releases.title import parse_title
from rutrackarr.rutracker import torrent
from rutrackarr.rutracker.parse import SearchRow
from rutrackarr.torznab.downloads import Download, DownloadStore

log = logging.getLogger(__name__)


class TrackingError(RuntimeError):
    pass


@dataclass(frozen=True)
class Tracked:
    topic_id: int
    title: str
    forum: str
    forum_id: int | None
    size: int
    seeders: int
    info_hash: str
    source: str  # manual | grab
    state: str  # active | gone
    content_kind: str | None
    content_id: int | None
    season: int | None
    content_title: str | None
    created_at: datetime
    last_checked_at: datetime | None
    last_changed_at: datetime | None
    error: str | None

    @property
    def manual(self) -> bool:
        return self.source == "manual"

    def row(self) -> SearchRow:
        """As a search result row, so searches can match and offer it."""
        return SearchRow(
            topic_id=self.topic_id, title=self.title, forum_id=self.forum_id, forum=self.forum,
            size=self.size, seeders=max(1, self.seeders), leechers=0, downloads=0,
            added=self.last_changed_at or self.created_at, author="", approved=None,
        )  # fmt: skip


def _utc(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


def _from_row(r: TrackedRow) -> Tracked:
    return Tracked(
        r.topic_id, r.title, r.forum, r.forum_id, r.size, r.seeders, r.info_hash.upper(),
        r.source, r.state, r.content_kind, r.content_id, r.season, r.content_title,
        _utc(r.created_at), _utc(r.last_checked_at), _utc(r.last_changed_at), r.error,  # type: ignore[arg-type]
    )  # fmt: skip


class Tracker:
    def __init__(
        self,
        sessions: sessionmaker,
        qbit: Qbit,
        activity: Activity,
        downloads: DownloadStore,
        settings: Any,  # SettingsService
        client: Any = None,  # RuTrackerClient (topic pages, .torrent downloads)
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._sessions, self._qbit, self._activity = sessions, qbit, activity
        self._downloads, self._settings, self._client = downloads, settings, client
        self._transport = transport

    # --- reading -------------------------------------------------------------------------------

    def all(self, include_gone: bool = True) -> list[Tracked]:
        with self._sessions() as s:
            q = select(TrackedRow).order_by(TrackedRow.created_at.desc())
            if not include_gone:
                q = q.where(TrackedRow.state == "active")
            return [_from_row(r) for r in s.scalars(q)]

    def get(self, topic_id: int) -> Tracked | None:
        with self._sessions() as s:
            r = s.get(TrackedRow, topic_id)
            return _from_row(r) if r else None

    def by_hash(self, rhash: str) -> Tracked | None:
        with self._sessions() as s:
            r = s.scalars(select(TrackedRow).where(TrackedRow.info_hash == rhash.upper())).first()
            return _from_row(r) if r else None

    def owns(self, rhash: str) -> bool:
        """The torrent belongs to a topic tracked by hand (RuTrackarr's, not Sonarr's)."""
        t = self.by_hash(rhash)
        return t is not None and t.manual and t.state == "active"

    def search_rows(self) -> list[SearchRow]:
        return [t.row() for t in self.all(include_gone=False)]

    def releases(self, t: Tracked) -> list[Download]:
        """Sonarr/Radarr releases (proxy downloads) that use this topic's torrent."""
        return [d for d in self._downloads.active() if (d.real_hash or "") == t.info_hash]

    # --- writing -------------------------------------------------------------------------------

    def _save(self, **fields: Any) -> None:
        with self._sessions.begin() as s:
            r = s.get(TrackedRow, fields["topic_id"]) or TrackedRow(
                topic_id=fields["topic_id"], created_at=datetime.now(UTC)
            )
            for k, v in fields.items():
                setattr(r, k, v)
            s.add(r)

    def link(
        self, topic_id: int, kind: str, content_id: int, season: int | None, name: str
    ) -> None:
        """A search matched the topic: remember which series/film (first match wins)."""
        with self._sessions.begin() as s:
            r = s.get(TrackedRow, topic_id)
            if r is None or r.content_id is not None:
                return
            r.content_kind, r.content_id, r.season, r.content_title = kind, content_id, season, name
        self._activity.event(
            "linked", f"Tracked topic linked to {kind}:{content_id}"
            f"{f' S{season}' if season is not None else ''}: {name}", topic_id=topic_id,
        )  # fmt: skip

    def on_grab(self, download: Download, rhash: str) -> None:
        """Sonarr/Radarr added a release through the proxy: track its topic (if switched on)."""
        if str(self._settings.get("tracking.auto_track") or "on") != "on" or not download.topic_id:
            return
        existing = self.get(download.topic_id)
        if existing is not None and existing.state == "active":
            return
        self._save(
            topic_id=download.topic_id, title=download.title or download.name,
            forum=download.forum, forum_id=None, size=0, seeders=0,
            info_hash=rhash.upper(), source="grab", state="active",
            content_kind=download.content_kind, content_id=download.content_id,
            season=download.season, content_title=download.release, error=None,
        )  # fmt: skip
        self._activity.event(
            "tracked", f"Tracking {download.release or download.title} (grabbed)",
            topic_id=download.topic_id,
        )  # fmt: skip

    async def track(
        self,
        topic_id: int,
        title: str | None = None,
        forum: str | None = None,
        forum_id: int | None = None,
        size: int = 0,
        seeders: int = 0,
    ) -> Tracked:
        """Track a topic by hand: add its torrent to qBittorrent (tracking category) unless it's
        there already, files tagged like any RuTrackarr release."""
        if not self._qbit.configured():
            raise TrackingError("Set up the download client (qBittorrent) first")
        existing = self.get(topic_id)
        if existing is not None and existing.state == "active" and existing.manual:
            return existing
        if not title:
            info = await self._client.topic(topic_id)
            title, forum, forum_id = info.title, info.forum, info.forum_id
        data = await self._client.download(topic_id)
        tinfo = torrent.read(data)
        rhash = tinfo.info_hash.lower()
        category = str(self._settings.get("tracking.category") or "rutrackarr/tracked")
        present = await topics.present(self._qbit, rhash)
        if present is None:
            t = parse_title(title)
            section = classify(forum or "")
            tag = file_tag(release_name(t, section, assess(t, section), None))
            if not await topics.add(
                self._qbit, data, f"rutracker-{topic_id}.torrent", tag, {"category": category}
            ):
                raise TrackingError(
                    "qBittorrent did not take the torrent (does the category exist?)"
                )
            how = f"added to qBittorrent ({category})"
        else:
            # Grabbed by Sonarr/Radarr before: RuTrackarr takes it over.
            if present.get("category") != category:
                await topics.move(self._qbit, rhash, category)
            how = "already in qBittorrent, taken over"
        self._save(
            topic_id=topic_id, title=title, forum=forum or "", forum_id=forum_id,
            size=size or sum(n for _, n in tinfo.files), seeders=seeders,
            info_hash=rhash.upper(), source="manual", state="active", error=None,
        )  # fmt: skip
        self._activity.event("tracked", f"Tracking {title} — {how}", topic_id=topic_id)
        return self.get(topic_id)  # type: ignore[return-value]

    def gone(self, rhash: str) -> None:
        """The topic's torrent disappeared from qBittorrent."""
        t = self.by_hash(rhash)
        if t is None or t.state != "active":
            return
        self._save(topic_id=t.topic_id, state="gone")
        self._activity.event(
            "gone", f"Tracked topic's torrent removed from qBittorrent: {t.title}",
            level="warn", topic_id=t.topic_id,
        )  # fmt: skip

    async def untrack(self, topic_id: int) -> None:
        """Stop following the topic; its torrent stays. One tracked by hand that Sonarr/Radarr
        use is handed over to them (moved into their releases' category)."""
        t = self.get(topic_id)
        if t is None:
            return
        cats = {d.category for d in self.releases(t) if d.category}
        if t.manual and t.state == "active" and len(cats) == 1:
            await topics.move(self._qbit, t.info_hash.lower(), cats.pop())
        with self._sessions.begin() as s:
            if (r := s.get(TrackedRow, topic_id)) is not None:
                s.delete(r)
        self._activity.event("untracked", f"No longer tracking {t.title}", topic_id=topic_id)

    async def remove(self, topic_id: int, delete_files: bool = True) -> list[str]:
        """Untrack and delete the torrent (and its download files — imported episodes are
        hardlinks in the library and stay). Releases Sonarr/Radarr still have in their queue are
        removed there first (not blocklisted). → notes on what was done."""
        t = self.get(topic_id)
        if t is None:
            raise TrackingError("Not tracked")
        notes = []
        for d in self.releases(t):
            app = "radarr" if (d.category or "").startswith(("radarr", "movie")) else "sonarr"
            if await remove_from_queue(self._settings, app, d.info_hash, self._transport):
                notes.append(f"removed from {app.title()}'s queue: {d.release or d.name}")
            self._downloads.removed(d.info_hash)
        if t.state == "active":
            await topics.delete(self._qbit, t.info_hash.lower(), delete_files)
            notes.append("torrent deleted" + (" with its files" if delete_files else ""))
        with self._sessions.begin() as s:
            if (r := s.get(TrackedRow, topic_id)) is not None:
                s.delete(r)
        self._activity.event(
            "removed", f"Removed tracked topic {t.title}: {'; '.join(notes) or 'nothing to clean'}",
            topic_id=topic_id,
        )  # fmt: skip
        return notes


async def remove_from_queue(
    settings: Any, app: str, download_id: str, transport: httpx.AsyncBaseTransport | None = None
) -> bool:
    """Take a download out of Sonarr's/Radarr's queue (not from the client, not blocklisted).
    False when it isn't queued there (already imported) or the app isn't connected."""
    url = str(settings.get(f"{app}.url") or "").strip().rstrip("/")
    key = settings.get(f"{app}.api_key")
    if not url or not key:
        return False
    try:
        async with httpx.AsyncClient(
            timeout=15, transport=transport, headers={"X-Api-Key": str(key)}
        ) as c:
            r = await c.get(
                f"{url}/api/v3/queue",
                params={"pageSize": 1000, "includeUnknownSeriesItems": "true",
                        "includeUnknownMovieItems": "true"},
            )  # fmt: skip
            records = r.json().get("records", []) if r.status_code == 200 else []
            ids = {
                q["id"]
                for q in records
                if str(q.get("downloadId", "")).upper() == download_id.upper()
            }
            for qid in ids:
                await c.delete(
                    f"{url}/api/v3/queue/{qid}",
                    params={"removeFromClient": "false", "blocklist": "false"},
                )
            return bool(ids)
    except (httpx.HTTPError, ValueError) as e:
        log.warning("%s queue removal of %s: %s", app, download_id, e)
        return False
