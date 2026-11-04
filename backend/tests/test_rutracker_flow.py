"""End-to-end flows through the API with a fake network."""

import json
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from rutrackarr.app import create_app
from rutrackarr.config import BootstrapSettings
from tests.fixtures import pages

HTML = {"content-type": "text/html; charset=windows-1251"}


class FakeNet:
    """Scripted RuTracker + FlareSolverr. `routes` maps (method, path) -> list of responders."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.routes: dict[tuple[str, str], list] = {}

    def on(self, method: str, path: str, *responders) -> None:
        self.routes.setdefault((method, path), []).extend(responders)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        key = (request.method, request.url.path)
        queue = self.routes.get(key)
        if not queue:
            return httpx.Response(404, text=f"unexpected {key}")
        responder = queue.pop(0) if len(queue) > 1 else queue[0]
        return responder(request) if callable(responder) else responder


def html(text: str, status: int = 200, cookies: dict[str, str] | None = None) -> httpx.Response:
    headers = dict(HTML)
    resp = httpx.Response(status, content=text.encode("cp1251"), headers=headers)
    if cookies:
        resp.headers.update({"set-cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())})
    return resp


@pytest.fixture
def net():
    return FakeNet()


@pytest.fixture
def api(net, tmp_path):
    app = create_app(
        BootstrapSettings(data_dir=tmp_path / "data", static_dir=tmp_path / "none"),
        transport=httpx.MockTransport(net.handler),
    )
    client = TestClient(app)
    client.put(
        "/api/settings",
        json={
            "values": {
                "rutracker.username": "tester",
                "rutracker.password": "pässword",
                "rutracker.requests_per_minute": 60,
            }
        },
    )
    return client


def test_login_ok_persists_encrypted_session(api, net, tmp_path):
    net.on("GET", "/forum/login.php", html(pages.LOGIN_FORM))
    net.on(
        "POST", "/forum/login.php", html(pages.INDEX_LOGGED_IN, cookies={"bb_session": "0-1-abc"})
    )
    r = api.post("/api/rutracker/login", json={})
    assert r.json() == {"status": "ok", "username": "tester", "captcha_id": None}
    post = next(c for c in net.calls if c.method == "POST")
    form = parse_qs(post.content.decode("ascii"), encoding="cp1251")
    assert form["login_username"] == ["tester"]
    assert form["login_password"] == ["p&#228;ssword"]  # like a browser on a cp1251 form
    assert form["login"] == ["вход"]
    assert "%E2%F5%EE%E4" in post.content.decode("ascii")  # "вход" in windows-1251
    session = api.get("/api/rutracker/session").json()
    assert session["has_session"] and session["username"] == "tester"
    raw = (tmp_path / "data" / "rutrackarr.db").read_bytes()
    assert b"0-1-abc" not in raw  # cookies stored encrypted


def test_login_captcha_round_trip(api, net):
    net.on("GET", "/forum/login.php", html(pages.LOGIN_FORM_CAPTCHA))
    net.on(
        "GET",
        "/captcha/abc/123.jpg",
        httpx.Response(200, content=b"JPEG", headers={"content-type": "image/jpeg"}),
    )
    r = api.post("/api/rutracker/login", json={}).json()
    assert r["status"] == "captcha" and r["captcha_id"]
    img = api.get(f"/api/rutracker/captcha/{r['captcha_id']}")
    assert img.status_code == 200 and img.content == b"JPEG"
    net.on("POST", "/forum/login.php", html(pages.INDEX_LOGGED_IN, cookies={"bb_session": "s"}))
    ok = api.post(
        "/api/rutracker/login", json={"captcha_id": r["captcha_id"], "captcha_code": "x7k2"}
    ).json()
    assert ok["status"] == "ok"
    post = next(c for c in net.calls if c.method == "POST")
    form = parse_qs(post.content.decode("ascii"), encoding="cp1251")
    assert form["cap_sid"] == ["SID123"] and form["cap_code_deadbeef"] == ["x7k2"]


def test_login_wrong_password(api, net):
    net.on("GET", "/forum/login.php", html(pages.LOGIN_FORM))
    net.on("POST", "/forum/login.php", html(pages.LOGIN_WRONG))
    r = api.post("/api/rutracker/login", json={})
    assert r.status_code == 502 and "неверный пароль" in r.json()["detail"]
    assert "неверный пароль" in api.get("/api/rutracker/session").json()["last_error"]


def test_cloudflare_challenge_solved_via_flaresolverr(api, net):
    challenge = httpx.Response(
        403,
        text="<title>Just a moment...</title>",
        headers={"cf-mitigated": "challenge", "server": "cloudflare"},
    )
    net.on("GET", "/forum/login.php", challenge, html(pages.LOGIN_FORM))
    solution = {
        "status": "ok",
        "solution": {
            "userAgent": "SolverUA/1.0",
            "cookies": [{"name": "cf_clearance", "value": "CLEAR"}],
        },
    }
    net.on("POST", "/v1", httpx.Response(200, json=solution))
    net.on("POST", "/forum/login.php", html(pages.INDEX_LOGGED_IN, cookies={"bb_session": "s"}))
    assert api.post("/api/rutracker/login", json={}).json()["status"] == "ok"
    retried = [c for c in net.calls if c.url.path == "/forum/login.php"][1]
    assert "cf_clearance=CLEAR" in retried.headers.get("cookie", "")
    assert retried.headers["user-agent"] == "SolverUA/1.0"
    fs = next(c for c in net.calls if c.url.path == "/v1")
    assert json.loads(fs.content)["cmd"] == "request.get"
    assert api.get("/api/rutracker/session").json()["cf_solved_at"] is not None


def test_search_relogs_in_once_when_session_expired(api, net):
    net.on(
        "GET",
        "/forum/tracker.php",
        html(pages.search_page("", logged_in=False)),
        html(pages.search_page(pages.ROW_HYOUKA)),
    )
    net.on("GET", "/forum/login.php", html(pages.LOGIN_FORM))
    net.on("POST", "/forum/login.php", html(pages.INDEX_LOGGED_IN, cookies={"bb_session": "s"}))
    r = api.get("/api/rutracker/search", params={"q": "Хёка"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["results"][0]["topic_id"] == 4211111
    assert body["results"][0]["url"].endswith("/forum/viewtopic.php?t=4211111")
    searches = [c for c in net.calls if c.url.path == "/forum/tracker.php"]
    assert len(searches) == 2 and "nm=%D5%B8%EA%E0" in str(searches[0].url)  # cp1251 "Хёка"
    assert sum(1 for c in net.calls if c.method == "POST") == 1


def test_not_configured(make_client):
    r = make_client().post("/api/rutracker/login", json={})
    assert r.status_code == 400
