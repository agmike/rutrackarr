"""The settings rutrackarr knows about: one definition per key."""

from dataclasses import dataclass
from typing import Literal

Kind = Literal["string", "url", "int", "secret", "choice"]


@dataclass(frozen=True)
class FieldDef:
    kind: Kind
    default: str | int | None = None
    minimum: int | None = None
    maximum: int | None = None
    url: bool = False  # a secret that must be an http(s) URL
    choices: tuple[str, ...] = ()  # kind "choice"


FIELDS: dict[str, FieldDef] = {
    # RuTracker account and request budget
    "rutracker.username": FieldDef("string", ""),
    "rutracker.password": FieldDef("secret"),
    "rutracker.base_url": FieldDef("url", "https://rutracker.org"),
    "rutracker.requests_per_minute": FieldDef("int", 10, minimum=1, maximum=60),
    # Search result cache (Sonarr repeats the same query per title, episode and search type)
    "search.cache_minutes": FieldDef("int", 60, minimum=0, maximum=1440),
    "search.rss_cache_minutes": FieldDef("int", 5, minimum=0, maximum=60),
    # Cloudflare challenge solver
    "flaresolverr.url": FieldDef("url", "http://flaresolverr:8191/"),
    "flaresolverr.timeout_seconds": FieldDef("int", 60, minimum=10, maximum=300),
    # Metadata (titles by ID)
    "tmdb.read_access_token": FieldDef("secret"),
    # Optional arr connections (lookups, history in the query log)
    "sonarr.url": FieldDef("url", "http://sonarr:8989"),
    "sonarr.api_key": FieldDef("secret"),
    "radarr.url": FieldDef("url", "http://radarr:7878"),
    "radarr.api_key": FieldDef("secret"),
    # Download client: qBittorrent behind RuTrackarr's qBittorrent-compatible proxy (empty URL:
    # off — .torrent files are served as RuTracker sends them)
    # Either qBittorrent's own Web UI (URL + login), or qui's client proxy (qui URL + a proxy
    # token, used as <qui URL>/proxy/<token>, no login).
    "qbittorrent.mode": FieldDef("choice", "qbittorrent", choices=("qbittorrent", "qui")),
    "qbittorrent.url": FieldDef("url", ""),
    "qbittorrent.username": FieldDef("string", "admin"),
    "qbittorrent.password": FieldDef("secret"),
    "qui.url": FieldDef("url", ""),
    "qui.token": FieldDef("secret"),
    # Tracked topics: track what Sonarr/Radarr grab; qBittorrent category for topics tracked by
    # hand (one no Sonarr/Radarr client asks for)
    "tracking.auto_track": FieldDef("choice", "on", choices=("on", "off")),
    "tracking.category": FieldDef("string", "rutrackarr/tracked"),
    # Update checks: RuTracker's per-section feeds (one request per section with tracked
    # topics), plus a slower per-topic check (ongoing topics; finished ones weekly)
    "tracking.feed_minutes": FieldDef("int", 15, minimum=5, maximum=240),
    "tracking.check_hours": FieldDef("int", 24, minimum=1, maximum=168),
    # Alerts: Apprise URLs (space- or comma-separated), e.g. tgram://<bot token>/<chat id>
    "alerts.apprise_urls": FieldDef("secret"),
    # General
    "general.query_log_retention_days": FieldDef("int", 30, minimum=1, maximum=365),
}

API_KEY = "torznab.api_key"
