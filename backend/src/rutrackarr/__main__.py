"""Entry point: `rutrackarr` / `python -m rutrackarr`."""

import uvicorn

from rutrackarr.app import create_app
from rutrackarr.config import BootstrapSettings


def main() -> None:
    settings = BootstrapSettings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
