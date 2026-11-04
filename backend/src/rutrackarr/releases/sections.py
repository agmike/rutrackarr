"""Which RuTracker sections hold video we can offer, and what kind.

Classified from the section (forum) name — positive matches only: a section that
doesn't look like a known video section is excluded. See docs/title-format.md.
"""

from dataclasses import dataclass

# Substrings (lowercase) of sections that are never results: device-specific encodes,
# audio, extras, books, music, parodies, archives.
_EXCLUDED = (
    "psp",
    "ipod",
    "iphone",
    "ipad",
    "apple tv",
    "смартфон",
    "кпк",
    "звуковые дорожки",
    "саундтрек",
    "трейлер",
    "некондиц",
    "смешным переводом",
    "пародии",
    "обои",
    "манга",
    "ранобэ",
    "amv",
    "артбук",
    "комикс",
    "[аудио]",
    "аудиокниг",
    "lossless",
    "lossy",
    "архив",
    "музык",
    "клип",
    "концерт",
)
_ANIME = ("аниме", "ван-пис", "гандам", "наруто", "покемон", "онгоинг", "дунхуа")


@dataclass(frozen=True)
class Section:
    kind: str  # "anime" | "movie" | "series" | "other"
    origin: str  # "anime" | "foreign" | "russian" | "unknown"
    video: bool  # offered as a result at all

    @property
    def label(self) -> str:
        return "other" if not self.video else f"{self.origin} {self.kind}"


EXCLUDED = Section("other", "unknown", False)


def classify(name: str) -> Section:
    n = " ".join(name.lower().split())
    if n == "видео" or any(x in n for x in _EXCLUDED):
        return EXCLUDED
    if any(x in n for x in _ANIME):
        return Section("anime", "anime", True)
    russian = "русск" in n or "наше кино" in n or "российск" in n or "советск" in n
    if "сериал" in n:
        return Section("series", "russian" if russian else "foreign", True)
    if "кино" in n or "фильм" in n:
        return Section("movie", "russian" if russian else "foreign", True)
    return EXCLUDED
