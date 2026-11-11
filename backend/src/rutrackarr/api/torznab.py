"""Torznab endpoint for Sonarr/Radarr: /torznab/api and /torznab/download/{topic_id}."""

import logging
import time
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response

from rutrackarr import __version__
from rutrackarr.activity import caller_of
from rutrackarr.releases.companions import find_video, plan
from rutrackarr.releases.companions import fonts as _fonts
from rutrackarr.releases.naming import file_tag, renamed_from, tagged
from rutrackarr.releases.title import parse_title
from rutrackarr.rutracker import torrent
from rutrackarr.rutracker.errors import RuTrackerError
from rutrackarr.rutracker.ratelimit import REQUEST_COUNT
from rutrackarr.torznab import feed
from rutrackarr.torznab.search import Request as SearchRequest
from rutrackarr.torznab.search import Trace, run

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
    started, counter = time.monotonic(), [0]
    token = REQUEST_COUNT.set(counter)
    releases, error, trace = [], None, Trace()
    try:
        releases = await run(
            request.app.state.torznab_cache, req, request.app.state.resolver,
            overrides=request.app.state.overrides.get, trace=trace,
            tracked=request.app.state.tracker.searchable,
        )  # fmt: skip
        _link_tracked(request, releases, trace)
    except RuTrackerError as e:
        error = str(e)
        request.app.state.rutracker_store.record_error(error)
        log.warning("torznab %s q=%r failed: %s", req.kind, req.q, e)
    finally:
        REQUEST_COUNT.reset(token)
        request.app.state.activity.query(
            caller_of(request.headers.get("user-agent", "")),
            "rss" if req.kind == "search" and not req.q and not _has_ids(req) else req.kind,
            _describe(req),
            len(releases),
            counter[0],
            round((time.monotonic() - started) * 1000),
            error,
            list(trace.rows.values()),
        )
    if error is not None:
        return Response(feed.error(900, f"RuTracker: {error}"), media_type=XML)
    key = request.query_params["apikey"]
    base = str(request.base_url).rstrip("/") + request.app.state.settings.normalized_url_base
    client = request.app.state.rutracker
    return Response(
        feed.results(
            releases,
            download_url=lambda rel: (
                f"{base}/torznab/download/{rel.row.topic_id}?" + urlencode(_link_params(key, rel))
            ),
            topic_url=client.topic_url,
        ),
        media_type=XML,
    )


def _link_tracked(request: Request, releases: list, trace: Trace) -> None:
    """Tracked topics a series/film search matched: remember which one they are."""
    tracker = request.app.state.tracker
    for rel in releases:
        if rel.row.topic_id not in trace.tracked:
            continue
        if rel.tvdbid:
            tracker.link(rel.row.topic_id, "tv", rel.tvdbid, _season(rel), rel.name)
        elif rel.tmdbid:
            tracker.link(rel.row.topic_id, "movie", rel.tmdbid, None, rel.name)


def _link_params(key: str, rel: Any) -> dict[str, str]:
    """Download link query: the release name, and what it is (so a grab can be tracked as that
    series/film)."""
    params = {"apikey": key, "name": rel.name}
    if rel.episode is not None:
        params["ep"] = str(rel.episode)  # one episode of the topic (its numbering)
    if rel.tmdbid and not rel.tvdbid:
        params |= {"tmdbid": str(rel.tmdbid)}
    elif rel.tvdbid:
        params |= {"tvdbid": str(rel.tvdbid)}
        if (season := _season(rel)) is not None:
            params["season"] = str(season)
    return params


def _season(rel: Any) -> int | None:
    """The release's season: from the metadata (anime), else from the topic title."""
    return rel.season if rel.season is not None else rel.title.season


def _has_ids(req: SearchRequest) -> bool:
    return bool(req.tvdbid or req.tmdbid or req.imdbid)


