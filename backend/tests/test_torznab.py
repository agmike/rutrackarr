"""Torznab API: caps, auth, search → renamed releases, filtering, download."""

from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree as ET

import httpx
import pytest

from rutrackarr.releases.language import assess
from rutrackarr.releases.naming import categories, release_name
from rutrackarr.releases.sections import classify
from rutrackarr.releases.title import parse_title
from rutrackarr.torznab import search as search_mod
from rutrackarr.torznab.search import SearchCache, clean_query
from tests.fixtures import pages
from tests.test_rutracker_flow import api, html, net  # noqa: F401  (fixtures)

NS = {"torznab": "http://torznab.com/schemas/2015/feed"}
FRIEREN_S2 = (
    "Фрирен, провожающая в последний путь (ТВ-2) / Sousou no Frieren 2nd Season / Frieren: Beyond "
    "Journey's End Season 2 [TV+Special] [10+11 из 10+11] [JAP+Sub] & [10+0 из 10+11] [RUS(ext)] "
    "[2026, приключения, драма, фэнтези, BDRip] [1080p]"
)
FRIEREN_S1 = (
    "Фрирен, провожающая в последний путь (ТВ-1) / Sousou no Frieren / Frieren: Beyond Journey's End "
    "[TV] [28 из 28] [RUS(int), JAP+Sub] [2023, приключения, WEB-DL] [1080p]"
)
FRIEREN_OST = "(OST) Sousou no Frieren / Frieren: Beyond Journey's End - 2023, MP3"
INTERSTELLAR = (
    "Интерстеллар / Interstellar (Кристофер Нолан / Christopher Nolan) [2014, США, фантастика, "
    "UHD BDRemux 2160p, HDR10, Dolby Vision] [IMAX] Dub + MVO + 2x AVO + Original (Eng) + Sub (Rus, Eng)"
)


def name(title: str, forum: str, query: str | None = None) -> str:
    t, s = parse_title(title), classify(forum)
    return release_name(t, s, assess(t, s), query)


def test_release_names():
    assert name(FRIEREN_S2, "Аниме (HD Video)", "Frieren Beyond Journeys End") == (
        "Frieren Beyond Journeys End S02 1080p BluRay JAPANESE RUSSIAN OrigSubs RusVoice RusSubs "
        "RTA-T1 -RuTracker"
    )
    assert (
        name(
            "Большой Куш / One Piece / Ван-Пис [TV] [1156-1180 из 1000+] [RUS(ext), JAP+Sub] [1999, WEB-DL] [1080p]",
            "Ван-Пис",
        )
        == "One Piece - 1156-1180 1080p WEB-DL JAPANESE RUSSIAN OrigSubs RusVoice RusSubs RTA-T1 -RuTracker"
    )
    assert name(INTERSTELLAR, "Зарубежное кино (UHD Video)") == (
        "Interstellar 2014 2160p BluRay REMUX HDR10 DV ENGLISH RUSSIAN OrigSubs RusDub RusSubs EngSubs "
        "RTA-T1 -RuTracker"
    )
    assert (
        name(
            "Молодой Шерлок / Young Sherlock / Сезон: 1 / Серии: 1-6 из 8 (Гай Ричи) [2026, Великобритания, "
            "WEB-DLRip-AVC] DVO (Кубик в Кубе) + Original",
            "Сериалы Великобритании и Ирландии",
        )
        == "Young Sherlock S01E01-E06 WEBRip h264 RUSSIAN RusDVO RTA-T2 -RuTracker"
    )
    assert (
        name(
            "Слово пацана. Кровь на асфальте / Сезон: 1 / Серии: 1-8 из 8 (Жора Крыжовников) [2023, драма, WEBRip 1080p] + Sub (Rus)",
            "Русские сериалы (HD Video)",
        )
        == "Слово пацана. Кровь на асфальте S01 1080p WEBRip RUSSIAN RusSubs RTA-T1 -RuTracker"
    )


def test_categories():
    t = parse_title(INTERSTELLAR)
    assert categories(classify("Зарубежное кино (UHD Video)"), t) == [2000, 2045]
    t = parse_title(FRIEREN_S2)
    assert categories(classify("Аниме (HD Video)"), t) == [5000, 5040, 5070]


@pytest.mark.parametrize(
    ("q", "clean", "year"),
    [
        ("Frieren Beyond Journeys End S02E05", "Frieren Beyond Journeys End", None),
        ("Interstellar 2014", "Interstellar", 2014),
        ("Interstellar (2014)", "Interstellar", 2014),
        ("Taxi 4", "Taxi 4", None),
        ("One Piece Season 2", "One Piece", None),
    ],
)
def test_clean_query(q, clean, year):
    assert clean_query(q) == (clean, year)


def items(resp: httpx.Response) -> list[ET.Element]:
    root = ET.fromstring(resp.content)
    assert root.tag == "rss", resp.text
    return root.findall("./channel/item")


def key(api) -> str:  # noqa: F811
    return api.get("/api/settings/api-key").json()["api_key"]


