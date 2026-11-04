"""Title parser, sections and language ranking — against real search exports."""

import json
from pathlib import Path

import pytest

from rutrackarr.releases.language import EN_DUB, ORIGINAL_SUBS, OTHER, RU_VOICE, UNKNOWN, assess
from rutrackarr.releases.sections import classify
from rutrackarr.releases.title import parse_title

CORPUS = sorted((Path(__file__).parent / "data" / "search").glob("*.json"))
ROWS = [r for f in CORPUS for r in json.loads(f.read_text())["results"]]
VIDEO = [r for r in ROWS if classify(r["forum"]).video]


def langs(t):
    return [(a.lang, a.voice, a.original, a.count) for a in t.audio]


def test_corpus_loaded():
    assert len(CORPUS) >= 9 and len(VIDEO) > 100


@pytest.mark.parametrize("row", VIDEO, ids=lambda r: str(r["topic_id"]))
def test_every_video_title_parses(row):
    t = parse_title(row["title"])
    assert t.names, row["title"]
    assert t.year and 1900 < t.year < 2100
    assert t.source, row["title"]
    assert assess(t, classify(row["forum"])).tier != UNKNOWN, row["title"]


@pytest.mark.parametrize(
    ("forum", "label"),
    [
        ("Аниме (HD Video)", "anime anime"),
        ("Ван-Пис", "anime anime"),
        ("Аниме (QC подраздел)", "anime anime"),
        ("Зарубежное кино (UHD Video)", "foreign movie"),
        ("Фильмы 2011-2015", "foreign movie"),
        ("Сериалы Великобритании и Ирландии (HD Video)", "foreign series"),
        ("Мультсериалы", "foreign series"),
        ("Русские сериалы (HD Video)", "russian series"),
        ("Аниме для PSP", "other"),
        ("Саундтреки к аниме (lossless)", "other"),
        ("Звуковые дорожки и Переводы (Аниме)", "other"),
        ("Фильмы HD для Apple TV", "other"),
        ("[Видео Юмор] Фильмы со смешным переводом (пародии)", "other"),
        ("Видео", "other"),
        ("Манга (на русском языке)", "other"),
        ("Химия / Биохимия", "other"),
    ],
)
def test_sections(forum, label):
    assert classify(forum).label == label


def test_anime_split_language_groups():
    t = parse_title(
        "Фрирен, провожающая в последний путь (ТВ-2) / Sousou no Frieren 2nd Season / Frieren: Beyond "
        "Journey's End Season 2 [TV+Special] [10+11 из 10+11] [JAP+Sub] & [10+0 из 10+11] [RUS(ext)] "
        "[2026, приключения, драма, фэнтези, BDRip] [1080p]"
    )
    assert t.names[:2] == ["Фрирен, провожающая в последний путь", "Sousou no Frieren 2nd Season"]
    assert (t.season, t.kinds) == (2, ["TV", "Special"])
    e = t.episodes
    assert (e.first, e.last, e.total, e.specials, e.specials_total) == (1, 10, 10, 11, 11)
    assert e.complete
    jap, rus = t.audio
    assert (jap.lang, jap.partial) == ("jpn", False)
    assert (rus.lang, rus.external, rus.partial) == ("rus", True, True)
    assert t.subs == ["rus"]
    assert (t.year, t.source, t.resolution) == (2026, "BDRip", "1080p")
    v = assess(t, classify("Аниме (HD Video)"))
    assert (v.tier, v.label, v.original) == (ORIGINAL_SUBS, "Original + Sub (rus)", "jpn")


def test_anime_open_total_and_names_with_parentheses():
    t = parse_title(
        "Большой Куш / One Piece / Ван-Пис [TV] [1156-1180 из 1000+] [RUS(ext), JAP+Sub] "
        "[1999, приключения, комедия, фэнтези, сёнэн, WEB-DL] [1080p]"
    )
    assert (t.episodes.first, t.episodes.last, t.episodes.total) == (1156, 1180, None)
    assert not t.episodes.complete
    t = parse_title(
        "Евангелион 3.0+1.01: Как-то раз / Shin Evangelion Gekijouban 3.0+1.01 (Анно Хидэаки) [Movie] "
        "[RUS(int), JAP+Sub] [2021, экшен, BDRemux] [2160p]"
    )
    assert t.names == ["Евангелион 3.0+1.01: Как-то раз", "Shin Evangelion Gekijouban 3.0+1.01"]
    assert (t.director, t.season, t.episodes, t.resolution) == ("Анно Хидэаки", None, None, "2160p")
    t = parse_title(
        "Евангелион: 3.0 (-46 часов) / Evangelion: 3.0 (-46h) [Special] [RUS(int),JAP+Sub] [2023, BDRip] [1080p]"
    )
    assert (
        t.names == ["Евангелион: 3.0 (-46 часов)", "Evangelion: 3.0 (-46h)"] and t.director is None
    )


