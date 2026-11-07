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


def topic_page_with(title: str, info_hash: str) -> httpx.Response:
    page = topic_page(title).text.replace(
        "</body>",
        f'<a class="magnet-link" href="magnet:?xt=urn:btih:{info_hash}&tr=x">m</a></body>',
    )
    return html(page)


def test_feed_entries():
    from datetime import UTC, datetime

    from rutrackarr.tracking.tracker import feed_entries, ongoing

    atom = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>[Обновлено] X</title>'
        '<link href="https://rutracker.org/forum/viewtopic.php?t=6830000"/>'
        "<updated>2026-11-07T10:00:00+00:00</updated></entry>"
        "<entry><title>Y</title><id>tag:rto,2026:/t/5</id></entry></feed>"
    )
    assert feed_entries(atom) == {6830000: datetime(2026, 11, 7, 10, tzinfo=UTC)}
    assert ongoing("X [TV] [1-7 из 12] [2026]") and not ongoing("X [TV] [12 из 12] [2026]")


def test_check_unchanged_and_backstop(api, net, qbit):  # noqa: F811
    _, real = track_by_url(api, net)
    tracker = api.app.state.tracker
    assert [t.topic_id for t in tracker.due()] == [6830000]  # never checked
    net.routes[("GET", "/forum/viewtopic.php")] = [topic_page_with(TOPIC, real.upper())]
    assert api.post("/api/tracked/6830000/check").json() == {"result": "unchanged"}
    assert tracker.due() == []
    t = tracked(api)[6830000]
    assert t["last_checked_at"] and t["forum"] == FORUM


def test_update_applied_in_place(api, net, qbit):  # noqa: F811
    data, old = track_by_url(api, net)
    login(api)
    add(api, torrent.mark(data, RELEASE))  # Sonarr uses the topic too
    old_files = list(qbit.files[old])
    new_ep = "[SubsPlus+] Nia Liston - The Merciless Maiden - S01E03 (ADN WEB-DL 1080p AVC AAC) [ABCDEF12].mkv"
    new_data, new_hash = make_torrent(TOPIC, [*NIA_FILES, new_ep])
    new = new_hash.lower()
    for path in ("torrents/recheck", "torrents/renameFolder"):
        net.on("POST", f"/api/v2/{path}", qbit.handle)
    title = TOPIC + " [1-3 из 12]"
    net.routes[("GET", "/forum/viewtopic.php")] = [topic_page_with(title, new_hash)]
    net.routes[("GET", "/forum/dl.php")] = [httpx.Response(200, content=new_data)]
    assert api.post("/api/tracked/6830000/check").json() == {"result": "updated"}
    assert old not in qbit.torrents and new in qbit.torrents
    assert qbit.torrents[new]["category"] == TRACKED
    assert qbit.added[-1]["fields"]["savepath"] == "/data/torrents/sonarr"
    assert set(old_files) <= set(qbit.files[new])  # same names: the recheck finds the data
    (added_ep,) = set(qbit.files[new]) - set(old_files)
    assert added_ep.endswith(" -RuTracker.mkv")  # the new episode is tagged too
    assert "torrents/recheck" in qbit.calls and f"delete:{old}:false" in qbit.calls
    t = tracked(api)[6830000]
    assert t["title"] == title and t["last_changed_at"]
    items = api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json()
    assert [i["name"] for i in items] == [RELEASE]  # Sonarr's release now backed by the new torrent
    assert "updated" in [e["kind"] for e in api.get("/api/status/events").json()["items"]]


def test_feeds_trigger_checks(api, net, qbit):  # noqa: F811
    import asyncio

    _, real = track_by_url(api, net)
    atom = (
        '<feed><entry><link href="https://rutracker.org/forum/viewtopic.php?t=6830000"/>'
        "<updated>2099-01-01T00:00:00+00:00</updated></entry></feed>"
    )
    net.on("GET", "/atom/f/1105.atom", httpx.Response(200, text=atom))
    net.routes[("GET", "/forum/viewtopic.php")] = [topic_page_with(TOPIC, real.upper())]
    assert asyncio.run(api.app.state.tracker.poll_feeds()) == 1
    assert tracked(api)[6830000]["last_checked_at"]


def test_status_shows_tracked_topics(api, net, qbit):  # noqa: F811
    import asyncio

    data, _ = track_by_url(api, net)
    d = api.get("/api/status/downloads").json()
    (item,) = d["items"]
    assert item["tracked"] is True and item["category"] == TRACKED and d["totals"]["torrents"] == 1
    net.on("GET", "/atom/f/1105.atom", httpx.Response(200, text="<feed></feed>"))
    asyncio.run(api.app.state.tracker.poll_feeds())
    s = api.get("/api/status/tracking").json()
    assert (s["manual"], s["grabbed"], s["gone"], s["due"]) == (1, 0, 0, 1)
    assert s["feeds_at"] and s["feeds"] == [
        {"forum_id": 1105, "forum": FORUM, "tracked": 1, "status": 200, "entries": 0}
    ]
    # Once Sonarr uses it, it's shown as Sonarr's release instead.
    login(api)
    add(api, torrent.mark(data, RELEASE))
    items = api.get("/api/status/downloads").json()["items"]
    assert [i.get("tracked", False) for i in items] == [False]
