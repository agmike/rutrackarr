"""Non-anime ID searches: TMDb names, original language, season by year; films via Radarr."""

import httpx

from tests.fixtures import pages
from tests.test_rutracker_flow import api, html, net  # noqa: F401  (fixtures)
from tests.test_torznab import NS, items, key

SHERLOCK_TV = {
    "id": 19885, "name": "Шерлок", "original_name": "Sherlock", "original_language": "en", "first_air_date": "2010-07-25",
    "seasons": [{"season_number": 0, "air_date": "2010-01-01"}, {"season_number": 1, "air_date": "2010-07-25"},
                {"season_number": 3, "air_date": "2014-01-01"}],
    "translations": {"translations": [{"iso_639_1": "en", "data": {"name": "Sherlock"}}]},
    "alternative_titles": {"results": [{"title": "BBC Sherlock"}]},
}  # fmt: skip
INTERSTELLAR = {
    "id": 157336, "title": "Интерстеллар", "original_title": "Interstellar", "original_language": "en",
    "release_date": "2014-11-05", "imdb_id": "tt0816692",
    "translations": {"translations": [{"iso_639_1": "en", "data": {"title": "Interstellar"}}]},
    "alternative_titles": {"titles": []},
}  # fmt: skip


def configure(api, net):  # noqa: F811
    net.on("GET", "/Fribb/anime-lists/master/anime-list-full.json", httpx.Response(200, json=[]))
    api.put(
        "/api/settings",
        json={
            "values": {
                "tmdb.read_access_token": "tok",
                "sonarr.url": "http://sonarr:8989/sonarr",
                "sonarr.api_key": "k",
                "radarr.url": "http://radarr:7878/radarr",
                "radarr.api_key": "k",
            }
        },
    )


def test_series_via_tmdb(api, net):  # noqa: F811
    configure(api, net)
    net.on("GET", "/3/find/176941", httpx.Response(200, json={"tv_results": [{"id": 19885}]}))
    net.on("GET", "/3/tv/19885", httpx.Response(200, json=SHERLOCK_TV))
    net.on(
        "GET",
        "/sonarr/api/v3/series",
        httpx.Response(200, json=[{"title": "Sherlock", "year": 2010, "seriesType": "standard"}]),
    )
    rows = "".join(
        [
            pages.row(1, "Шерлок / Sherlock / Сезон: 1 / Серии: 1-3 из 3 (Пол МакГиган) [2010, Великобритания, WEB-DL 1080p] MVO (Первый канал) + Original", "Сериалы Великобритании и Ирландии (HD Video)", forum_id=193),
            pages.row(2, "Шерлок / Sherlock (Колм Маккарти) [2014, Великобритания, WEB-DL 1080p] Dub + Original + Sub (Rus, Eng)", "Сериалы Великобритании и Ирландии (HD Video)", forum_id=193),
            pages.row(3, "Шерлок в России / Серии: 1-8 из 8 (Нурбек Эген) [2020, детектив, WEBRip-AVC] + Sub (Rus)", "Русские сериалы", forum_id=9),
        ]
    )  # fmt: skip
    net.on("GET", "/forum/tracker.php", html(pages.search_page(rows)))
    found = items(
        api.get("/torznab/api", params={"t": "tvsearch", "tvdbid": "176941", "apikey": key(api)})
    )
    titles = sorted(i.findtext("title") for i in found)
    assert titles == [
        # Original track without a stated language: ENGLISH from TMDb.
        "Sherlock S01 1080p WEB-DL ENGLISH RUSSIAN OrigAudio RusMVO RTA-T2 -RuTracker",
        # No season number in the title: 2014 is season 3's year.
        "Sherlock S03 1080p WEB-DL ENGLISH RUSSIAN OrigAudio OrigSubs RusDub RusSubs EngSubs RTA-T1 -RuTracker",
    ]  # "Шерлок в России" is another series
    attrs = {a.get("name"): a.get("value") for a in found[0].findall("torznab:attr", NS)}
    assert attrs["tvdbid"] == "176941"
    auth = next(c for c in net.calls if c.url.path == "/3/tv/19885").headers["authorization"]
    assert auth == "Bearer tok"


