import httpx
from fastapi.testclient import TestClient

from rutrackarr.app import create_app
from rutrackarr.config import BootstrapSettings


def make(tmp_path, handler):
    app = create_app(
        BootstrapSettings(data_dir=tmp_path / "d", static_dir=tmp_path / "s"),
        transport=httpx.MockTransport(handler),
    )
    return TestClient(app)


def test_sonarr_ok_and_key_sent(tmp_path):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["key"] = str(req.url), req.headers.get("x-api-key")
        return httpx.Response(200, json={"appName": "Sonarr", "version": "4.0.20.3014"})

    c = make(tmp_path, handler)
    c.put(
        "/api/settings",
        json={"values": {"sonarr.url": "http://sonarr:8989/sonarr/", "sonarr.api_key": "k123"}},
    )
    r = c.post("/api/arr/sonarr/test")
    assert r.json() == {"app": "Sonarr", "version": "4.0.20.3014"}
    assert seen == {"url": "http://sonarr:8989/sonarr/api/v3/system/status", "key": "k123"}


def test_radarr_wrong_key_and_missing(tmp_path):
    c = make(tmp_path, lambda req: httpx.Response(401))
    assert c.post("/api/arr/radarr/test").status_code == 400  # not configured
    c.put(
        "/api/settings",
        json={"values": {"radarr.url": "http://radarr:7878/radarr", "radarr.api_key": "bad"}},
    )
    r = c.post("/api/arr/radarr/test")
    assert r.status_code == 502 and "rejected the API key" in r.json()["detail"]


def test_html_answer_hints_url_base(tmp_path):
    c = make(
        tmp_path,
        lambda req: httpx.Response(200, text="<html>", headers={"content-type": "text/html"}),
    )
    c.put(
        "/api/settings",
        json={"values": {"sonarr.url": "http://sonarr:8989", "sonarr.api_key": "k"}},
    )
    assert "URL base" in c.post("/api/arr/sonarr/test").json()["detail"]


def test_unsaved_form_values_are_tested(tmp_path):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v3/system/status":  # saved default without the URL base
            return httpx.Response(307, headers={"location": "/sonarr/api/v3/system/status"})
        seen["url"], seen["key"] = str(req.url), req.headers.get("x-api-key")
        return httpx.Response(200, json={"appName": "Sonarr", "version": "4"})

    c = make(tmp_path, handler)
    c.put("/api/settings", json={"values": {"sonarr.api_key": "saved-key"}})
    r = c.post("/api/arr/sonarr/test")  # saved default URL http://sonarr:8989
    assert r.status_code == 502 and "URL base is probably missing" in r.json()["detail"]
    r = c.post("/api/arr/sonarr/test", json={"url": "http://sonarr:8989/sonarr", "api_key": None})
    assert r.status_code == 200, r.text
    assert seen == {"url": "http://sonarr:8989/sonarr/api/v3/system/status", "key": "saved-key"}
    c.post("/api/arr/sonarr/test", json={"url": "http://sonarr:8989/sonarr", "api_key": "typed"})
    assert seen["key"] == "typed"


def test_qbittorrent_unsaved_values_and_login(tmp_path):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v2/auth/login":
            seen["login"] = (str(req.url), req.content.decode())
            ok = b"password=pw" in req.content
            r = httpx.Response(204) if ok else httpx.Response(401)  # qBittorrent 5.2
            if ok:
                r.headers["set-cookie"] = "SID=s1; path=/"
            return r
        if req.url.path == "/api/v2/app/version":
            assert "SID=s1" in req.headers.get("cookie", "")
            return httpx.Response(200, text="v5.2.4")
        return httpx.Response(404)

    c = make(tmp_path, handler)
    assert c.post("/api/arr/qbittorrent/test").status_code == 400  # no URL
    r = c.post(
        "/api/arr/qbittorrent/test",
        json={"url": "http://gluetun:8090/", "username": "admin", "password": "pw"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"app": "qBittorrent", "version": "v5.2.4"}
    assert seen["login"][0] == "http://gluetun:8090/api/v2/auth/login"
    r = c.post(
        "/api/arr/qbittorrent/test",
        json={"url": "http://gluetun:8090", "username": "admin", "password": "nope"},
    )
    assert r.status_code == 502 and "rejected" in r.json()["detail"]
