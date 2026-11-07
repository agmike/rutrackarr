"""Alerts: problems that need attention, shown as a banner in the UI and sent through Apprise
(Telegram, ntfy, Discord, email, a JSON webhook… — https://github.com/caronc/apprise/wiki).

Conditions are raised and cleared; each change is sent once (problem, then "resolved"), never
repeated while it lasts. Some events are one-off notices (a tracked topic torrent gone).
State is kept in memory: after a restart, conditions are found again by the background checks
without a fresh notification for ones that were already known in the activity log.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

log = logging.getLogger(__name__)


@dataclass
class Alert:
    key: str
    level: str  # warn | error
    message: str
    since: datetime

    def to_json(self) -> dict[str, str]:
        d = asdict(self)
        d["since"] = self.since.isoformat()
        return d


def send(urls: str, title: str, body: str) -> str | None:
    """Send through Apprise right away; None on success, else what went wrong."""
    import apprise  # imported on use: it's sizeable and only needed when alerts are set up

    targets = [u for u in urls.replace(",", " ").split() if u.strip()]
    if not targets:
        return "no Apprise URLs set"
    ap = apprise.Apprise()
    bad = [u.split("://", 1)[0] + "://…" for u in targets if not ap.add(u)]
    if bad:
        return f"not understood by Apprise: {', '.join(bad)}"
    return None if ap.notify(title=title, body=body) else "Apprise could not deliver (see logs)"


class Alerts:
    def __init__(self, urls: Callable[[], str | None]) -> None:
        self._urls = urls
        self._active: dict[str, Alert] = {}
        self._lock = threading.Lock()

    def active(self) -> list[Alert]:
        with self._lock:
            return sorted(self._active.values(), key=lambda a: a.since)

    def is_active(self, key: str) -> bool:
        return key in self._active

    def raise_(self, key: str, message: str, level: str = "error", notify: bool = True) -> None:
        with self._lock:
            known = key in self._active
            self._active[key] = Alert(
                key, level, message, self._active[key].since if known else datetime.now(UTC)
            )
        if not known and notify:
            self.notify(f"RuTrackarr: {message}", message)

    def clear(self, key: str, message: str) -> None:
        with self._lock:
            was = self._active.pop(key, None)
        if was is not None:
            self.notify(f"RuTrackarr: resolved — {message}", message)

    def notify(self, title: str, body: str) -> None:
        """Fire and forget (Apprise is synchronous; requests must not wait for it)."""
        urls = (self._urls() or "").strip()
        if not urls:
            return

        def go() -> None:
            try:
                if problem := send(urls, title, body):
                    log.warning("alert not sent: %s", problem)
            except Exception as e:
                log.warning("alert not sent: %s", e)

        threading.Thread(target=go, name="alert", daemon=True).start()

    # --- activity log hook ---------------------------------------------------------------------

    def on_event(self, kind: str, level: str, message: str) -> None:
        """Events that are alerts: RuTracker failing/back, topic torrents gone."""
        if kind == "rutracker_error":
            self.raise_("rutracker", message)
        elif kind == "rutracker_ok":
            self.clear("rutracker", message)
        elif kind == "gone":
            self.notify("RuTrackarr: topic torrent removed", message)
        elif kind == "update_failed":
            self.notify("RuTrackarr: tracked topic update failed", message)
