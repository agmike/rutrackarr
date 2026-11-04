"""Language preference: how well a release's audio/subtitles fit the wanted languages.

Default preference (one list for everything):

1. Original audio + subtitles (Russian or English)
2. Russian voice: dub > multi-voice > two-voice > author's > single-voice > type not stated
3. English dub (foreign, non-English content only)
4. Anything else (original without subtitles, other languages)

Russian-made content is always "original"; English subtitles are a bonus there.
A title without any language information is "unknown" — never ranked as missing.
"""

from dataclasses import dataclass, field

from rutrackarr.releases.sections import Section
from rutrackarr.releases.title import Audio, ParsedTitle

ORIGINAL_SUBS, RU_VOICE, EN_DUB, OTHER, UNKNOWN = 1, 2, 3, 4, 9
_VOICE_ORDER = ("dub", "mvo", "dvo", "avo", "vo", None)
_VOICE_LABEL = {
    "dub": "dub",
    "mvo": "multi-voice",
    "dvo": "two-voice",
    "avo": "author's VO",
    "vo": "single-voice",
    None: "voice",
}
_ANIME_ORIGINAL = {"jpn", "chi", "kor"}


@dataclass
class LanguageVerdict:
    tier: int
    label: str
    rank: int  # sort key: lower is better
    original: str | None = None  # original language, when known
    en_subs: bool = False
    notes: list[str] = field(default_factory=list)


def assess(t: ParsedTitle, section: Section) -> LanguageVerdict:
    notes: list[str] = []
    if t.hardsub == "hardsub":
        notes.append("hardsub")
    en_subs = "eng" in t.subs
    original_audio = _original_tracks(t, section)
    russian_made = section.origin == "russian" or any(a.lang == "rus" for a in original_audio)
    if russian_made:
        label = "Original (Russian)" + (" + EN subs" if en_subs else "")
        return LanguageVerdict(
            ORIGINAL_SUBS, label, 100 + (0 if en_subs else 1), "rus", en_subs, notes
        )

    if t.audio and all(a.lang == "zxx" for a in t.audio):
        return LanguageVerdict(ORIGINAL_SUBS, "No dialogue", 100, "zxx", en_subs, notes)

    if not (t.audio or t.subs or t.subs_unknown):
        return LanguageVerdict(UNKNOWN, "Not in title", 900, notes=["check the topic page"])

    original_lang = next((a.lang for a in original_audio if a.lang), None)
    subs_ok = "rus" in t.subs or en_subs or t.subs_unknown
    if original_audio and subs_ok:
        ordered = sorted(t.subs, key=lambda c: {"rus": 0, "eng": 1}.get(c, 2))
        langs = ", ".join(ordered) if ordered else "?"
        rank = 100 + (0 if "rus" in t.subs else 1)
        return LanguageVerdict(
            ORIGINAL_SUBS, f"Original + Sub ({langs})", rank, original_lang, en_subs, notes
        )

    ru = [a for a in t.audio if a.lang == "rus" and _not_in(a, original_audio)]
    if ru:
        best = min(ru, key=lambda a: _VOICE_ORDER.index(a.voice))
        if best.voice is None:
            notes.append("voice type not in title")
        if best.partial:
            notes.append("Russian audio on part of the episodes")
        rank = 200 + _VOICE_ORDER.index(best.voice) * 10 + (5 if best.partial else 0)
        return LanguageVerdict(
            RU_VOICE, f"RU {_VOICE_LABEL[best.voice]}", rank, original_lang, en_subs, notes
        )

    en = [a for a in t.audio if a.lang == "eng" and _not_in(a, original_audio)]
    if en and original_lang != "eng":
        return LanguageVerdict(EN_DUB, "EN dub", 300, original_lang, en_subs, notes)

    label = "Original, no subs" if original_audio else "Other languages"
    return LanguageVerdict(OTHER, label, 400, original_lang, en_subs, notes)


def _original_tracks(t: ParsedTitle, section: Section) -> list[Audio]:
    """Stated originals ("Original Eng"), or the Japanese/Chinese/Korean track in anime."""
    stated = [a for a in t.audio if a.original]
    if stated or section.kind != "anime":
        return stated
    return [a for a in t.audio if a.lang in _ANIME_ORIGINAL and a.voice is None]


def _not_in(a: Audio, tracks: list[Audio]) -> bool:
    return all(a is not o for o in tracks)
