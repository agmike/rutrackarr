"""Background chores while the app runs: the RuTracker heartbeat and log pruning.

The heartbeat only runs while RuTracker is failing (the status page shows an error): it checks
again every few minutes until a request succeeds, which clears the error. While all is well it
sends nothing — Sonarr's own searches keep the session fresh.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI

from rutrackarr.rutracker.errors import RuTrackerError

log = logging.getLogger(__name__)

TICK = 60  # seconds
HEARTBEAT_EVERY = 300
PRUNE_EVERY = 6 * 3600


async def tick(app: FastAPI, state: dict[str, float]) -> None:
    """One round: retry RuTracker if it's failing and due; prune the logs if due."""
    now = time.monotonic()
    store = app.state.rutracker_store
    svc = app.state.settings_service
    if (
        svc.get("rutracker.username")
        and store.failing()
        and now - state.get("heartbeat", 0) >= HEARTBEAT_EVERY
    ):
        state["heartbeat"] = now
        try:
            await app.state.rutracker.check()
        except RuTrackerError as e:
            store.record_error(str(e))
        except Exception as e:
            log.warning("heartbeat: %s", e)
    if now - state.get("prune", 0) >= PRUNE_EVERY:
        state["prune"] = now
        try:
            app.state.activity.prune(int(svc.get("general.query_log_retention_days") or 30))
        except Exception as e:
            log.warning("prune: %s", e)


async def _loop(app: FastAPI) -> None:
    state: dict[str, float] = {}
    while True:
        await tick(app, state)
        await asyncio.sleep(TICK)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[Any]:
    task = asyncio.create_task(_loop(app))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
