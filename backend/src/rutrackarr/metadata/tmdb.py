"""TMDb (themoviedb.org, v3 API with the read access token): Russian, original, English and
alternative titles, original language and (for series) season air years — for non-anime ID
searches. Responses are cached for a week."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

import httpx

from rutrackarr.metadata.cache import MetadataCache

log = logging.getLogger(__name__)
API = "https://api.themoviedb.org/3"
TTL = timedelta(days=7)

# TMDb's ISO 639-1 codes → the ISO 639-2 codes the title parser uses.
LANG_639_2 = {
    "en": "eng", "ru": "rus", "uk": "ukr", "ja": "jpn", "ko": "kor", "zh": "chi", "cn": "chi",
    "fr": "fra", "de": "deu", "es": "spa", "it": "ita", "pt": "por", "nl": "nld", "pl": "pol",
    "sv": "swe", "da": "dan", "no": "nor", "nb": "nor", "fi": "fin", "tr": "tur", "he": "heb",
    "hi": "hin", "th": "tha", "cs": "ces", "kk": "kaz", "be": "bel",
}  # fmt: skip


@dataclass(frozen=True)
class TmdbTitle:
    tmdb_id: int
    kind: str  # "tv" | "movie"
    russian: str
    original: str
    english: str
    original_language: str | None  # ISO 639-2 ("eng")
    year: int | None
    names: list[str] = field(default_factory=list)  # every title, for matching
    season_years: dict[int, int] = field(default_factory=dict)  # season → first air year
    imdb_id: str | None = None


def _year(date: str | None) -> int | None:
    return int(date[:4]) if date and date[:4].isdigit() else None


class Tmdb:
    def __init__(
        self,
        token: Callable[[], str | None],
        cache: MetadataCache,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token, self._cache, self._transport = token, cache, transport

    @property
    def configured(self) -> bool:
        return bool(self._token())

    async def check(self) -> str | None:
        """None when the token works, else what's wrong."""
        token = self._token()
        if not token:
            return "no token"
        try:
            async with httpx.AsyncClient(
                timeout=10, transport=self._transport, headers={"Authorization": f"Bearer {token}"}
            ) as c:
                r = await c.get(API + "/authentication")
        except httpx.HTTPError as e:
            return f"unreachable: {e}"
        if r.status_code == 401:
            return "token rejected"
        return None if r.status_code == 200 else f"HTTP {r.status_code}"

    async def tv_by_tvdb(self, tvdb_id: int) -> TmdbTitle | None:
        found = await self._get(
            f"find:tvdb:{tvdb_id}", f"/find/{tvdb_id}", {"external_source": "tvdb_id"}
        )
        hits = (found or {}).get("tv_results") or []
        return await self.details("tv", hits[0]["id"]) if hits else None

    async def movie_by_imdb(self, imdb_id: str) -> TmdbTitle | None:
        found = await self._get(
            f"find:imdb:{imdb_id}", f"/find/{imdb_id}", {"external_source": "imdb_id"}
        )
        hits = (found or {}).get("movie_results") or []
        return await self.details("movie", hits[0]["id"]) if hits else None

    async def details(self, kind: str, tmdb_id: int) -> TmdbTitle | None:
        params = {
            "language": "ru-RU",
            "append_to_response": "alternative_titles,translations,external_ids",
        }
        d = await self._get(f"{kind}:{tmdb_id}", f"/{kind}/{tmdb_id}", params)
        if not d:
            return None
        title_key, orig_key = (
            ("name", "original_name") if kind == "tv" else ("title", "original_title")
        )
        english = ""
        for tr in (d.get("translations") or {}).get("translations") or []:
            if tr.get("iso_639_1") == "en":
                english = (tr.get("data") or {}).get(title_key) or ""
        alts = (d.get("alternative_titles") or {}).get(
            "results" if kind == "tv" else "titles"
        ) or []
        names: list[str] = []
        for n in [d.get(title_key), d.get(orig_key), english, *(a.get("title") for a in alts)]:
            if n and n not in names:
                names.append(n)
        seasons = {
            s["season_number"]: y
            for s in d.get("seasons") or []
            if s.get("season_number") and (y := _year(s.get("air_date")))
        }
        lang = d.get("original_language")
        return TmdbTitle(
            tmdb_id=tmdb_id,
            kind=kind,
            russian=d.get(title_key) or "",
            original=d.get(orig_key) or "",
            english=english,
            original_language=LANG_639_2.get(lang or "", lang),
            year=_year(d.get("first_air_date") if kind == "tv" else d.get("release_date")),
            names=names,
            season_years=seasons,
            imdb_id=(d.get("external_ids") or {}).get("imdb_id") or d.get("imdb_id"),
        )

    async def _get(self, key: str, path: str, params: dict):  # type: ignore[no-untyped-def]
        token = self._token()
        if not token:
            return None
        found, value = self._cache.get(f"tmdb:{key}", TTL)
        if found:
            return value
        try:
            async with httpx.AsyncClient(
                timeout=20, transport=self._transport, headers={"Authorization": f"Bearer {token}"}
            ) as c:
                r = await c.get(API + path, params=params)
        except httpx.HTTPError as e:
            log.warning("tmdb %s: %s", path, e)
            return None
        if r.status_code == 404:
            self._cache.put(f"tmdb:{key}", None)
            return None
        if r.status_code != 200:
            log.warning("tmdb %s: HTTP %s", path, r.status_code)
            return None
        value = r.json()
        self._cache.put(f"tmdb:{key}", value)
        return value
