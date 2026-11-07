from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SettingRow(Base):
    """One setting value. Secret values are stored encrypted."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class RuTrackerSessionRow(Base):
    """The single RuTracker session: cookies (encrypted), the matching User-Agent, state."""

    __tablename__ = "rutracker_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    cookies: Mapped[str | None] = mapped_column(Text)  # encrypted JSON
    user_agent: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(String(200))
    logged_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cf_solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DownloadRow(Base):
    """A .torrent RuTrackarr served: its info hash and file list (never the torrent itself —
    it carries the passkey). Lets Sonarr's import script ask which files belong together."""

    __tablename__ = "downloads"

    info_hash: Mapped[str] = mapped_column(String(40), primary_key=True)
    topic_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    forum: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    files: Mapped[str] = mapped_column(Text, nullable=False)  # JSON [[path, size], ...]
    # Served marked (the download client proxy is on): the release name in the mark, and once
    # Sonarr/Radarr added it through the proxy, the real torrent's hash and their category.
    release: Mapped[str | None] = mapped_column(Text, nullable=True)
    real_hash: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class MetadataRow(Base):
    """Cached metadata (e.g. a Shikimori entry) as JSON, by key."""

    __tablename__ = "metadata_cache"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QueryRow(Base):
    """One Torznab search request from Sonarr/Radarr (kept for the status page's stats)."""

    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    caller: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # search | tvsearch | movie | rss
    query: Mapped[str] = mapped_column(Text, nullable=False)  # what was asked, for display
    results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rutracker_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventRow(Base):
    """Something that happened: a grab, a torrent added/moved/removed, RuTracker down/up."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="info")  # info|warn|error
    message: Mapped[str] = mapped_column(Text, nullable=False)
    topic_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class OverrideRow(Base):
    """Per series/film search overrides, edited on the Overrides page."""

    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # tv (TVDB id) | movie (TMDb id)
    external_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")  # for display
    extra_titles: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    replace_titles: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    release_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    season_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    include_regex: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclude_regex: Mapped[str | None] = mapped_column(Text, nullable=True)
    pins: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # [{topic_id, season}]
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QueryResultRow(Base):
    """What a logged query found on RuTracker and why each topic was kept or dropped."""

    __tablename__ = "query_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    topic_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    forum: Mapped[str] = mapped_column(Text, nullable=False, default="")
    release: Mapped[str | None] = mapped_column(Text, nullable=True)  # kept: the release name
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # dropped: why