def test_movie_via_tmdb_and_radarr(api, net):  # noqa: F811
    configure(api, net)
    net.on("GET", "/3/movie/157336", httpx.Response(200, json=INTERSTELLAR))
    net.on(
        "GET",
        "/radarr/api/v3/movie",
        httpx.Response(
            200, json=[{"title": "Interstellar", "year": 2014, "originalTitle": "Interstellar"}]
        ),
    )
    rows = "".join(
        [
            pages.row(5, "Интерстеллар / Interstellar (Кристофер Нолан / Christopher Nolan) [2014, США, BDRip 1080p] Dub + Original + Sub (Rus, Eng)", "Зарубежное кино (HD Video)", forum_id=313),
            pages.row(6, "Интерстеллар / Interstellar (Гэри Тейлор) [1989, США, VHSRip] VO", "Фильмы до 1990 года", forum_id=2090),
        ]
    )  # fmt: skip
    net.on("GET", "/forum/tracker.php", html(pages.search_page(rows)))
    found = items(
        api.get(
            "/torznab/api",
            params={"t": "movie", "imdbid": "", "tmdbid": "157336", "apikey": key(api)},
        )
    )
    assert [i.findtext("title") for i in found] == [
        "Interstellar 2014 1080p BluRay ENGLISH RUSSIAN OrigAudio OrigSubs RusDub RusSubs EngSubs RTA-T1 -RuTracker"
    ]  # the 1989 film of the same name is dropped
    attrs = {a.get("name"): a.get("value") for a in found[0].findall("torznab:attr", NS)}
    assert (attrs["tmdbid"], attrs["imdbid"]) == ("157336", "tt0816692")


def test_imdb_digits_accepted(api, net):  # noqa: F811
    configure(api, net)
    net.on(
        "GET", "/3/find/tt0816692", httpx.Response(200, json={"movie_results": [{"id": 157336}]})
    )
    net.on("GET", "/3/movie/157336", httpx.Response(200, json=INTERSTELLAR))
    net.on("GET", "/radarr/api/v3/movie", httpx.Response(200, json=[]))
    net.on(
        "GET",
        "/radarr/api/v3/movie/lookup/tmdb",
        httpx.Response(200, json={"title": "Interstellar", "year": 2014}),
    )
    net.on("GET", "/forum/tracker.php", html(pages.search_page("")))
    r = api.get("/torznab/api", params={"t": "movie", "imdbid": "0816692", "apikey": key(api)})
    assert r.status_code == 200 and any(c.url.path == "/3/find/tt0816692" for c in net.calls)


PALE_COCOON = {
    "id": 20683, "title": "Бледный кокон", "original_title": "ペイル・コクーン", "original_language": "ja",
    "release_date": "2005-12-01", "imdb_id": "tt1506448",
    "translations": {"translations": [{"iso_639_1": "en", "data": {"title": "Pale Cocoon"}}]},
    "alternative_titles": {"titles": []},
}  # fmt: skip


def test_anime_film_filed_as_ova_is_a_film(api, net):  # noqa: F811
    configure(api, net)
    net.on("GET", "/3/movie/20683", httpx.Response(200, json=PALE_COCOON))
    net.on(
        "GET",
        "/radarr/api/v3/movie",
        httpx.Response(200, json=[{"title": "Pale Cocoon", "year": 2005}]),
    )
    rows = "".join(
        [
            pages.row(7, "Бледный Кокон / Aoi Tamago / Pale Cocoon [OVA] [RUS(int), JAP+Sub] [2005, драма, BDRip] [1080p]", "Аниме (HD Video)", forum_id=1105),
            pages.row(8, "Бледный Кокон / Pale Cocoon [TV] [1-12 из 12] [JAP+Sub] [2005, драма, BDRip] [1080p]", "Аниме (HD Video)", forum_id=1105),
        ]
    )  # fmt: skip
    seen: list[str] = []

    def tracker(request):
        seen.append(request.url.params.get("nm", ""))
        return html(pages.search_page(rows))

    net.on("GET", "/forum/tracker.php", tracker)
    found = items(
        api.get(
            "/torznab/api",
            params={"t": "movie", "tmdbid": "20683", "cat": "2000,2040", "apikey": key(api)},
        )
    )
    titles = [i.findtext("title") for i in found]
    assert len(titles) == 1 and titles[0].startswith("Pale Cocoon 2005 1080p BluRay")  # a film name
    cats = [
        a.get("value") for a in found[0].findall("torznab:attr", NS) if a.get("name") == "category"
    ]
    assert "2000" in cats  # film categories, so Radarr takes it
    assert (
        len(seen) == 2
    )  # the Japanese title isn't searched (it would be RuTracker's newest topics)
