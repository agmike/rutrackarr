"""From a Torznab request to ranked, renamed releases."""

import asyncio
import functools
import json
import logging
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rutrackarr.releases.language import LanguageVerdict, assess
from rutrackarr.releases.naming import categories, is_absolute, is_movie, release_name
from rutrackarr.releases.sections import Catalogue, Section
from rutrackarr.releases.title import ParsedTitle, parse_title
from rutrackarr.rutracker.client import RuTrackerClient
from rutrackarr.rutracker.parse import Forum, SearchRow
from rutrackarr.torznab.idsearch import Match, Resolver, SeriesContext, match, with_override

_WORD = re.compile(r"[^\W_]+")
CATALOGUE_TTL = 7 * 24 * 3600
log = logging.getLogger(__name__)


@dataclass
class Request:
    kind: str  # "search" | "tvsearch" | "movie"
    q: str = ""
    season: int | None = None
    ep: int | None = None
    absolute: int | None = None  # anime absolute episode, from the end of a t=search query
    cats: list[int] = field(default_factory=list)
    tvdbid: int | None = None
    tmdbid: int | None = None
    imdbid: str | None = None


@dataclass
class Release:
    row: SearchRow
    title: ParsedTitle
    section: Section
    language: LanguageVerdict
    name: str
    categories: list[int]
    season: int | None = None  # from metadata (ID search), wins over the title
    tvdbid: int | None = None
    tmdbid: int | None = None
    imdbid: str | None = None


