"""Status page data: connected apps, downloads in progress, recent grabs."""

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request

from rutrackarr import __version__
from rutrackarr.qbit.proxy import forget_gone
from rutrackarr.qbit.upstream import QbitError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/status", tags=["status"])

CONNECTIONS_TTL = 60  # seconds: the page refreshes often; Sonarr, TMDb, Shikimori needn't
CHECK_TIMEOUT = 10

State = Literal["ok", "warn", "error", "off"]


@dataclass
class Check:
    label: str
    ok: bool


@dataclass
class Connection:
    id: str
    name: str
    state: State
    detail: str = ""
    version: str | None = None
    checks: list[Check] = field(default_factory=list)


# --- connections -----------------------------------------------------------------------------


@router.get("/connections")
async def connections(request: Request, refresh: bool = False) -> dict[str, Any]:
    cache = getattr(request.app.state, "status_connections", None)
    if cache and not refresh and time.monotonic() - cache[0] < CONNECTIONS_TTL:
        return cache[1]  # type: ignore[no-any-return]
    checks = [
        ("sonarr", "Sonarr", _arr(request, "sonarr")),
        ("radarr", "Radarr", _arr(request, "radarr")),
        ("qbittorrent", "qBittorrent", _qbittorrent(request)),
        ("flaresolverr", "FlareSolverr", _flaresolverr(request)),
        ("tmdb", "TMDb", _tmdb(request)),
        ("shikimori", "Shikimori", _shikimori(request)),
        ("animelist", "Anime ID list", _animelist(request)),
        ("catalogue", "Section catalogue", _catalogue(request)),
    ]
    results = await asyncio.gather(*(_bounded(i, n, c) for i, n, c in checks))
    body = {"checked_at": datetime.now(UTC).isoformat(), "items": [asdict(c) for c in results]}
    request.app.state.status_connections = (time.monotonic(), body)
    return body


async def _bounded(id_: str, name: str, check: Any) -> Connection:
    try:
        return await asyncio.wait_for(check, CHECK_TIMEOUT + 5)  # type: ignore[no-any-return]
    except TimeoutError:
        return Connection(id_, name, "error", "check timed out")


async def _arr(request: Request, app: Literal["sonarr", "radarr"]) -> Connection:
    """Reachable, and set up to use RuTrackarr: its indexer, its download client (and the
    indexer using it), and — Sonarr — the companion tracks script."""
    svc = request.app.state.settings_service
    name = app.title()
    url = str(svc.get(f"{app}.url") or "").strip().rstrip("/")
    key = svc.get(f"{app}.api_key")
    if not url or not key:
        return Connection(app, name, "off", "not configured")
    base = request.app.state.settings.normalized_url_base
    try:
        async with httpx.AsyncClient(
            timeout=CHECK_TIMEOUT,
            transport=request.app.state.http_transport,
            headers={"X-Api-Key": str(key)},
        ) as c:
            status = await c.get(f"{url}/api/v3/system/status")
            if status.status_code != 200:
                return Connection(app, name, "error", f"HTTP {status.status_code}")
            parts = ["indexer", "downloadclient"] + (["notification"] if app == "sonarr" else [])
            got = await asyncio.gather(*(c.get(f"{url}/api/v3/{p}") for p in parts))
    except (httpx.HTTPError, ValueError) as e:
        return Connection(app, name, "error", f"unreachable: {e}")
    version = str(status.json().get("version", "")) or None
    lists = {p: (r.json() if r.status_code == 200 else []) for p, r in zip(parts, got, strict=True)}

    def path(value: Any) -> str:
        return urlparse(str(value or "")).path.rstrip("/")

    indexers = [
        i
        for i in lists["indexer"]
        if path(_field(i, "baseUrl")).endswith(f"{base}/torznab")
        and str(i.get("implementation", "")).lower() == "torznab"
    ]
    enabled = [
        i
        for i in indexers
        if i.get("enableRss") or i.get("enableAutomaticSearch") or i.get("enableInteractiveSearch")
    ]
    clients = [
        d
        for d in lists["downloadclient"]
        if str(d.get("implementation", "")).lower() == "qbittorrent"
        and str(_field(d, "urlBase") or "").rstrip("/") == f"{base}/qbit"
    ]
    client_ids = {d.get("id") for d in clients if d.get("enable")}
    checks = [
        Check("RuTrackarr indexer enabled", bool(enabled)),
        Check("RuTrackarr download client enabled", bool(client_ids)),
        Check(
            "Indexer uses the RuTrackarr download client",
            any(i.get("downloadClientId") in client_ids for i in enabled),
        ),
    ]
    if app == "sonarr":
        scripts = [
            n
            for n in lists["notification"]
            if "rutrackarr-companions" in str(_field(n, "path") or "")
        ]
        checks.append(Check("Companion tracks script", bool(scripts)))
    state: State = "ok" if all(c.ok for c in checks) else "warn"
    detail = "" if state == "ok" else "reachable, not fully set up"
    return Connection(app, name, state, detail, version, checks)


