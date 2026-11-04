"""HTTP session for RuTracker: cookies, User-Agent, cp1251, Cloudflare via FlareSolverr."""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlencode, urljoin

import httpx

from rutrackarr.rutracker import parse
from rutrackarr.rutracker.errors import CloudflareError, MaintenanceError, RuTrackerError
from rutrackarr.rutracker.ratelimit import RequestSpacer
from rutrackarr.rutracker.store import SessionStore

log = logging.getLogger(__name__)

ENCODING = "cp1251"
# After a challenge, keep going through FlareSolverr for this long (seconds).
VIA_FLARESOLVERR_FOR = 30 * 60
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36"
)


def encode_form(data: dict[str, str]) -> bytes:
    """application/x-www-form-urlencoded in windows-1251, as RuTracker expects.

    Characters windows-1251 can't represent are sent as HTML numeric references
    (&#228;), exactly like a browser submitting the site's cp1251 login form.
    """
    return urlencode(data, encoding=ENCODING, errors="xmlcharrefreplace").encode("ascii")


def encode_query(params: dict[str, str]) -> str:
    return urlencode(params, encoding=ENCODING, errors="xmlcharrefreplace")


def is_cloudflare_challenge(resp: httpx.Response) -> bool:
    if resp.headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    if resp.status_code in (403, 503) and "cloudflare" in resp.headers.get("server", "").lower():
        head = resp.content[:4096].decode("latin-1", "replace").lower()
        return "just a moment" in head or "cf-chl" in head or "challenge-platform" in head
    return False


class RuTrackerHttp:
    def __init__(
        self,
        store: SessionStore,
        base_url: Callable[[], str],
        flaresolverr_url: Callable[[], str],
        flaresolverr_timeout: Callable[[], int],
        spacer: RequestSpacer,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._store = store
        self._base_url = base_url
        self._fs_url = flaresolverr_url
        self._fs_timeout = flaresolverr_timeout
        self._spacer = spacer
        self._transport = transport
        self._via_fs_until = 0.0

    def url(self, path: str) -> str:
        return urljoin(self._base_url().rstrip("/") + "/", path.lstrip("/"))

    def _client(self, cookies: dict[str, str], user_agent: str | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            cookies=cookies,
            headers={
                "User-Agent": user_agent or DEFAULT_UA,
                "Accept-Language": "ru,en;q=0.8",
            },
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
            transport=self._transport,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        form: dict[str, str] | None = None,
    ) -> httpx.Response:
        """One request with the stored session.

        Goes direct first; when Cloudflare challenges it, the request is repeated
        through FlareSolverr (its intended use: a browser fetches the page for us),
        and further requests go through FlareSolverr for VIA_FLARESOLVERR_FOR seconds.
        """
        url = self.url(path)
        if params:
            url = f"{url}?{encode_query(params)}"
        if time.monotonic() < self._via_fs_until:
            return await self._via_flaresolverr(method, url, form)
        state = self._store.load()
        await self._spacer.wait()
        async with self._client(state.cookies, state.user_agent) as client:
            try:
                if form is not None:
                    resp = await client.request(
                        method,
                        url,
                        content=encode_form(form),
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                else:
                    resp = await client.request(method, url)
            except httpx.HTTPError as e:
                raise RuTrackerError(f"RuTracker unreachable: {e}") from e
            # Keep cookies the site set (session, cf_clearance refreshes).
            merged = {**state.cookies, **{c.name: c.value for c in client.cookies.jar}}
            if merged != state.cookies:
                self._store.update(cookies=merged)
        if not is_cloudflare_challenge(resp):
            if resp.charset_encoding is None:
                resp.encoding = ENCODING
            self._raise_if_maintenance(resp)
            return resp
        log.info("Cloudflare challenge on %s — routing through FlareSolverr", path)
        self._via_fs_until = time.monotonic() + VIA_FLARESOLVERR_FOR
        return await self._via_flaresolverr(method, url, form)

    async def _via_flaresolverr(
        self, method: str, url: str, form: dict[str, str] | None
    ) -> httpx.Response:
        """Fetch a page through FlareSolverr's browser, carrying our session cookies."""
        state = self._store.load()
        timeout = self._fs_timeout()
        payload: dict[str, object] = {
            "cmd": "request.post" if form is not None else "request.get",
            "url": url,
            "maxTimeout": timeout * 1000,
            "cookies": [{"name": k, "value": v} for k, v in state.cookies.items()],
        }
        if form is not None:
            # FlareSolverr builds and submits the form in the browser (UTF-8).
            payload["postData"] = urlencode(form)
        await self._spacer.wait()
        try:
            async with httpx.AsyncClient(timeout=timeout + 15, transport=self._transport) as c:
                r = await c.post(self._fs_url().rstrip("/") + "/v1", json=payload)
        except httpx.HTTPError as e:
            raise CloudflareError(f"FlareSolverr unreachable: {e}") from e
        data = r.json() if "json" in r.headers.get("content-type", "") else {}
        if data.get("status") != "ok":
            raise CloudflareError(f"FlareSolverr failed: {data.get('message') or r.status_code}")
        sol = data.get("solution") or {}
        cookies = {**state.cookies, **{c["name"]: c["value"] for c in sol.get("cookies", [])}}
        self._store.update(
            cookies=cookies,
            user_agent=sol.get("userAgent") or state.user_agent,
            cf_solved_at=datetime.now(UTC),
        )
        resp = httpx.Response(
            int(sol.get("status") or 200),
            text=sol.get("response") or "",
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request(method, url),
        )
        self._raise_if_maintenance(resp)
        return resp

    @staticmethod
    def _raise_if_maintenance(resp: httpx.Response) -> None:
        if "html" not in resp.headers.get("content-type", ""):
            return
        if msg := parse.maintenance_message(resp.text):
            raise MaintenanceError(f"RuTracker is down for maintenance: {msg}")

    async def fetch_absolute(self, url: str) -> httpx.Response:
        """GET an absolute URL (e.g. the captcha image) with the session's cookies and UA."""
        state = self._store.load()
        async with self._client(state.cookies, state.user_agent) as client:
            try:
                return await client.get(url)
            except httpx.HTTPError as e:
                raise RuTrackerError(f"Could not fetch {url}: {e}") from e

    async def flaresolverr_health(self) -> str:
        url = self._fs_url().rstrip("/") + "/health"
        async with httpx.AsyncClient(timeout=10, transport=self._transport) as c:
            r = await c.get(url)
        r.raise_for_status()
        return r.json().get("status", "ok") if "json" in r.headers.get("content-type", "") else "ok"
