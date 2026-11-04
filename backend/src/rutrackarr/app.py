"""Application factory."""

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from rutrackarr import __version__
from rutrackarr.api import settings as settings_api
from rutrackarr.api import system
from rutrackarr.config import BootstrapSettings
from rutrackarr.crypto import SecretBox
from rutrackarr.db.engine import make_engine, make_sessionmaker, migrate
from rutrackarr.settings.service import SettingsService


def create_app(settings: BootstrapSettings | None = None) -> FastAPI:
    settings = settings or BootstrapSettings()
    base = settings.normalized_url_base

    app = FastAPI(
        title="rutrackarr",
        version=__version__,
        docs_url=f"{base}/api/docs",
        openapi_url=f"{base}/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings

    engine = make_engine(settings.data_dir)
    migrate(engine)
    app.state.settings_service = SettingsService(
        make_sessionmaker(engine),
        SecretBox.from_settings(settings.secret_key, settings.data_dir),
        settings.api_key,
    )
    app.state.settings_service.api_key()  # ensure a Torznab API key exists

    app.include_router(system.router, prefix=f"{base}/api")
    app.include_router(settings_api.router, prefix=f"{base}/api")

    # Built SPA: static assets + index.html fallback for client-side routes.
    # The build uses relative asset URLs; <base href> carries the URL base.
    static = settings.static_dir
    if (static / "index.html").is_file():
        index_html = (static / "index.html").read_text(encoding="utf-8")
        index_html = index_html.replace('<base href="/" />', f'<base href="{base}/" />', 1)
        app.mount(f"{base}/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get(f"{base}/{{path:path}}", include_in_schema=False, response_model=None)
        async def spa(path: str) -> FileResponse | HTMLResponse:
            if path.startswith("api/"):
                return HTMLResponse("Not Found", status_code=404)
            candidate = (static / path).resolve()
            if path and candidate.is_file() and static.resolve() in candidate.parents:
                return FileResponse(candidate)
            return HTMLResponse(index_html)

    return app
