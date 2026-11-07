"""The real qBittorrent behind the proxy: one logged-in session, re-login on 403."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import httpx

log = logging.getLogger(__name__)


class QbitError(RuntimeError):
    pass


class Qbit:
    def __init__(
        self,
        url: Callable[[], str | None],
        credentials: Callable[[], tuple[str | None, str | None]],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url, self._credentials, self._transport = url, credentials, transport
        self._cookies: httpx.Cookies | None = None
        self._lock = asyncio.Lock()

    def configured(self) -> bool:
        return bool((self._url() or "").strip())

    def _base(self) -> str:
        return (self._url() or "").rstrip("/") + "/api/v2/"

    def _client(self, cookies: httpx.Cookies | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=30, transport=self._transport, cookies=cookies)

    async def _login(self) -> None:
        user, password = self._credentials()
        if not user and not password:  # qui's client proxy: no login (as Sonarr does)
            self._cookies = httpx.Cookies()
            return
        async with self._client() as c:
            try:
                r = await c.post(
                    self._base() + "auth/login",
                    data={"username": user or "", "password": password or ""},
                )
            except httpx.HTTPError as e:
                raise QbitError(f"qBittorrent unreachable: {e}") from e
        # qBittorrent < 5.2: 200 "Ok." / 200 "Fails."; 5.2+: 204 / 401.
        if r.status_code not in (200, 204) or r.text.strip() not in ("Ok.", ""):
            raise QbitError(f"qBittorrent login failed (HTTP {r.status_code})")
        self._cookies = r.cookies

    async def request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        """`path` relative to /api/v2/ ("torrents/info"); kwargs as for httpx."""
        for attempt in range(2):
            if self._cookies is None or attempt:
                async with self._lock:
                    await self._login()
            async with self._client(self._cookies) as c:
                try:
                    r = await c.request(method, self._base() + path, **kw)
                except httpx.HTTPError as e:
                    raise QbitError(f"qBittorrent unreachable: {e}") from e
            if r.status_code != 403:
                return r
        return r

    async def json(self, path: str, **params: str) -> Any:
        r = await self.request("GET", path, params=params)
        if r.status_code != 200:
            raise QbitError(f"qBittorrent {path}: HTTP {r.status_code}")
        return r.json()

    async def post(self, path: str, **data: str) -> httpx.Response:
        return await self.request("POST", path, data=data)
