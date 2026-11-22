"""0.16.5: a second grab of the same episodes of the same topic, still queued under another
release name (Sonarr's RSS sync and a search racing, under two of the series' titles), is
answered "Ok." but not listed: one queue item, one import."""

from datetime import timedelta

import httpx

from rutrackarr.rutracker import torrent
from tests.test_companions import NIA_FILES, make_torrent
from tests.test_qbit_proxy import CATEGORY, TOPIC, add, key, login, qbit  # noqa: F401
from tests.test_rutracker_flow import api, net  # noqa: F401  (fixtures)

FIRST = "FX Senshi Kurumi-chan S01E01-E08 1080p WEB-DL JAPANESE RUSSIAN RTA-T1 -RuTracker"
SECOND = "FX Fighter Kurumi-chan S01E01-E08 1080p WEB-DL JAPANESE RUSSIAN RTA-T1 -RuTracker"


def grab(api, name: str, season: int = 1, ep: int | None = None) -> bytes:  # noqa: F811
    params = {"apikey": key(api), "name": name, "tvdbid": 472962, "season": season}
    if ep is not None:
        params["ep"] = ep
    r = api.get("/torznab/download/6830000", params=params)
    assert r.status_code == 200, r.text
    assert add(api, r.content).text == "Ok."
    return r.content


def listed(api) -> list[str]:  # noqa: F811
    items = api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json()
    return sorted(i["name"] for i in items)


def setup(api, net):  # noqa: F811
    data, _ = make_torrent(TOPIC, NIA_FILES)
    net.on("GET", "/forum/dl.php", httpx.Response(200, content=data))
    login(api)


def test_duplicate_grab_not_listed(api, net, qbit):  # noqa: F811
    setup(api, net)
    grab(api, FIRST)
    second = grab(api, SECOND)
    assert listed(api) == [FIRST]  # one queue item for Sonarr
    assert len(qbit.torrents) == 1
    events = api.get("/api/status/events").json()["items"]
    assert any(e["kind"] == "duplicate" and FIRST in e["message"] for e in events)
    # A call Sonarr makes for the duplicate's hash doesn't break anything.
    h = torrent.read(second).info_hash.lower()
    assert api.get("/qbit/api/v2/torrents/info", params={"hashes": h}).json() == []


def test_other_season_or_episode_is_not_a_duplicate(api, net, qbit):  # noqa: F811
    setup(api, net)
    grab(api, "Show S01 -RuTracker", season=1)
    grab(api, "Show S02 -RuTracker", season=2)  # a multi-season topic, grabbed per season
    grab(api, "Show S01E03 -RuTracker", season=1, ep=3)
    grab(api, "Show S01E04 -RuTracker", season=1, ep=4)
    assert len(listed(api)) == 4


def test_regrab_after_removal_is_listed(api, net, qbit):  # noqa: F811
    setup(api, net)
    first = grab(api, FIRST)
    h = torrent.read(first).info_hash.lower()
    assert (
        api.post(
            "/qbit/api/v2/torrents/delete", data={"hashes": h, "deleteFiles": "false"}
        ).status_code
        == 200
    )
    grab(api, SECOND)
    assert listed(api) == [SECOND]


def test_after_the_grace_the_apps_queue_decides(api, net, qbit, monkeypatch):  # noqa: F811
    from rutrackarr.qbit import proxy

    monkeypatch.setattr(proxy, "DUPLICATE_GRACE", timedelta(0))
    api.put(
        "/api/settings",
        json={"values": {"sonarr.url": "http://sonarr:8989/sonarr", "sonarr.api_key": "k"}},
    )
    queue: dict = {"records": []}
    net.on("GET", "/sonarr/api/v3/queue", lambda r: httpx.Response(200, json=queue))
    setup(api, net)
    first = grab(api, FIRST)
    # Still in Sonarr's queue: the second grab is a duplicate.
    queue["records"] = [{"downloadId": torrent.read(first).info_hash.upper()}]
    grab(api, SECOND)
    assert listed(api) == [FIRST]
    # Gone from the queue (removed there, files kept in the client): a re-grab is listed.
    queue["records"] = []
    grab(api, "FX Fighter Kurumi-chan S01E01-E08 1080p WEB-DL JAPANESE RTA-T1 -RuTracker")
    assert len(listed(api)) == 2