def _field(item: dict[str, Any], name: str) -> Any:
    return next((f.get("value") for f in item.get("fields", []) if f.get("name") == name), None)


async def _qbittorrent(request: Request) -> Connection:
    qbit = request.app.state.qbit
    if not qbit.configured():
        return Connection("qbittorrent", "qBittorrent", "off", "download client proxy off")
    try:
        r = await qbit.request("GET", "app/version")
    except QbitError as e:
        return Connection("qbittorrent", "qBittorrent", "error", str(e))
    if r.status_code != 200:
        return Connection("qbittorrent", "qBittorrent", "error", f"HTTP {r.status_code}")
    return Connection("qbittorrent", "qBittorrent", "ok", "", r.text.strip().lstrip("v") or None)


async def _flaresolverr(request: Request) -> Connection:
    try:
        status = await request.app.state.rutracker_http.flaresolverr_health()
    except Exception as e:
        return Connection("flaresolverr", "FlareSolverr", "error", f"unreachable: {e}")
    return Connection("flaresolverr", "FlareSolverr", "ok", "" if status == "ok" else status)


async def _tmdb(request: Request) -> Connection:
    tmdb = request.app.state.tmdb
    if not tmdb.configured:
        return Connection("tmdb", "TMDb", "off", "no token — non-anime ID searches use titles only")
    problem = await tmdb.check()
    return Connection("tmdb", "TMDb", "error" if problem else "ok", problem or "")


async def _shikimori(request: Request) -> Connection:
    ok = await request.app.state.shikimori.check()
    return Connection("shikimori", "Shikimori", "ok" if ok else "error", "" if ok else "no answer")


async def _animelist(request: Request) -> Connection:
    at, entries = request.app.state.animelist.info()
    if at is None:
        return Connection("animelist", "Anime ID list", "warn", "not downloaded yet")
    age = time.time() - at
    detail = f"updated {_ago(age)}" + (f", {entries} entries" if entries else "")
    return Connection("animelist", "Anime ID list", "ok" if age < 3 * 86400 else "warn", detail)


async def _catalogue(request: Request) -> Connection:
    at, sections = request.app.state.torznab_cache.catalogue_info()
    if at is None:
        return Connection("catalogue", "Section catalogue", "warn", "not loaded yet")
    age = time.time() - at
    detail = f"{sections} video sections, updated {_ago(age)}"
    return Connection(
        "catalogue", "Section catalogue", "ok" if age < 14 * 86400 else "warn", detail
    )


def _ago(seconds: float) -> str:
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 2 * 86400:
        return f"{int(seconds // 3600)} h ago"
    return f"{int(seconds // 86400)} days ago"


# --- service ---------------------------------------------------------------------------------


@router.get("/service")
def service(request: Request) -> dict[str, Any]:
    """Version, uptime, the RuTracker request budget right now, and query totals."""
    started = request.app.state.started_at
    activity = request.app.state.activity
    return {
        "version": __version__,
        "started_at": started.isoformat(),
        "uptime_seconds": round((datetime.now(UTC) - started).total_seconds()),
        "rutracker": request.app.state.spacer.stats(),
        "queries_24h": activity.stats(24),
        "queries_7d": activity.stats(24 * 7),
    }


# --- downloads -------------------------------------------------------------------------------


