"""Alerts: raised and cleared once each, the UI banner list, the Apprise test endpoint."""

import asyncio

import httpx
import pytest

from rutrackarr import alerts as alerts_mod
from rutrackarr.background import check_services
from tests.fixtures import pages
from tests.test_rutracker_flow import api, html, net  # noqa: F401  (fixtures)
from tests.test_torznab import key


@pytest.fixture
def sent(api, monkeypatch):  # noqa: F811
    out: list[str] = []
    monkeypatch.setattr(api.app.state.alerts, "notify", lambda title, body: out.append(title))
    return out


def banner(api):  # noqa: F811
    return [a["key"] for a in api.get("/api/alerts").json()["items"]]


def test_rutracker_outage_alerts_once_then_resolves(api, net, sent):  # noqa: F811
    net.on("GET", "/forum/tracker.php", html(pages.MAINTENANCE, status=503))
    for word in ("a", "b", "c"):
        api.get("/torznab/api", params={"t": "search", "q": word, "apikey": key(api)})
    assert banner(api) == ["rutracker"]
    assert len(sent) == 1 and "RuTracker" in sent[0]
    net.on("GET", "/forum/index.php", html(pages.INDEX_LOGGED_IN))
    api.post("/api/rutracker/check")
    assert banner(api) == []
    assert len(sent) == 2 and "resolved" in sent[1]


def test_service_checks(api, net, sent):  # noqa: F811
    net.on("GET", "/health", httpx.Response(500))
    asyncio.run(check_services(api.app))
    assert banner(api) == ["flaresolverr"]
    asyncio.run(check_services(api.app))
    assert len(sent) == 1  # not repeated while it lasts
    net.routes[("GET", "/health")] = [httpx.Response(200, json={"status": "ok"})]
    asyncio.run(check_services(api.app))
    assert banner(api) == [] and "resolved" in sent[-1]


def test_failed_searches_alert(api, net, sent, monkeypatch):  # noqa: F811
    net.on("GET", "/health", httpx.Response(200, json={"status": "ok"}))
    net.on("GET", "/forum/tracker.php", html(pages.MAINTENANCE, status=503))
    for i in range(5):
        api.get("/torznab/api", params={"t": "search", "q": f"q{i}", "apikey": key(api)})
    asyncio.run(check_services(api.app))
    assert set(banner(api)) == {"rutracker", "searches"}


def test_send_and_test_endpoint(api, monkeypatch):  # noqa: F811
    assert alerts_mod.send("", "t", "b") == "no Apprise URLs set"
    assert "not understood" in alerts_mod.send("nosuchscheme://x", "t", "b")
    assert api.post("/api/alerts/test").status_code == 400  # nothing configured
    calls = []
    monkeypatch.setattr(
        "rutrackarr.api.alerts.send", lambda urls, title, body: calls.append(urls) or None
    )
    r = api.post("/api/alerts/test", json={"urls": "tgram://token/chat"})
    assert r.json() == {"status": "sent"} and calls == ["tgram://token/chat"]


def test_chores_are_due_right_after_boot(api, net, monkeypatch):  # noqa: F811
    """Monotonic time starts at boot: on a fresh machine "never ran" must still mean due."""
    from rutrackarr import background

    assert background.due({}, "x", 5.0, 300) and not background.due({"x": 1.0}, "x", 5.0, 300)
    monkeypatch.setattr(background.time, "monotonic", lambda: 5.0)
    net.on("GET", "/health", httpx.Response(500))
    asyncio.run(background.tick(api.app, {}))
    assert [a["key"] for a in api.get("/api/alerts").json()["items"]] == ["flaresolverr"]
