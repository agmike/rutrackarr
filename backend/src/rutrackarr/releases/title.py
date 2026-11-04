"""RuTracker topic title parser (reference: docs/title-format.md).

One tolerant parser for all sections. It records what a title states and nothing more:
anything it can't read stays unknown (`leftovers`) rather than being guessed.

    Names / … / Сезон: N / Серии: a-b из c (Director) [brackets…] trailing translations
"""

import re
from dataclasses import dataclass, field

# Language spellings seen in titles -> ISO 639-2 code.
_LANGS = {
    "rus": "rus",
    "ru": "rus",
    "рус": "rus",
    "eng": "eng",
    "en": "eng",
    "jap": "jpn",
    "jpn": "jpn",
    "ukr": "ukr",
    "ua": "ukr",
    "kor": "kor",
    "chi": "chi",
    "chn": "chi",
    "zho": "chi",
    "deu": "deu",
    "ger": "deu",
    "fra": "fra",
    "fre": "fra",
    "ita": "ita",
    "spa": "spa",
    "esp": "spa",
    "heb": "heb",
    "nld": "nld",
    "dut": "nld",
    "dutch": "nld",
    "kaz": "kaz",
    "bel": "bel",
    "tur": "tur",
    "pol": "pol",
    "por": "por",
    "hin": "hin",
    "swe": "swe",
    "fin": "fin",
    "nor": "nor",
    "dan": "dan",
    "cze": "ces",
    "ces": "ces",
    "tha": "tha",
    "geo": "kat",
    "est": "est",
    "lav": "lav",
    "lit": "lit",
    "uzb": "uzb",
    "aze": "aze",
}
_VOICES = ("dub", "mvo", "dvo", "avo", "vo")


def lang_code(token: str) -> str | None:
    return _LANGS.get(token.strip(" .«»\"'").lower())


@dataclass
class Audio:
    lang: str | None  # ISO 639-2; None = not stated
    voice: str | None = None  # dub / mvo / dvo / avo / vo; None = not stated
    original: bool = False  # stated as the original track ("Original")
    count: int = 1
    info: str | None = None  # studio / author / source
    external: bool | None = None  # RUS(ext) / RUS(int)
    partial: bool = False  # covers fewer episodes than the video (anime "&" groups)


@dataclass
class Episodes:
    first: int | None
    last: int | None
    total: int | None  # None = open / unknown ("XXX", "1000+")
    specials: int | None = None
    specials_total: int | None = None

    @property
    def complete(self) -> bool:
        return self.total is not None and self.first in (0, 1) and self.last == self.total


@dataclass
class ParsedTitle:
    raw: str
    names: list[str] = field(default_factory=list)
    director: str | None = None
    prefix: list[str] = field(default_factory=list)  # leading "[iPad]", "(OST)" …
    kinds: list[str] = field(default_factory=list)  # TV, Movie, OVA, ONA, Special, CM
    season: int | None = None
    season_last: int | None = None
    episodes: Episodes | None = None
    year: int | None = None
    year_end: int | None = None
    source: str | None = None  # normalised: BDRemux, BDRip, WEB-DL, WEBRip, …
    uhd: bool = False
    codec: str | None = None  # from the "-AVC" / "-HEVC" suffix
    resolution: str | None = None
    hdr: list[str] = field(default_factory=list)
    hardsub: str | None = None  # hardsub / semi / russian
    localized_video: bool = False
    tags: list[str] = field(default_factory=list)  # editions and other bracket tags
    audio: list[Audio] = field(default_factory=list)
    subs: list[str] = field(default_factory=list)  # subtitle languages
    subs_unknown: bool = False  # "Sub" without languages
    leftovers: list[str] = field(default_factory=list)


