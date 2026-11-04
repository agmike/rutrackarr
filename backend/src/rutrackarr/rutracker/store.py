"""Persistence of the RuTracker session (cookies encrypted at rest)."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from rutrackarr.crypto import SecretBox
from rutrackarr.db.models import RuTrackerSessionRow


@dataclass
class SessionState:
    cookies: dict[str, str]
    user_agent: str | None
    username: str | None
    logged_in_at: datetime | None
    last_ok_at: datetime | None
    cf_solved_at: datetime | None
    last_error: str | None
    last_error_at: datetime | None


class SessionStore:
    def __init__(self, sessions: sessionmaker, box: SecretBox) -> None:
        self._sessions = sessions
        self._box = box

    def load(self) -> SessionState:
        with self._sessions() as s:
            row = s.get(RuTrackerSessionRow, 1)
            cookies: dict[str, str] = {}
            if row is not None and row.cookies:
                plain = self._box.decrypt(row.cookies)
                cookies = json.loads(plain) if plain else {}
            return SessionState(
                cookies=cookies,
                user_agent=row.user_agent if row else None,
                username=row.username if row else None,
                logged_in_at=row.logged_in_at if row else None,
                last_ok_at=row.last_ok_at if row else None,
                cf_solved_at=row.cf_solved_at if row else None,
                last_error=row.last_error if row else None,
                last_error_at=row.last_error_at if row else None,
            )

    def update(self, **fields: object) -> None:
        """Update columns; `cookies` (a dict) is encrypted before storing."""
        with self._sessions.begin() as s:
            row = s.get(RuTrackerSessionRow, 1)
            if row is None:
                row = RuTrackerSessionRow(id=1)
                s.add(row)
            for key, value in fields.items():
                if key == "cookies":
                    value = self._box.encrypt(json.dumps(value)) if value else None
                setattr(row, key, value)

    def record_error(self, message: str) -> None:
        self.update(last_error=message[:1000], last_error_at=datetime.now(UTC))

    def clear(self) -> None:
        self.update(cookies=None, username=None, logged_in_at=None, last_ok_at=None)
