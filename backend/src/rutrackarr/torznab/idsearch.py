"""ID searches: a TVDB id → the names to search RuTracker for and the season each topic is.

Anime: the anime ID list maps the TVDB id to MyAnimeList entries (= Shikimori ids), each with
its TVDB season and episode offset. Shikimori gives every name of each entry (Russian, romaji,
English, synonyms, Japanese) — the names RuTracker titles use. A topic belongs to the entry
whose names it shares; that entry's TVDB season is the topic's season, whatever the topic
title says (or doesn't). Releases are named after Sonarr's own title of the series.

Not anime (or not in the list): Sonarr's title and alternate titles are searched and matched.
"""

import re
from dataclasses import dataclass, field

from rutrackarr.metadata.animelist import AnimeEntry, AnimeList
from rutrackarr.metadata.shikimori import Shikimori
from rutrackarr.metadata.sonarr import RadarrTitles, SonarrTitles
from rutrackarr.metadata.tmdb import Tmdb, TmdbTitle
from rutrackarr.releases.title import ParsedTitle

MAX_QUERIES = 4
MAX_ENTRIES = 12  # Shikimori lookups per series (each cached for a week)
_WORD = re.compile(r"[^\W_]+")


def norm(name: str) -> str:
    """Words only, lower case, apostrophes dropped: "Frieren: Beyond Journey's End" →
    "frieren beyond journeys end"."""
    name = name.replace("'", "").replace("’", "").replace("ё", "е").replace("Ё", "Е")
    return " ".join(w.casefold() for w in _WORD.findall(name))


def _head(name: str) -> str:
    """The part before a subtitle (":" or " - "), normalised."""
    return norm(re.split(r"\s*:\s*|\s+-\s+", name, maxsplit=1)[0])


@dataclass
class Entry:
    """One anime entry (≈ one season / film / OVA) with its names."""

    mal_id: int
    season: int | None
    offset: int
    russian: str
    romaji: str
    names: set[str] = field(default_factory=set)  # normalised
    heads: set[str] = field(default_factory=set)  # normalised, before a subtitle


@dataclass
class SeriesContext:
    tvdb_id: int | None
    title: str  # Sonarr's/Radarr's title (what releases are named after)
    entries: list[Entry]  # anime entries (seasons); empty for other series and films
    other_names: set[str]  # normalised Sonarr/Radarr/TMDb titles
    queries: list[str]
    kind: str = "tv"  # "tv" | "movie"
    original_language: str | None = None  # ISO 639-2, from TMDb
    season_years: dict[int, int] = field(default_factory=dict)  # season → air year (TMDb)
    year: int | None = None  # the film's year (Radarr/TMDb)
    tmdb_id: int | None = None
    imdb_id: str | None = None


@dataclass(frozen=True)
class Match:
    season: int | None
    offset: int
    mal_id: int | None


def _entry(e: AnimeEntry, names: list[str], russian: str, romaji: str) -> Entry:
    return Entry(
        e.mal_id,
        e.tvdb_season,
        e.tvdb_offset,
        russian,
        romaji,
        {n for n in map(norm, names) if n},
        {h for h in map(_head, names) if h},
    )


def _unique(queries: list[str | None]) -> list[str]:
    seen: set[str] = set()
    out = []
    for q in queries:
        if q and norm(q) and norm(q) not in seen:
            seen.add(norm(q))
            out.append(q)
    return out[:MAX_QUERIES]


