"""ID searches: TVDB id → anime list → Shikimori names → RuTracker → season by entry."""

from urllib.parse import parse_qs
from xml.etree import ElementTree as ET

import httpx

from rutrackarr.releases.title import parse_title
from rutrackarr.torznab.idsearch import Entry, SeriesContext, match, norm
from tests.fixtures import pages
from tests.test_rutracker_flow import api, html, net  # noqa: F401  (fixtures)
from tests.test_torznab import FRIEREN_OST, FRIEREN_S1, FRIEREN_S2, NS, items, key

ANIME_LIST = [
    {
        "mal_id": 52991,
        "type": "TV",
        "tvdb_id": 424536,
        "season": {"tvdb": 1, "tmdb": 1},
        "themoviedb_id": {"tv": 209867},
    },
    {
        "mal_id": 59978,
        "type": "TV",
        "tvdb_id": 424536,
        "season": {"tvdb": 2, "tmdb": 1},
        "episode_offset": {"tmdb": 28},
    },
    {"mal_id": 99999, "type": "TV", "anidb_id": 1},  # no TVDB/TMDb/IMDb: dropped by compact()
]
SHIKI = {
    52991: {"name": "Sousou no Frieren", "russian": "Провожающая в последний путь Фрирен", "english": ["Frieren: Beyond Journey's End"],
            "synonyms": ["Фрирен, провожающая в последний путь"], "japanese": ["葬送のフリーレン"], "kind": "tv", "aired_on": "2023-09-29"},
    59978: {"name": "Sousou no Frieren 2nd Season", "russian": "Провожающая в последний путь Фрирен 2",
            "english": ["Frieren: Beyond Journey's End Season 2"], "synonyms": ["Фрирен, провожающая в последний путь 2"],
            "japanese": ["葬送のフリーレン 第2期"], "kind": "tv", "aired_on": "2026-01-16"},
}  # fmt: skip
SONARR = [{"title": "Frieren: Beyond Journey's End", "year": 2023, "seriesType": "anime", "tvdbId": 424536,
           "alternateTitles": [{"title": "Sousou no Frieren"}]}]  # fmt: skip


def setup(net, api, rows: str):  # noqa: F811
    net.on(
        "GET",
        "/Fribb/anime-lists/master/anime-list-full.json",
        httpx.Response(200, json=ANIME_LIST),
    )
    for mal, d in SHIKI.items():
        net.on("GET", f"/api/animes/{mal}", httpx.Response(200, json={"id": mal, **d}))
    net.on("GET", "/sonarr/api/v3/series", httpx.Response(200, json=SONARR))
    net.on("GET", "/forum/tracker.php", html(pages.search_page(rows)))
    api.put(
        "/api/settings",
        json={"values": {"sonarr.url": "http://sonarr:8989/sonarr", "sonarr.api_key": "k"}},
    )


def test_id_search_assigns_tvdb_season_from_shikimori_entry(api, net):  # noqa: F811
    unmarked_s2 = FRIEREN_S2.replace(" (ТВ-2)", "").replace("Sousou no Frieren 2nd Season / ", "")
    rows = "".join(
        [
            pages.row(1, FRIEREN_S1, "Аниме (HD Video)"),
            pages.row(2, FRIEREN_S2, "Аниме (HD Video)"),
            pages.row(3, FRIEREN_OST, "Саундтреки к аниме (lossy)", forum_id=282),
            pages.row(
                4, unmarked_s2, "Аниме (HD Video)"
            ),  # only the English "Season 2" name says so
            pages.row(
                5,
                "Другой сериал / Another Show [TV] [12 из 12] [JAP+Sub] [2023, WEB-DL] [1080p]",
                "Аниме (HD Video)",
            ),
        ]
    )
    setup(net, api, rows)
    params = {
        "t": "tvsearch",
        "tvdbid": "424536",
        "season": "2",
        "cat": "5000,5070",
        "apikey": key(api),
    }
    found = items(api.get("/torznab/api", params=params))
    titles = [i.findtext("title") for i in found]
    assert len(titles) == 2 and all(
        t.startswith("Frieren: Beyond Journey's End S02 ") for t in titles
    ), titles
    attrs = {a.get("name"): a.get("value") for a in found[0].findall("torznab:attr", NS)}
    assert attrs["tvdbid"] == "424536"
    searched = sorted(
        {
            parse_qs(c.url.query.decode("ascii"), encoding="cp1251")["nm"][0]
            for c in net.calls
            if c.url.path == "/forum/tracker.php"
        }
    )
    assert searched == sorted(
        {
            "Провожающая%в%последний%путь%Фрирен%2",
            "Sousou%no%Frieren%2nd%Season",
            "Frieren%Beyond%Journey%s%End",
        }
    )
    # Season 1 from the same cached results; Shikimori and the list asked once each.
    found = items(api.get("/torznab/api", params={**params, "season": "1"}))
    assert [i.findtext("title").split(" 1080p")[0] for i in found] == [
        "Frieren: Beyond Journey's End S01"
    ]
    assert sum(1 for c in net.calls if c.url.path == "/api/animes/52991") == 1
    assert sum(1 for c in net.calls if c.url.path.endswith("anime-list-full.json")) == 1


