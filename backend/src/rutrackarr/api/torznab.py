"""Torznab endpoint for Sonarr/Radarr: /torznab/api and /torznab/download/{topic_id}."""

import logging

from fastapi import APIRouter, Request, Response

from rutrackarr import __version__
from rutrackarr.rutracker.errors import RuTrackerError
from rutrackarr.torznab import feed
from rutrackarr.torznab.search import Request as SearchRequest
from rutrackarr.torznab.search import run

router = APIRouter(tags=["torznab"])
log = logging.getLogger(__name__)
XML = "application/xml"


def _authorized(request: Request) -> bool:
    key = request.query_params.get("apikey", "")
    return bool(key) and key == request.app.state.settings_service.api_key()


def _int(value: str | None) -> int | None:
    return int(value) if value and value.strip().isdigit() else None


@router.get("/api")
async def api(request: Request) -> Response:
    p = request.query_params
    t = p.get("t", "")
    if t == "caps":
        return Response(feed.caps(__version__), media_type=XML)
    if not _authorized(request):
        return Response(feed.error(100, "Incorrect API key"), media_type=XML)
    if t not in ("search", "tvsearch", "tv-search", "movie", "movie-search"):
        return Response(feed.error(202, f"No such function: {t or '(none)'}"), media_type=XML)
    if _int(p.get("offset")):
        return Response(feed.results([], str, str), media_type=XML)  # one page only
    req = SearchRequest(
        kind="tvsearch" if t.startswith("tv") else "movie" if t.startswith("movie") else "search",
        q=p.get("q", ""),
        season=_int(p.get("season")),
        ep=_int(p.get("ep")),
        cats=[int(c) for c in p.get("cat", "").split(",") if c.strip().isdigit()],
    )
    try:
        releases = await run(request.app.state.torznab_cache, req)
    except RuTrackerError as e:
        request.app.state.rutracker_store.record_error(str(e))
        log.warning("torznab %s q=%r failed: %s", req.kind, req.q, e)
        return Response(feed.error(900, f"RuTracker: {e}"), media_type=XML)
    key = request.query_params["apikey"]
    base = str(request.base_url).rstrip("/") + request.app.state.settings.normalized_url_base
    client = request.app.state.rutracker
    return Response(
        feed.results(
            releases,
            download_url=lambda tid: f"{base}/torznab/download/{tid}?apikey={key}",
            topic_url=client.topic_url,
        ),
        media_type=XML,
    )


@router.get("/download/{topic_id}")
async def download(topic_id: int, request: Request) -> Response:
    """The .torrent, fetched from RuTracker when asked for and never stored (it has the passkey)."""
    if not _authorized(request):
        return Response(feed.error(100, "Incorrect API key"), media_type=XML, status_code=401)
    try:
        data = await request.app.state.rutracker.download(topic_id)
    except RuTrackerError as e:
        request.app.state.rutracker_store.record_error(str(e))
        return Response(feed.error(900, f"RuTracker: {e}"), media_type=XML, status_code=502)
    return Response(
        data,
        media_type="application/x-bittorrent",
        headers={"Content-Disposition": f'attachment; filename="rutracker-{topic_id}.torrent"'},
    )
