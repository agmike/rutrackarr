"""Alerts: what's wrong right now (the UI banner), and a test message through Apprise."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from rutrackarr.alerts import send

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def current(request: Request) -> dict[str, Any]:
    return {"items": [a.to_json() for a in request.app.state.alerts.active()]}


class AlertTest(BaseModel):
    urls: str | None = None  # unsaved value from the form; falls back to the saved one


@router.post("/test")
async def test(request: Request, body: AlertTest | None = None) -> dict[str, str]:
    urls = (body.urls if body and body.urls else None) or request.app.state.settings_service.get(
        "alerts.apprise_urls"
    )
    if not urls:
        raise HTTPException(status_code=400, detail="No Apprise URLs set")
    problem = await asyncio.to_thread(
        send, str(urls), "RuTrackarr test alert", "Alerts from RuTrackarr reach this channel."
    )
    if problem:
        raise HTTPException(status_code=502, detail=problem)
    return {"status": "sent"}
