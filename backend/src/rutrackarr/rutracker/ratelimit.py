"""Spacing between requests to RuTracker (shared by everything that talks to it)."""

import asyncio
import contextvars
import time
from collections import deque
from collections.abc import Callable

# Requests made on behalf of the current Torznab query (the query log's "RuTracker requests";
# none = answered from cache). A list so tasks spawned by the query add to the same count.
REQUEST_COUNT: contextvars.ContextVar[list[int] | None] = contextvars.ContextVar(
    "rutracker_request_count", default=None
)


class RequestSpacer:
    """Allow at most `per_minute()` requests per minute by spacing them evenly."""

    def __init__(self, per_minute: Callable[[], int]) -> None:
        self._per_minute = per_minute
        self._lock = asyncio.Lock()
        self._next_at = 0.0
        self._waiting = 0
        self._recent: deque[float] = deque()

    async def wait(self) -> None:
        self._waiting += 1
        try:
            async with self._lock:
                interval = 60.0 / max(1, self._per_minute())
                now = time.monotonic()
                if now < self._next_at:
                    await asyncio.sleep(self._next_at - now)
                    now = time.monotonic()
                self._next_at = now + interval
        finally:
            self._waiting -= 1
        self._recent.append(now)
        counter = REQUEST_COUNT.get()
        if counter is not None:
            counter[0] += 1

    def stats(self) -> dict[str, int]:
        """Requests in the last minute, the limit, how many wait their turn, and roughly how
        long the last of them waits."""
        now = time.monotonic()
        while self._recent and now - self._recent[0] > 60:
            self._recent.popleft()
        per_minute = max(1, self._per_minute())
        backlog = max(0.0, self._next_at - now) + max(0, self._waiting - 1) * 60.0 / per_minute
        return {
            "per_minute": per_minute,
            "last_minute": len(self._recent),
            "waiting": self._waiting,
            "wait_seconds": round(backlog) if self._waiting else 0,
        }