def test_unknown_id_without_query_returns_nothing(api, net):  # noqa: F811
    setup(net, api, "")
    net.on("GET", "/sonarr/api/v3/series", httpx.Response(200, json=[]))
    net.on("GET", "/sonarr/api/v3/series/lookup", httpx.Response(200, json=[]))
    r = api.get("/torznab/api", params={"t": "tvsearch", "tvdbid": "1", "apikey": key(api)})
    assert ET.fromstring(r.content).findall("./channel/item") == []


def _ctx(*entries: Entry, other: set[str] | None = None) -> SeriesContext:
    return SeriesContext(1, "Show", list(entries), other or set(), [])


def _entry(season: int, *names: str, offset: int = 0) -> Entry:
    from rutrackarr.torznab.idsearch import _head

    return Entry(
        season,
        season,
        offset,
        names[0],
        names[0],
        {norm(n) for n in names},
        {_head(n) for n in names},
    )


def test_match_prefers_more_names_then_stated_season():
    s1 = _entry(1, "Городская демонесса", "Machikado Mazoku", "The Demon Girl Next Door")
    s2 = _entry(
        2,
        "Городская демонесса 2",
        "Machikado Mazoku: 2-choume",
        "Machikado Mazoku 2",
        "The Demon Girl Next Door 2",
    )
    t = parse_title(
        "Городская дьяволица 2 / Machikado Mazoku 2 / The Demon Girl Next Door 2 [TV] [12 из 12] [JAP+Sub] [2022, WEBRip] [1080p]"
    )
    assert match(_ctx(s1, s2), t).season == 2
    t = parse_title(
        "Городская демонесса (ТВ-1) / Machikado Mazoku / The Demon Girl Next Door [TV] [12 из 12] [JAP+Sub] [2019, BDRip] [1080p]"
    )
    assert match(_ctx(s1, s2), t).season == 1
    # Subtitle-only overlap still matches (long romaji with an extra part on RuTracker).
    nia = _entry(
        1,
        "Kyouran Reijou Nia Liston: Byoujaku Reijou ni Tensei shita Kamigoroshi no Bujin no Karei naru Musouroku",
    )
    t = parse_title(
        "Ниа / Kyouran Reijou Nia Liston: Byoujaku Reijou ni Tensei shita Kamigoroshi (Kami-goroshi) no Bujin [TV] [1-5 из 12] [JAP+Sub] [2026, WEB-DL] [1080p]"
    )
    assert match(_ctx(nia), t).season == 1
    # Not this series, unless Sonarr's own titles match.
    other = parse_title("Другое / Something Else [TV] [12 из 12] [JAP+Sub] [2020, WEB-DL] [1080p]")
    assert match(_ctx(s1), other) is None
    assert match(_ctx(s1, other={norm("Something Else")}), other).season is None


def test_episode_offset_for_split_cours():
    part2 = _entry(1, "Show Part 2", offset=12)
    t = parse_title("Шоу / Show Part 2 [TV] [1-6 из 12] [JAP+Sub] [2024, WEB-DL] [1080p]")
    from rutrackarr.releases.language import assess
    from rutrackarr.releases.naming import release_name
    from rutrackarr.releases.sections import classify

    s = classify("Аниме (HD Video)")
    m = match(_ctx(part2), t)
    name = release_name(
        t, s, assess(t, s), None, series_title="Show", season=m.season, offset=m.offset
    )
    assert name.startswith("Show S01E13-E18 1080p")
