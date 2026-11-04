"""Settings API used by the web UI."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from rutrackarr.settings.service import ApiKeyPinnedError, SettingsError, SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsView(BaseModel):
    values: dict[str, Any]
    secrets: dict[str, bool]
    api_key_pinned: bool


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


class ApiKeyView(BaseModel):
    api_key: str
    pinned: bool


def _svc(request: Request) -> SettingsService:
    return request.app.state.settings_service


@router.get("", response_model=SettingsView)
def get_settings(request: Request) -> dict[str, Any]:
    return _svc(request).public_view()


@router.put("", response_model=SettingsView)
def update_settings(body: SettingsUpdate, request: Request) -> dict[str, Any]:
    svc = _svc(request)
    try:
        svc.update(body.values)
    except SettingsError as e:
        raise HTTPException(status_code=422, detail={"errors": e.errors}) from None
    return svc.public_view()


@router.get("/api-key", response_model=ApiKeyView)
def get_api_key(request: Request) -> dict[str, Any]:
    svc = _svc(request)
    return {"api_key": svc.api_key(), "pinned": svc.public_view()["api_key_pinned"]}


@router.post("/api-key/regenerate", response_model=ApiKeyView)
def regenerate_api_key(request: Request) -> dict[str, Any]:
    try:
        return {"api_key": _svc(request).regenerate_api_key(), "pinned": False}
    except ApiKeyPinnedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
