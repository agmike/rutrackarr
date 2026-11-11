"""Release names and categories for Sonarr/Radarr.

A RuTracker title is rewritten into a scene-style name Sonarr/Radarr parse reliably:

    <Name> <S02 | S02E01-E08 | - 1156-1180 | 2014> <1080p> <BluRay> <h264> <HDR>
        <JAPANESE RUSSIAN> <OrigSoftSubs | RusDub …> <RTA-T1> -RuTracker

- Name: the title Sonarr/Radarr searched for (always one of the series' own titles, so the
  release maps back to it); for RSS, the first Latin name of the RuTracker title with season
  hints removed. The season goes into SxxEyy.
- Language words (JAPANESE, RUSSIAN, …) are for Sonarr/Radarr's own language detection.
- CamelCase tokens (RusDub, OrigSoftSubs, EngVoice, …) and the tier token RTA-T<n> are for custom
  formats; single words, so Sonarr's language parser doesn't read "RUS" out of them, and no
  "dub" word of its own (TRaSH's anime "Dubs Only" format would score it -10000). Subtitle
  tokens end in "SoftSubs": Radarr takes any other word ending in "Subs" for burned-in
  subtitles and rejects the release.
"""

import re

from rutrackarr.releases.language import LanguageVerdict
from rutrackarr.releases.sections import Section
from rutrackarr.releases.title import ParsedTitle

_SOURCE = {
    "BDRemux": "BluRay REMUX",
    "Blu-ray": "COMPLETE BLURAY",
    "BDRip": "BluRay",
    "HD-DVD": "HDDVD",
    "WEB-DL": "WEB-DL",
    "WEBRip": "WEBRip",
    "HDTV": "HDTV",
    "HDTVRip": "HDTV",
    "DVD": "DVD",
    "DVDRemux": "DVD REMUX",
    "DVDRip": "DVDRip",
    "HDRip": "HDRip",
    "DMRip": "WEBRip",
    "TVRip": "TVRip",
    "VHSRip": "VHSRip",
    "LDRip": "LDRip",
    "CAMRip": "CAM",
    "Hybrid": "Hybrid",
}
_CODEC = {"AVC": "h264", "HEVC": "h265"}
_HDR = {
    "HDR10": "HDR10",
    "HDR10+": "HDR10Plus",
    "Dolby Vision": "DV",
    "Dolby Vision TV": "DV",
    "HLG": "HLG",
}
_LANG_WORD = {
    "rus": "RUSSIAN",
    "eng": "ENGLISH",
    "jpn": "JAPANESE",
    "kor": "KOREAN",
    "chi": "CHINESE",
    "ukr": "UKRAINIAN",
    "deu": "GERMAN",
    "fra": "FRENCH",
    "ita": "ITALIAN",
    "spa": "SPANISH",
}
_VOICE_TOKEN = {"dub": "RusDub", "mvo": "RusMVO", "dvo": "RusDVO", "avo": "RusAVO", "vo": "RusVO"}
_SEASON_HINTS = re.compile(
    r"\s*\b(?:season\s*\d+|\d+(?:st|nd|rd|th)\s+season|сезон\s*\d+)\b|\s*\((?:ТВ|TV)-?\d*\)", re.I
)
_LATIN = re.compile(r"[A-Za-z]")
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_WORD = re.compile(r"[^\W_]+")


def is_movie(section: Section, t: ParsedTitle) -> bool:
    return section.kind == "movie" or (section.kind == "anime" and "Movie" in t.kinds)


def categories(section: Section, t: ParsedTitle) -> list[int]:
    """Newznab categories: Movies 2000 (SD 2030, HD 2040, UHD 2045), TV 5000 (SD 5030, HD 5040,
    UHD 5045, Anime 5070)."""
    uhd = t.uhd or t.resolution == "2160p"
    hd = t.resolution in ("720p", "810p", "960p", "1080p", "1080i", "1440p")
    if is_movie(section, t):
        return [2000, 2045 if uhd else 2040 if hd else 2030]
    cats = [5000, 5045 if uhd else 5040 if hd else 5030]
    if section.kind == "anime":
        cats.append(5070)
    return cats


def pick_name(t: ParsedTitle, query: str | None) -> str:
    """The name to publish: Latin names first, the one sharing most words with the query."""
    names = [_SEASON_HINTS.sub("", n).strip(" .,:-") for n in t.names] or [t.raw]
    latin = [n for n in names if _LATIN.search(n) and not _CYRILLIC.search(n)]
    pool = latin or names
    if not query:
        return pool[0]
    wanted = {w.lower() for w in _WORD.findall(query)}
    return max(pool, key=lambda n: len(wanted & {w.lower() for w in _WORD.findall(n)}))