_LEADING = re.compile(r"^\s*(\[[^\[\]]*\]|\([^()]*\))\s*")
_SEASON_PAREN = re.compile(
    r"\(\s*(ТВ|TV|ОВА|OVA|ONA)(?:\s*-\s*(\d+))?(?:\s*,\s*часть\s*(\d+))?\s*\)", re.I
)
_EDITION_PAREN = re.compile(r"\(([^()]*(?:edition|version|cut|imax)[^()]*)\)", re.I)
_SEASON_HINT = re.compile(r"\b(?:season|сезон)\s*(\d+)\b|\b(\d+)(?:st|nd|rd|th)\s+season\b", re.I)
_SEASON_PART = re.compile(r"^сезон(?:ы)?\s*:\s*(\d+)(?:\s*-\s*(\d+))?", re.I)
_EPISODES_PART = re.compile(r"^(?:серии|серия|фильмы|выпуски|эпизоды)\s*:\s*(.+)$", re.I)
_SPLIT_NAMES = re.compile(r"\s+/\s*|\s*/\s+")

_KIND = re.compile(
    r"^(?:TV|Movie|OVA|ONA|Special|CM|Extra|PV)(?:\s*\+\s*(?:TV|Movie|OVA|ONA|Special|CM|Extra|PV))*$",
    re.I,
)
_COUNT = re.compile(
    r"^(?P<single>серия\s+)?(?P<a>\d+)(?:\s*-\s*(?P<b>\d+))?"
    r"(?:\s*\+\s*(?P<sa>\d+)(?:\s*-\s*(?P<sb>\d+))?)?"
    r"(?:\s*-?\s*(?:я|й|ая))?"
    r"(?:\s+из\s+(?P<total>\S+))?\s*$",
    re.I,
)
_SLASH_COUNT = re.compile(r"^(\d+)\s*/\s*(\d+)$")
_YEAR = re.compile(r"^\s*(\d{4})(?:\s*-\s*(\d{4}))?\s*(?:г\.?|\.)?\s*(?:,|$)")
_SOURCE = re.compile(
    r"(?<![\w-])(?P<uhd>UHD\s+)?(?P<src>BD[\s-]?Remux|Blu-?ray(?:\s+disc)?|BDRip|HDDVDRip|HD-DVD|"
    r"WEB-DLRip|WEB-DL|WEB-?Rip|WP-?Rip|HDTVRip|HDTV|DVDRip|DVD-?Remux|DVD[59]|DVD|HDRip|DMRip|"
    r"IPTVRip|SATRip|DVBRip|TVRip|VHSRip|LDRip|CAMRip|Hybrid)(?:-(?P<codec>AVC|HEVC|ASP))?(?![\w])",
    re.I,
)
_SOURCE_NAMES = {
    "bdremux": "BDRemux",
    "bd remux": "BDRemux",
    "bd-remux": "BDRemux",
    "blu-ray": "Blu-ray",
    "bluray": "Blu-ray",
    "blu-ray disc": "Blu-ray",
    "bluray disc": "Blu-ray",
    "bdrip": "BDRip",
    "hddvdrip": "BDRip",
    "hd-dvd": "HD-DVD",
    "web-dlrip": "WEBRip",
    "web-dl": "WEB-DL",
    "webrip": "WEBRip",
    "web-rip": "WEBRip",
    "wprip": "WEBRip",
    "wp-rip": "WEBRip",
    "hdtvrip": "HDTVRip",
    "hdtv": "HDTV",
    "dvdrip": "DVDRip",
    "dvdremux": "DVDRemux",
    "dvd-remux": "DVDRemux",
    "dvd5": "DVD",
    "dvd9": "DVD",
    "dvd": "DVD",
    "hdrip": "HDRip",
    "dmrip": "DMRip",
    "iptvrip": "TVRip",
    "satrip": "TVRip",
    "dvbrip": "TVRip",
    "tvrip": "TVRip",
    "vhsrip": "VHSRip",
    "ldrip": "LDRip",
    "camrip": "CAMRip",
    "hybrid": "Hybrid",
}
_RES = re.compile(r"(?<!\d)(2160|1440|1080|960|810|720|576|480|360)\s*([pi])\b", re.I)
_4K = re.compile(r"\b4k\b", re.I)
_HDR = re.compile(r"\b(HDR10\+|HDR10|HLG|Dolby\s+Vision(?:\s+TV)?)", re.I)
_HARDSUB = {"хардсаб": "hardsub", "полухардсаб": "semi", "русский хардсаб": "russian"}
_ANIME_LANG_TOKEN = re.compile(r"^(sub|[a-z]{2,5})(?:\((int|ext|(\d+)\*(\w+))\))?$", re.I)
_TRAILING_ITEM = re.compile(r"^(?:(\d+)\s*[xх×]\s*)?([a-z]{2,8})\b\.?\s*(.*)$", re.I)
_PLUS_OUTSIDE_PARENS = re.compile(r"\s*\+\s*(?![^()]*\))")


