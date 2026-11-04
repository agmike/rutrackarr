"""RuTracker operations: login (with captcha), session check, search, torrent download."""

import re
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from rutrackarr.rutracker import parse
from rutrackarr.rutracker.errors import LoginFailedError, NotConfiguredError, RuTrackerError
from rutrackarr.rutracker.http import RuTrackerHttp
from rutrackarr.rutracker.store import SessionStore

LOGIN = "forum/login.php"
SEARCH = "forum/tracker.php"
DOWNLOAD = "forum/dl.php"
CAPTCHA_TTL = 600


@dataclass
class LoginResult:
    status: str  # "ok" | "captcha"
    username: str | None = None
    captcha_id: str | None = None


def search_term(query: str) -> str:
    """RuTracker search: anything that isn't a letter/digit becomes the % wildcard."""
    return re.sub(r"[^0-9A-Za-zА-Яа-яЁё]+", "%", query.strip()).strip("%")


class RuTrackerClient:
    def __init__(self, http: RuTrackerHttp, store: SessionStore, credentials) -> None:  # type: ignore[no-untyped-def]
        self._http = http
        self._store = store
        self._credentials = credentials  # () -> (username, password)
        self._captchas: dict[str, tuple[float, parse.CaptchaChallenge]] = {}

    # --- captcha ---------------------------------------------------------------
    def _remember(self, ch: parse.CaptchaChallenge) -> str:
        now = time.monotonic()
        self._captchas = {k: v for k, v in self._captchas.items() if now - v[0] < CAPTCHA_TTL}
        cid = secrets.token_urlsafe(12)
        self._captchas[cid] = (now, ch)
        return cid

    def captcha(self, cid: str) -> parse.CaptchaChallenge | None:
        entry = self._captchas.get(cid)
        return entry[1] if entry and time.monotonic() - entry[0] < CAPTCHA_TTL else None

    async def captcha_image(self, cid: str) -> tuple[bytes, str]:
        ch = self.captcha(cid)
        if ch is None:
            raise RuTrackerError("Captcha expired — start the login again")
        r = await self._http.fetch_absolute(ch.image_url)
        if r.status_code != 200:
            raise RuTrackerError(f"Captcha image not available (HTTP {r.status_code})")
        return r.content, r.headers.get("content-type", "image/jpeg")

    # --- login -----------------------------------------------------------------
    async def login(
        self, captcha_id: str | None = None, captcha_code: str | None = None
    ) -> LoginResult:
        username, password = self._credentials()
        if not username or not password:
            raise NotConfiguredError("RuTracker username and password are not set")
        # ASCII button value (as Jackett): FlareSolverr submits forms as UTF-8.
        form = {"login_username": username, "login_password": password, "login": "Login"}
        if captcha_id:
            ch = self.captcha(captcha_id)
            if ch is None:
                raise LoginFailedError("Captcha expired — start the login again")
            form["cap_sid"] = ch.sid
            form[ch.code_field] = (captcha_code or "").strip()
            self._captchas.pop(captcha_id, None)
        else:
            page = await self._http.request("GET", LOGIN)
            if user := parse.logged_in_user(page.text):
                return self._logged_in(user)
            if ch := parse.captcha(page.text):
                return LoginResult("captcha", captcha_id=self._remember(ch))
        resp = await self._http.request("POST", LOGIN, form=form)
        if user := parse.logged_in_user(resp.text):
            return self._logged_in(user)
        if ch := parse.captcha(resp.text):
            return LoginResult("captcha", captcha_id=self._remember(ch))
        message = (
            parse.login_error(resp.text) or "login failed (no session after submitting the form)"
        )
        self._store.record_error(f"Login failed: {message}")
        raise LoginFailedError(message)

    def _logged_in(self, user: str) -> LoginResult:
        now = datetime.now(UTC)
        self._store.update(username=user, logged_in_at=now, last_ok_at=now, last_error=None)
        return LoginResult("ok", username=user)

    async def check(self) -> str | None:
        """Logged-in username if the stored session is valid (one cheap request)."""
        page = await self._http.request("GET", "forum/index.php")
        user = parse.logged_in_user(page.text)
        if user:
            self._store.update(username=user, last_ok_at=datetime.now(UTC))
        return user

    def logout(self) -> None:
        self._store.clear()

    # --- search / download -----------------------------------------------------
    async def search(self, query: str, forums: list[int] | None = None) -> list[parse.SearchRow]:
        params = {"nm": search_term(query)}
        if forums:
            params["f"] = ",".join(str(f) for f in forums)
        page = await self._http.request("GET", SEARCH, params=params)
        if parse.logged_in_user(page.text) is None:
            # Session expired: log in once (never in a loop) and retry.
            result = await self.login()
            if result.status != "ok":
                raise LoginFailedError("RuTracker asks for a captcha — log in on the settings page")
            page = await self._http.request("GET", SEARCH, params=params)
            if parse.logged_in_user(page.text) is None:
                raise LoginFailedError("Still not logged in after re-login")
        self._store.update(last_ok_at=datetime.now(UTC))
        return parse.search_rows(page.text)

    async def download(self, topic_id: int) -> bytes:
        resp = await self._http.request("GET", DOWNLOAD, params={"t": str(topic_id)})
        if "bittorrent" not in resp.headers.get("content-type", "") and not resp.content.startswith(
            b"d8:"
        ):
            raise RuTrackerError("RuTracker did not return a .torrent file (not logged in?)")
        return resp.content

    def topic_url(self, topic_id: int) -> str:
        return self._http.url(f"forum/viewtopic.php?t={topic_id}")