def _norm(text: str) -> str:
    text = _SEASON_HINTS.sub(" ", text).replace("'", "").replace("’", "")
    return " ".join(w.lower() for w in _WORD.findall(text))


def names_title(t: ParsedTitle, query: str) -> bool:
    """One of the RuTracker names is the searched title: the same words (punctuation and season
    hints aside), or the title followed by a subtitle after ":" / " - ". A partial match
    ("LEGO One Piece" for "One Piece") is not enough: naming that release after the query
    would make it look like an episode of the other series."""
    wanted = _norm(query)
    if not wanted:
        return False
    for n in t.names:
        if _norm(n) == wanted:
            return True
        head = re.split(r"\s*:\s*|\s+-\s+", n, maxsplit=1)[0]
        if head != n and _norm(head) == wanted:
            return True
    return False


def is_absolute(t: ParsedTitle, section: Section) -> bool:
    """Long-running anime without seasons (One Piece 1156-1180): absolute episode numbers."""
    e = t.episodes
    if section.kind != "anime" or t.season is not None or e is None:
        return False
    return (e.first or 1) > 1 and (e.total is None or (e.last or 0) > 100)


def numbering(
    t: ParsedTitle,
    section: Section,
    season: int | None = None,
    offset: int = 0,
    year: int | None = None,
) -> str:
    """S02 / S02E01-E08 / S01E08 for series, "- 1156-1180" for long anime, the year for movies.
    `season`/`offset` come from metadata (the TVDB season and episode offset of the anime entry
    the topic belongs to) and win over what the title says."""
    if is_movie(section, t):
        year = year or t.year
        return str(year) if year else ""
    e = t.episodes
    if is_absolute(t, section) and e:
        return f"- {e.first:03d}" if e.first == e.last else f"- {e.first:03d}-{e.last:03d}"
    if t.season_last and season is None:
        return f"S{t.season:02d}-S{t.season_last:02d}"
    s = f"S{season or t.season or 1:02d}"
    if e is None or e.first is None or e.last is None or (e.complete and not offset):
        return s
    first, last = e.first + offset, e.last + offset
    if first == last:
        return f"{s}E{first:02d}"
    return f"{s}E{first:02d}-E{last:02d}"


def language_tokens(
    t: ParsedTitle, verdict: LanguageVerdict, original_language: str | None = None
) -> list[str]:
    """`original_language` (ISO 639-2, from TMDb) names an "Original" track whose language the
    title doesn't state — Sonarr/Radarr's "Language: Not Original" checks need the word."""
    has_original = verdict.original is not None or any(a.original for a in t.audio)
    words: list[str] = []
    stated = [verdict.original, *(a.lang for a in t.audio)]
    if has_original and original_language and not any(a.original and a.lang for a in t.audio):
        stated.insert(0, original_language)
    for code in stated:
        word = _LANG_WORD.get(code or "")
        if word and word not in words:
            words.append(word)
    tokens: list[str] = []
    if has_original and verdict.label != "No dialogue":
        tokens.append("OrigAudio")  # the original track is there, with or without subtitles
    if verdict.label == "No dialogue":
        tokens.append("NoDialogue")
    elif verdict.tier == 1 and verdict.original != "rus":
        tokens.append("OrigSoftSubs")
    # Only the best Russian voice type: custom-format scores add up, so listing every track
    # would make "one more voice-over" look like an upgrade of the same release.
    voices = {a.voice for a in t.audio if a.lang == "rus" and not a.original}
    best = next((v for v in ("dub", "mvo", "dvo", "avo", "vo") if v in voices), None)
    if best:
        tokens.append(_VOICE_TOKEN[best])
    elif None in voices:
        tokens.append("RusVoice")
    if any(a.lang == "eng" and not a.original and verdict.original != "eng" for a in t.audio):
        tokens.append("EngVoice")  # not "EngDub": TRaSH's anime "Dubs Only" matches eng_?dub
    if "rus" in t.subs or t.subs_unknown:
        tokens.append("RusSoftSubs")
    if "eng" in t.subs:
        tokens.append("EngSoftSubs")
    return [*words, *tokens, f"RTA-T{verdict.tier}"]