def parse_title(raw: str) -> ParsedTitle:
    t = ParsedTitle(raw=raw)
    s = raw.replace("\xa0", " ").strip()
    while m := _LEADING.match(s):
        t.prefix.append(m.group(1)[1:-1].strip())
        s = s[m.end() :]
    cut = s.find("[")
    head, rest = (s, "") if cut < 0 else (s[:cut], s[cut:])
    _parse_head(t, head)
    _parse_rest(t, rest)
    _merge_unstated_voices(t)
    return t


def _merge_unstated_voices(t: ParsedTitle) -> None:
    """[RUS(int)] … DVO (Team): one Russian track, stated twice — keep the typed one."""
    for lang in {a.lang for a in t.audio if a.voice}:
        typed = [a for a in t.audio if a.lang == lang and a.voice and not a.original]
        bare = [a for a in t.audio if a.lang == lang and not a.voice and not a.original]
        if typed and bare:
            if bare[0].external is not None:
                typed[0].external = bare[0].external
            t.audio = [a for a in t.audio if all(a is not b for b in bare)]


# --- head: names, director, season/episode parts ------------------------------------
def _parse_head(t: ParsedTitle, head: str) -> None:
    head = head.strip()
    m = re.search(r"\(([^()]*)\)\s*/?\s*$", head)
    # A trailing "(…)" is the director — unless it's a season marker or has digits ("(-46h)").
    if (
        m
        and not _SEASON_PAREN.fullmatch(m.group(0).strip(" /"))
        and not re.search(r"\d", m.group(1))
    ):
        t.director = m.group(1).strip() or None
        head = head[: m.start()]
    head = head.strip().rstrip("/").strip()
    hint: int | None = None
    for part in (p.strip() for p in _SPLIT_NAMES.split(head)):
        if not part:
            continue
        if m := _SEASON_PART.match(part):
            t.season = int(m.group(1))
            t.season_last = int(m.group(2)) if m.group(2) else None
            continue
        if m := _EPISODES_PART.match(part):
            t.episodes = _parse_count(m.group(1)) or t.episodes
            if t.episodes is None:
                t.leftovers.append(part)
            continue
        if m := _SEASON_PAREN.search(part):
            kind, num = m.group(1).upper(), m.group(2)
            if num and kind in ("ТВ", "TV") and t.season is None:
                t.season = int(num)
            part = (part[: m.start()] + part[m.end() :]).strip()
        if m := _EDITION_PAREN.search(part):
            t.tags.append(m.group(1).strip())
            part = (part[: m.start()] + part[m.end() :]).strip()
        if hint is None and (m := _SEASON_HINT.search(part)):
            hint = int(m.group(1) or m.group(2))
        if part:
            t.names.append(" ".join(part.split()))
    if t.season is None and hint is not None:
        t.season = hint