def _describe(req: SearchRequest) -> str:
    """ "tvdb:410378 S1" / "One Piece 1156" / "tmdb:157336" / "(newest)" for the query log."""
    parts = [
        f"tvdb:{req.tvdbid}" if req.tvdbid else "",
        f"tmdb:{req.tmdbid}" if req.tmdbid else "",
        req.imdbid or "",
        req.q,
        f"S{req.season}" if req.season is not None else "",
        f"E{req.ep}" if req.ep is not None else "",
        f"#{req.absolute}" if getattr(req, "absolute", None) else "",
    ]
    return " ".join(p for p in parts if p) or "(newest)"


@router.get("/download/{topic_id}")
async def download(
    topic_id: int,
    request: Request,
    name: str = "",
    tvdbid: int | None = None,
    tmdbid: int | None = None,
    season: int | None = None,
    ep: int | None = None,
) -> Response:
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
    request.app.state.activity.event(
        "grab",
        f"{caller_of(request.headers.get('user-agent', ''))} grabbed "
        f"{name.strip() or f'topic {topic_id}'}",
        topic_id=topic_id,
    )
    release = name.strip() if request.app.state.qbit.configured() else ""
    if release:
        try:
            data = torrent.mark(data, release)
        except torrent.TorrentError as e:
            log.warning("topic %s: could not mark the torrent: %s", topic_id, e)
            release = ""
    content = ("tv", tvdbid, season) if tvdbid else ("movie", tmdbid, None) if tmdbid else None
    _remember(request, topic_id, data, release or None, content, ep)
    return Response(
        data,
        media_type="application/x-bittorrent",
        headers={"Content-Disposition": f'attachment; filename="rutracker-{topic_id}.torrent"'},
    )


def _remember(
    request: Request,
    topic_id: int,
    data: bytes,
    release: str | None = None,
    content: tuple[str, int, int | None] | None = None,
    episode: int | None = None,
) -> None:
    """Keep the info hash and file list (not the torrent) for the import script."""
    try:
        info = torrent.read(data)
    except torrent.TorrentError as e:
        log.warning("topic %s: could not read the torrent: %s", topic_id, e)
        return
    row = request.app.state.torznab_cache.find(topic_id)
    request.app.state.downloads.remember(
        info,
        topic_id,
        row.title if row else "",
        row.forum if row else "",
        release,
        content,
        episode,
    )


@router.get("/companions")
def companions(request: Request, hash: str = "", source: str = "", fonts: bool = False) -> Response:
    """For Sonarr's import script: the external tracks that belong to an imported video.

    Plain text, tab-separated: a ``#video`` line with the video's path inside the torrent (the
    script strips it from the source path to find the torrent's folder), then one line per
    companion file: path inside the torrent, suffix for the episode's name. With ``fonts``, then
    a ``#font`` line per font file of the torrent (path inside it), for a shared font folder.
    """
    if not _authorized(request):
        return Response("Incorrect API key\n", media_type="text/plain", status_code=401)
    download = request.app.state.downloads.get(hash)
    if download is None:
        return Response("Not a RuTrackarr download\n", media_type="text/plain", status_code=404)
    # Added through the qBittorrent proxy, video files are renamed on disk (the release's tag,
    # maybe an episode mark, maybe an older tag after a topic update): matched forwards from the
    # torrent's original names.
    name = PurePosixPath(source.replace("\\", "/")).name
    hits = [f for f in download.files if renamed_from(PurePosixPath(f).name, name)]
    if not hits:  # last resort: case differences
        tag = file_tag(download.release) if download.release and download.real_hash else None
        on_disk = {tagged(f, tag) if tag else f: f for f in download.files}
        if (folded := find_video(list(on_disk), source)) is not None:
            hits = [on_disk[folded]]
    if not hits:
        return Response("Video not in this torrent\n", media_type="text/plain", status_code=404)
    video = hits[0]
    found = str(PurePosixPath(video).parent / name) if "/" in video else name
    title = parse_title(download.title) if download.title else None
    lines = [f"#video\t{found}"] + [
        f"{c.path}\t{c.suffix}" for c in plan(download.files, video, title)
    ]
    if fonts:  # asked for by script versions that can link them
        lines += [f"#font\t{f}" for f in _fonts(download.files)]
    return Response("\n".join(lines) + "\n", media_type="text/plain; charset=utf-8")
