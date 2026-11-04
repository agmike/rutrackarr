"""RuTracker session, login (with captcha), raw search; FlareSolverr test."""

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from rutrackarr.rutracker.client import RuTrackerClient
from rutrackarr.rutracker.errors import NotConfiguredError, RuTrackerError

router = APIRouter(tags=["rutracker"])


def _client(request: Request) -> RuTrackerClient:
    return request.app.state.rutracker


def _fail(e: RuTrackerError, request: Request | None = None) -> HTTPException:
    """HTTP error for the UI; RuTracker/Cloudflare failures are also kept as `last_error`."""
    if request is not None and not isinstance(e, NotConfiguredError):
        request.app.state.rutracker_store.record_error(str(e))
    return HTTPException(
        status_code=400 if isinstance(e, NotConfiguredError) else 502, detail=str(e)
    )


class SessionView(BaseModel):
    configured: bool
    has_session: bool
    username: str | None
    logged_in_at: datetime | None
    last_ok_at: datetime | None
    cf_solved_at: datetime | None
    last_error: str | None
    last_error_at: datetime | None


class LoginRequest(BaseModel):
    captcha_id: str | None = None
    captcha_code: str | None = None


class LoginView(BaseModel):
    status: str
    username: str | None = None
    captcha_id: str | None = None


class SearchResult(BaseModel):
    topic_id: int
    title: str
    forum_id: int | None
    forum: str
    size: int
    seeders: int
    leechers: int
    downloads: int
    added: datetime | None
    author: str
    approved: str | None
    url: str


class SearchView(BaseModel):
    query: str
    took_ms: int
    results: list[SearchResult]


@router.get("/rutracker/session", response_model=SessionView)
def session(request: Request) -> dict[str, Any]:
    svc = request.app.state.settings_service
    st = request.app.state.rutracker_store.load()
    return {
        "configured": bool(svc.get("rutracker.username")) and bool(svc.get("rutracker.password")),
        "has_session": bool(st.cookies.get("bb_session")),
        "username": st.username,
        "logged_in_at": st.logged_in_at,
        "last_ok_at": st.last_ok_at,
        "cf_solved_at": st.cf_solved_at,
        "last_error": st.last_error,
        "last_error_at": st.last_error_at,
    }


@router.post("/rutracker/login", response_model=LoginView)
async def login(body: LoginRequest, request: Request) -> dict[str, Any]:
    try:
        r = await _client(request).login(body.captcha_id, body.captcha_code)
    except RuTrackerError as e:
        raise _fail(e, request) from None
    return {"status": r.status, "username": r.username, "captcha_id": r.captcha_id}


@router.post("/rutracker/check")
async def check(request: Request) -> dict[str, Any]:
    try:
        user = await _client(request).check()
    except RuTrackerError as e:
        raise _fail(e, request) from None
    return {"logged_in": user is not None, "username": user}


@router.post("/rutracker/logout")
def logout(request: Request) -> dict[str, bool]:
    _client(request).logout()
    return {"ok": True}


@router.get("/rutracker/captcha/{captcha_id}")
async def captcha_image(captcha_id: str, request: Request) -> Response:
    try:
        data, ctype = await _client(request).captcha_image(captcha_id)
    except RuTrackerError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "no-store"})


@router.get("/rutracker/search", response_model=SearchView)
async def search(request: Request, q: str = "", f: str = "") -> dict[str, Any]:
    client = _client(request)
    forums = [int(x) for x in f.split(",") if x.strip().isdigit()] or None
    start = time.monotonic()
    try:
        rows = await client.search(q, forums)
    except RuTrackerError as e:
        raise _fail(e, request) from None
    return {
        "query": q,
        "took_ms": int((time.monotonic() - start) * 1000),
        "results": [{**r.__dict__, "url": client.topic_url(r.topic_id)} for r in rows],
    }


@router.post("/flaresolverr/test")
async def flaresolverr_test(request: Request) -> dict[str, str]:
    try:
        status = await request.app.state.rutracker_http.flaresolverr_health()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FlareSolverr not reachable: {e}") from None
    return {"status": status}
