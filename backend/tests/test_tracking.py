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


SHERLOCK_S1 = "Шерлок / Sherlock / Сезон: 1 / Серии: 1-3 из 3 (Пол МакГиган) [2010, Великобритания, WEB-DL 1080p] MVO (Первый канал) + Original"


def _sherlock_tracked(api, **fields):  # noqa: F811
    from datetime import UTC, datetime

    api.app.state.tracker._save(
        topic_id=1, title=SHERLOCK_S1, forum="Зарубежные сериалы (HD Video)", forum_id=193,
        size=1, seeders=5, info_hash="A" * 40, source="grab", state="active",
        content_kind="tv", content_id=176941, season=1, last_changed_at=datetime.now(UTC),
    )  # fmt: skip
    if fields:
        api.app.state.tracker._save(topic_id=1, **fields)


def test_tracked_topic_answers_an_episode_search_itself(api, net):  # noqa: F811
    from tests.test_overrides import sherlock, titles

    seen = sherlock(api, net)
    _sherlock_tracked(api)
    assert titles(api, season="1", ep="2") == ["Sherlock S01", "Sherlock S01E02"]
    assert seen == []  # RuTracker not asked
    titles(api, season="1", ep="5")  # not in the tracked topic: RuTracker is searched
    assert seen


def test_rss_offers_the_newest_episodes_of_updated_topics(api, net):  # noqa: F811
    from datetime import UTC, datetime, timedelta

    from tests.test_overrides import sherlock

    sherlock(api, net)
    _sherlock_tracked(api)
    r = api.get("/torznab/api", params={"t": "tvsearch", "apikey": key(api)})
    names = [i.findtext("title").split(" 1080p")[0] for i in ET.fromstring(r.content).iter("item")]
    assert {"Sherlock S01E01", "Sherlock S01E02", "Sherlock S01E03"} <= set(names)
    old = datetime.now(UTC) - timedelta(days=10)
    api.app.state.tracker._save(topic_id=1, last_changed_at=old)
    r = api.get("/torznab/api", params={"t": "tvsearch", "apikey": key(api)})
    names = [i.findtext("title") for i in ET.fromstring(r.content).iter("item")]
    assert not any("S01E0" in n for n in names)


def test_grabbed_topics_follow_sonarr(api, net):  # noqa: F811
    import asyncio

    _sherlock_tracked(api)
    api.app.state.tracker._save(
        topic_id=2, title="hand", forum="x", forum_id=193, size=1, seeders=1, info_hash="B" * 40,
        source="manual", state="active", content_kind="tv", content_id=176941, season=1,
    )  # fmt: skip
    api.put(
        "/api/settings",
        json={"values": {"sonarr.url": "http://sonarr:8989/sonarr", "sonarr.api_key": "k"}},
    )
    series = {"tvdbId": 176941, "monitored": True,
              "seasons": [{"seasonNumber": 1, "monitored": False,
                           "statistics": {"episodeFileCount": 3}}]}  # fmt: skip
    answer = {"status": 200, "items": [series]}
    net.on(
        "GET",
        "/sonarr/api/v3/series",
        lambda r: httpx.Response(answer["status"], json=answer["items"]),
    )
    sync = api.app.state.tracker.sync_library
    assert asyncio.run(sync())["paused"] == 1
    assert tracked(api)[1]["state"] == "paused" and tracked(api)[2]["state"] == "active"
    assert all(t.topic_id != 1 for t in api.app.state.tracker.due(limit=10))
    series["seasons"][0]["monitored"] = True
    assert asyncio.run(sync())["resumed"] == 1 and tracked(api)[1]["state"] == "active"
    answer["items"] = []
    assert asyncio.run(sync())["untracked"] == 1
    assert 1 not in tracked(api) and 2 in tracked(api)  # hand-tracked stays
    answer["status"] = 500
    _sherlock_tracked(api)
    assert asyncio.run(sync()) == {"untracked": 0, "paused": 0, "resumed": 0}  # can't tell


