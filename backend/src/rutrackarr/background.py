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
SERVICES_EVERY = 300
FAILED_SEARCHES = 5  # failed Torznab searches within FAILED_WINDOW raise an alert
FAILED_WINDOW = 0.25  # hours


def due(state: dict[str, float], key: str, now: float, every: float) -> bool:
    """Never run (whatever the clock says — monotonic time starts at boot), or `every` ago."""
    last = state.get(key)
    return last is None or now - last >= every


async def tick(app: FastAPI, state: dict[str, float]) -> None:
    """One round: retry RuTracker if it's failing and due; prune the logs if due."""
    now = time.monotonic()
    store = app.state.rutracker_store
    svc = app.state.settings_service
    if (
        svc.get("rutracker.username")
        and store.failing()
        and due(state, "heartbeat", now, HEARTBEAT_EVERY)
    ):
        state["heartbeat"] = now
        try:
            await app.state.rutracker.check()
        except RuTrackerError as e:
            store.record_error(str(e))
        except Exception as e:
            log.warning("heartbeat: %s", e)
    await track_updates(app, state, now)
    if due(state, "services", now, SERVICES_EVERY):
        state["services"] = now
        await check_services(app)
    if due(state, "prune", now, PRUNE_EVERY):
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


async def check_services(app: FastAPI) -> None:
    """FlareSolverr and qBittorrent reachable; not too many failed searches lately."""
    alerts = app.state.alerts
    try:
        await app.state.rutracker_http.flaresolverr_health()
        alerts.clear("flaresolverr", "FlareSolverr answers again")
    except Exception as e:
        alerts.raise_("flaresolverr", f"FlareSolverr unreachable: {e}")
    qbit = app.state.qbit
    if qbit.configured():
        try:
            r = await qbit.request("GET", "app/version")
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            alerts.clear("qbittorrent", "qBittorrent answers again")
        except Exception as e:
            alerts.raise_("qbittorrent", f"qBittorrent unreachable: {e}")
    else:
        alerts.clear("qbittorrent", "qBittorrent proxy switched off")
    try:
        failed = app.state.activity.stats(FAILED_WINDOW)["errors"]
    except Exception as e:
        log.warning("failed-search check: %s", e)
        return
    if failed >= FAILED_SEARCHES:
        alerts.raise_(
            "searches",
            f"{failed} Sonarr/Radarr searches failed in the last {int(FAILED_WINDOW * 60)} min",
            level="warn",
        )
    elif failed == 0:
        alerts.clear("searches", "searches succeed again")


LIBRARY_SYNC_HOURS = 6
EXPIRE_EVERY = 3600  # seconds: untrack topics past their TTL


async def track_updates(app: FastAPI, state: dict[str, float], now: float) -> None:
    """Tracked topics: the section feeds every `tracking.feed_minutes`, a couple of slow
    per-topic checks per round (each one RuTracker request), the Sonarr/Radarr library sync and
    the TTL (topics not updated for too long are untracked)."""
    tracker, svc = app.state.tracker, app.state.settings_service
    if not app.state.qbit.configured() or not svc.get("rutracker.username"):
        return
    try:
        if due(state, "feeds", now, 60 * int(svc.get("tracking.feed_minutes") or 15)):
            state["feeds"] = now
            await tracker.poll_feeds()
        for t in tracker.due(limit=2):
            await tracker.check(t.topic_id)
        if due(state, "library", now, LIBRARY_SYNC_HOURS * 3600):
            state["library"] = now
            await tracker.sync_library()
        if due(state, "expire", now, EXPIRE_EVERY):
            state["expire"] = now
            await tracker.expire()
    except Exception as e:
        log.warning("tracked topic checks: %s", e)
