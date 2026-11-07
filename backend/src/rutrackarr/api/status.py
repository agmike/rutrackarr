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


# --- downloads -------------------------------------------------------------------------------


@router.get("/downloads")
async def downloads(request: Request) -> dict[str, Any]:
    """Releases added through the download client proxy and not removed, with their topic's
    torrent state from qBittorrent."""
    qbit = request.app.state.qbit
    if not qbit.configured():
        return {"configured": False, "items": []}
    active = [d for d in request.app.state.downloads.active() if d.real_hash]
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
        items.append(
            {
                "hash": d.info_hash,
                "release": d.release or d.name,
                "category": d.category or "",
                "topic_id": d.topic_id,
                "topic_url": client.topic_url(d.topic_id) if d.topic_id else None,
                "added_at": d.added_at.isoformat() if d.added_at else None,
                "status": _status(t) if t else ("unknown" if error else "missing"),
                "state": t.get("state") if t else None,
                "progress": t.get("progress") if t else None,
                "size": t.get("size") if t else None,
                "dlspeed": t.get("dlspeed") if t else None,
                "upspeed": t.get("upspeed") if t else None,
                "eta": t.get("eta") if t else None,
                "ratio": t.get("ratio") if t else None,
            }
        )
    order = {"downloading": 0, "stalled": 1, "queued": 2, "stopped": 3, "error": 4, "seeding": 5}
    items.sort(key=lambda i: (order.get(i["status"], 6), i["added_at"] or ""), reverse=False)
    return {"configured": True, "error": error, "items": items}


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