def test_grabbed_topic_untracked_when_its_files_leave_the_library(api, net):  # noqa: F811
    import asyncio

    _sherlock_tracked(api)
    api.put(
        "/api/settings",
        json={"values": {"sonarr.url": "http://sonarr:8989/sonarr", "sonarr.api_key": "k"}},
    )
    stats = {"episodeFileCount": 0}
    series = {"tvdbId": 176941, "monitored": True,
              "seasons": [{"seasonNumber": 1, "monitored": True, "statistics": stats}]}  # fmt: skip
    queue = {"records": [{"id": 1, "downloadId": "A" * 40}]}
    net.on("GET", "/sonarr/api/v3/series", lambda r: httpx.Response(200, json=[series]))
    net.on("GET", "/sonarr/api/v3/queue", lambda r: httpx.Response(200, json=queue))
    sync = api.app.state.tracker.sync_library
    assert asyncio.run(sync())["untracked"] == 0  # still downloading: in Sonarr's queue
    queue["records"] = []
    stats["episodeFileCount"] = 1
    assert asyncio.run(sync())["untracked"] == 0  # something of it is in the library
    stats["episodeFileCount"] = 0
    assert asyncio.run(sync())["untracked"] == 1 and 1 not in tracked(api)
    events = api.get("/api/status/events").json()["items"]
    assert any("nothing of it left in the library" in e["message"] for e in events)


def test_library_event_webhook(api, net, monkeypatch):  # noqa: F811
    from rutrackarr.api import tracked as tracked_api

    calls = []
    monkeypatch.setattr(tracked_api, "schedule_library_sync", lambda app: calls.append(app))
    url = "/api/tracked/library-event"
    assert api.post(url, json={"eventType": "SeriesDelete"}).status_code == 401
    r = api.post(url, params={"apikey": key(api)}, json={"eventType": "Test"})
    assert r.status_code == 200 and calls == []
    r = api.post(url, headers={"X-Api-Key": key(api)}, json={"eventType": "EpisodeFileDelete"})
    assert r.status_code == 200 and len(calls) == 1


# --- 0.16: track "ongoing only", TTL, Downloads page --------------------------------------------


def test_title_ongoing_and_latest_season():
    from rutrackarr.tracking.tracker import latest_season, title_ongoing

    assert title_ongoing("Шоу / Show [TV] [1-7 из 12] [2026, WEB-DL 1080p]")
    assert title_ongoing("Шоу / Show [TV] [1-7 из XXX] [2026, WEB-DL 1080p]")
    assert not title_ongoing("Шоу / Show [TV] [1-12 из 12] [2026, WEB-DL 1080p]")
    assert not title_ongoing(SHERLOCK_S1)  # 1-3 из 3
    assert not title_ongoing("Фильм / Film (2024) WEB-DL 1080p")  # no episode range
    seasons = [
        {"seasonNumber": 0, "statistics": {"totalEpisodeCount": 9}},
        {"seasonNumber": 1, "statistics": {"totalEpisodeCount": 12}},
        {"seasonNumber": 2, "statistics": {"totalEpisodeCount": 6}},
        {"seasonNumber": 3, "statistics": {"totalEpisodeCount": 0}},  # announced, empty
    ]
    assert latest_season({"seasons": seasons}) == 2
    assert latest_season({"seasons": []}) is None


def _grab(api, net, **params):  # noqa: F811
    data, _ = make_torrent(TOPIC, NIA_FILES)
    net.on("GET", "/forum/dl.php", httpx.Response(200, content=data))
    r = api.get(
        "/torznab/download/6830000",
        params={"apikey": key(api), "name": RELEASE, **params},
    )
    login(api)
    assert add(api, r.content).text == "Ok."


