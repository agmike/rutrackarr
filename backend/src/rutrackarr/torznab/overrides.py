"""Per series/film search overrides (the Overrides page): what Sonarr's aliases can't express.

Keyed by the ID Sonarr/Radarr search with: TVDB id for series, TMDb id for films.
- extra titles: more names to search RuTracker for (or instead of the automatic ones);
- release title: the title releases are named after (instead of Sonarr's/Radarr's);
- season offset: a topic's own season number + offset (non-anime topics that number seasons
  differently from TVDB);
- include / exclude regex on RuTracker titles;
- pins: topics that belong to this series (optionally to a season) whatever their titles say —
  they apply when the topic shows up in a search for the series.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from rutrackarr.db.models import OverrideRow

Kind = Literal["tv", "movie"]


class OverrideError(ValueError):
    pass


@dataclass(frozen=True)
class Pin:
    topic_id: int
    season: int | None = None


@dataclass
class Override:
    kind: Kind
    external_id: int
    title: str = ""
    extra_titles: list[str] = field(default_factory=list)
    replace_titles: bool = False
    release_title: str | None = None
    season_offset: int | None = None
    include_regex: str | None = None
    exclude_regex: str | None = None
    pins: list[Pin] = field(default_factory=list)
    note: str = ""
    id: int | None = None
    updated_at: datetime | None = None

    def pin(self, topic_id: int) -> Pin | None:
        return next((p for p in self.pins if p.topic_id == topic_id), None)

    def allows(self, title: str) -> str | None:
        """None when the RuTracker title passes the regexes, else why not."""
        if self.include_regex and not re.search(self.include_regex, title, re.I):
            return "not matched by the override's include filter"
        if self.exclude_regex and re.search(self.exclude_regex, title, re.I):
            return "excluded by the override's exclude filter"
        return None

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return d


def from_json(d: dict[str, Any]) -> Override:
    """Validated: kind, a positive id, compilable regexes, unique pins."""
    kind = d.get("kind")
    if kind not in ("tv", "movie"):
        raise OverrideError("kind must be 'tv' or 'movie'")
    try:
        external_id = int(d.get("external_id") or 0)
    except (TypeError, ValueError):
        raise OverrideError("external_id must be a number") from None
    if external_id <= 0:
        raise OverrideError("external_id (TVDB id for series, TMDb id for films) is required")
    for key in ("include_regex", "exclude_regex"):
        if d.get(key):
            try:
                re.compile(d[key])
            except re.error as e:
                raise OverrideError(f"{key}: {e}") from None
    pins: list[Pin] = []
    for p in d.get("pins") or []:
        try:
            pin = Pin(
                int(p["topic_id"]), int(p["season"]) if p.get("season") not in (None, "") else None
            )
        except (KeyError, TypeError, ValueError):
            raise OverrideError(f"bad pin: {p!r}") from None
        if any(x.topic_id == pin.topic_id for x in pins):
            raise OverrideError(f"topic {pin.topic_id} pinned twice")
        pins.append(pin)
    offset = d.get("season_offset")
    return Override(
        kind=kind,
        external_id=external_id,
        title=str(d.get("title") or "").strip(),
        extra_titles=[t.strip() for t in d.get("extra_titles") or [] if str(t).strip()],
        replace_titles=bool(d.get("replace_titles")),
        release_title=(str(d.get("release_title") or "").strip() or None),
        season_offset=int(offset) if offset not in (None, "", 0) else None,
        include_regex=(d.get("include_regex") or None),
        exclude_regex=(d.get("exclude_regex") or None),
        pins=pins,
        note=str(d.get("note") or ""),
    )


class OverrideStore:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    def get(self, kind: Kind, external_id: int | None) -> Override | None:
        if not external_id:
            return None
        with self._sessions() as s:
            row = s.scalars(
                select(OverrideRow).where(
                    OverrideRow.kind == kind, OverrideRow.external_id == external_id
                )
            ).first()
            return _from_row(row) if row else None

    def all(self) -> list[Override]:
        with self._sessions() as s:
            rows = s.scalars(select(OverrideRow).order_by(OverrideRow.title, OverrideRow.id))
            return [_from_row(r) for r in rows]

    def save(self, o: Override) -> Override:
        """Create or replace the override for (kind, external_id)."""
        with self._sessions.begin() as s:
            row = s.scalars(
                select(OverrideRow).where(
                    OverrideRow.kind == o.kind, OverrideRow.external_id == o.external_id
                )
            ).first() or OverrideRow(kind=o.kind, external_id=o.external_id)
            row.title, row.note = o.title, o.note
            row.extra_titles = json.dumps(o.extra_titles, ensure_ascii=False)
            row.replace_titles = o.replace_titles
            row.release_title, row.season_offset = o.release_title, o.season_offset
            row.include_regex, row.exclude_regex = o.include_regex, o.exclude_regex
            row.pins = json.dumps([asdict(p) for p in o.pins])
            row.updated_at = datetime.now(UTC)
            s.add(row)
            s.flush()
            return _from_row(row)

    def delete(self, override_id: int) -> bool:
        with self._sessions.begin() as s:
            row = s.get(OverrideRow, override_id)
            if row is None:
                return False
            s.delete(row)
            return True


def _from_row(r: OverrideRow) -> Override:
    updated = r.updated_at.replace(tzinfo=UTC) if r.updated_at.tzinfo is None else r.updated_at
    return Override(
        kind=r.kind,  # type: ignore[arg-type]
        external_id=r.external_id,
        title=r.title,
        extra_titles=json.loads(r.extra_titles or "[]"),
        replace_titles=r.replace_titles,
        release_title=r.release_title,
        season_offset=r.season_offset,
        include_regex=r.include_regex,
        exclude_regex=r.exclude_regex,
        pins=[Pin(**p) for p in json.loads(r.pins or "[]")],
        note=r.note,
        id=r.id,
        updated_at=updated,
    )
