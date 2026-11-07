"""Application factory."""

from datetime import UTC, datetime

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from rutrackarr import __version__
from rutrackarr.activity import Activity
from rutrackarr.alerts import Alerts
from rutrackarr.api import alerts as alerts_api
from rutrackarr.api import arr as arr_api
from rutrackarr.api import overrides as overrides_api
from rutrackarr.api import rutracker as rutracker_api
from rutrackarr.api import sandbox as sandbox_api
from rutrackarr.api import settings as settings_api
from rutrackarr.api import status as status_api
from rutrackarr.api import system
from rutrackarr.api import torznab as torznab_api
from rutrackarr.api import tracked as tracked_api
from rutrackarr.background import lifespan
from rutrackarr.config import BootstrapSettings
from rutrackarr.crypto import SecretBox
from rutrackarr.db.engine import make_engine, make_sessionmaker, migrate
from rutrackarr.metadata.animelist import AnimeList
from rutrackarr.metadata.cache import MetadataCache
from rutrackarr.metadata.shikimori import Shikimori
from rutrackarr.metadata.sonarr import RadarrTitles, SonarrTitles
from rutrackarr.metadata.tmdb import Tmdb
from rutrackarr.qbit import proxy as qbit_proxy
from rutrackarr.qbit.upstream import Qbit
from rutrackarr.rutracker.client import RuTrackerClient
from rutrackarr.rutracker.http import RuTrackerHttp
from rutrackarr.rutracker.ratelimit import RequestSpacer
from rutrackarr.rutracker.store import SessionStore
from rutrackarr.settings.service import SettingsService
from rutrackarr.torznab.downloads import DownloadStore
from rutrackarr.torznab.idsearch import Resolver
from rutrackarr.torznab.overrides import OverrideStore
from rutrackarr.torznab.search import SearchCache
from rutrackarr.tracking.tracker import Tracker


def create_app(
    settings: BootstrapSettings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or BootstrapSettings()
    base = settings.normalized_url_base

    app = FastAPI(
        lifespan=lifespan,
        title="RuTrackarr",
        version=__version__,
        docs_url=f"{base}/api/docs",
        openapi_url=f"{base}/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.http_transport = transport

    engine = make_engine(settings.data_dir)
    migrate(engine)
    sessions = make_sessionmaker(engine)
    box = SecretBox.from_settings(settings.secret_key, settings.data_dir)
    svc = SettingsService(sessions, box, settings.api_key)
    app.state.settings_service = svc
    svc.api_key()  # ensure a Torznab API key exists

    app.state.started_at = datetime.now(UTC)
    app.state.activity = Activity(sessions)
    app.state.alerts = Alerts(lambda: svc.get("alerts.apprise_urls"))
    app.state.activity.listeners.append(app.state.alerts.on_event)
    store = SessionStore(sessions, box)
    store.on_event = lambda kind, message, level: app.state.activity.event(
        kind, message, level=level
    )
    http = RuTrackerHttp(
        store,
        base_url=lambda: str(svc.get("rutracker.base_url")),
        flaresolverr_url=lambda: str(svc.get("flaresolverr.url")),
        flaresolverr_timeout=lambda: int(svc.get("flaresolverr.timeout_seconds") or 60),
        spacer=(
            spacer := RequestSpacer(lambda: int(svc.get("rutracker.requests_per_minute") or 10))
        ),
        transport=transport,
    )
    app.state.rutracker_store = store
    if store.failing():  # known before this start: shown, not sent again
        app.state.alerts.raise_("rutracker", f"RuTracker: {store.load().last_error}", notify=False)
    app.state.spacer = spacer
    app.state.rutracker_http = http
    app.state.rutracker = RuTrackerClient(
        http, store, lambda: (svc.get("rutracker.username"), svc.get("rutracker.password"))
    )

    app.state.downloads = DownloadStore(sessions)
    app.state.overrides = OverrideStore(sessions)
    app.state.qbit = Qbit(
        lambda: svc.qbittorrent_target()[0],
        lambda: svc.qbittorrent_target()[1:],
        transport,
    )
    app.state.tracker = Tracker(
        sessions, app.state.qbit, app.state.activity, app.state.downloads, svc,
        app.state.rutracker, transport,
    )  # fmt: skip
    ua = f"RuTrackarr/{__version__} (+https://github.com/agmike/rutrackarr)"
    app.state.animelist = AnimeList(settings.data_dir / "anime-list.json", transport, user_agent=ua)
    app.state.shikimori = Shikimori(MetadataCache(sessions), transport, user_agent=ua)
    app.state.tmdb = Tmdb(
        lambda: svc.get("tmdb.read_access_token"), MetadataCache(sessions), transport
    )
    app.state.resolver = Resolver(
        app.state.animelist,
        app.state.shikimori,
        SonarrTitles(lambda: svc.get("sonarr.url"), lambda: svc.get("sonarr.api_key"), transport),
        app.state.tmdb,
        RadarrTitles(lambda: svc.get("radarr.url"), lambda: svc.get("radarr.api_key"), transport),
    )
    app.state.torznab_cache = SearchCache(
        app.state.rutracker,
        catalogue_path=settings.data_dir / "sections.json",
        ttl=lambda: 60 * int(svc.get("search.cache_minutes") or 0),
        rss_ttl=lambda: 60 * int(svc.get("search.rss_cache_minutes") or 0),
    )

    app.include_router(torznab_api.router, prefix=f"{base}/torznab")
    app.include_router(qbit_proxy.router, prefix=f"{base}/qbit")
    app.include_router(system.router, prefix=f"{base}/api")
    app.include_router(settings_api.router, prefix=f"{base}/api")
    app.include_router(rutracker_api.router, prefix=f"{base}/api")
    app.include_router(arr_api.router, prefix=f"{base}/api")
    app.include_router(status_api.router, prefix=f"{base}/api")
    app.include_router(alerts_api.router, prefix=f"{base}/api")
    app.include_router(overrides_api.router, prefix=f"{base}/api")
    app.include_router(sandbox_api.router, prefix=f"{base}/api")
    app.include_router(tracked_api.router, prefix=f"{base}/api")

    # Built SPA: static assets + index.html fallback for client-side routes.
    # The build uses relative asset URLs; <base href> carries the URL base.
    static = settings.static_dir
    if (static / "index.html").is_file():
        index_html = (static / "index.html").read_text(encoding="utf-8")
        index_html = index_html.replace('<base href="/" />', f'<base href="{base}/" />', 1)
        app.mount(f"{base}/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get(f"{base}/{{path:path}}", include_in_schema=False, response_model=None)
        async def spa(path: str) -> FileResponse | HTMLResponse:
            if path.startswith(("api/", "torznab/", "qbit/")):
                return HTMLResponse("Not Found", status_code=404)
            candidate = (static / path).resolve()
            if path and candidate.is_file() and static.resolve() in candidate.parents:
                return FileResponse(candidate)
            return HTMLResponse(index_html)

    return app