def test_track_ongoing_only(api, net, qbit):  # noqa: F811
    api.put(
        "/api/settings",
        json={
            "values": {
                "tracking.auto_track": "ongoing",
                "sonarr.url": "http://sonarr:8989/sonarr",
                "sonarr.api_key": "k",
            }
        },
    )
    series = {
        "tvdbId": 424242, "monitored": True, "status": "ended",
        "seasons": [{"seasonNumber": 1, "statistics": {"totalEpisodeCount": 12}},
                    {"seasonNumber": 2, "statistics": {"totalEpisodeCount": 12}}],
    }  # fmt: skip
    net.on("GET", "/sonarr/api/v3/series", lambda r: httpx.Response(200, json=[series]))

    def regrab(season: str) -> bool:
        api.delete("/api/tracked/6830000", params={"delete_files": "false"})
        _grab(api, net, tvdbid="424242", season=season)
        return 6830000 in tracked(api)

    assert not regrab("2")  # the series has ended
    series["status"] = "continuing"
    assert not regrab("1")  # an older season of a continuing series
    assert regrab("2")  # its latest season
    series["status"] = "ended"
    assert not regrab("2")
    # A film is never "ongoing".
    api.delete("/api/tracked/6830000", params={"delete_files": "false"})
    _grab(api, net, tmdbid="550")
    assert 6830000 not in tracked(api)


def test_ttl(api, net, qbit):  # noqa: F811
    import asyncio
    from datetime import UTC, datetime, timedelta

    tracker = api.app.state.tracker
    old = datetime.now(UTC) - timedelta(days=40)
    _sherlock_tracked(api, last_changed_at=old)  # grabbed, 40 days without an update
    t = tracked(api)[1]
    assert (t["ttl_days"], t["ttl"]) == (None, 30)  # the setting's default
    assert t["expires_at"].startswith((old + timedelta(days=30)).date().isoformat())
    # By hand: no TTL unless given one.
    tracker._save(
        topic_id=2, title="hand", forum="x", forum_id=193, size=1, seeders=1, info_hash="B" * 40,
        source="manual", state="active", last_changed_at=old,
    )  # fmt: skip
    tracker._save(
        topic_id=3, title="hand, 5 days", forum="x", forum_id=193, size=1, seeders=1,
        info_hash="C" * 40, source="manual", state="active", last_changed_at=old, ttl_days=5,
    )  # fmt: skip
    assert tracked(api)[2]["expires_at"] is None
    # A grabbed topic can be exempted (0 = never) …
    r = api.put("/api/tracked/1/ttl", json={"ttl_days": 0})
    assert r.status_code == 200 and r.json() == {"ttl_days": 0, "ttl": None, "expires_at": None}
    assert asyncio.run(tracker.expire()) == 1  # only topic 3
    assert set(tracked(api)) == {1, 2}
    # … and back to the default; the setting at 0 turns the auto TTL off.
    api.put("/api/tracked/1/ttl", json={"ttl_days": None})
    api.put("/api/settings", json={"values": {"tracking.auto_ttl_days": 0}})
    assert asyncio.run(tracker.expire()) == 0
    api.put("/api/settings", json={"values": {"tracking.auto_ttl_days": 30}})
    assert asyncio.run(tracker.expire()) == 1 and set(tracked(api)) == {2}
    events = api.get("/api/status/events").json()["items"]
    assert any("not updated for 30 days" in e["message"] for e in events)
    assert api.put("/api/tracked/99/ttl", json={"ttl_days": 3}).status_code == 404
    assert api.put("/api/tracked/2/ttl", json={"ttl_days": -1}).status_code == 422


def test_track_by_hand_with_ttl(api, net, qbit):  # noqa: F811
    data, _ = make_torrent(TOPIC, NIA_FILES)
    net.on("GET", "/forum/viewtopic.php", topic_page(TOPIC))
    net.on("GET", "/forum/dl.php", httpx.Response(200, content=data))
    assert api.post("/api/tracked", json={"topic": "6830000", "ttl_days": 14}).status_code == 200
    assert tracked(api)[6830000]["ttl"] == 14
    # Tracking it again sets the TTL given (empty: none).
    assert api.post("/api/tracked", json={"topic": "6830000"}).status_code == 200
    assert tracked(api)[6830000]["ttl"] is None and len(qbit.added) == 1