def release_name(
    t: ParsedTitle,
    section: Section,
    verdict: LanguageVerdict,
    query: str | None,
    *,
    series_title: str | None = None,
    season: int | None = None,
    offset: int = 0,
    year: int | None = None,
    original_language: str | None = None,
) -> str:
    """`series_title` is Sonarr's own title of the series an ID search resolved the topic to.
    Otherwise `query`, the (cleaned) title Sonarr/Radarr searched for — one of the series' own
    titles or aliases, so a release named after it maps back to the series — when a RuTracker
    name *is* that title; else the best Latin name (RSS, unrelated hits)."""
    query = (query or "").strip()
    if series_title:
        name = series_title
    elif query and names_title(t, query):
        name = query
    else:
        name = pick_name(t, query or None)
    parts = [name, numbering(t, section, season, offset, year)]
    resolution = t.resolution or ("2160p" if t.uhd else None)
    parts += [resolution or "", _SOURCE.get(t.source or "", t.source or "")]
    parts.append(_CODEC.get(t.codec or "", ""))
    parts += [_HDR[h] for h in t.hdr if h in _HDR]
    parts += language_tokens(t, verdict, original_language)
    if section.qc:
        parts.append("RTA-QC")  # a QC subsection's release: scored down by its custom format
    name = " ".join(p for p in parts if p)
    return f"{' '.join(name.split())} -RuTracker"


_FILE_TOKENS = re.compile(
    r"\b(?:OrigAudio|NoDialogue|Orig(?:Soft)?Subs|Rus(?:Dub|MVO|DVO|AVO|VO|Voice|(?:Soft)?Subs)"
    r"|Eng(?:Voice|(?:Soft)?Subs)|RTA-T\d|RTA-QC)\b"
)
VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".wmv", ".mov", ".webm"}


def file_tag(release: str) -> str:
    """The part of a release name that video files get too, so Sonarr/Radarr score an imported
    file as they scored the grab: "… OrigAudio RusSubs RTA-T1 -RuTracker" → that tail."""
    return " ".join([*dict.fromkeys(_FILE_TOKENS.findall(release)), "-RuTracker"])


# What RuTrackarr appends to a video file's name: tag tokens, the marker, and for a later
# season's topic that numbers its episodes from 1, the episode as Sonarr numbers it (after the
# marker, where an original name never has anything — "… RTA-T1 -RuTracker S02E01.mkv").
_TAGGED = re.compile(r"^(?P<base>.*) -RuTracker(?: S\d{2,3}E\d{2,4})?$")


def tagged(path: str, tag: str, mark: str | None = None) -> str:
    """ "Show/Ep 01.mkv" → "Show/Ep 01 <tag>.mkv", with `mark` "Show/Ep 01 <tag> S02E01.mkv"
    (video files only, at most once)."""
    head, sep, name = path.rpartition("/")
    stem, dot, ext = name.rpartition(".")
    if not dot or f".{ext.lower()}" not in VIDEO_EXTS or _TAGGED.match(stem):
        return path
    return f"{head}{sep}{stem} {tag}{f' {mark}' if mark else ''}.{ext}"


def with_mark(path: str, mark: str) -> str:
    """A tagged video file's name with its episode mark set ("… -RuTracker S02E01.mkv");
    untagged files are left alone."""
    head, sep, name = path.rpartition("/")
    stem, dot, ext = name.rpartition(".")
    m = _TAGGED.match(stem) if dot else None
    if m is None:
        return path
    return f"{head}{sep}{m['base']} -RuTracker {mark}.{ext}"


def untagged(path: str) -> str:
    """The file name before RuTrackarr tagged it: "Show/Ep 01 OrigAudio RusSubs RTA-T1
    -RuTracker S02E01.mkv" → "Show/Ep 01.mkv" (whatever tokens the tag had). Approximate when
    the original name itself ended in a tag-like word — compare with `renamed_from` instead
    where it matters."""
    head, sep, name = path.rpartition("/")
    stem, dot, ext = name.rpartition(".")
    m = _TAGGED.match(stem) if dot else None
    if m is None:
        return path
    words = m["base"].split(" ")
    while len(words) > 1 and _FILE_TOKENS.fullmatch(words[-1]):
        words.pop()
    return f"{head}{sep}{' '.join(words)}.{ext}"


def renamed_from(original: str, name: str) -> bool:
    """`name` is the file `original` (a name from the .torrent) as RuTrackarr may have renamed
    it: unchanged, or with tag tokens (whichever tag it got back then), the marker and an episode
    mark appended. Compared forwards from the original, so it's exact."""
    if name == original:
        return True
    ohead, _, oname = original.rpartition("/")
    nhead, _, nname = name.rpartition("/")
    if ohead != nhead:
        return False
    ostem, odot, oext = oname.rpartition(".")
    nstem, ndot, next_ = nname.rpartition(".")
    if not (odot and ndot) or oext != next_ or not nstem.startswith(f"{ostem} "):
        return False
    m = re.fullmatch(r"((?:\S+ )*)-RuTracker(?: S\d{2,3}E\d{2,4})?", nstem[len(ostem) + 1 :])
    return m is not None and all(_FILE_TOKENS.fullmatch(w) for w in m.group(1).split())