def test_film_translations_and_uhd():
    t = parse_title(
        "Интерстеллар / Interstellar (Кристофер Нолан / Christopher Nolan) [2014, США, Великобритания, "
        "фантастика, боевик, детектив, приключения, UHD BDRemux 2160p, HDR10, Dolby Vision] [IMAX] [Hybrid] "
        "Dub + MVO + 2x AVO + 2x VO + Dub (Ukr) + Original (Eng) + Sub (Rus, Ukr, Eng)"
    )
    assert t.director == "Кристофер Нолан / Christopher Nolan"
    assert (t.source, t.uhd, t.resolution, t.hdr) == (
        "BDRemux",
        True,
        "2160p",
        ["HDR10", "Dolby Vision"],
    )
    assert t.tags == ["IMAX", "Hybrid"]
    assert langs(t) == [
        ("rus", "dub", False, 1),
        ("rus", "mvo", False, 1),
        ("rus", "avo", False, 2),
        ("rus", "vo", False, 2),
        ("ukr", "dub", False, 1),
        ("eng", None, True, 1),
    ]
    assert t.subs == ["rus", "ukr", "eng"]
    v = assess(t, classify("Зарубежное кино (UHD Video)"))
    assert (v.tier, v.label, v.en_subs) == (ORIGINAL_SUBS, "Original + Sub (rus, eng, ukr)", True)


@pytest.mark.parametrize(
    ("trailing", "expected"),
    [
        (
            "Dub (Rus, Ukr) + MVO (Омикрон) + AVO (Ю.Сербин, Ю.Живов) + Original (Eng) + Sub",
            [
                ("rus", "dub", False, 1),
                ("ukr", "dub", False, 1),
                ("rus", "mvo", False, 1),
                ("rus", "avo", False, 1),
                ("eng", None, True, 1),
            ],
        ),
        (
            "5 x MVO (HDrezka Studio, LostFilm) + DVO + Dub + Original + Sub (Rus, Eng)",
            [
                ("rus", "mvo", False, 5),
                ("rus", "dvo", False, 1),
                ("rus", "dub", False, 1),
                (None, None, True, 1),
            ],
        ),
        (
            "2x Dub + 2x MVO + DVO + 3x AVO + VO + 3x MVO Ukr + Sub Rus, Eng + Original Eng",
            [
                ("rus", "dub", False, 2),
                ("rus", "mvo", False, 2),
                ("rus", "dvo", False, 1),
                ("rus", "avo", False, 3),
                ("rus", "vo", False, 1),
                ("ukr", "mvo", False, 3),
                ("eng", None, True, 1),
            ],
        ),
        (
            "Dub + 3х MVO (Jaskier, TVShows, LostFilm) + Sub Rus, Eng + Original Eng",
            [("rus", "dub", False, 1), ("rus", "mvo", False, 3), ("eng", None, True, 1)],
        ),
        (
            "MVO (NewStudio) + Jap + Original (Eng) + Sub (Rus, Eng)",
            [("rus", "mvo", False, 1), ("jpn", None, False, 1), ("eng", None, True, 1)],
        ),
        (
            "Dub + Original (eng) + Sub (rus, eng)",
            [("rus", "dub", False, 1), ("eng", None, True, 1)],
        ),
    ],
)
def test_trailing_translations(trailing, expected):
    t = parse_title(
        f"Фильм / Film (Режиссёр / Director) [2014, США, драма, BDRip 1080p] {trailing}"
    )
    assert langs(t) == expected
    assert not t.leftovers