def test_downloads_page(api, net, qbit):  # noqa: F811
    api.put(
        "/api/settings",
        json={"values": {"sonarr.url": "http://sonarr:8989/sonarr", "sonarr.api_key": "k",
                         "tracking.auto_track": "off"}},
    )  # fmt: skip
    queue = {"records": []}
    status = {"code": 200}
    net.on("GET", "/sonarr/api/v3/queue", lambda r: httpx.Response(status["code"], json=queue))
    _grab(api, net, tvdbid="424242", season="1")
    virtual = api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json()[0]
    queue["records"] = [{"id": 1, "downloadId": virtual["hash"].upper()}]
    page = api.get("/api/downloads").json()
    assert page["configured"] and [len(i["releases"]) for i in page["items"]] == [1]
    item = page["items"][0]
    assert item["tracked"] is None and item["releases"][0]["in_queue"] is True
    assert item["title"] in (TOPIC, RELEASE) and item["status"] == "downloading"
    # Imported (out of Sonarr's queue) and not tracked: no longer RuTrackarr's business.
    queue["records"] = []
    assert api.get("/api/downloads").json()["items"] == []
    # Tracked by hand: listed whatever its state, with its TTL.
    net.on("GET", "/forum/viewtopic.php", topic_page(TOPIC))
    api.post("/api/tracked", json={"topic": "6830000", "ttl_days": 7})
    item = api.get("/api/downloads").json()["items"][0]
    assert item["tracked"]["source"] == "manual" and item["tracked"]["ttl"] == 7
    assert item["releases"][0]["in_queue"] is False  # its imported release still shown
    # Sonarr's queue unreadable: unfinished releases count as in progress.
    api.delete("/api/tracked/6830000", params={"delete_files": "false"})
    _grab(api, net, tvdbid="424242", season="1")
    status["code"] = 500
    items = api.get("/api/downloads").json()["items"]
    assert len(items) == 1 and items[0]["releases"][0]["in_queue"] is None


# --- 0.16.2: later seasons numbered from 1 get "SxxEyy" after the marker ------------------------

S2_TOPIC = "Kusuriya no Hitorigoto 2nd Season [TV] [1-2 из 24] [BDRip 1080p]"
S2_EP = "Kusuriya no Hitorigoto II - {n:02d} [BDRip 1080p HEVC]"
S2_FILES = [
    *(f"{S2_EP.format(n=n)}.mkv" for n in (1, 2)),
    *(f"RUS Sound [AniLibria]/{S2_EP.format(n=n)}.mka" for n in (1, 2)),
]
TAG = "OrigAudio RusSoftSubs RTA-T1 -RuTracker"


def test_naming_marks_and_forward_matching():
    from rutrackarr.releases.naming import renamed_from, tagged, untagged, with_mark

    o = "Show/Show II - 01 [BDRip].mkv"
    t = tagged(o, TAG, "S02E01")
    assert t == "Show/Show II - 01 [BDRip] OrigAudio RusSoftSubs RTA-T1 -RuTracker S02E01.mkv"
    assert untagged(t) == o and tagged(t, TAG) == t  # reversible; never tagged twice
    assert with_mark(tagged(o, TAG), "S02E01") == t and with_mark(o, "S02E01") == o
    assert renamed_from(o, t) and renamed_from(o, o)
    assert renamed_from(o, tagged(o, "RusVoice RTA-T2 -RuTracker"))  # an older tag
    assert not renamed_from("Show/Show II - 1.mkv", t)  # another file
    assert not renamed_from(o, t.replace("Show/", "Other/"))  # another folder
    # An original ending in a tag-like word or "SxxEyy" is matched exactly forwards.
    o2 = "Show/Show S02E01 RusSubs.mkv"
    assert renamed_from(o2, tagged(o2, TAG)) and untagged(tagged(o2, TAG)) == "Show/Show S02E01.mkv"


