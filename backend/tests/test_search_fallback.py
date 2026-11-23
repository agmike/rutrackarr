"""0.16.7: Sonarr's anime episode search (tvdbid + q=07, then season/ep) is answered by a
tracked topic that has the episode; otherwise RuTracker is asked, and while it's unavailable an
ID search gets the last result for the same query (if any). Text searches always report the
error."""

import httpx

from tests.fixtures import pages
from tests.test_overrides import ROWS, sherlock
from tests.test_rutracker_flow import api, html, net  # noqa: F401  (fixtures)
from tests.test_torznab import items, key
from tests.test_tracking import _sherlock_tracked


def ask(api, **params):  # noqa: F811
    p = {"t": "tvsearch", "tvdbid": "176941", "apikey": key(api)} | params
    return api.get("/torznab/api", params=p)


def names(r) -> list[str]:
    return sorted(i.findtext("title").split(" 1080p")[0] for i in items(r))


def down(net, how):  # noqa: F811
    def responder(request: httpx.Request) -> httpx.Response:
        if how == "unreachable":
            raise httpx.ConnectError("connection refused", request=request)
        if how == "502":
            return html("<html><title>rutracker.org | 502: Bad gateway</title></html>", status=502)
        return html("<html><title>Что-то другое</title><body>?</body></html>")  # not logged in

    net.routes[("GET", "/forum/tracker.php")] = [responder]


def age_cache(api) -> None:  # noqa: F811  (past the TTL, within the fallback window)
    cache = api.app.state.torznab_cache
    for k, (at, rows) in list(cache._data.items()):
        cache._data[k] = (at - 2 * 3600, rows)


def one_season(net) -> None:  # noqa: F811
    series = [{"title": "Sherlock", "year": 2010, "seriesType": "anime", "tvdbId": 176941,
               "seasons": [{"seasonNumber": 0}, {"seasonNumber": 1}]}]  # fmt: skip
    net.routes[("GET", "/sonarr/api/v3/series")] = [httpx.Response(200, json=series)]


def test_absolute_episode_answered_by_a_tracked_topic(api, net):  # noqa: F811
    seen = sherlock(api, net)
    one_season(net)
    _sherlock_tracked(api)
    assert names(ask(api, q="02")) == ["Sherlock S01", "Sherlock S01E02"]
    assert seen == []  # RuTracker not asked
    ask(api, q="05")  # not in the tracked topic (1-3): RuTracker is searched
    assert seen


def test_absolute_number_of_a_multi_season_series_is_not_mapped(api, net):  # noqa: F811
    # Seasons 1 and 2: "02" may be season 2's own episode 2 (Sonarr's scene numbering for
    # "Show 2nd Season 02"), not the first season's.
    seen = sherlock(api, net)
    _sherlock_tracked(api)
    assert "Sherlock S01E02" not in names(ask(api, q="02"))
    assert seen  # RuTracker asked, as before


def test_id_search_falls_back_on_the_cache_while_rutracker_is_down(api, net):  # noqa: F811
    sherlock(api, net)
    first = names(ask(api, season="1", ep="2"))
    assert "Sherlock S01E02" in first
    age_cache(api)
    for how in ("unreachable", "502"):
        down(net, how)
        r = ask(api, season="1", ep="2")
        assert b"<error" not in r.content, how
        assert names(r) == first, how
    events = api.get("/api/status/events").json()["items"]
    assert any(e["kind"] == "rutracker_error" for e in events)


def test_no_cache_or_not_an_outage_reports_the_error(api, net):  # noqa: F811
    sherlock(api, net)
    down(net, "unreachable")
    assert b"<error" in ask(api, season="1", ep="2").content  # nothing cached
    net.routes[("GET", "/forum/tracker.php")] = [html(pages.search_page(ROWS))]
    ask(api, season="1", ep="2")
    age_cache(api)
    down(net, "other")  # an unexpected page (not a 5xx): not an outage
    assert b"<error" in ask(api, season="1", ep="2").content


def test_text_search_reports_the_error(api, net):  # noqa: F811
    sherlock(api, net)
    params = {"t": "search", "q": "Sherlock 02", "apikey": key(api)}
    assert api.get("/torznab/api", params=params).status_code == 200
    age_cache(api)
    down(net, "unreachable")
    assert b"<error" in api.get("/torznab/api", params=params).content
