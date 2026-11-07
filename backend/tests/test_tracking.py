"""Tracked topics: by hand (RuTrackarr's torrent) and from grabs; in searches; remove/untrack."""

from xml.etree import ElementTree as ET

import httpx

from rutrackarr.rutracker import torrent
from tests.fixtures import pages
from tests.test_companions import NIA_FILES, make_torrent
from tests.test_qbit_proxy import CATEGORY, RELEASE, TOPIC, add, login, qbit  # noqa: F401
from tests.test_rutracker_flow import api, html, net  # noqa: F401  (fixtures)
from tests.test_torznab import key

TRACKED = "rutrackarr/tracked"
FORUM = "Аниме (HD Video)"


def topic_page(title: str) -> httpx.Response:
    return html(
        f"<html><head><title>{title} :: RuTracker.org</title></head><body>{pages.LOGGED_IN_HEADER}"
        '<table><tr><td class="nav t-breadcrumb-top"><a href="index.php">Главная</a> » '
        f'<a href="viewforum.php?f=33">Аниме</a> » <a href="viewforum.php?f=1105">{FORUM}</a>'
        f'</td></tr></table><h1 class="maintitle"><a id="topic-title">{title}</a></h1></body></html>'
    )


def track_by_url(api, net):  # noqa: F811
    data, _ = make_torrent(TOPIC, NIA_FILES)
    net.on("GET", "/forum/viewtopic.php", topic_page(TOPIC))
    net.on("GET", "/forum/dl.php", httpx.Response(200, content=data))
    r = api.post(
        "/api/tracked", json={"topic": "https://rutracker.org/forum/viewtopic.php?t=6830000"}
    )
    assert r.status_code == 200, r.text
    return data, torrent.read(data).info_hash.lower()


def tracked(api):  # noqa: F811
    return {t["topic_id"]: t for t in api.get("/api/tracked").json()["items"]}


def test_track_by_hand(api, net, qbit):  # noqa: F811
    _, real = track_by_url(api, net)
    assert qbit.added[0]["hash"] == real and qbit.added[0]["fields"]["category"] == TRACKED
    assert all(" -RuTracker" in f for f in qbit.files[real] if f.endswith(".mkv"))  # tagged
    t = tracked(api)[6830000]
    assert (t["source"], t["state"], t["forum"], t["content_id"]) == (
        "manual",
        "active",
        FORUM,
        None,
    )
    assert t["torrent"]["category"] == TRACKED and t["in_queue"] == 0
    # Tracking it again changes nothing.
    assert api.post("/api/tracked", json={"topic": "6830000"}).status_code == 200
    assert len(qbit.added) == 1


def test_sonarr_grab_reuses_a_hand_tracked_topic(api, net, qbit):  # noqa: F811
    data, real = track_by_url(api, net)
    marked = torrent.mark(data, RELEASE)
    login(api)
    assert add(api, marked).text == "Ok."
    assert len(qbit.added) == 1 and qbit.torrents[real]["category"] == TRACKED  # not moved
    items = api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json()
    assert [t["name"] for t in items] == [RELEASE]  # Sonarr sees its release
    virtual = items[0]["hash"]
    api.post(
        "/qbit/api/v2/torrents/setCategory",
        data={"hashes": virtual, "category": "sonarr/completed"},
    )
    assert qbit.torrents[real]["category"] == TRACKED  # doesn't follow the post-import category
    api.post("/qbit/api/v2/torrents/delete", data={"hashes": virtual, "deleteFiles": "true"})
    assert real in qbit.torrents  # Sonarr can't delete RuTrackarr's torrent


