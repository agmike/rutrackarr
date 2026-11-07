"""Overrides (applied to ID searches), the search sandbox, and the query log's per-topic results."""

import httpx

from tests.fixtures import pages
from tests.test_rutracker_flow import api, html, net  # noqa: F401  (fixtures)
from tests.test_tmdb_search import SHERLOCK_TV, configure
from tests.test_torznab import items, key

UK = "Сериалы Великобритании и Ирландии (HD Video)"
ROWS = "".join(
    [
        pages.row(1, "Шерлок / Sherlock / Сезон: 1 / Серии: 1-3 из 3 (Пол МакГиган) [2010, Великобритания, WEB-DL 1080p] MVO (Первый канал) + Original", UK, forum_id=193),
        pages.row(2, "Шерлок / Sherlock (Колм Маккарти) [2014, Великобритания, WEB-DL 1080p] Dub + Original + Sub (Rus, Eng)", UK, forum_id=193),
        pages.row(3, "Шерлок в России / Серии: 1-8 из 8 (Нурбек Эген) [2020, детектив, WEBRip-AVC] + Sub (Rus)", "Русские сериалы", forum_id=9),
        pages.row(4, "Детектив с Бейкер-стрит / Сезон: 2 / Серии: 1-3 из 3 [2012, Великобритания, WEB-DL 1080p] MVO", UK, forum_id=193),
    ]
)  # fmt: skip


def sherlock(api, net):  # noqa: F811
    configure(api, net)
    net.on("GET", "/3/find/176941", httpx.Response(200, json={"tv_results": [{"id": 19885}]}))
    net.on("GET", "/3/tv/19885", httpx.Response(200, json=SHERLOCK_TV))
    series = [{"title": "Sherlock", "year": 2010, "seriesType": "standard", "tvdbId": 176941,
               "seasons": [{"seasonNumber": 1}, {"seasonNumber": 2}]}]  # fmt: skip
    net.on("GET", "/sonarr/api/v3/series", httpx.Response(200, json=series))
    net.on("GET", "/radarr/api/v3/movie", httpx.Response(200, json=[]))
    seen: list[str] = []

    def tracker(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["nm"])
        return html(pages.search_page(ROWS))

    net.on("GET", "/forum/tracker.php", tracker)
    return seen


def titles(api, **params):  # noqa: F811
    found = items(
        api.get(
            "/torznab/api",
            params={"t": "tvsearch", "tvdbid": "176941", "apikey": key(api)} | params,
        )
    )
    return sorted(i.findtext("title").split(" 1080p")[0] for i in found)


def test_override_titles_pins_offset_and_filters(api, net):  # noqa: F811
    sherlock(api, net)
    assert titles(api) == ["Sherlock S01", "Sherlock S03"]
    r = api.post(
        "/api/overrides",
        json={
            "kind": "tv", "external_id": 176941, "title": "Sherlock",
            "extra_titles": ["Детектив с Бейкер-стрит"], "release_title": "Sherlock (2010)",
            "pins": [{"topic_id": 4, "season": 2}], "exclude_regex": r"Колм",
        },
    )  # fmt: skip
    assert r.status_code == 200, r.text
    # The extra title is searched; topic 4 is pinned to season 2; topic 2 is excluded.
    assert titles(api) == ["Sherlock (2010) S01", "Sherlock (2010) S02"]
    ctx = api.post("/api/sandbox/search", json={"tvdbid": 176941}).json()["context"]
    assert ctx["queries"][0] == "Детектив с Бейкер-стрит" and ctx["override"]["pins"]
    assert titles(api, season="2") == ["Sherlock (2010) S02"]


def test_override_validation_export_import(api):  # noqa: F811
    bad = api.post("/api/overrides", json={"kind": "tv", "external_id": 1, "include_regex": "("})
    assert bad.status_code == 422 and "include_regex" in bad.json()["detail"]
    assert api.post("/api/overrides", json={"kind": "x", "external_id": 1}).status_code == 422
    api.post(
        "/api/overrides", json={"kind": "tv", "external_id": 5, "title": "A", "season_offset": -1}
    )
    exported = api.get("/api/overrides/export").json()
    assert exported["items"][0]["season_offset"] == -1 and "id" not in exported["items"][0]
    oid = api.get("/api/overrides").json()["items"][0]["id"]
    assert api.delete(f"/api/overrides/{oid}").json() == {"ok": True}
    assert api.get("/api/overrides").json()["items"] == []
    assert api.post("/api/overrides/import", json=exported).json() == {"imported": 1}
    assert api.get("/api/overrides").json()["items"][0]["title"] == "A"


def test_sandbox_shows_every_topic_and_why(api, net):  # noqa: F811
    sherlock(api, net)
    lib = api.get("/api/sandbox/library", params={"q": "sher"}).json()["items"]
    assert lib[0]["tvdbid"] == 176941 and lib[0]["seasons"] == [1, 2]
    r = api.post("/api/sandbox/search", json={"kind": "tvsearch", "tvdbid": 176941, "season": 1})
    body = r.json()
    assert body["context"]["title"] == "Sherlock" and body["kept"] == 1
    why = {row["topic_id"]: (row["kept"], row["reason"]) for row in body["rows"]}
    assert why[1] == (True, None)
    assert why[2][1] == "season 1 asked for, topic is S3"
    assert why[3][1].startswith("not Sherlock")
    assert body["searches"] and all("cached" in s for s in body["searches"])
    # Not logged as a query.
    assert api.get("/api/status/queries").json()["items"] == []


def test_query_log_keeps_per_topic_results(api, net):  # noqa: F811
    sherlock(api, net)
    titles(api)
    (q,) = api.get("/api/status/queries").json()["items"]
    detail = api.get(f"/api/status/queries/{q['id']}").json()["items"]
    assert [d["topic_id"] for d in detail if d["release"]] == [1, 2]
    dropped = api.get("/api/status/dropped", params={"reason": "not "}).json()["items"]
    assert {d["topic_id"] for d in dropped} == {3, 4}
    titles(api, season="9")
    assert (
        api.get("/api/status/queries", params={"empty": "true"}).json()["items"][0]["query"]
        == "tvdb:176941 S9"
    )
