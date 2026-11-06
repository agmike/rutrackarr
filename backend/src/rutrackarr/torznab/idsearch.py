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
from rutrackarr.metadata.sonarr import SonarrTitles
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
    tvdb_id: int
    title: str  # Sonarr's title (what releases are named after)
    entries: list[Entry]
    other_names: set[str]  # normalised Sonarr title + alternate titles
    queries: list[str]


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


class Resolver:
    def __init__(self, animelist: AnimeList, shikimori: Shikimori, sonarr: SonarrTitles) -> None:
        self._list, self._shiki, self._sonarr = animelist, shikimori, sonarr

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
        title = series.title if series else (entries[0].romaji if entries else "")
        if not title:
            return None
        other = {norm(n) for n in ([series.title, *series.alternate_titles] if series else [])}
        queries: list[str] = []
        for entry in entries:
            if season is not None and entry.season != season:
                continue
            queries += [entry.russian, entry.romaji]
        queries += [series.title] if series else []
        seen: set[str] = set()
        unique = []
        for q in queries:
            if q and norm(q) not in seen:
                seen.add(norm(q))
                unique.append(q)
        return SeriesContext(tvdb_id, title, entries, {o for o in other if o}, unique[:MAX_QUERIES])


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
