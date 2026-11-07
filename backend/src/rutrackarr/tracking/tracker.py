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
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from rutrackarr.activity import Activity
from rutrackarr.db.models import TrackedRow
from rutrackarr.qbit import topics
from rutrackarr.qbit.upstream import Qbit
from rutrackarr.releases.language import assess
from rutrackarr.releases.naming import file_tag, release_name, tagged
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
        # Search rows by topic id (the Torznab result cache): section and size of a grab.
        self.find_row: Callable[[int], SearchRow | None] = lambda _topic_id: None
        self.spacer: Any = None  # RuTracker request spacing (feeds count against the budget)

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
        row = self.find_row(download.topic_id)
        self._save(
            topic_id=download.topic_id, title=download.title or download.name,
            forum=download.forum, forum_id=row.forum_id if row else None,
            size=row.size if row else 0, seeders=row.seeders if row else 0,
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

    # --- updates -------------------------------------------------------------------------------

    async def poll_feeds(self) -> int:
        """Read the feed of every section with tracked topics; check the topics it lists as
        changed since their last check. → topics checked."""
        by_forum: dict[int, list[Tracked]] = {}
        for t in self.all(include_gone=False):
            if t.forum_id:
                by_forum.setdefault(t.forum_id, []).append(t)
        checked = 0
        async with httpx.AsyncClient(
            timeout=30, transport=self._transport, follow_redirects=True
        ) as c:
            for forum_id, tracked in by_forum.items():
                if self.spacer is not None:
                    await self.spacer.wait()
                try:
                    r = await c.get(FEED_URL.format(forum_id=forum_id))
                    entries = feed_entries(r.text) if r.status_code == 200 else {}
                except httpx.HTTPError as e:
                    log.warning("feed %s: %s", forum_id, e)
                    continue
                for t in tracked:
                    if t.topic_id not in entries:
                        continue
                    when = entries[t.topic_id]
                    if t.last_checked_at and when and when <= t.last_checked_at:
                        continue
                    await self.check(t.topic_id)
                    checked += 1
        return checked

    def due(self, limit: int = 2) -> list[Tracked]:
        """Topics whose slow per-topic check is due: ongoing ones every `tracking.check_hours`,
        finished ones a week as rarely; never-checked ones first."""
        hours = int(self._settings.get("tracking.check_hours") or 24)
        now = datetime.now(UTC)
        due = []
        for t in self.all(include_gone=False):
            every = timedelta(hours=hours * (1 if ongoing(t.title) else COMPLETE_CHECK_FACTOR))
            if t.last_checked_at is None or now - t.last_checked_at >= every:
                due.append(t)
        due.sort(key=lambda t: t.last_checked_at or datetime.min.replace(tzinfo=UTC))
        return due[:limit]

    async def check(self, topic_id: int) -> str:
        """Look at the topic now: title, section and its torrent's hash (magnet link) from the
        page; the new torrent is applied when the hash changed. → "unchanged" | "updated" |
        "gone" | the error."""
        t = self.get(topic_id)
        if t is None:
            raise TrackingError("Not tracked")
        now = datetime.now(UTC)
        try:
            info = await self._client.topic(topic_id)
        except Exception as e:
            self._save(topic_id=topic_id, last_checked_at=now, error=f"check failed: {e}")
            return str(e)
        self._save(
            topic_id=topic_id, last_checked_at=now, title=info.title, forum=info.forum or t.forum,
            forum_id=info.forum_id or t.forum_id, error=None,
        )  # fmt: skip
        if t.state != "active":
            return "gone"
        if info.info_hash and info.info_hash == t.info_hash:
            return "unchanged"
        try:
            data = await self._client.download(topic_id)
            if torrent.read(data).info_hash == t.info_hash:
                return "unchanged"  # no magnet link on the page: compared the .torrent
            await self.apply_update(self.get(topic_id), info.title, data)  # type: ignore[arg-type]
        except Exception as e:
            log.warning("update of topic %s failed: %s", topic_id, e)
            self._save(topic_id=topic_id, error=f"update failed: {e}")
            self._activity.event(
                "update_failed", f"Updating {info.title} failed: {e}", level="error",
                topic_id=topic_id,
            )  # fmt: skip
            return f"update failed: {e}"
        return "updated"

    async def apply_update(self, t: Tracked, title: str, data: bytes) -> None:
        """Replace the topic's torrent by its new version in place: same folder, category and
        file names (so the recheck finds what's already downloaded), then drop the old one
        keeping its data, and re-point Sonarr's/Radarr's releases."""
        old_hash = t.info_hash.lower()
        old = await topics.present(self._qbit, old_hash)
        if old is None:
            self.gone(t.info_hash)
            return
        new = torrent.read(data)
        new_hash = new.info_hash.lower()
        if await topics.present(self._qbit, new_hash) is None:
            form = {
                "category": old.get("category") or "", "savepath": old.get("save_path") or "",
                "stopped": "true", "paused": "true",
            }  # fmt: skip
            upload = (f"rutracker-{t.topic_id}.torrent", data, "application/x-bittorrent")
            r = await self._qbit.request(
                "POST", "torrents/add", data=form, files=[("torrents", upload)]
            )
            if r.status_code != 200 or r.text.strip() == "Fails.":
                raise TrackingError(
                    f"qBittorrent did not take the new torrent (HTTP {r.status_code})"
                )
            old_files = [f.get("name", "") for f in await topics.files(self._qbit, old_hash)]
            new_files = [f.get("name", "") for f in await topics.files(self._qbit, new_hash)]
            old_root, new_root = _root(old_files), _root(new_files)
            if old_root and new_root and old_root != new_root:
                await self._qbit.post(
                    "torrents/renameFolder", hash=new_hash, oldPath=new_root, newPath=old_root
                )
                new_files = [old_root + f[len(new_root) :] for f in new_files]
            old_tag, new_tag = _tag(t.title, t.forum), _tag(title, t.forum)
            existing = set(old_files)
            for f in new_files:
                target = tagged(f, old_tag)
                target = target if target in existing else tagged(f, new_tag)
                if target != f:
                    await self._qbit.post(
                        "torrents/renameFile", hash=new_hash, oldPath=f, newPath=target
                    )
            await self._qbit.post("torrents/recheck", hashes=new_hash)
            if not str(old.get("state", "")).startswith(("stopped", "paused")):
                await topics.start(self._qbit, new_hash)
        await topics.delete(self._qbit, old_hash, delete_files=False)
        self._downloads.repoint(old_hash, new_hash)
        before = parse_title(t.title).episodes
        after = parse_title(title).episodes
        change = (
            f"episodes {before.first}-{before.last} → {after.first}-{after.last}"
            if before and after and (before.first, before.last) != (after.first, after.last)
            else "new torrent"
        )
        self._save(
            topic_id=t.topic_id, info_hash=new_hash.upper(), title=title,
            size=sum(n for _, n in new.files), last_changed_at=datetime.now(UTC), error=None,
        )  # fmt: skip
        self._activity.event(
            "updated", f"Tracked topic updated ({change}): {title}", topic_id=t.topic_id
        )


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


# --- update detection and applying updates (M5b) ----------------------------------------------

FEED_URL = "https://feed.rutracker.cc/atom/f/{forum_id}.atom"
COMPLETE_CHECK_FACTOR = 7  # finished topics: checked this many times less often
_TOPIC_LINK = re.compile(r"[?&]t=(\d+)")


def ongoing(title: str) -> bool:
    """Episodes still to come ("1-7 из 12"), or unknown."""
    e = parse_title(title).episodes
    if e is None:
        return True
    if e.complete:
        return False
    return not (e.total and e.last and e.last >= e.total)


def feed_entries(xml: str) -> dict[int, datetime | None]:
    """Topic id → last update, from a RuTracker section's Atom feed."""
    from selectolax.lexbor import LexborHTMLParser

    out: dict[int, datetime | None] = {}
    for entry in LexborHTMLParser(xml).css("entry"):
        link = entry.css_first("link")
        href = (link.attributes.get("href") if link is not None else "") or ""
        ident = entry.css_first("id")
        m = _TOPIC_LINK.search(href) or _TOPIC_LINK.search(ident.text() if ident else "")
        if not m:
            continue
        updated = entry.css_first("updated")
        when = None
        if updated is not None:
            try:
                when = datetime.fromisoformat(updated.text(strip=True).replace("Z", "+00:00"))
            except ValueError:
                when = None
        out[int(m.group(1))] = when
    return out


def _root(files: list[str]) -> str:
    """The torrent's top folder ("" for a single file)."""
    heads = {f.split("/", 1)[0] for f in files if "/" in f}
    return heads.pop() if len(heads) == 1 and all("/" in f for f in files) else ""


def _tag(title: str, forum: str) -> str:
    t = parse_title(title)
    section = classify(forum or "")
    return file_tag(release_name(t, section, assess(t, section), None))
