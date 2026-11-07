"""Torrents RuTrackarr served to Sonarr/Radarr, by info hash."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from rutrackarr.db.models import DownloadRow
from rutrackarr.rutracker.torrent import TorrentInfo


@dataclass(frozen=True)
class Download:
    info_hash: str
    topic_id: int
    title: str
    forum: str
    name: str
    files: list[str]
    release: str | None = None  # served marked: the release name (proxy on)
    real_hash: str | None = None  # added through the proxy: the real torrent
    category: str | None = None
    added: bool = False
    created_at: datetime | None = None  # served
    added_at: datetime | None = None  # added through the proxy
    content_kind: str | None = None  # tv | movie: what Sonarr/Radarr grabbed it as
    content_id: int | None = None  # TVDB id / TMDb id
    season: int | None = None
    episode: int | None = None  # a single-episode release (topic's numbering)
    file: str | None = None  # …its video file in the torrent (untagged path)


class DownloadStore:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    def remember(
        self,
        info: TorrentInfo,
        topic_id: int,
        title: str,
        forum: str,
        release: str | None = None,
        content: tuple[str, int, int | None] | None = None,
        episode: int | None = None,
    ) -> None:
        """`info` is the torrent as served (marked: its hash is the one Sonarr/Radarr track);
        `content`: (tv|movie, TVDB/TMDb id, season) of the search result it was grabbed from."""
        with self._sessions.begin() as s:
            row = s.get(DownloadRow, info.info_hash) or DownloadRow(info_hash=info.info_hash)
            row.topic_id, row.title, row.forum, row.name = topic_id, title, forum, info.name
            row.files = json.dumps([[path, size] for path, size in info.files], ensure_ascii=False)
            row.release = release
            if content is not None:
                row.content_kind, row.content_id, row.season = content
            row.episode = episode
            row.created_at = datetime.now(UTC)
            s.merge(row)

    def added(self, info: TorrentInfo, release: str, real_hash: str, category: str) -> None:
        """A marked torrent was added through the proxy (`info`: as Sonarr/Radarr sent it)."""
        with self._sessions.begin() as s:
            row = s.get(DownloadRow, info.info_hash)
            if row is None:  # served before the proxy was on, or by another instance
                row = DownloadRow(info_hash=info.info_hash, topic_id=0, title="", forum="")
                row.name = info.name
                row.files = json.dumps([[p, n] for p, n in info.files], ensure_ascii=False)
                row.created_at = datetime.now(UTC)
            row.release, row.real_hash, row.category = release, real_hash.upper(), category
            row.added_at = datetime.now(UTC)
            s.merge(row)

    def active(self) -> list[Download]:
        """Downloads added through the proxy and not removed since."""
        with self._sessions() as s:
            rows = s.scalars(select(DownloadRow).where(DownloadRow.added_at.is_not(None)))
            return [_download(r) for r in rows]

    def recent(self, limit: int = 10) -> list[Download]:
        """The torrents served most recently."""
        with self._sessions() as s:
            q = select(DownloadRow).order_by(DownloadRow.created_at.desc()).limit(limit)
            return [_download(r) for r in s.scalars(q)]

    def set_file(self, info_hash: str, file: str | None) -> None:
        """The video file a single-episode release is (None: not found — the whole topic)."""
        with self._sessions.begin() as s:
            row = s.get(DownloadRow, info_hash.strip().upper())
            if row is not None:
                row.file = file

    def repoint(self, old_real: str, new_real: str) -> None:
        """A topic's torrent was replaced by its updated version."""
        with self._sessions.begin() as s:
            for row in s.scalars(
                select(DownloadRow).where(DownloadRow.real_hash == old_real.upper())
            ):
                row.real_hash = new_real.upper()

    def set_category(self, info_hash: str, category: str) -> None:
        with self._sessions.begin() as s:
            row = s.get(DownloadRow, info_hash.strip().upper())
            if row is not None:
                row.category = category

    def removed(self, info_hash: str) -> None:
        """Removed from Sonarr/Radarr's download client (kept for the import script)."""
        with self._sessions.begin() as s:
            row = s.get(DownloadRow, info_hash.strip().upper())
            if row is not None:
                row.added_at = None

    def get(self, info_hash: str) -> Download | None:
        with self._sessions() as s:
            row = s.get(DownloadRow, info_hash.strip().upper())
            return _download(row) if row is not None else None


def _download(row: DownloadRow) -> Download:
    files = [path for path, _ in json.loads(row.files)]
    return Download(
        row.info_hash, row.topic_id, row.title, row.forum, row.name, files,
        release=row.release, real_hash=row.real_hash, category=row.category,
        added=row.added_at is not None,
        created_at=_utc(row.created_at), added_at=_utc(row.added_at),
        content_kind=row.content_kind, content_id=row.content_id, season=row.season,
        episode=row.episode, file=row.file,
    )  # fmt: skip


def _utc(dt: datetime | None) -> datetime | None:
    """SQLite drops the time zone; the stored times are UTC."""
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt
