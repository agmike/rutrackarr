"""Tracked topics page: list (with the torrent's live state), track by hand, untrack, remove."""

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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


@router.post("")
async def track(request: Request, body: TrackBody) -> dict[str, Any]:
    topic_id = topic_id_of(body.topic)
    if topic_id is None:
        raise HTTPException(status_code=422, detail="Expected a topic id or a RuTracker topic URL")
    try:
        t = await request.app.state.tracker.track(
            topic_id, body.title, body.forum, body.forum_id, body.size, body.seeders
        )
    except TrackingError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except (RuTrackerError, QbitError) as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    return {"topic_id": t.topic_id, "title": t.title}


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


FEED_URLS = ("https://feed.rutracker.cc/atom/f/{forum_id}.atom",)


@router.get("/feed-check")
async def feed_check(request: Request, forum_id: int | None = None) -> dict[str, Any]:
    """Try RuTracker's per-section Atom feed (for update detection, M5b): status, entries and
    a few titles. `forum_id` defaults to the section of a tracked topic."""
    import httpx
    from selectolax.lexbor import LexborHTMLParser

    if forum_id is None:
        forum_id = next(
            (t.forum_id for t in request.app.state.tracker.all(False) if t.forum_id), 1105
        )
    results = []
    async with httpx.AsyncClient(
        timeout=20, transport=request.app.state.http_transport, follow_redirects=True,
        headers={"User-Agent": "RuTrackarr feed check"},
    ) as c:  # fmt: skip
        for template in FEED_URLS:
            url = template.format(forum_id=forum_id)
            try:
                r = await c.get(url)
            except httpx.HTTPError as e:
                results.append({"url": url, "error": str(e)})
                continue
            entries = LexborHTMLParser(r.text).css("entry") if r.status_code == 200 else []
            results.append(
                {
                    "url": url, "status": r.status_code,
                    "content_type": r.headers.get("content-type", ""),
                    "entries": len(entries),
                    "sample": [
                        (e.css_first("title").text(strip=True) if e.css_first("title") else "")
                        for e in entries[:5]
                    ],
                    "snippet": "" if entries else r.text[:300],
                }
            )  # fmt: skip
    return {"forum_id": forum_id, "results": results}
