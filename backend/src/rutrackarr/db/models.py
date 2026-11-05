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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
