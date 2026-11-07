"""Status page endpoints: connections, downloads, recent grabs."""

import httpx

from rutrackarr.rutracker import torrent
from tests.test_qbit_proxy import CATEGORY, RELEASE, add, login, qbit, serve  # noqa: F401
from tests.test_rutracker_flow import api, net  # noqa: F401  (fixtures)

BASE = "http://sonarr:8989/sonarr"


def sonarr_setup(net, *, client_enabled=True, bound=True, script=True):  # noqa: F811
    net.on("GET", "/sonarr/api/v3/system/status", httpx.Response(200, json={"version": "4.0.20"}))
    net.on(
        "GET",
        "/sonarr/api/v3/indexer",
        httpx.Response(
            200,
            json=[
                {
                    "id": 7, "implementation": "Torznab", "enableRss": True,
                    "downloadClientId": 2 if bound else 0,
                    "fields": [{"name": "baseUrl", "value": "http://rutrackarr:8787/torznab"}],
                },
                {"id": 8, "implementation": "Torznab", "enableRss": True, "fields": [
                    {"name": "baseUrl", "value": "http://prowlarr:9696/1/"}]},
            ],
        ),
    )  # fmt: skip
    net.on(
        "GET",
        "/sonarr/api/v3/downloadclient",
        httpx.Response(
            200,
            json=[
                {"id": 1, "implementation": "QBittorrent", "enable": True,
                 "fields": [{"name": "urlBase", "value": "/proxy/x"}]},
                {"id": 2, "implementation": "QBittorrent", "enable": client_enabled,
                 "fields": [{"name": "urlBase", "value": "/qbit"}]},
            ],
        ),
    )  # fmt: skip
    script_path = {"name": "path", "value": "/config/scripts/rutrackarr-companions.sh"}
    notes = [{"implementation": "CustomScript", "fields": [script_path]}] if script else []
    net.on("GET", "/sonarr/api/v3/notification", httpx.Response(200, json=notes))


def connections(api):  # noqa: F811
    r = api.get("/api/status/connections", params={"refresh": "true"})
    assert r.status_code == 200, r.text
    return {c["id"]: c for c in r.json()["items"]}


def test_connections_overview(api, net):  # noqa: F811
    sonarr_setup(net)
    net.on("GET", "/health", httpx.Response(200, json={"status": "ok"}))
    net.on("GET", "/api/animes/1", httpx.Response(200, json={"id": 1, "name": "Cowboy Bebop"}))
    api.put("/api/settings", json={"values": {"sonarr.url": BASE, "sonarr.api_key": "k"}})
    c = connections(api)
    assert c["sonarr"]["state"] == "ok" and c["sonarr"]["version"] == "4.0.20"
    assert all(ch["ok"] for ch in c["sonarr"]["checks"])
    assert c["radarr"]["state"] == "off"
    assert c["qbittorrent"]["state"] == "off"
    assert c["tmdb"]["state"] == "off"
    assert c["flaresolverr"]["state"] == "ok"
    assert c["shikimori"]["state"] == "ok"
    assert c["animelist"]["state"] == "warn"  # never downloaded in tests
    # Cached: a second call doesn't ask again.
    calls = len(net.calls)
    api.get("/api/status/connections")
    assert len(net.calls) == calls


def test_sonarr_not_fully_set_up(api, net):  # noqa: F811
    sonarr_setup(net, bound=False, script=False)
    api.put("/api/settings", json={"values": {"sonarr.url": BASE, "sonarr.api_key": "k"}})
    s = connections(api)["sonarr"]
    assert s["state"] == "warn"
    failed = {ch["label"] for ch in s["checks"] if not ch["ok"]}
    assert failed == {"Indexer uses the RuTrackarr download client", "Companion tracks script"}


def test_sonarr_unreachable(api, net):  # noqa: F811
    net.on("GET", "/sonarr/api/v3/system/status", httpx.Response(401))
    api.put("/api/settings", json={"values": {"sonarr.url": BASE, "sonarr.api_key": "k"}})
    assert connections(api)["sonarr"]["state"] == "error"


def test_downloads_and_grabs(api, net, qbit):  # noqa: F811
    assert connections(api)["qbittorrent"]["state"] == "error"  # fake has no app/version
    data, marked = serve(api, net)
    grabs = api.get("/api/status/grabs").json()["items"]
    assert grabs[0]["release"] == RELEASE and grabs[0]["via_proxy"] is False
    assert grabs[0]["topic_url"].endswith("viewtopic.php?t=6830000")
    login(api)
    add(api, marked)
    real = torrent.read(data).info_hash.lower()
    qbit.torrents[real] |= {"progress": 0.25, "dlspeed": 1000, "eta": 60}
    items = api.get("/api/status/downloads").json()["items"]
    assert len(items) == 1
    d = items[0]
    assert d["release"] == RELEASE and d["category"] == CATEGORY
    assert d["status"] == "downloading" and d["progress"] == 0.25 and d["eta"] == 60
    assert api.get("/api/status/grabs").json()["items"][0]["via_proxy"] is True
    qbit.torrents[real] |= {"progress": 1.0, "state": "stalledUP"}
    assert api.get("/api/status/downloads").json()["items"][0]["status"] == "seeding"
    del qbit.torrents[real]
    assert api.get("/api/status/downloads").json()["items"][0]["status"] == "missing"


def test_downloads_proxy_off(api):  # noqa: F811
    assert api.get("/api/status/downloads").json() == {"configured": False, "items": []}