@router.get("/downloads")
async def downloads(request: Request) -> dict[str, Any]:
    """Releases added through the download client proxy and not removed, with their topic's
    torrent state from qBittorrent. A topic gone from qBittorrent is forgotten (and logged)."""
    qbit = request.app.state.qbit
    if not qbit.configured():
        return {"configured": False, "items": [], "totals": None}
    store, activity = request.app.state.downloads, request.app.state.activity
    active = [d for d in store.active() if d.real_hash]
    reals: dict[str, dict[str, Any]] = {}
    error = None
    if active:
        hashes = "|".join(sorted({d.real_hash.lower() for d in active if d.real_hash}))
        try:
            reals = {
                str(t.get("hash", "")).upper(): t
                for t in await qbit.json("torrents/info", hashes=hashes)
            }
        except QbitError as e:
            error = str(e)
    client = request.app.state.rutracker
    items = []
    for d in active:
        t = reals.get(d.real_hash or "")
        if t is None and error is None:
            forget_gone(store, activity, d, request.app.state.tracker)
            continue
        items.append(
            {
                "hash": d.info_hash,
                "real_hash": d.real_hash,
                "release": d.release or d.name,
                "category": d.category or "",
                "topic_id": d.topic_id,
                "topic_url": client.topic_url(d.topic_id) if d.topic_id else None,
                "added_at": d.added_at.isoformat() if d.added_at else None,
                "status": _status(t) if t else "unknown",
                **{
                    k: (t.get(k) if t else None)
                    for k in (
                        "state",
                        "progress",
                        "size",
                        "dlspeed",
                        "upspeed",
                        "eta",
                        "ratio",
                        "uploaded",
                        "downloaded",
                        "num_seeds",
                        "num_leechs",
                    )
                },
            }
        )
    order = {"downloading": 0, "stalled": 1, "queued": 2, "stopped": 3, "error": 4, "seeding": 5}
    items.sort(key=lambda i: (order.get(i["status"], 6), i["release"]))
    # Totals per topic torrent: several releases can share one.
    torrents = list(reals.values())
    totals = {
        "releases": len(items),
        "torrents": len(torrents),
        "downloading": sum(1 for i in items if i["status"] in ("downloading", "stalled", "queued")),
        "seeding": sum(1 for i in items if i["status"] == "seeding"),
        "dlspeed": sum(int(t.get("dlspeed") or 0) for t in torrents),
        "upspeed": sum(int(t.get("upspeed") or 0) for t in torrents),
        "uploaded": sum(int(t.get("uploaded") or 0) for t in torrents),
        "size": sum(int(t.get("size") or 0) for t in torrents),
    }
    return {"configured": True, "error": error, "items": items, "totals": totals}


def _status(t: dict[str, Any]) -> str:
    state = str(t.get("state", ""))
    if state in ("error", "missingFiles"):
        return "error"
    if t.get("progress", 0) >= 1 or state.endswith("UP"):
        return "seeding"
    if state in ("stoppedDL", "pausedDL"):
        return "stopped"
    if state in ("queuedDL", "checkingDL", "checkingResumeData", "metaDL", "forcedMetaDL"):
        return "queued"
    if state == "stalledDL":
        return "stalled"
    return "downloading"


# --- activity and queries --------------------------------------------------------------------


@router.get("/events")
def events(request: Request, limit: int = 25, exclude: str = "") -> dict[str, Any]:
    """Newest first; `exclude`: comma-separated kinds left out (e.g. "grab")."""
    kinds = tuple(k.strip() for k in exclude.split(",") if k.strip())
    client = request.app.state.rutracker
    return {
        "items": [
            {
                "at": e.at.isoformat(),
                "kind": e.kind,
                "level": e.level,
                "message": e.message,
                "topic_url": client.topic_url(e.topic_id) if e.topic_id else None,
            }
            for e in request.app.state.activity.events(max(1, min(limit, 200)), kinds)
        ]
    }


@router.get("/queries")
def queries(
    request: Request, limit: int = 25, errors: bool = False, empty: bool = False
) -> dict[str, Any]:
    """Newest first; `errors`: failed ones only; `empty`: ones that found nothing."""
    activity = request.app.state.activity
    return {
        "items": [
            {
                "id": q.id,
                "at": q.at.isoformat(),
                "caller": q.caller,
                "kind": q.kind,
                "query": q.query,
                "results": q.results,
                "rutracker_requests": q.rutracker_requests,
                "duration_ms": q.duration_ms,
                "error": q.error,
            }
            for q in activity.queries(max(1, min(limit, 200)), errors, empty)
        ]
    }


# --- recent grabs ----------------------------------------------------------------------------


@router.get("/grabs")
def grabs(request: Request, limit: int = 10) -> dict[str, Any]:
    """The .torrent files served most recently (what Sonarr/Radarr grabbed)."""
    client = request.app.state.rutracker
    out = []
    for d in request.app.state.downloads.recent(max(1, min(limit, 50))):
        out.append(
            {
                "hash": d.info_hash,
                "release": d.release or d.title or d.name,
                "topic_id": d.topic_id,
                "topic_url": client.topic_url(d.topic_id) if d.topic_id else None,
                "served_at": d.created_at.isoformat() if d.created_at else None,
                "via_proxy": d.real_hash is not None,
                "category": d.category,
            }
        )
    return {"items": out}


@router.get("/queries/{query_id}")
def query_detail(query_id: int, request: Request) -> dict[str, Any]:
    client = request.app.state.rutracker
    rows = request.app.state.activity.details(query_id)
    return {"items": [r | {"topic_url": client.topic_url(r["topic_id"])} for r in rows]}


@router.get("/dropped")
def dropped(request: Request, reason: str = "", limit: int = 100) -> dict[str, Any]:
    """Topics searches found but dropped (newest first); `reason`: a prefix such as "unparsed"
    or "not " (didn't match the series)."""
    client = request.app.state.rutracker
    rows = request.app.state.activity.dropped(reason, max(1, min(limit, 500)))
    return {"items": [r | {"topic_url": client.topic_url(r["topic_id"])} for r in rows]}
