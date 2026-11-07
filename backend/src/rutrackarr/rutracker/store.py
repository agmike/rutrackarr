"""Persistence of the RuTracker session (cookies encrypted at rest)."""

import json
from collections.abc import Callable
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
        # Called on the transitions only: (kind, message, level) — "RuTracker failing" when an
        # error follows success, "RuTracker OK" when success follows an error.
        self.on_event: Callable[[str, str, str], None] | None = None

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

    def failing(self) -> bool:
        """An error is the latest news (not cleared by a success since)."""
        return self.load().last_error is not None

    def record_error(self, message: str) -> None:
        was_failing = self.failing()
        self.update(last_error=message[:1000], last_error_at=datetime.now(UTC))
        if not was_failing and self.on_event:
            self.on_event("rutracker_error", f"RuTracker: {message[:300]}", "error")

    def mark_ok(self, **fields: object) -> None:
        """A request succeeded: clears the error shown on the status page."""
        was_failing = self.failing()
        self.update(last_ok_at=datetime.now(UTC), last_error=None, **fields)
        if was_failing and self.on_event:
            self.on_event("rutracker_ok", "RuTracker answers again", "info")

    def clear(self) -> None:
        self.update(cookies=None, username=None, logged_in_at=None, last_ok_at=None)