def _parse_count(text: str) -> Episodes | None:
    text = text.strip()
    if m := _SLASH_COUNT.match(text):
        return Episodes(1, int(m.group(1)), int(m.group(2)))
    first, _, specials_part = text.partition(" / ")  # "3 из 3 / 1 из 1"
    m = _COUNT.match(first.strip())
    if not m:
        return None
    a, b = int(m.group("a")), m.group("b")
    if m.group("single") or (b is None and re.search(r"-?\s*(?:я|й|ая)\s*$", first)):
        ep = Episodes(a, a, None)
    elif b is None:
        ep = Episodes(1 if a else 0, a, None)
    else:
        ep = Episodes(a, int(b), None)
    if m.group("sa") is not None:
        sa, sb = int(m.group("sa")), m.group("sb")
        ep.specials = (int(sb) - sa + 1) if sb else sa
    if (total := m.group("total")) and (tm := re.fullmatch(r"(\d+)(?:\+(\d+))?", total)):
        ep.total = int(tm.group(1))
        ep.specials_total = int(tm.group(2)) if tm.group(2) else None
    if specials_part and (sm := _COUNT.match(specials_part.strip())):
        ep.specials = int(sm.group("b") or sm.group("a"))
    return ep


# --- rest: bracket groups and trailing translations ---------------------------------
def _parse_rest(t: ParsedTitle, rest: str) -> None:
    group = 0
    main_count: Episodes | None = None
    pending_count: Episodes | None = None
    trailing: list[str] = []
    for m in re.finditer(r"\[([^\[\]]*)\]|([^\[\]]+)", rest):
        if m.group(2) is not None:
            text = m.group(2).strip()
            if text == "&":
                group += 1
            elif text:
                trailing.append(text)
            continue
        c = m.group(1).strip()
        if not c:
            continue
        if _KIND.match(c):
            t.kinds = [
                k.strip().upper() if len(k.strip()) <= 3 else k.strip().title()
                for k in c.split("+")
            ]
            continue
        if " - " in c and (ep := _parse_count(c.split(" - ", 1)[0])):  # "1-497 из ХХХ - JAP+Sub"
            langs = c.split(" - ", 1)[1]
            main_count = main_count or ep
            _apply_anime_langs(t, langs, partial=_is_partial(ep, main_count))
            continue
        if ep := _parse_count(c):
            pending_count = ep
            if group == 0 and main_count is None:
                main_count = ep
            continue
        if _apply_anime_langs(t, c, partial=group > 0 and _is_partial(pending_count, main_count)):
            continue
        if c.lower() in _HARDSUB:
            t.hardsub = _HARDSUB[c.lower()]
            continue
        if _YEAR.match(c) and t.year is None:
            _parse_year_bracket(t, c)
            continue
        if re.fullmatch(r"\d{3,4}[pi]", c, re.I):
            t.resolution = t.resolution or c.lower()
            continue
        if sm := re.search(r"(\d+)\s*сезон|сезон\s*(\d+)", c, re.I):
            t.season = t.season or int(sm.group(1) or sm.group(2))
            if "special" in c.lower():
                t.kinds = t.kinds or ["TV", "Special"]
            continue
        if "локализованный видеоряд" in c.lower():
            t.localized_video = True
        t.tags.append(c)
    t.episodes = t.episodes or main_count
    if trailing:
        _parse_trailing(t, " ".join(trailing))


def _is_partial(ep: Episodes | None, main: Episodes | None) -> bool:
    if ep is None or main is None:
        return False
    return (ep.last, ep.specials or 0) != (main.last, main.specials or 0)


def _apply_anime_langs(t: ParsedTitle, text: str, *, partial: bool = False) -> bool:
    """Anime-style block: [RUS(int), ENG, JAP+Sub]. Applies only if every token is valid."""
    tokens = [x.strip() for x in re.split(r"[,+]", text) if x.strip()]
    if not tokens:
        return False
    parsed = []
    for tok in tokens:
        m = _ANIME_LANG_TOKEN.match(tok)
        if not m or (m.group(1).lower() != "sub" and not lang_code(m.group(1))):
            return False
        parsed.append(m)
    for m in parsed:
        word, extra = m.group(1).lower(), (m.group(2) or "").lower()
        if word == "sub":
            if "rus" not in t.subs:
                t.subs.append("rus")  # anime rules: "Sub" = toggleable Russian subtitles
            continue
        a = Audio(lang=lang_code(word), partial=partial)
        if extra in ("int", "ext"):
            a.external = extra == "ext"
        elif m.group(3):
            a.count, a.voice = int(m.group(3)), m.group(4).lower()
        t.audio.append(a)
    return True