def test_season_marks():
    from rutrackarr.releases.episodes import season_marks

    vids = [f"{S2_EP.format(n=n)}.mkv" for n in (1, 2)]
    assert season_marks(S2_FILES, 2, 1, 2) == {vids[0]: "S02E01", vids[1]: "S02E02"}
    assert season_marks(S2_FILES, 1, 1, 2) == {}  # season 1: absolute = season numbering
    assert season_marks(S2_FILES, None) == {}
    absolute = [f"Show - {n}.mkv" for n in (25, 26)]
    assert season_marks(absolute, 2, 25, 26) == {}  # Sonarr maps absolute numbers itself
    explicit = [f"Show S02E0{n}.mkv" for n in (1, 2)]
    assert season_marks(explicit, 2) == {}


def test_later_season_grab_gets_episode_marks(api, net, qbit):  # noqa: F811
    data, real = make_torrent(S2_TOPIC, S2_FILES)
    net.on("GET", "/forum/dl.php", httpx.Response(200, content=data))
    release = "Kusuriya no Hitorigoto S02 1080p BluRay JAPANESE RUSSIAN " + TAG
    r = api.get(
        "/torznab/download/6830000",
        params={"apikey": key(api), "name": release, "tvdbid": "431162", "season": "2"},
    )
    login(api)
    assert add(api, r.content).text == "Ok."
    names = qbit.files[real.lower()]
    videos = sorted(n for n in names if n.endswith(".mkv"))
    assert [v.rsplit(" ", 1)[-1] for v in videos] == ["S02E01.mkv", "S02E02.mkv"]
    assert all(" -RuTracker S02E0" in v for v in videos)
    assert not any(n.endswith(".mka") and "RuTracker" in n for n in names)  # tracks untouched
    # Adding it again (another grab) renames nothing twice.
    add(api, r.content)
    assert sorted(n for n in qbit.files[real.lower()] if n.endswith(".mkv")) == videos
    # The companion script finds the marked video and its tracks.
    virtual = api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json()[0]
    src = f"/data/download/sonarr/{videos[1]}"
    r = api.get(
        "/torznab/companions",
        params={"hash": virtual["hash"], "source": src, "apikey": key(api)},
    )
    assert r.status_code == 200, r.text
    lines = [line.split("\t") for line in r.text.splitlines()]
    assert lines[0] == ["#video", videos[1].split("/", 1)[1]]  # inside the torrent folder
    assert [p for p, _ in lines[1:]] == [f"RUS Sound [AniLibria]/{S2_EP.format(n=2)}.mka"]


def test_update_keeps_marked_names_and_marks_new_episodes(api, net, qbit):  # noqa: F811
    test_later_season_grab_gets_episode_marks(api, net, qbit)
    old = next(h for h in qbit.torrents)
    old_files = list(qbit.files[old])
    new_files = [*S2_FILES, f"{S2_EP.format(n=3)}.mkv"]
    new_data, new_hash = make_torrent(S2_TOPIC, new_files)
    for path in ("torrents/recheck", "torrents/renameFolder"):
        net.on("POST", f"/api/v2/{path}", qbit.handle)
    title = S2_TOPIC.replace("[1-2 из 24]", "[1-3 из 24]")
    net.routes[("GET", "/forum/viewtopic.php")] = [topic_page_with(title, new_hash)]
    net.routes[("GET", "/forum/dl.php")] = [httpx.Response(200, content=new_data)]
    assert tracked(api)[6830000]["season"] == 2
    assert api.post("/api/tracked/6830000/check").json() == {"result": "updated"}
    new = new_hash.lower()
    assert set(old_files) <= set(qbit.files[new])  # marked names kept: the recheck finds them
    (added,) = set(qbit.files[new]) - set(old_files)
    assert added.endswith(" -RuTracker S02E03.mkv")