@dataclass
class Trace:
    """How a search went, for the sandbox and the query log: the context it resolved to, the
    RuTracker searches it made, and every topic seen with its release name or why it was
    dropped."""

    context: dict | None = None
    searches: list[dict] = field(default_factory=list)  # {query, results, cached}
    rows: dict[int, dict] = field(default_factory=dict)  # topic id → {..., release, reason}

    def seen(self, row: SearchRow, release: "Release | None", reason: str | None) -> None:
        entry = self.rows.setdefault(
            row.topic_id,
            {
                "topic_id": row.topic_id, "title": row.title, "forum": row.forum,
                "size": row.size, "seeders": row.seeders, "release": None, "reason": None,
            },
        )  # fmt: skip
        if release is not None and reason is None:
            entry["release"], entry["reason"] = release.name, None
        elif entry["release"] is None:
            entry["reason"] = reason


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
    """RuTracker results per query. Text searches live long (a season search repeats each query
    for every episode and title, over 10+ minutes); the no-query RSS feed lives short so new
    topics show up quickly. TTLs are read on every lookup, so settings apply immediately."""

    def __init__(
        self,
        client: RuTrackerClient,
        ttl: Callable[[], float] = lambda: 3600,
        rss_ttl: Callable[[], float] = lambda: 300,
        catalogue_path: Path | None = None,
    ) -> None:
        self._client, self._ttl, self._rss_ttl = client, ttl, rss_ttl
        self._data: dict[str, tuple[float, list[SearchRow]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._catalogue_path = catalogue_path
        self.catalogue: Catalogue | None = None
        self._catalogue_at = 0.0
        if catalogue_path and catalogue_path.exists():
            try:
                forums = [Forum(*f) for f in json.loads(catalogue_path.read_text(encoding="utf-8"))]
                self.catalogue = Catalogue(forums)
                self._catalogue_at = catalogue_path.stat().st_mtime
            except (ValueError, TypeError, OSError) as e:
                log.warning("section catalogue unreadable: %s", e)

    def catalogue_info(self) -> tuple[float | None, int]:
        """(updated at, as a timestamp; video sections known)."""
        if self.catalogue is None:
            return None, 0
        return (self._catalogue_at or None), len(self.catalogue.video_ids())

    def _update_catalogue(self) -> None:
        """Rebuild the section catalogue from the last search page, at most once a week."""
        forums = self._client.last_forums
        if not forums or time.time() - self._catalogue_at < CATALOGUE_TTL:
            return
        self.catalogue = Catalogue(forums)
        self._catalogue_at = time.time()
        if self._catalogue_path:
            try:
                rows = [[f.forum_id, f.name, f.parent_id, f.group] for f in forums]
                self._catalogue_path.write_text(
                    json.dumps(rows, ensure_ascii=False), encoding="utf-8"
                )
            except OSError as e:
                log.warning("section catalogue not saved: %s", e)

    async def search(self, q: str) -> list[SearchRow]:
        return (await self.search_ex(q))[0]

    async def search_ex(self, q: str, fresh: bool = False) -> tuple[list[SearchRow], bool]:
        """(rows, answered from cache); `fresh` asks RuTracker even when cached."""
        key = " ".join(q.lower().split())
        ttl = self._ttl() if key else self._rss_ttl()
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:  # concurrent identical queries share one RuTracker request
            now = time.monotonic()
            keep = max(self._ttl(), self._rss_ttl())  # drop entries no lookup can use any more
            self._data = {k: v for k, v in self._data.items() if now - v[0] < keep}
            hit = self._data.get(key)
            if hit and now - hit[0] < ttl and not fresh:
                return hit[1], True
            # Video sections only: a common word ("Шерлок") otherwise fills the single result
            # page with audiobooks and books, and the series never shows up.
            forums = self.catalogue.video_ids() if self.catalogue else None
            rows = await self._client.search(q, forums or None)
            self._update_catalogue()
            self._data[key] = (time.monotonic(), rows)
            return rows, False

    def find(self, topic_id: int) -> SearchRow | None:
        """A topic from recent search results (Sonarr grabs what it was just shown)."""
        for _, rows in self._data.values():
            for row in rows:
                if row.topic_id == topic_id:
                    return row
        return None


def _wanted(req: Request, rel: Release, year: int | None) -> bool:
    return _reject(req, rel, year) is None


def _reject(req: Request, rel: Release, year: int | None) -> str | None:
    """None when Sonarr/Radarr asked for this release, else why not."""
    if not rel.section.video:
        return f"not a video section ({rel.section.kind or rel.row.forum})"
    movie = is_movie(rel.section, rel.title)
    if req.kind == "tvsearch" and movie:
        return "a film, Sonarr asked for a series"
    if req.kind == "movie" and not movie:
        return "a series, Radarr asked for a film"
    if req.cats and not set(req.cats) & set(rel.categories):
        return "not in the categories asked for"
    t = rel.title
    if req.season is not None and not movie:
        if rel.season is not None:
            season = last = rel.season
        else:
            season = (
                t.season if t.season is not None else (None if is_absolute(t, rel.section) else 1)
            )
            last = t.season_last or season
        if season is not None and not (season <= req.season <= last):
            span = f"S{season}" if season == last else f"S{season}-S{last}"
            return f"season {req.season} asked for, topic is {span}"
    e = t.episodes
    # Absolute-numbered anime (One Piece 1156-1180) can't be compared with Sonarr's per-season
    # episode numbers; Sonarr maps the absolute numbers itself.
    unchecked = (
        e is None or e.complete or e.first is None or e.last is None
        or (req.absolute is None and is_absolute(t, rel.section))
    )  # fmt: skip
    if req.ep is not None and not unchecked and not (e.first <= req.ep <= e.last):  # type: ignore[union-attr,operator]
        return f"episode {req.ep} asked for, topic has {e.first}-{e.last}"  # type: ignore[union-attr]
    absolute = req.absolute is not None and is_absolute(t, rel.section) and not unchecked
    if absolute and not (e.first <= req.absolute <= e.last):  # type: ignore[union-attr,operator]
        return f"episode {req.absolute} asked for, topic has {e.first}-{e.last}"  # type: ignore[union-attr]
    if year and movie and t.year and abs(t.year - year) > 1:
        return f"year {t.year}, asked for {year}"
    return None


@functools.lru_cache(maxsize=4096)
def _analyse(title_text: str, section: Section) -> tuple[ParsedTitle, Section, LanguageVerdict]:
    """Parse once per title: Sonarr asks for the same results dozens of times per search.
    The returned objects are shared and must not be modified."""
    title = parse_title(title_text)
    return title, section, assess(title, section)


def section_of(row: SearchRow, catalogue: Catalogue | None) -> Section:
    return (
        catalogue.section(row.forum_id, row.forum)
        if catalogue
        else Catalogue([]).section(None, row.forum)
    )


def build(
    row: SearchRow,
    query: str | None,
    ctx: SeriesContext | None = None,
    catalogue: Catalogue | None = None,
) -> Release | None:
    """A release for Sonarr/Radarr. With an ID search context, topics that aren't the series or
    film are dropped (None); season, episode offset, year, original language and name come
    from the metadata."""
    return _build(row, query, ctx, catalogue)[0]


def _build(
    row: SearchRow,
    query: str | None,
    ctx: SeriesContext | None = None,
    catalogue: Catalogue | None = None,
) -> tuple[Release | None, str | None]:
    """build() with the reason a topic was dropped."""
    title, section, language = _analyse(row.title, section_of(row, catalogue))
    if ctx is None:
        name = release_name(title, section, language, query)
        return Release(row, title, section, language, name, categories(section, title)), None
    ov = ctx.override
    if ov is not None and (why := ov.allows(row.title)):
        return None, why
    pin = ov.pin(row.topic_id) if ov is not None else None
    m = Match(pin.season, 0, None) if pin else match(ctx, title)
    if m is None:
        if not any(n for n in title.names):
            return None, "unparsed: no names found in the title"
        return None, f"not {ctx.title} (names don't match)"
    movie = ctx.kind == "movie"
    if movie and ctx.year and title.year and abs(title.year - ctx.year) > 1:
        return None, f"a different film: {title.year}, not {ctx.year}"  # remakes
    season = None if movie or is_absolute(title, section) else m.season
    if (
        season is None
        and not pin
        and not movie
        and ov is not None
        and ov.season_offset
        and title.season is not None
    ):
        season = title.season + ov.season_offset  # fmt: skip
    if season is None and not movie and title.season is None and title.year and ctx.season_years:
        # A topic without a season number: the season that aired that year.
        season = next((n for n, y in sorted(ctx.season_years.items()) if y == title.year), None)
    name = release_name(
        title, section, language, query,
        series_title=ctx.title, season=season, offset=m.offset,
        year=ctx.year if movie else None, original_language=ctx.original_language,
    )  # fmt: skip
    return Release(
        row, title, section, language, name, categories(section, title),
        season, ctx.tvdb_id, ctx.tmdb_id if movie else None, ctx.imdb_id if movie else None,
    ), None  # fmt: skip


async def run(
    cache: SearchCache,
    req: Request,
    resolver: Resolver | None = None,
    overrides: "Callable[[str, int | None], object] | None" = None,
    trace: Trace | None = None,
    fresh: bool = False,
) -> list[Release]:
    """`overrides(kind, id)` → the series/film override (or None); `trace` collects how the
    search went; `fresh` bypasses the RuTracker result cache."""
    trace = trace if trace is not None else Trace()
    ctx = None
    if resolver is not None and req.kind != "movie" and req.tvdbid:
        ctx = await resolver.tv(req.tvdbid, req.season)
        ov = overrides("tv", req.tvdbid) if overrides and ctx else None
        ctx = with_override(ctx, ov) if ctx is not None and ov is not None else ctx
    elif resolver is not None and req.kind == "movie" and (req.tmdbid or req.imdbid):
        ctx = await resolver.movie(req.tmdbid, req.imdbid)
        ov = overrides("movie", ctx.tmdb_id) if overrides and ctx else None
        ctx = with_override(ctx, ov) if ctx is not None and ov is not None else ctx
    if ctx is not None:
        trace.context = _describe(ctx)
        return await _run_ids(cache, req, ctx, trace, fresh)
    if (req.tvdbid or req.tmdbid or req.imdbid) and not req.q:
        trace.context = {"error": "nothing known about this id, and no title to search for"}
        return []  # nothing known about this id and no title to fall back on
    q, year = clean_query(req.q)
    if req.kind == "search" and req.absolute is None:
        q, req.absolute = absolute_episode(q)

    async def search(text: str) -> list[Release]:
        rows, cached = await cache.search_ex(text, fresh)
        trace.searches.append({"query": text, "results": len(rows), "cached": cached})
        out = []
        for row in rows:
            rel, _ = _build(row, q, None, cache.catalogue)
            if rel is not None and q and not matches_query(rel.title, q):
                trace.seen(row, None, f"names don't match the query {q!r}")
                continue
            if rel is not None:
                out.append(rel)
        return out

    releases = await search(q)
    words = q.split()
    if q and not any(r.section.video for r in releases) and len(words) > 2:
        # RuTracker's search is literal about words ("Journeys" vs "Journey's"): retry wider.
        releases = await search(" ".join(words[:2]))
    return _keep(req, releases, year, trace)


def _keep(req: Request, releases: list[Release], year: int | None, trace: Trace) -> list[Release]:
    out = []
    for rel in releases:
        why = _reject(req, rel, year)
        trace.seen(rel.row, rel, why)
        if why is None:
            out.append(rel)
    return out


def _describe(ctx: SeriesContext) -> dict:
    ov = ctx.override
    return {
        "kind": ctx.kind, "title": ctx.title, "queries": ctx.queries,
        "tvdb_id": ctx.tvdb_id, "tmdb_id": ctx.tmdb_id, "imdb_id": ctx.imdb_id,
        "year": ctx.year, "original_language": ctx.original_language,
        "seasons": [
            {"season": e.season, "offset": e.offset, "names": [e.russian, e.romaji]}
            for e in ctx.entries
        ],
        "override": ov.to_json() if ov is not None else None,
    }  # fmt: skip


async def _run_ids(
    cache: SearchCache,
    req: Request,
    ctx: SeriesContext,
    trace: Trace | None = None,
    fresh: bool = False,
) -> list[Release]:
    """One RuTracker search per name of the series (cached), merged by topic."""
    trace = trace if trace is not None else Trace()
    rows: dict[int, SearchRow] = {}
    for q in ctx.queries:
        found, cached = await cache.search_ex(q, fresh)
        trace.searches.append({"query": q, "results": len(found), "cached": cached})
        for row in found:
            rows.setdefault(row.topic_id, row)
    releases = []
    for row in rows.values():
        rel, why = _build(row, None, ctx, cache.catalogue)
        if rel is None:
            trace.seen(row, None, why)
        else:
            releases.append(rel)
    return _keep(req, releases, None, trace)