def _parse_year_bracket(t: ParsedTitle, c: str) -> None:
    m = _YEAR.match(c)
    assert m
    t.year = int(m.group(1))
    t.year_end = int(m.group(2)) if m.group(2) else None
    if sm := _SOURCE.search(c):
        t.source = _SOURCE_NAMES.get(" ".join(sm.group("src").lower().split()), sm.group("src"))
        t.uhd = bool(sm.group("uhd"))
        t.codec = sm.group("codec").upper() if sm.group("codec") else None
    if rm := _RES.search(c):
        t.resolution = f"{rm.group(1)}{rm.group(2).lower()}"
    elif _4K.search(c):
        t.resolution = "2160p"
    for hm in _HDR.finditer(c):
        name = " ".join(hm.group(1).split())
        name = {"dolby vision": "Dolby Vision", "dolby vision tv": "Dolby Vision TV"}.get(
            name.lower(), name.upper()
        )
        if name not in t.hdr:
            t.hdr.append(name)


def _parse_trailing(t: ParsedTitle, text: str) -> None:
    """Film/series style: Dub + 2x MVO (Studio) + AVO (Author) + Original Eng + Sub (Rus, Eng)."""
    for item in _PLUS_OUTSIDE_PARENS.split(text.strip().lstrip("+").strip()):
        item = item.strip()
        if not item:
            continue
        m = _TRAILING_ITEM.match(item)
        if not m:
            t.leftovers.append(item)
            continue
        count = int(m.group(1)) if m.group(1) else 1
        word, rest = m.group(2).lower(), m.group(3).strip()
        if word in _VOICES:
            _voice(t, word, count, rest)
        elif word == "original":
            langs = _langs(_unparen(rest))
            t.audio.append(Audio(lang=langs[0] if langs else None, original=True))
        elif word == "sub":
            _subs(t, rest)
        elif (code := lang_code(word)) and rest.lower().startswith("sub"):  # "Rus Sub (hvblack)"
            if code not in t.subs:
                t.subs.append(code)
        elif (code := lang_code(word)) and not rest:
            t.audio.append(Audio(lang=code, count=count))  # bare "Eng", "2x Ukr"
        else:
            t.leftovers.append(item)


def _unparen(s: str) -> str:
    s = s.strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    return s.strip().strip('«»"').strip()


def _langs(s: str) -> list[str]:
    return [c for c in (lang_code(x) for x in s.split(",")) if c]


def _voice(t: ParsedTitle, voice: str, count: int, rest: str) -> None:
    inner = _unparen(rest)
    tokens = [x.strip() for x in inner.split(",") if x.strip()]
    codes = [lang_code(x) for x in tokens]
    if tokens and all(codes):  # Dub (Rus, Ukr) / MVO (Ukr)
        for code in codes:
            t.audio.append(Audio(lang=code, voice=voice, count=count))
        return
    first = inner.split(maxsplit=1)
    if len(tokens) == 1 and first and (code := lang_code(first[0])):  # MVO Ukr
        info = first[1] if len(first) > 1 else None
        t.audio.append(
            Audio(lang=code, voice=voice, count=count, info=_unparen(info) if info else None)
        )
        return
    t.audio.append(Audio(lang="rus", voice=voice, count=count, info=inner or None))


def _subs(t: ParsedTitle, rest: str) -> None:
    langs = _langs(_unparen(rest))
    if not langs:
        t.subs_unknown = True
    for code in langs:
        if code not in t.subs:
            t.subs.append(code)
