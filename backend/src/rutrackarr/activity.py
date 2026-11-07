"""Query log and activity log (status page): what Sonarr/Radarr asked, and what happened.

Both are kept for `general.query_log_retention_days`. Writes never fail the request that
causes them — a broken log only loses the entry.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from rutrackarr.db.models import EventRow, QueryRow

log = logging.getLogger(__name__)


def caller_of(user_agent: str) -> str:
    """ "Sonarr/4.0.20.3014 (…)" → "Sonarr"; anything else → its product name or "other"."""
    ua = user_agent.strip()
    for known in ("Sonarr", "Radarr", "Prowlarr", "Lidarr", "Readarr", "Jackett"):
        if ua.lower().startswith(known.lower()):
            return known
    head = ua.split("/", 1)[0].split(" ", 1)[0]
    return head[:32] if head else "other"


@dataclass(frozen=True)
class Event:
    at: datetime
    kind: str
    level: str
    message: str
    topic_id: int | None


@dataclass(frozen=True)
class Query:
    at: datetime
    caller: str
    kind: str
    query: str
    results: int
    rutracker_requests: int
    duration_ms: int
    error: str | None


class Activity:
    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    # --- writing -------------------------------------------------------------------------------

    def query(
        self,
        caller: str,
        kind: str,
        query: str,
        results: int,
        rutracker_requests: int,
        duration_ms: int,
        error: str | None = None,
    ) -> None:
        self._add(
            QueryRow(
                at=datetime.now(UTC), caller=caller[:32], kind=kind[:16], query=query[:500],
                results=results, rutracker_requests=rutracker_requests,
                duration_ms=duration_ms, error=(error or None) and error[:1000],
            )
        )  # fmt: skip

    def event(
        self, kind: str, message: str, *, level: str = "info", topic_id: int | None = None
    ) -> None:
        log.info("event %s: %s", kind, message)
        self._add(
            EventRow(
                at=datetime.now(UTC), kind=kind[:32], level=level, message=message[:2000],
                topic_id=topic_id,
            )
        )  # fmt: skip

    def _add(self, row: Any) -> None:
        try:
            with self._sessions.begin() as s:
                s.add(row)
        except Exception as e:
            log.warning("activity log write failed: %s", e)

    def prune(self, days: int) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=max(1, days))
        with self._sessions.begin() as s:
            s.execute(delete(QueryRow).where(QueryRow.at < cutoff))
            s.execute(delete(EventRow).where(EventRow.at < cutoff))

    # --- reading -------------------------------------------------------------------------------

    def events(self, limit: int = 20) -> list[Event]:
        with self._sessions() as s:
            rows = s.scalars(select(EventRow).order_by(EventRow.id.desc()).limit(limit))
            return [Event(_utc(r.at), r.kind, r.level, r.message, r.topic_id) for r in rows]

    def queries(self, limit: int = 20, errors_only: bool = False) -> list[Query]:
        with self._sessions() as s:
            q = select(QueryRow).order_by(QueryRow.id.desc()).limit(limit)
            if errors_only:
                q = q.where(QueryRow.error.is_not(None))
            return [
                Query(
                    _utc(r.at), r.caller, r.kind, r.query, r.results, r.rutracker_requests,
                    r.duration_ms, r.error,
                )
                for r in s.scalars(q)
            ]  # fmt: skip

    def stats(self, hours: int) -> dict[str, Any]:
        """Totals for the last `hours`: queries, by caller and kind, from cache (no RuTracker
        request), errors, RuTracker requests, average and slowest answer."""
        since = datetime.now(UTC) - timedelta(hours=hours)
        with self._sessions() as s:
            where = QueryRow.at >= since
            total, cached, errors, requests, avg_ms, max_ms = s.execute(
                select(
                    func.count(),
                    func.sum((QueryRow.rutracker_requests == 0).cast(QueryRow.results.type)),
                    func.count(QueryRow.error),
                    func.coalesce(func.sum(QueryRow.rutracker_requests), 0),
                    func.avg(QueryRow.duration_ms),
                    func.max(QueryRow.duration_ms),
                ).where(where)
            ).one()
            by_caller = dict(
                s.execute(
                    select(QueryRow.caller, func.count()).where(where).group_by(QueryRow.caller)
                ).all()
            )
            by_kind = dict(
                s.execute(
                    select(QueryRow.kind, func.count()).where(where).group_by(QueryRow.kind)
                ).all()
            )
        return {
            "hours": hours,
            "queries": total or 0,
            "cached": int(cached or 0),
            "errors": errors or 0,
            "rutracker_requests": int(requests or 0),
            "avg_ms": round(avg_ms) if avg_ms is not None else None,
            "max_ms": max_ms,
            "by_caller": by_caller,
            "by_kind": by_kind,
        }


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
