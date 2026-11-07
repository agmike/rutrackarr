"""Torznab endpoint for Sonarr/Radarr: /torznab/api and /torznab/download/{topic_id}."""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response

from rutrackarr import __version__
from rutrackarr.releases.companions import find_video, plan
from rutrackarr.releases.naming import file_tag, tagged
from rutrackarr.releases.title import parse_title
from rutrackarr.rutracker import torrent
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


def _imdb(value: str | None) -> str | None:
    """Radarr sends "tt0816692" or just the digits."""
    v = (value or "").strip()
    if not v:
        return None
    return v if v.startswith("tt") else f"tt{int(v):07d}" if v.isdigit() else None


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
        tvdbid=_int(p.get("tvdbid")),
        tmdbid=_int(p.get("tmdbid")),
        imdbid=_imdb(p.get("imdbid")),
    )
    try:
        releases = await run(request.app.state.torznab_cache, req, request.app.state.resolver)
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
            download_url=lambda rel: (
                f"{base}/torznab/download/{rel.row.topic_id}?"
                + urlencode({"apikey": key, "name": rel.name})
            ),
            topic_url=client.topic_url,
        ),
        media_type=XML,
    )


@router.get("/download/{topic_id}")
async def download(topic_id: int, request: Request, name: str = "") -> Response:
    """The .torrent, fetched from RuTracker when asked for and never stored (it has the passkey).

    With the qBittorrent proxy on, marked with the release `name` (see rutrackarr.qbit.proxy):
    each release is its own download, added through the proxy as the real topic."""
    if not _authorized(request):
        return Response(feed.error(100, "Incorrect API key"), media_type=XML, status_code=401)
    try:
        data = await request.app.state.rutracker.download(topic_id)
    except RuTrackerError as e:
        request.app.state.rutracker_store.record_error(str(e))
        return Response(feed.error(900, f"RuTracker: {e}"), media_type=XML, status_code=502)
    release = name.strip() if request.app.state.qbit.configured() else ""
    if release:
        try:
            data = torrent.mark(data, release)
        except torrent.TorrentError as e:
            log.warning("topic %s: could not mark the torrent: %s", topic_id, e)
            release = ""
    _remember(request, topic_id, data, release or None)
    return Response(
        data,
        media_type="application/x-bittorrent",
        headers={"Content-Disposition": f'attachment; filename="rutracker-{topic_id}.torrent"'},
    )


def _remember(request: Request, topic_id: int, data: bytes, release: str | None = None) -> None:
    """Keep the info hash and file list (not the torrent) for the import script."""
    try:
        info = torrent.read(data)
    except torrent.TorrentError as e:
        log.warning("topic %s: could not read the torrent: %s", topic_id, e)
        return
    row = request.app.state.torznab_cache.find(topic_id)
    request.app.state.downloads.remember(
        info, topic_id, row.title if row else "", row.forum if row else "", release
    )


@router.get("/companions")
def companions(request: Request, hash: str = "", source: str = "") -> Response:
    """For Sonarr's import script: the external tracks that belong to an imported video.

    Plain text, tab-separated: a ``#video`` line with the video's path inside the torrent (the
    script strips it from the source path to find the torrent's folder), then one line per
    companion file: path inside the torrent, suffix for the episode's name.
    """
    if not _authorized(request):
        return Response("Incorrect API key\n", media_type="text/plain", status_code=401)
    download = request.app.state.downloads.get(hash)
    if download is None:
        return Response("Not a RuTrackarr download\n", media_type="text/plain", status_code=404)
    # Added through the qBittorrent proxy: video files carry the release's tag on disk.
    tag = file_tag(download.release) if download.release and download.real_hash else None
    on_disk = {tagged(f, tag) if tag else f: f for f in download.files}
    found = find_video(list(on_disk), source)
    if found is None:
        return Response("Video not in this torrent\n", media_type="text/plain", status_code=404)
    video = on_disk[found]
    title = parse_title(download.title) if download.title else None
    lines = [f"#video\t{found}"] + [
        f"{c.path}\t{c.suffix}" for c in plan(download.files, video, title)
    ]
    return Response("\n".join(lines) + "\n", media_type="text/plain; charset=utf-8")
