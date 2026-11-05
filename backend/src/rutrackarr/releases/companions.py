"""External audio/subtitle files that belong to a video in a RuTracker torrent.

RuTracker puts external tracks in their own folders (one per dub team / translation), with no
fixed folder names; the file names follow the video's name so players load them
(``RUS Sound [StudioBand]/<video name>.StudioBand.mka``). Sonarr ignores them, so a Sonarr
custom script links them next to the imported episode under Jellyfin/Plex/Kodi names:
``<episode>.<lang>.<title>.<flags>.<ext>`` (e.g. ``….ru.StudioBand.mka``,
``….ru.StudioBand signs.forced.ass``).

Only the torrent's file list is used — never the files. Languages come from folder/file name
tokens, then from the topic title (``RUS(ext)``, anime ``Sub`` = Russian subtitles).
"""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from rutrackarr.releases.title import ParsedTitle

AUDIO = {".mka", ".ac3", ".eac3", ".dts", ".aac", ".flac", ".m4a", ".mp3", ".opus", ".thd", ".wav"}
SUBS = {".ass", ".ssa", ".srt", ".sup", ".vtt", ".sub", ".idx"}
VIDEO = {".mkv", ".mp4", ".avi", ".m2ts", ".ts", ".wmv", ".mov", ".webm"}

_LANG_TOKENS = {
    "ru": ("rus", "ru", "russian", "рус", "русская", "русские", "русский"),
    "uk": ("ukr", "ua", "ukrainian", "укр", "украинская", "украинские"),
    "en": ("eng", "en", "english", "англ", "английская", "английские"),
    "ja": ("jap", "jpn", "ja", "japanese", "яп", "японская"),
}
_SIGNS = ("signs", "sign", "надписи", "надпись", "forced", "titles", "songs")
_NOISE = {
    "sound", "sounds", "audio", "voice", "dub", "mvo", "dvo", "avo", "vo", "sub", "subs",
    "subtitle", "subtitles", "ext", "external", "озвучка", "озвучки", "звук", "звуковые",
    "дорожки", "дорожка", "субтитры", "субтитров", "перевод", "full", "полные",
}  # fmt: skip
_WORD = re.compile(r"[^\W\d_]+|\d+")  # letters and digits apart: "rus2" → rus, 2


@dataclass(frozen=True)
class Companion:
    path: str  # inside the torrent
    suffix: str  # appended to the episode's path without extension: "ru.StudioBand.mka"


def find_video(files: list[str], source: str) -> str | None:
    """The torrent path of the file Sonarr imported (matched by file name)."""
    name = PurePosixPath(source.replace("\\", "/")).name
    exact = [f for f in files if PurePosixPath(f).name == name]
    if exact:
        return exact[0]
    folded = [f for f in files if PurePosixPath(f).name.casefold() == name.casefold()]
    return folded[0] if folded else None


def plan(files: list[str], video: str, title: ParsedTitle | None = None) -> list[Companion]:
    v = PurePosixPath(video)
    stem = v.stem.casefold()
    extras = [f for f in files if f != video and PurePosixPath(f).suffix.lower() in AUDIO | SUBS]
    matched = [f for f in extras if PurePosixPath(f).stem.casefold().startswith(stem)]
    videos = [f for f in files if PurePosixPath(f).suffix.lower() in VIDEO]
    if not matched and len(videos) == 1:
        matched = extras  # a single film: every external track is its own
    out: list[Companion] = []
    used: set[str] = set()
    for f in sorted(matched):
        suffix = first = _suffix(f, v.stem, title)
        n = 2
        while suffix.casefold() in used:  # two tracks with the same name: number them
            head, _, ext = first.rpartition(".")
            suffix = ".".join(x for x in (head, str(n), ext) if x)
            n += 1
        used.add(suffix.casefold())
        out.append(Companion(f, suffix))
    return out


def _suffix(path: str, video_stem: str, title: ParsedTitle | None) -> str:
    p = PurePosixPath(path)
    ext = p.suffix.lower()
    audio = ext in AUDIO
    # The part of the file name after the video's name (".StudioBand"), or the whole name of a
    # track that isn't named after the video ("rus.srt" in a single-film torrent).
    if p.stem.casefold().startswith(video_stem.casefold()):
        rest = p.stem[len(video_stem) :]
    else:
        rest = p.stem
    words = [w.casefold() for part in [*p.parent.parts, rest] for w in _WORD.findall(part)]
    lang = next(
        (code for code, toks in _LANG_TOKENS.items() if any(w in toks for w in words)), None
    )
    lang = lang or _title_default(title, audio)
    signs = not audio and any(w.startswith(_SIGNS) for w in words)
    team = _team(rest) or _team_from_dirs(p.parent.parts)
    label = " ".join(x for x in (team, "signs" if signs else "") if x)
    fields = [lang, label, "forced" if signs else None, ext.lstrip(".")]
    return ".".join(x for x in fields if x)


def _title_default(title: ParsedTitle | None, audio: bool) -> str | None:
    if title is None:
        return None
    if audio:
        external = [a for a in title.audio if a.external]
        langs = {a.lang for a in external} or {a.lang for a in title.audio if not a.original}
        langs.discard(None)
        return "ru" if langs == {"rus"} else None
    return "ru" if title.subs == ["rus"] or (title.subs_unknown and not title.subs) else None


def _clean(text: str) -> str:
    keep = [
        w
        for w in re.findall(r"[^\s.\[\]()_]+", text)
        if w.casefold() not in _NOISE
        and not any(w.casefold() in toks for toks in _LANG_TOKENS.values())
        and not w.casefold().startswith(_SIGNS)
    ]
    return " ".join(keep).strip(" -")


def _team(rest: str) -> str:
    return _clean(rest)


def _team_from_dirs(parts: tuple[str, ...]) -> str:
    for part in reversed(parts):
        m = re.search(r"\[([^\]]+)\]", part)  # "RUS Sound [StudioBand]"
        if m and (team := _clean(m.group(1))):
            return team
        if team := _clean(part):
            return team
    return ""