def test_subtitle_spellings():
    t = parse_title(
        "Х / X / Сезон: 1 / Серии: 1-4 из 6 (Р) [2024, драма, WEB-DL 1080p] Original + Rus Sub (hvblack)"
    )
    assert t.subs == ["rus"] and langs(t) == [(None, None, True, 1)]
    t = parse_title(
        "Х / X (Р) [1964-1965, детектив, DVDRemux] Original + Sub (Rus, Родерик Аллейн) + Sub (Eng )"
    )
    assert t.subs == ["rus", "eng"] and (t.year, t.year_end) == (1964, 1965)
    t = parse_title("Х / X (Р) [2026, драма, WEB-DLRip-AVC] MVO (RuDub) + Sub (Dutch, Eng)")
    assert t.subs == ["nld", "eng"] and (t.source, t.codec) == ("WEBRip", "AVC")


def test_russian_series():
    t = parse_title(
        "Слово пацана. Кровь на асфальте / Сезон: 1 / Серии: 1-8 из 8 (Жора Крыжовников) "
        "[2023, драма, SDR, WEBRip 2160p] + Sub (Rus)"
    )
    assert (t.names, t.season, t.director) == (
        ["Слово пацана. Кровь на асфальте"],
        1,
        "Жора Крыжовников",
    )
    assert (t.episodes.first, t.episodes.last, t.episodes.total) == (1, 8, 8)
    assert (t.source, t.resolution, t.hdr, t.subs) == ("WEBRip", "2160p", [], ["rus"])
    v = assess(t, classify("Русские сериалы (UHD Video)"))
    assert (v.tier, v.label, v.en_subs) == (ORIGINAL_SUBS, "Original (Russian)", False)
    t = parse_title(
        "Слово пацана. Кровь на асфальте / Сезон: 1 / Серии: 8-я / (Жора Крыжовников) [2023, Драма, DVDRip]"
    )
    assert (t.episodes.first, t.episodes.last, t.director) == (8, 8, "Жора Крыжовников")


def test_language_tiers():
    anime, film = classify("Аниме (HD Video)"), classify("Зарубежное кино (HD Video)")
    v = assess(parse_title("А / A [TV] [12 из 12] [RUS(int)] [2020, WEBRip] [1080p]"), anime)
    assert (v.tier, v.label, v.notes) == (RU_VOICE, "RU voice", ["voice type not in title"])
    dub = assess(parse_title("Ф / F (Р / D) [2014, США, BDRip] Dub + MVO"), film)
    mvo = assess(parse_title("Ф / F (Р / D) [2014, США, BDRip] MVO (LostFilm) + Original"), film)
    assert (dub.tier, dub.label, mvo.label) == (
        RU_VOICE,
        "RU dub",
        "RU multi-voice",
    ) and dub.rank < mvo.rank
    v = assess(parse_title("А / A [TV] [12 из 12] [ENG, JAP] [2020, WEBRip] [1080p]"), anime)
    assert (v.tier, v.label) == (EN_DUB, "EN dub")
    v = assess(parse_title("Ф / F (Р / D) [2014, США, BDRip] Original (Eng)"), film)
    assert (v.tier, v.label) == (OTHER, "Original, no subs")
    v = assess(
        parse_title("Ф / F (Р / D) [1975, СССР, драма, HDTV 1080i] Original Rus + Sub Eng"), film
    )
    assert (v.label, v.en_subs) == ("Original (Russian) + EN subs", True)
    v = assess(parse_title("Ф / F (Р / D) [2014, США, BDRip]"), film)
    assert (v.tier, v.label) == (UNKNOWN, "Not in title")


def test_no_dialogue():
    t = parse_title(
        "История одной улицы / Aru Machi Kado (Machikado) no Monogatari / Tales of the Street Corner / "
        "Tale of a Street Corner / Story of a Street Corner / Osamu Tezuka Works: The Experimental Films "
        "[Movie] [ZXX] [1962, драма, романтика, BDRip] [720p]"
    )
    assert langs(t) == [("zxx", None, False, 1)] and t.kinds == ["Movie"]
    assert t.names[1] == "Aru Machi Kado (Machikado) no Monogatari"
    v = assess(t, classify("Аниме (HD Video)"))
    assert (v.tier, v.label) == (ORIGINAL_SUBS, "No dialogue")
