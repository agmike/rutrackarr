"""Tracked topics page: list (with the torrent's live state), track by hand, untrack, remove."""

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from rutrackarr.qbit.upstream import QbitError
from rutrackarr.rutracker.errors import RuTrackerError
from rutrackarr.tracking.tracker import TrackingError

router = APIRouter(prefix="/tracked", tags=["tracked"])


def topic_id_of(text: str) -> int | None:
    """A topic id, or a topic URL (…viewtopic.php?t=6918173)."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    m = re.search(r"[?&]t=(\d+)", text)
    return int(m.group(1)) if m else None


@router.get("")
async def list_tracked(request: Request) -> dict[str, Any]:
    tracker = request.app.state.tracker
    items = tracker.all()
    live: dict[str, dict[str, Any]] = {}
    error = None
    hashes = "|".join(t.info_hash.lower() for t in items if t.state == "active")
    if hashes and request.app.state.qbit.configured():
        try:
            torrents = await request.app.state.qbit.json("torrents/info", hashes=hashes)
            live = {str(t.get("hash", "")).upper(): t for t in torrents}
        except QbitError as e:
            error = str(e)
    client = request.app.state.rutracker
    out = []
    for t in items:
        q = live.get(t.info_hash, {})
        releases = tracker.releases(t)
        out.append(
            {
                "topic_id": t.topic_id, "topic_url": client.topic_url(t.topic_id),
                "title": t.title, "forum": t.forum, "source": t.source, "state": t.state,
                "content_kind": t.content_kind, "content_id": t.content_id, "season": t.season,
                "content_title": t.content_title,
                "created_at": t.created_at.isoformat(),
                "last_checked_at": t.last_checked_at.isoformat() if t.last_checked_at else None,
                "last_changed_at": t.last_changed_at.isoformat() if t.last_changed_at else None,
                "error": t.error,
                "ttl_days": t.ttl_days,
                "ttl": tracker.ttl(t),
                "expires_at": (e.isoformat() if (e := tracker.expires_at(t)) else None),
                "releases": [d.release or d.name for d in releases],
                "in_queue": len(releases),
                "torrent": {
                    k: q.get(k) for k in ("state", "progress", "size", "category", "dlspeed",
                                          "upspeed", "uploaded", "ratio")
                } if q else None,
            }
        )  # fmt: skip
    return {"error": error, "items": out}


class TrackBody(BaseModel):
    topic: str  # id or URL
    title: str | None = None  # from a search result (saves fetching the topic page)
    forum: str | None = None
    forum_id: int | None = None
    size: int = 0
    seeders: int = 0
    ttl_days: int | None = Field(default=None, ge=0, le=3650)  # None/0: never untracked


class TtlBody(BaseModel):
    # None: the default (by hand: never; grabbed: the tracking.auto_ttl_days setting); 0: never
    ttl_days: int | None = Field(default=None, ge=0, le=3650)


@router.post("")
async def track(request: Request, body: TrackBody) -> dict[str, Any]:
    topic_id = topic_id_of(body.topic)
    if topic_id is None:
        raise HTTPException(status_code=422, detail="Expected a topic id or a RuTracker topic URL")
    try:
        t = await request.app.state.tracker.track(
            topic_id,
            body.title,
            body.forum,
            body.forum_id,
            body.size,
            body.seeders,
            body.ttl_days,
        )
    except TrackingError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except (RuTrackerError, QbitError) as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    return {"topic_id": t.topic_id, "title": t.title}


@router.post("/{topic_id}/check")
async def check(topic_id: int, request: Request) -> dict[str, str]:
    """Check the topic for an update now (one RuTracker request; more when it changed)."""
    try:
        result = await request.app.state.tracker.check(topic_id)
    except TrackingError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return {"result": result}


@router.put("/{topic_id}/ttl")
def set_ttl(topic_id: int, body: TtlBody, request: Request) -> dict[str, Any]:
    tracker = request.app.state.tracker
    try:
        tracker.set_ttl(topic_id, body.ttl_days)
    except TrackingError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    t = tracker.get(topic_id)
    until = tracker.expires_at(t)
    return {
        "ttl_days": t.ttl_days,
        "ttl": tracker.ttl(t),
        "expires_at": until.isoformat() if until else None,
    }


@router.post("/{topic_id}/untrack")
async def untrack(topic_id: int, request: Request) -> dict[str, bool]:
    try:
        await request.app.state.tracker.untrack(topic_id)
    except QbitError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    return {"ok": True}


@router.delete("/{topic_id}")
async def remove(topic_id: int, request: Request, delete_files: bool = True) -> dict[str, Any]:
    try:
        notes = await request.app.state.tracker.remove(topic_id, delete_files)
    except TrackingError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except QbitError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    return {"notes": notes}


@router.post("/library-event")
async def library_event(request: Request) -> dict[str, Any]:
    """Sonarr/Radarr Connect → Webhook (On Series/Movie Delete, On Episode/Movie File Delete):
    grabbed topics are checked against the library right away (debounced) instead of at the next
    6-hourly sync. Authenticated by the API key (?apikey= or X-Api-Key), like the Torznab API."""
    key = request.query_params.get("apikey") or request.headers.get("X-Api-Key", "")
    if not key or key != request.app.state.settings_service.api_key():
        raise HTTPException(401, "API key required")
    try:
        event = (await request.json()).get("eventType", "")
    except ValueError:
        event = ""
    if event != "Test":
        schedule_library_sync(request.app)
    return {"ok": True, "event": event}


LIBRARY_EVENT_DELAY = 30.0  # seconds: a series delete sends a burst of events


def schedule_library_sync(app: Any) -> None:
    import asyncio
    import logging

    if getattr(app.state, "library_sync_task", None) and not app.state.library_sync_task.done():
        return

    async def run() -> None:
        await asyncio.sleep(LIBRARY_EVENT_DELAY)
        try:
            await app.state.tracker.sync_library()
        except Exception as e:
            logging.getLogger(__name__).warning("library sync: %s", e)

    app.state.library_sync_task = asyncio.create_task(run())