def test_caps_and_auth(api):  # noqa: F811
    r = api.get("/torznab/api", params={"t": "caps"})
    root = ET.fromstring(r.content)
    assert root.find("./searching/tv-search").get("supportedParams") == "season,ep,tvdbid"
    assert root.find("./searching/search").get("available") == "no"
    assert {c.get("id") for c in root.iter("subcat")} >= {"5070", "2045"}
    r = api.get("/torznab/api", params={"t": "tvsearch", "q": "x", "apikey": "wrong"})
    assert ET.fromstring(r.content).get("code") == "100"


def test_tvsearch_filters_and_renames(api, net):  # noqa: F811
    rows = "".join(
        [
            pages.row(1, FRIEREN_S2, "Аниме (HD Video)", seeders=27),
            pages.row(2, FRIEREN_S1, "Аниме (HD Video)"),
            pages.row(3, FRIEREN_OST, "Саундтреки к аниме (lossy)", forum_id=282),
        ]
    )
    net.on("GET", "/forum/tracker.php", html(pages.search_page(rows)))
    params = {
        "t": "tvsearch",
        "q": "Frieren Beyond Journeys End",
        "season": "2",
        "apikey": key(api),
    }
    found = items(api.get("/torznab/api", params=params))
    assert [i.findtext("title") for i in found] == [
        "Frieren Beyond Journeys End S02 1080p BluRay JAPANESE RUSSIAN OrigSubs RusVoice RusSubs "
        "RTA-T1 -RuTracker"
    ]
    item = found[0]
    assert item.findtext("guid").endswith("/forum/viewtopic.php?t=1")
    link = urlparse(item.findtext("link"))
    assert link.path == "/torznab/download/1" and parse_qs(link.query)["apikey"] == [key(api)]
    attrs = {a.get("name"): a.get("value") for a in item.findall("torznab:attr", NS)}
    assert attrs["seeders"] == "27" and attrs["peers"] == "28"
    assert [c.text for c in item.findall("category")] == ["5000", "5040", "5070"]
    assert item.findtext("description") == FRIEREN_S2
    # Same query again: served from the cache, no second RuTracker request.
    api.get("/torznab/api", params={**params, "season": "1"})
    assert sum(1 for c in net.calls if c.url.path == "/forum/tracker.php") == 1


def test_movie_search_skips_series_and_checks_year(api, net):  # noqa: F811
    rows = pages.row(5, INTERSTELLAR, "Зарубежное кино (UHD Video)", forum_id=1457)
    net.on("GET", "/forum/tracker.php", html(pages.search_page(rows)))
    found = items(
        api.get("/torznab/api", params={"t": "movie", "q": "Interstellar 2014", "apikey": key(api)})
    )
    assert len(found) == 1
    assert (
        items(
            api.get(
                "/torznab/api", params={"t": "movie", "q": "Interstellar 1990", "apikey": key(api)}
            )
        )
        == []
    )
    assert (
        items(
            api.get(
                "/torznab/api", params={"t": "tvsearch", "q": "Interstellar", "apikey": key(api)}
            )
        )
        == []
    )


def test_retry_with_fewer_words(api, net):  # noqa: F811
    seen = []

    def tracker(request: httpx.Request) -> httpx.Response:
        nm = request.url.params["nm"]
        seen.append(nm)
        rows = pages.row(1, FRIEREN_S2, "Аниме (HD Video)") if nm == "Frieren%Beyond" else ""
        return html(pages.search_page(rows))

    net.on("GET", "/forum/tracker.php", tracker)
    params = {"t": "tvsearch", "q": "Frieren Beyond Journeys End", "apikey": key(api)}
    assert len(items(api.get("/torznab/api", params=params))) == 1
    assert seen == ["Frieren%Beyond%Journeys%End", "Frieren%Beyond"]


def test_rutracker_error_is_torznab_error(api, net):  # noqa: F811
    net.on("GET", "/forum/tracker.php", html(pages.MAINTENANCE, status=503))
    r = api.get("/torznab/api", params={"t": "search", "q": "x", "apikey": key(api)})
    err = ET.fromstring(r.content)
    assert err.tag == "error" and err.get("code") == "900" and "04:45" in err.get("description")


def test_download(api, net):  # noqa: F811
    torrent = b"d8:announce3:urle"
    net.on(
        "GET",
        "/forum/dl.php",
        httpx.Response(200, content=torrent, headers={"content-type": "application/x-bittorrent"}),
    )
    assert api.get("/torznab/download/7", params={"apikey": "nope"}).status_code == 401
    r = api.get("/torznab/download/7", params={"apikey": key(api)})
    assert r.status_code == 200 and r.content == torrent
    assert r.headers["content-type"] == "application/x-bittorrent"


