"""The community anime ID list (Fribb/anime-lists): MAL (= Shikimori) ids ↔ TVDB (with season
and episode offset), TMDb and IMDb ids. Downloaded daily, kept compact in the data directory."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)
LIST_URL = "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-full.json"
MAX_AGE = 24 * 3600


@dataclass(frozen=True)
class AnimeEntry:
    mal_id: int
    kind: str
    tvdb_id: int | None = None
    tvdb_season: int | None = None
    tvdb_offset: int = 0  # TVDB episode = entry episode + offset (split cours)
    tmdb_tv: int | None = None
    tmdb_movie: int | None = None
    imdb: tuple[str, ...] = ()


def compact(raw: list[dict]) -> list[dict]:
    """Keep what links MAL to TVDB/TMDb/IMDb (the full list is ~7.5 MB)."""
    out = []
    for e in raw:
        tmdb = e.get("themoviedb_id") or {}
        if not e.get("mal_id") or not (e.get("tvdb_id") or tmdb or e.get("imdb_id")):
            continue
        out.append(
            {
                "mal": e["mal_id"],
                "kind": e.get("type") or "",
                "tvdb": e.get("tvdb_id"),
                "season": (e.get("season") or {}).get("tvdb"),
                "offset": (e.get("episode_offset") or {}).get("tvdb") or 0,
                "tmdb_tv": tmdb.get("tv") if isinstance(tmdb, dict) else None,
                "tmdb_movie": tmdb.get("movie") if isinstance(tmdb, dict) else None,
                "imdb": [i for i in (e.get("imdb_id") or []) if i],
            }
        )
    return out


class AnimeList:
    def __init__(
        self,
        path: Path,
        transport: httpx.AsyncBaseTransport | None = None,
        url: str = LIST_URL,
        user_agent: str = "RuTrackarr",
    ) -> None:
        self._path, self._transport, self._url, self._ua = path, transport, url, user_agent
        self._lock = asyncio.Lock()
        self._loaded_at = 0.0
        self._by_tvdb: dict[int, list[AnimeEntry]] = {}
        self._by_tmdb_tv: dict[int, list[AnimeEntry]] = {}
        self._by_imdb: dict[str, list[AnimeEntry]] = {}
        self._by_mal: dict[int, AnimeEntry] = {}

    async def ensure(self) -> None:
        """Load the list; download it when missing or older than a day. Failures keep the
        previous copy (or none) — lookups then just find nothing."""
        if time.time() - self._loaded_at < MAX_AGE and self._by_mal:
            return
        async with self._lock:
            if time.time() - self._loaded_at < MAX_AGE and self._by_mal:
                return
            fresh = self._path.exists() and time.time() - self._path.stat().st_mtime < MAX_AGE
            if not fresh:
                try:
                    async with httpx.AsyncClient(
                        timeout=60, transport=self._transport, headers={"User-Agent": self._ua}
                    ) as c:
                        r = await c.get(self._url)
                        r.raise_for_status()
                    self._path.write_text(json.dumps(compact(r.json())), encoding="utf-8")
                except (httpx.HTTPError, ValueError, OSError) as e:
                    log.warning("anime ID list download failed: %s", e)
            if self._path.exists():
                self._index(json.loads(self._path.read_text(encoding="utf-8")))
            self._loaded_at = time.time()

    def _index(self, rows: list[dict]) -> None:
        by_tvdb: dict[int, list[AnimeEntry]] = {}
        by_tmdb: dict[int, list[AnimeEntry]] = {}
        by_imdb: dict[str, list[AnimeEntry]] = {}
        by_mal: dict[int, AnimeEntry] = {}
        for r in rows:
            e = AnimeEntry(
                r["mal"], r["kind"], r["tvdb"], r["season"], r["offset"] or 0,
                r["tmdb_tv"], r["tmdb_movie"], tuple(r["imdb"]),
            )  # fmt: skip
            by_mal[e.mal_id] = e
            if e.tvdb_id:
                by_tvdb.setdefault(e.tvdb_id, []).append(e)
            if e.tmdb_tv:
                by_tmdb.setdefault(e.tmdb_tv, []).append(e)
            for i in e.imdb:
                by_imdb.setdefault(i, []).append(e)
        self._by_tvdb, self._by_tmdb_tv, self._by_imdb, self._by_mal = (
            by_tvdb,
            by_tmdb,
            by_imdb,
            by_mal,
        )

    def by_tvdb(self, tvdb_id: int) -> list[AnimeEntry]:
        return self._by_tvdb.get(tvdb_id, [])

    def by_tmdb_tv(self, tmdb_id: int) -> list[AnimeEntry]:
        return self._by_tmdb_tv.get(tmdb_id, [])

    def by_imdb(self, imdb_id: str) -> list[AnimeEntry]:
        return self._by_imdb.get(imdb_id, [])
