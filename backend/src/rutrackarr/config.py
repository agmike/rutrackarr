"""Bootstrap configuration from the environment.

Only what is needed before the database exists lives here; everything else is
managed on the settings page and stored in the database.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class BootstrapSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RUTRACKARR_", env_file=None)

    host: str = "0.0.0.0"  # noqa: S104 - container default; bind address is the operator's choice
    port: int = 8787
    data_dir: Path = Path("/data")
    # Serve under a path prefix behind a reverse proxy (e.g. "/rutrackarr").
    url_base: str = ""
    log_level: str = "info"
    # Key for encrypting secrets at rest; generated into data_dir when unset.
    secret_key: str | None = None
    # Optional pinned Torznab API key (e.g. managed by a deployment tool).
    api_key: str | None = None
    # Built frontend (static files); empty → API only.
    static_dir: Path = Path(__file__).parent / "static"

    @property
    def normalized_url_base(self) -> str:
        base = self.url_base.strip().rstrip("/")
        return "" if base in ("", "/") else ("/" + base.lstrip("/"))