def test_anime_absolute_searches_share_one_rutracker_query(api, net):  # noqa: F811
    one_piece = (
        "Большой Куш / One Piece / Ван-Пис [TV] [1156-1180 из 1000+] [RUS(ext), JAP+Sub] "
        "[1999, WEB-DL] [1080p]"
    )
    rows = pages.row(1, one_piece, "Ван-Пис", forum_id=2544) + pages.row(
        2, FRIEREN_S1, "Аниме (HD Video)"
    )
    net.on("GET", "/forum/tracker.php", html(pages.search_page(rows)))
    k = key(api)
    hit = items(api.get("/torznab/api", params={"t": "search", "q": "One Piece 1160", "apikey": k}))
    miss = items(
        api.get("/torznab/api", params={"t": "search", "q": "One Piece 1100", "apikey": k})
    )
    assert [i.findtext("title").split(" 1080p")[0] for i in hit] == ["One Piece - 1156-1180"]
    assert miss == []
    searches = [c for c in net.calls if c.url.path == "/forum/tracker.php"]
    assert [c.url.params["nm"] for c in searches] == ["One%Piece"]


def test_english_dub_token_avoids_trash_dubs_only():
    t = name(
        "Фрирен / Sousou no Frieren [TV] [28 из 28] [RUS(int), ENG, JAP+Sub] [2023, WEB-DL] [1080p]",
        "Аниме (HD Video)",
    )
    assert "EngVoice" in t and "dub" not in t.lower().replace("rusdub", "")


async def test_cache_ttls(monkeypatch):
    calls: list[str] = []

    class Client:
        async def search(self, q):
            calls.append(q)
            return []

    now = [1000.0]
    monkeypatch.setattr(search_mod.time, "monotonic", lambda: now[0])
    ttl = [3600.0]
    cache = SearchCache(Client(), ttl=lambda: ttl[0], rss_ttl=lambda: 300)  # type: ignore[arg-type]
    await cache.search("Frieren")
    await cache.search("")
    now[0] += 1200  # 20 minutes: a long season search later
    await cache.search("frieren ")  # same normalised query: cached
    await cache.search("")  # RSS: expired after 5 minutes
    assert calls == ["Frieren", "", ""]
    ttl[0] = 0  # cache off (setting changed): every text search goes to RuTracker
    await cache.search("Frieren")
    assert calls[-1] == "Frieren" and len(calls) == 4


def test_titles_parsed_once():
    search_mod._analyse.cache_clear()
    row = search_mod.SearchRow(
        topic_id=1,
        title=FRIEREN_S2,
        forum_id=1105,
        forum="Аниме (HD Video)",
        size=1,
        seeders=1,
        leechers=0,
        downloads=0,
        added=None,
        author="",
        approved=None,
    )
    search_mod.build(row, "Frieren")
    search_mod.build(row, "Sousou no Frieren")
    info = search_mod._analyse.cache_info()
    assert (info.misses, info.hits) == (1, 1)


def test_only_best_russian_voice_in_name():
    n = name(
        "Молодой Шерлок / Young Sherlock / Сезон: 1 / Серии: 1-8 из 8 (Гай Ричи) [2026, Великобритания, "
        "WEB-DL 1080p] 5 x MVO (HDrezka Studio, LostFilm) + DVO (Кубик в Кубе) + Dub (WinMedia) + Original + Sub (Rus, Eng)",
        "Сериалы Великобритании и Ирландии (HD Video)",
    )
    tokens = n.split()
    assert "RusDub" in tokens and not {"RusMVO", "RusDVO", "RusVoice"} & set(tokens)
    n = name("А / A [TV] [12 из 12] [RUS(int)] [2020, WEBRip] [1080p]", "Аниме (HD Video)")
    assert "RusVoice" in n.split() and "RTA-T2" in n


def test_name_follows_the_alias_sonarr_searched_for():
    nia = (
        "Кёран Рэйдзё Ниа Листон / Kyouran Reijou Nia Liston: Byoujaku Reijou ni Tensei shita Kamigoroshi "
        "(Kami-goroshi) no Bujin no Karei Naru Musouroku [TV] [1-5 из 12] [RUS(ext), JAP+Sub] [2026, WEB-DL] [1080p]"
    )
    n = name(nia, "Онгоинги (HD Video)", "Kyouran Reijou Nia Liston")
    assert n.startswith("Kyouran Reijou Nia Liston S01E01-E05 1080p WEB-DL")
    # Not one of this topic's names: the RuTracker name stays (the romaji query above maps it).
    n = name(nia, "Онгоинги (HD Video)", "Nia Liston The Merciless Maiden")
    assert n.startswith("Kyouran Reijou Nia Liston: Byoujaku")
    assert name(nia, "Онгоинги (HD Video)").startswith("Kyouran Reijou Nia Liston: Byoujaku")  # RSS


def test_partial_name_match_keeps_the_rutracker_name():
    lego = (
        "LEGO Большой куш / LEGO Ван-Пис / LEGO One Piece / Сезон: 1 / Серии: 1-2 из 2 (Челси Кер) "
        "[2026, США, Мультсериал, WEB-DL 1080p] Dub + Original + Sub (Rus, Eng)"
    )
    assert name(lego, "Мультсериалы", "One Piece").startswith("LEGO One Piece S01")
    assert name(FRIEREN_S2, "Аниме (HD Video)", "Sousou no Frieren").startswith(
        "Sousou no Frieren S02"
    )
