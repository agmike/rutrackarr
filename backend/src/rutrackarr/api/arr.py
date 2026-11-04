"""Optional Sonarr/Radarr connections: connection test."""

from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/arr", tags=["arr"])


@router.post("/{app}/test")
async def test_connection(app: Literal["sonarr", "radarr"], request: Request) -> dict[str, str]:
    svc = request.app.state.settings_service
    url = str(svc.get(f"{app}.url") or "").rstrip("/")
    key = svc.get(f"{app}.api_key")
    if not url or not key:
        raise HTTPException(status_code=400, detail=f"{app.title()} URL and API key are not set")
    try:
        async with httpx.AsyncClient(
            timeout=10, transport=request.app.state.http_transport
        ) as client:
            r = await client.get(f"{url}/api/v3/system/status", headers={"X-Api-Key": str(key)})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"{app.title()} unreachable: {e}") from None
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
