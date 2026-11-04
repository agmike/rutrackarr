"""The settings rutrackarr knows about: one definition per key."""

from dataclasses import dataclass
from typing import Literal

Kind = Literal["string", "url", "int", "secret"]


@dataclass(frozen=True)
class FieldDef:
    kind: Kind
    default: str | int | None = None
    minimum: int | None = None
    maximum: int | None = None


FIELDS: dict[str, FieldDef] = {
    # RuTracker account and request budget
    "rutracker.username": FieldDef("string", ""),
    "rutracker.password": FieldDef("secret"),
    "rutracker.base_url": FieldDef("url", "https://rutracker.org"),
    "rutracker.requests_per_minute": FieldDef("int", 10, minimum=1, maximum=60),
    # Cloudflare challenge solver
    "flaresolverr.url": FieldDef("url", "http://flaresolverr:8191/"),
    "flaresolverr.timeout_seconds": FieldDef("int", 60, minimum=10, maximum=300),
    # Metadata (titles by ID)
    "tmdb.read_access_token": FieldDef("secret"),
    # Optional arr connections (lookups, history in the query log)
    "sonarr.url": FieldDef("url", ""),
    "sonarr.api_key": FieldDef("secret"),
    "radarr.url": FieldDef("url", ""),
    "radarr.api_key": FieldDef("secret"),
    # General
    "general.query_log_retention_days": FieldDef("int", 30, minimum=1, maximum=365),
}

API_KEY = "torznab.api_key"
