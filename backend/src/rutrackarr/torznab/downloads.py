"""Torrents RuTrackarr served to Sonarr/Radarr, by info hash."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

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


class DownloadStore:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    def remember(self, info: TorrentInfo, topic_id: int, title: str, forum: str) -> None:
        with self._sessions.begin() as s:
            row = s.get(DownloadRow, info.info_hash) or DownloadRow(info_hash=info.info_hash)
            row.topic_id, row.title, row.forum, row.name = topic_id, title, forum, info.name
            row.files = json.dumps([[path, size] for path, size in info.files], ensure_ascii=False)
            row.created_at = datetime.now(UTC)
            s.merge(row)

    def get(self, info_hash: str) -> Download | None:
        with self._sessions() as s:
            row = s.get(DownloadRow, info_hash.strip().upper())
            if row is None:
                return None
            files = [path for path, _ in json.loads(row.files)]
            return Download(row.info_hash, row.topic_id, row.title, row.forum, row.name, files)
