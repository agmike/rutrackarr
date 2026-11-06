"""Small JSON cache in the app database (Shikimori entries and the like)."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import sessionmaker

from rutrackarr.db.models import MetadataRow


class MetadataCache:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    def get(self, key: str, max_age: timedelta) -> tuple[bool, Any]:
        """(found and fresh, value). A cached `None` (e.g. "not found") counts as found."""
        with self._sessions() as s:
            row = s.get(MetadataRow, key)
            if row is None:
                return False, None
            fetched = (
                row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=UTC)
            )
            if datetime.now(UTC) - fetched > max_age:
                return False, None
            return True, json.loads(row.value)

    def put(self, key: str, value: Any) -> None:
        with self._sessions.begin() as s:
            s.merge(
                MetadataRow(
                    key=key,
                    value=json.dumps(value, ensure_ascii=False),
                    fetched_at=datetime.now(UTC),
                )
            )
