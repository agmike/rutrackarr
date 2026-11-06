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
_RUSSIAN = ("русск", "наше кино", "российск", "советск", "ссср", "отечествен")
_EXCLUDED_EXTRA = ("театр", "3d", "стерео", "без перевода")  # only for the section catalogue


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
    russian = any(x in n for x in _RUSSIAN)
    if "сериал" in n:
        return Section("series", "russian" if russian else "foreign", True)
    if "кино" in n or "фильм" in n:
        return Section("movie", "russian" if russian else "foreign", True)
    return EXCLUDED


def is_excluded(name: str) -> bool:
    n = " ".join(name.lower().split())
    return n == "видео" or any(x in n for x in _EXCLUDED)


VIDEO_GROUPS = ("кино, видео и тв", "сериалы")


class Catalogue:
    """RuTracker's sections as RuTrackarr classifies them, built from the search form's
    dropdown. A subsection takes its parent's kind ("Классика мирового кинематографа" under
    "Зарубежное кино" is a foreign film section) unless its own name excludes it; only the
    film and series groups count as video."""

    def __init__(self, forums: list) -> None:  # list[rutracker.parse.Forum]
        by_id = {f.forum_id: f for f in forums}
        self.sections: dict[int, Section] = {}
        for f in forums:
            self.sections[f.forum_id] = self._classify(f, by_id)

    @staticmethod
    def _classify(f, by_id) -> Section:  # type: ignore[no-untyped-def]
        if not any(g in f.group.lower() for g in VIDEO_GROUPS):
            return EXCLUDED
        n = f.name.lower()
        if is_excluded(f.name) or any(x in n for x in _EXCLUDED_EXTRA):
            return EXCLUDED
        own = classify(f.name)
        parent = by_id.get(f.parent_id) if f.parent_id else None
        inherited = classify(parent.name) if parent else EXCLUDED
        if not own.video:
            return inherited
        if inherited.video and inherited.origin == "russian" and own.origin == "foreign":
            return Section(own.kind, "russian", True)  # "Кино СССР" under "Наше кино"
        return own

    def video_ids(self) -> list[int]:
        return sorted(fid for fid, s in self.sections.items() if s.video)

    def section(self, forum_id: int | None, name: str) -> Section:
        if forum_id is not None and forum_id in self.sections:
            return self.sections[forum_id]
        return classify(name)
