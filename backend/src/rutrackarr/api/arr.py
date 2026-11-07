"""Optional Sonarr/Radarr connections: connection test."""

from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/arr", tags=["arr"])


class ArrTest(BaseModel):
    """Values entered in the form but not saved yet; missing ones fall back to settings."""

    url: str | None = None
    api_key: str | None = None


class QbitTest(BaseModel):
    """Values entered but not saved yet; missing ones fall back to the saved settings."""

    mode: str | None = None
    url: str | None = None
    username: str | None = None
    password: str | None = None
    qui_url: str | None = None
    qui_token: str | None = None


@router.post("/qbittorrent/test")
async def test_qbittorrent(request: Request, body: QbitTest | None = None) -> dict[str, str]:
    """Reach the qBittorrent behind the download client proxy: log in (qBittorrent mode) or go
    through qui's client proxy (no login), then ask its version."""
    svc = request.app.state.settings_service
    b = body or QbitTest()
    url, user, password = svc.qbittorrent_target(
        qbittorrent_mode=b.mode, qbittorrent_url=b.url, qbittorrent_username=b.username,
        qbittorrent_password=b.password, qui_url=b.qui_url, qui_token=b.qui_token,
    )  # fmt: skip
    if not url:
        raise HTTPException(status_code=400, detail="Download client URL (or qui token) not set")
    url = url.rstrip("/")
    try:
        async with httpx.AsyncClient(
            timeout=10, transport=request.app.state.http_transport
        ) as client:
            if user or password:
                r = await client.post(
                    f"{url}/api/v2/auth/login",
                    data={"username": user or "", "password": password or ""},
                )
                # qBittorrent < 5.2: 200 "Ok." / 200 "Fails."; 5.2+: 204 / 401.
                if r.text.strip() == "Fails." or r.status_code in (401, 403):
                    raise HTTPException(status_code=502, detail="qBittorrent rejected the login")
                if r.status_code not in (200, 204):
                    raise HTTPException(
                        status_code=502, detail=f"qBittorrent answered HTTP {r.status_code}"
                    )
                client.cookies = r.cookies
            v = await client.get(f"{url}/api/v2/app/version")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"qBittorrent unreachable: {e}") from None
    if v.status_code in (401, 403, 404):
        raise HTTPException(
            status_code=502,
            detail=f"HTTP {v.status_code} — "
            + ("check the qui URL and token" if not user else "check the login"),
        )
    return {"app": "qBittorrent", "version": v.text.strip() if v.status_code == 200 else "?"}


@router.post("/{app}/test")
async def test_connection(
    app: Literal["sonarr", "radarr"], request: Request, body: ArrTest | None = None
) -> dict[str, str]:
    svc = request.app.state.settings_service
    body = body or ArrTest()
    url = str(body.url or svc.get(f"{app}.url") or "").strip().rstrip("/")
    key = body.api_key or svc.get(f"{app}.api_key")
    if not url or not key:
        raise HTTPException(status_code=400, detail=f"{app.title()} URL and API key are not set")
    try:
        async with httpx.AsyncClient(
            timeout=10, transport=request.app.state.http_transport
        ) as client:
            r = await client.get(f"{url}/api/v3/system/status", headers={"X-Api-Key": str(key)})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"{app.title()} unreachable: {e}") from None
    if r.is_redirect:
        where = r.headers.get("location", "")
        raise HTTPException(
            status_code=502,
            detail=f"{app.title()} redirects to {where or 'another address'} — the URL base is "
            f"probably missing, e.g. http://{app}:{8989 if app == 'sonarr' else 7878}/{app}",
        )
    if r.status_code == 401:
        raise HTTPException(status_code=502, detail=f"{app.title()} rejected the API key")
    if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
        raise HTTPException(
            status_code=502,
            detail=f"{app.title()} answered HTTP {r.status_code} — check the URL (include the "
            "URL base, e.g. http://sonarr:8989/sonarr)",
        )
    data = r.json()
    return {
        "app": str(data.get("appName") or app.title()),
        "version": str(data.get("version", "?")),
    }
