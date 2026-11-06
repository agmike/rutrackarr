"""Shikimori (shikimori.io): Russian, romaji, English, Japanese names and synonyms per anime
entry. Ids are MyAnimeList's. Entries are cached for a week; requests are spaced well below
the API's limits (5/s, 90/min)."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta

import httpx

from rutrackarr.metadata.cache import MetadataCache

log = logging.getLogger(__name__)
BASE_URL = "https://shikimori.io"
TTL = timedelta(days=7)
SPACING = 1.0  # seconds between requests


@dataclass(frozen=True)
class AnimeNames:
    mal_id: int
    romaji: str
    russian: str
    kind: str
    year: int | None
    episodes: int | None
    names: list[str] = field(default_factory=list)  # every name, for matching


def _names(d: dict) -> list[str]:
    out: list[str] = []
    for v in (d.get("russian"), d.get("name"), d.get("license_name_ru"), *(d.get("english") or []),
              *(d.get("synonyms") or []), *(d.get("japanese") or [])):  # fmt: skip
        if isinstance(v, str) and v.strip() and v.strip() not in out:
            out.append(v.strip())
    return out


class Shikimori:
    def __init__(
        self,
        cache: MetadataCache,
        transport: httpx.AsyncBaseTransport | None = None,
        user_agent: str = "RuTrackarr",
        base_url: str = BASE_URL,
        spacing: float = SPACING,
    ) -> None:
        self._cache, self._transport, self._ua, self._base = cache, transport, user_agent, base_url
        self._spacing, self._lock, self._last = spacing, asyncio.Lock(), 0.0

    async def anime(self, mal_id: int) -> AnimeNames | None:
        key = f"shikimori:anime:{mal_id}"
        found, d = self._cache.get(key, TTL)
        if not found:
            d = await self._fetch(f"/api/animes/{mal_id}")
            if d is not False:  # False = request failed: don't cache, try again next time
                self._cache.put(key, d)
        if not d:
            return None
        aired = d.get("aired_on") or ""
        return AnimeNames(
            mal_id=mal_id,
            romaji=d.get("name") or "",
            russian=d.get("russian") or "",
            kind=d.get("kind") or "",
            year=int(aired[:4]) if aired[:4].isdigit() else None,
            episodes=d.get("episodes") or None,
            names=_names(d),
        )

    async def _fetch(self, path: str):  # type: ignore[no-untyped-def]
        """JSON, None for 404, False on failure."""
        async with self._lock:
            wait = self._last + self._spacing - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()
            try:
                async with httpx.AsyncClient(
                    timeout=20, transport=self._transport, headers={"User-Agent": self._ua}
                ) as c:
                    r = await c.get(self._base + path)
            except httpx.HTTPError as e:
                log.warning("shikimori %s: %s", path, e)
                return False
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            log.warning("shikimori %s: HTTP %s", path, r.status_code)
            return False
        return r.json()