def test_grabs_are_tracked_with_their_series(api, net, qbit):  # noqa: F811
    data, _ = make_torrent(TOPIC, NIA_FILES)
    net.on("GET", "/forum/dl.php", httpx.Response(200, content=data))
    r = api.get(
        "/torznab/download/6830000",
        params={"apikey": key(api), "name": RELEASE, "tvdbid": "424242", "season": "1"},
    )
    login(api)
    add(api, r.content)
    t = tracked(api)[6830000]
    assert (t["source"], t["content_kind"], t["content_id"], t["season"]) == (
        "grab",
        "tv",
        424242,
        1,
    )
    assert t["torrent"]["category"] == CATEGORY  # Sonarr's torrent, Sonarr's category
    api.put("/api/settings", json={"values": {"tracking.auto_track": "off"}})
    api.delete("/api/tracked/6830000", params={"delete_files": "false"})
    add(api, r.content)
    assert 6830000 not in tracked(api)


def test_tracked_topics_take_part_in_searches(api, net, qbit):  # noqa: F811
    track_by_url(api, net)
    net.on("GET", "/forum/tracker.php", html(pages.search_page("")))  # RuTracker finds nothing
    r = api.get(
        "/torznab/api", params={"t": "search", "q": "Kyouran Reijou Nia Liston", "apikey": key(api)}
    )
    titles = [i.findtext("title") for i in ET.fromstring(r.content).iter("item")]
    assert len(titles) == 1 and titles[0].startswith("Kyouran Reijou Nia Liston")
    sandbox = api.post(
        "/api/sandbox/search", json={"kind": "search", "q": "Kyouran Reijou Nia Liston"}
    )
    assert sandbox.json()["rows"][0]["tracked"] is True


def test_remove_cleans_sonarr_queue_and_deletes(api, net, qbit):  # noqa: F811
    data, real = track_by_url(api, net)
    login(api)
    add(api, torrent.mark(data, RELEASE))
    virtual = torrent.read(torrent.mark(data, RELEASE)).info_hash
    api.put(
        "/api/settings",
        json={"values": {"sonarr.url": "http://sonarr:8989/sonarr", "sonarr.api_key": "k"}},
    )
    deleted = []
    net.on(
        "GET",
        "/sonarr/api/v3/queue",
        httpx.Response(200, json={"records": [{"id": 77, "downloadId": virtual}]}),
    )
    net.on(
        "DELETE",
        "/sonarr/api/v3/queue/77",
        lambda r: deleted.append(dict(r.url.params)) or httpx.Response(200),
    )
    notes = api.delete("/api/tracked/6830000").json()["notes"]
    assert deleted == [{"removeFromClient": "false", "blocklist": "false"}]
    assert real not in qbit.torrents and f"delete:{real}:true" in qbit.calls
    assert any("Sonarr" in n for n in notes) and 6830000 not in tracked(api)
    assert api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json() == []


def test_untrack_hands_a_used_topic_to_sonarr(api, net, qbit):  # noqa: F811
    data, real = track_by_url(api, net)
    login(api)
    add(api, torrent.mark(data, RELEASE))
    api.post("/api/tracked/6830000/untrack")
    assert qbit.torrents[real]["category"] == CATEGORY and 6830000 not in tracked(api)


def test_id_search_links_a_tracked_topic(api, net):  # noqa: F811
    from tests.test_overrides import sherlock, titles

    sherlock(api, net)
    api.app.state.tracker._save(
        topic_id=1, title="Шерлок / Sherlock / Сезон: 1", forum="x", forum_id=193, size=1,
        seeders=1, info_hash="A" * 40, source="manual", state="active",
    )  # fmt: skip
    titles(api)
    t = tracked(api)[1]
    assert (t["content_kind"], t["content_id"], t["season"]) == ("tv", 176941, 1)
    assert "linked" in [e["kind"] for e in api.get("/api/status/events").json()["items"]]


def test_feed_check(api, net):  # noqa: F811
    atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Topic A</title></entry><entry><title>Topic B</title></entry></feed>'
    net.on(
        "GET",
        "/atom/f/1105.atom",
        httpx.Response(200, text=atom, headers={"content-type": "application/atom+xml"}),
    )
    r = api.get("/api/tracked/feed-check").json()
    (res,) = r["results"]
    assert (r["forum_id"], res["status"], res["entries"], res["sample"]) == (
        1105,
        200,
        2,
        ["Topic A", "Topic B"],
    )
