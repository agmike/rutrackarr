"""From a Torznab request to ranked, renamed releases."""

import asyncio
import math
import re
import time
from dataclasses import dataclass, field

from rutrackarr.releases.language import LanguageVerdict, assess
from rutrackarr.releases.naming import categories, is_absolute, is_movie, release_name
from rutrackarr.releases.sections import Section, classify
from rutrackarr.releases.title import ParsedTitle, parse_title
from rutrackarr.rutracker.client import RuTrackerClient
from rutrackarr.rutracker.parse import SearchRow

CACHE_TTL = 600  # seconds; Sonarr repeats the same query per alias/episode
_WORD = re.compile(r"[^\W_]+")


@dataclass
class Request:
    kind: str  # "search" | "tvsearch" | "movie"
    q: str = ""
    season: int | None = None
    ep: int | None = None
    absolute: int | None = None  # anime absolute episode, from the end of a t=search query
    cats: list[int] = field(default_factory=list)


@dataclass
class Release:
    row: SearchRow
    title: ParsedTitle
    section: Section
    language: LanguageVerdict
    name: str
    categories: list[int]


def absolute_episode(q: str) -> tuple[str, int | None]:
    """Sonarr's anime searches (t=search) append the absolute episode: "Sousou no Frieren 01",
    "One Piece 1156". Without stripping it every episode would be a separate RuTracker search.
    Only numbers of two or more digits — "Taxi 4" stays as it is."""
    if m := re.search(r"\s(\d{2,4})\s*$", q):
        return q[: m.start()].strip(), int(m.group(1))
    return q, None


def clean_query(q: str) -> tuple[str, int | None]:
    """Strip what Sonarr/Radarr append to titles: S01E05, "Season 2", a trailing year."""
    q = re.sub(r"\bS\d{1,2}(?:E\d{1,4})?\b", " ", q, flags=re.I)
    q = re.sub(r"\bseason\s*\d+\b", " ", q, flags=re.I)
    year = None
    if m := re.search(r"\(?\b((?:19|20)\d{2})\)?\s*$", q):
        year, q = int(m.group(1)), q[: m.start()]
    return " ".join(q.split()), year


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text.replace("'", "").replace("’", "")) if len(w) > 1}


def matches_query(t: ParsedTitle, q: str) -> bool:
    """At least 60% of the query's words appear in one of the release's names."""
    wanted = _words(q)
    if not wanted:
        return True
    need = math.ceil(len(wanted) * 0.6)
    return any(len(wanted & _words(n)) >= need for n in t.names)


class SearchCache:
    def __init__(self, client: RuTrackerClient, ttl: int = CACHE_TTL) -> None:
        self._client, self._ttl = client, ttl
        self._data: dict[str, tuple[float, list[SearchRow]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def search(self, q: str) -> list[SearchRow]:
        key = " ".join(q.lower().split())
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:  # concurrent identical queries share one RuTracker request
            hit = self._data.get(key)
            if hit and time.monotonic() - hit[0] < self._ttl:
                return hit[1]
            rows = await self._client.search(q)
            self._data[key] = (time.monotonic(), rows)
            return rows


def _wanted(req: Request, rel: Release, year: int | None) -> bool:
    if not rel.section.video:
        return False
    movie = is_movie(rel.section, rel.title)
    if (req.kind == "tvsearch" and movie) or (req.kind == "movie" and not movie):
        return False
    if req.cats and not set(req.cats) & set(rel.categories):
        return False
    t = rel.title
    if req.season is not None and not movie:
        season = t.season if t.season is not None else (None if is_absolute(t, rel.section) else 1)
        last = t.season_last or season
        if season is not None and not (season <= req.season <= last):
            return False
    e = t.episodes
    unchecked = e is None or e.complete or e.first is None or e.last is None
    if req.ep is not None and not unchecked and not (e.first <= req.ep <= e.last):  # type: ignore[union-attr,operator]
        return False
    absolute = req.absolute is not None and is_absolute(t, rel.section) and not unchecked
    if absolute and not (e.first <= req.absolute <= e.last):  # type: ignore[union-attr,operator]
        return False
    return not (year and movie and t.year and abs(t.year - year) > 1)


def build(row: SearchRow, query: str | None) -> Release:
    section = classify(row.forum)
    title = parse_title(row.title)
    language = assess(title, section)
    return Release(
        row,
        title,
        section,
        language,
        release_name(title, section, language, query),
        categories(section, title),
    )


async def run(cache: SearchCache, req: Request) -> list[Release]:
    q, year = clean_query(req.q)
    if req.kind == "search" and req.absolute is None:
        q, req.absolute = absolute_episode(q)
    rows = await cache.search(q)
    releases = [build(r, q) for r in rows]
    if q:
        releases = [r for r in releases if matches_query(r.title, q)]
        words = q.split()
        if not any(r.section.video for r in releases) and len(words) > 2:
            # RuTracker's search is literal about words ("Journeys" vs "Journey's"): retry wider.
            rows = await cache.search(" ".join(words[:2]))
            releases = [r for r in (build(row, q) for row in rows) if matches_query(r.title, q)]
    return [r for r in releases if _wanted(req, r, year)]
