"""Search sandbox: run the full Sonarr/Radarr search pipeline from the UI and show every step."""

import time
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

from rutrackarr.rutracker.errors import RuTrackerError
from rutrackarr.torznab.search import Request as SearchRequest
from rutrackarr.torznab.search import Trace, run

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
LIBRARY_TTL = 300


class Simulate(BaseModel):
    kind: Literal["tvsearch", "movie", "search"] = "tvsearch"
    q: str = ""
    tvdbid: int | None = None
    tmdbid: int | None = None
    imdbid: str | None = None
    season: int | None = None
    ep: int | None = None
    overrides: bool = True
    fresh: bool = False  # bypass the RuTracker result cache


@router.post("/search")
async def simulate(request: Request, body: Simulate) -> dict[str, Any]:
    """What Sonarr/Radarr would get for this search, and why each RuTracker topic was kept or
    dropped. Not logged as a query."""
    req = SearchRequest(
        kind=body.kind, q=body.q.strip(), season=body.season, ep=body.ep,
        tvdbid=body.tvdbid, tmdbid=body.tmdbid,
        imdbid=(body.imdbid or "").strip() or None,
    )  # fmt: skip
    trace, error, started = Trace(), None, time.monotonic()
    try:
        releases = await run(
            request.app.state.torznab_cache, req, request.app.state.resolver,
            overrides=request.app.state.overrides.get if body.overrides else None,
            trace=trace, fresh=body.fresh,
        )  # fmt: skip
    except RuTrackerError as e:
        releases, error = [], str(e)
    client = request.app.state.rutracker
    by_topic = {r.row.topic_id: r for r in releases}
    rows = []
    for d in trace.rows.values():
        rel = by_topic.get(d["topic_id"])
        rows.append(
            d | {
                "topic_url": client.topic_url(d["topic_id"]),
                "kept": rel is not None,
                "season": rel.season if rel else None,
                "categories": rel.categories if rel else [],
                "language": rel.language.label if rel else None,
            }
        )  # fmt: skip
    rows.sort(key=lambda r: (not r["kept"], -(r["seeders"] or 0)))
    return {
        "took_ms": round((time.monotonic() - started) * 1000),
        "error": error,
        "context": trace.context,
        "searches": trace.searches,
        "kept": len(releases),
        "rows": rows,
    }


@router.get("/library")
async def library(request: Request, q: str = "") -> dict[str, Any]:
    """Series and films from Sonarr/Radarr matching `q` — to pick what to simulate."""
    items = await _library(request)
    needle = q.casefold().strip()
    found = [i for i in items if needle in i["search"]] if needle else items
    return {"items": [{k: v for k, v in i.items() if k != "search"} for i in found[:25]]}


async def _library(request: Request) -> list[dict[str, Any]]:
    cached = getattr(request.app.state, "sandbox_library", None)
    if cached and time.monotonic() - cached[0] < LIBRARY_TTL:
        return cached[1]  # type: ignore[no-any-return]
    svc = request.app.state.settings_service
    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20, transport=request.app.state.http_transport) as c:
        for app, path in (("sonarr", "series"), ("radarr", "movie")):
            url = str(svc.get(f"{app}.url") or "").strip().rstrip("/")
            key = svc.get(f"{app}.api_key")
            if not url or not key:
                continue
            try:
                r = await c.get(f"{url}/api/v3/{path}", headers={"X-Api-Key": str(key)})
                data = r.json() if r.status_code == 200 else []
            except (httpx.HTTPError, ValueError):
                continue
            for s in data:
                names = [
                    s.get("title") or "",
                    *(a.get("title", "") for a in s.get("alternateTitles") or []),
                ]
                items.append(
                    {
                        "kind": "tvsearch" if app == "sonarr" else "movie",
                        "title": s.get("title") or "",
                        "year": s.get("year"),
                        "tvdbid": s.get("tvdbId") if app == "sonarr" else None,
                        "tmdbid": s.get("tmdbId") if app == "radarr" else None,
                        "imdbid": s.get("imdbId") if app == "radarr" else None,
                        "series_type": s.get("seriesType"),
                        "seasons": sorted(
                            x["seasonNumber"]
                            for x in s.get("seasons") or []
                            if x.get("seasonNumber")
                        ),
                        "search": " ".join(names).casefold(),
                    }
                )
    items.sort(key=lambda i: i["title"].casefold())
    request.app.state.sandbox_library = (time.monotonic(), items)
    return items