class Resolver:
    def __init__(
        self,
        animelist: AnimeList,
        shikimori: Shikimori,
        sonarr: SonarrTitles,
        tmdb: Tmdb | None = None,
        radarr: RadarrTitles | None = None,
    ) -> None:
        self._list, self._shiki, self._sonarr = animelist, shikimori, sonarr
        self._tmdb, self._radarr = tmdb, radarr

    async def tv(self, tvdb_id: int, season: int | None) -> SeriesContext | None:
        series = await self._sonarr.by_tvdb(tvdb_id)
        await self._list.ensure()
        mapped = [e for e in self._list.by_tvdb(tvdb_id) if e.tvdb_season is not None]
        # The entries of the wanted season first (and the series' TV entries when no season).
        wanted = [e for e in mapped if season is None or e.tvdb_season == season]
        others = [e for e in mapped if e not in wanted and e.tvdb_season not in (None, 0)]
        entries: list[Entry] = []
        for e in [*wanted, *others][:MAX_ENTRIES]:
            names = await self._shiki.anime(e.mal_id)
            if names:
                entries.append(_entry(e, names.names, names.russian, names.romaji))
        other = {norm(n) for n in ([series.title, *series.alternate_titles] if series else [])}
        if not entries:  # not anime (or not in the list): TMDb's Russian and original titles
            return await self._tv_tmdb(tvdb_id, series, other)
        title = series.title if series else entries[0].romaji
        queries: list[str | None] = []
        for entry in entries:
            if season is not None and entry.season != season:
                continue
            queries += [entry.russian, entry.romaji]
        queries += [series.title] if series else []
        return SeriesContext(tvdb_id, title, entries, {o for o in other if o}, _unique(queries))

    async def _tv_tmdb(self, tvdb_id: int, series, other: set[str]) -> SeriesContext | None:  # type: ignore[no-untyped-def]
        tm = await self._tmdb.tv_by_tvdb(tvdb_id) if self._tmdb else None
        title = series.title if series else (tm.english or tm.original if tm else "")
        if not title:
            return None
        names = {norm(n) for n in (tm.names if tm else [])} | other
        queries = [*([tm.russian, tm.original] if tm else []), series.title if series else None]
        return SeriesContext(
            tvdb_id, title, [], {n for n in names if n}, _unique(queries),
            original_language=tm.original_language if tm else None,
            season_years=tm.season_years if tm else {},
            tmdb_id=tm.tmdb_id if tm else None,
        )  # fmt: skip

    async def movie(self, tmdb_id: int | None, imdb_id: str | None) -> SeriesContext | None:
        if self._tmdb is None:
            return None
        tm: TmdbTitle | None = None
        if tmdb_id:
            tm = await self._tmdb.details("movie", tmdb_id)
        elif imdb_id:
            tm = await self._tmdb.movie_by_imdb(imdb_id)
        if tm is None:
            return None
        radarr = await self._radarr.by_tmdb(tm.tmdb_id) if self._radarr else None
        title = radarr.title if radarr else (tm.english or tm.original)
        names = [
            *tm.names,
            *([radarr.title, radarr.original_title, *radarr.alternate_titles] if radarr else []),
        ]
        return SeriesContext(
            None, title, [], {n for n in map(norm, names) if n},
            _unique([tm.russian, tm.original, title]),
            kind="movie", original_language=tm.original_language,
            year=(radarr.year if radarr and radarr.year else tm.year),
            tmdb_id=tm.tmdb_id, imdb_id=tm.imdb_id or imdb_id,
        )  # fmt: skip


def match(ctx: SeriesContext, t: ParsedTitle) -> Match | None:
    """Which entry (season) of the series a topic is, or None when it isn't this series.

    Entries are ranked by: how many of the topic's names equal one of the entry's names; then
    whether the topic states that entry's season; then how many names only share the part
    before a subtitle ("Kyouran Reijou Nia Liston: <long subtitle>" — at least two words, so a
    bare "Frieren" doesn't count).
    """
    names = [n for n in t.names if n]
    best: tuple[tuple[int, int, int], Entry] | None = None
    for entry in ctx.entries:
        exact = sum(1 for n in names if norm(n) in entry.names)
        heads = sum(1 for n in names if norm(n) not in entry.names and _shares_head(n, entry))
        if not (exact or heads):
            continue
        stated = 1 if t.season is not None and t.season == entry.season else 0
        rank = (exact, stated, heads)
        if best is None or rank > best[0]:
            best = (rank, entry)
    if best:
        e = best[1]
        return Match(e.season, e.offset, e.mal_id)
    if any(norm(n) in ctx.other_names or _head(n) in ctx.other_names for n in names):
        return Match(None, 0, None)  # this series, season from the title as usual
    return None


def _shares_head(name: str, entry: Entry) -> bool:
    candidates = {_head(name), norm(name)} & (entry.heads | entry.names)
    return any(len(c.split()) >= 2 for c in candidates)
