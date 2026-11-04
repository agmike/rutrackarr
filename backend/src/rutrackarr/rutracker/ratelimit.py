"""Spacing between requests to RuTracker (shared by everything that talks to it)."""

import asyncio
import time
from collections.abc import Callable


class RequestSpacer:
    """Allow at most `per_minute()` requests per minute by spacing them evenly."""

    def __init__(self, per_minute: Callable[[], int]) -> None:
        self._per_minute = per_minute
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def wait(self) -> None:
        async with self._lock:
            interval = 60.0 / max(1, self._per_minute())
            now = time.monotonic()
            if now < self._next_at:
                await asyncio.sleep(self._next_at - now)
                now = time.monotonic()
            self._next_at = now + interval
