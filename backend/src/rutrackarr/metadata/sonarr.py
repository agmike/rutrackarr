"""Series titles from Sonarr (the optional connection): the exact title Sonarr matches
releases against, its alternate titles, year and type."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

log = logging.getLogger(__name__)
TTL = 3600


@dataclass(frozen=True)
class SonarrSeries:
    tvdb_id: int
    title: str
    year: int | None
    series_type: str  # standard | daily | anime
    alternate_titles: list[str] = field(default_factory=list)


class SonarrTitles:
    def __init__(
        self,
        url: Callable[[], str | None],
        api_key: Callable[[], str | None],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url, self._key, self._transport = url, api_key, transport
        self._cache: dict[int, tuple[float, SonarrSeries | None]] = {}

    async def by_tvdb(self, tvdb_id: int) -> SonarrSeries | None:
        hit = self._cache.get(tvdb_id)
        if hit and time.monotonic() - hit[0] < TTL:
            return hit[1]
        url, key = (self._url() or "").rstrip("/"), self._key()
        if not url or not key:
            return None
        try:
            async with httpx.AsyncClient(
                timeout=15, transport=self._transport, headers={"X-Api-Key": str(key)}
            ) as c:
                r = await c.get(f"{url}/api/v3/series", params={"tvdbId": tvdb_id})
                items = r.json() if r.status_code == 200 else []
                if not items:  # not in the library (e.g. a search from "add series")
                    r = await c.get(
                        f"{url}/api/v3/series/lookup", params={"term": f"tvdb:{tvdb_id}"}
                    )
                    items = r.json() if r.status_code == 200 else []
        except (httpx.HTTPError, ValueError) as e:
            log.warning("sonarr lookup tvdb:%s: %s", tvdb_id, e)
            return None
        s = items[0] if items else None
        series = (
            SonarrSeries(
                tvdb_id=tvdb_id,
                title=s.get("title") or "",
                year=s.get("year") or None,
                series_type=s.get("seriesType") or "standard",
                alternate_titles=[
                    a["title"] for a in s.get("alternateTitles") or [] if a.get("title")
                ],
            )
            if s
            else None
        )
        self._cache[tvdb_id] = (time.monotonic(), series)
        return series


@dataclass(frozen=True)
class RadarrMovie:
    tmdb_id: int
    title: str
    year: int | None
    original_title: str = ""
    alternate_titles: list[str] = field(default_factory=list)


class RadarrTitles:
    """Movie titles from Radarr (the optional connection), by TMDb id."""

    def __init__(
        self,
        url: Callable[[], str | None],
        api_key: Callable[[], str | None],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url, self._key, self._transport = url, api_key, transport
        self._cache: dict[int, tuple[float, RadarrMovie | None]] = {}

    async def by_tmdb(self, tmdb_id: int) -> RadarrMovie | None:
        hit = self._cache.get(tmdb_id)
        if hit and time.monotonic() - hit[0] < TTL:
            return hit[1]
        url, key = (self._url() or "").rstrip("/"), self._key()
        if not url or not key:
            return None
        try:
            async with httpx.AsyncClient(
                timeout=15, transport=self._transport, headers={"X-Api-Key": str(key)}
            ) as c:
                r = await c.get(f"{url}/api/v3/movie", params={"tmdbId": tmdb_id})
                items = r.json() if r.status_code == 200 else []
                if not items:
                    r = await c.get(f"{url}/api/v3/movie/lookup/tmdb", params={"tmdbId": tmdb_id})
                    items = [r.json()] if r.status_code == 200 and r.json() else []
        except (httpx.HTTPError, ValueError) as e:
            log.warning("radarr lookup tmdb:%s: %s", tmdb_id, e)
            return None
        m = items[0] if items else None
        movie = (
            RadarrMovie(
                tmdb_id=tmdb_id,
                title=m.get("title") or "",
                year=m.get("year") or None,
                original_title=m.get("originalTitle") or "",
                alternate_titles=[
                    a["title"] for a in m.get("alternateTitles") or [] if a.get("title")
                ],
            )
            if m
            else None
        )
        self._cache[tmdb_id] = (time.monotonic(), movie)
        return movie
