"""Query log and activity log (status page): what Sonarr/Radarr asked, and what happened.

Both are kept for `general.query_log_retention_days`. Writes never fail the request that
causes them — a broken log only loses the entry.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from rutrackarr.db.models import EventRow, QueryResultRow, QueryRow

DETAIL_QUERIES = 2000  # per-topic results are kept for this many newest queries
DETAIL_ROWS = 80  # per query

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
    id: int
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
        # Told about every event: (kind, level, message) — the alerts.
        self.listeners: list[Callable[[str, str, str], None]] = []

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
        rows: list[dict] | None = None,
    ) -> int | None:
        """Log a query (and what it found: trace rows); → its id."""
        return self._add(
            QueryRow(
                at=datetime.now(UTC), caller=caller[:32], kind=kind[:16], query=query[:500],
                results=results, rutracker_requests=rutracker_requests,
                duration_ms=duration_ms, error=(error or None) and error[:1000],
            ),
            rows,
        )  # fmt: skip

    def event(
        self, kind: str, message: str, *, level: str = "info", topic_id: int | None = None
    ) -> None:
        log.info("event %s: %s", kind, message)
        for listener in self.listeners:
            try:
                listener(kind, level, message)
            except Exception as e:
                log.warning("event listener failed: %s", e)
        self._add(
            EventRow(
                at=datetime.now(UTC), kind=kind[:32], level=level, message=message[:2000],
                topic_id=topic_id,
            )
        )  # fmt: skip

    def _add(self, row: Any, details: list[dict] | None = None) -> int | None:
        """Logging must never break a request: failures only lose the entry."""
        try:
            with self._sessions.begin() as s:
                s.add(row)
                s.flush()
                for d in (details or [])[:DETAIL_ROWS]:
                    s.add(
                        QueryResultRow(
                            query_id=row.id, topic_id=d["topic_id"], title=d["title"][:500],
                            forum=(d.get("forum") or "")[:200], release=d.get("release"),
                            reason=(d.get("reason") or None) and d["reason"][:300],
                        )
                    )  # fmt: skip
                return int(row.id)
        except Exception as e:
            log.warning("activity log write failed: %s", e)
            return None

    def prune(self, days: int) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=max(1, days))
        with self._sessions.begin() as s:
            s.execute(delete(QueryRow).where(QueryRow.at < cutoff))
            s.execute(delete(EventRow).where(EventRow.at < cutoff))
            newest = s.scalar(select(func.max(QueryRow.id))) or 0
            s.execute(
                delete(QueryResultRow).where(QueryResultRow.query_id <= newest - DETAIL_QUERIES)
            )
            s.execute(
                delete(QueryResultRow).where(QueryResultRow.query_id.not_in(select(QueryRow.id)))
            )

    # --- reading -------------------------------------------------------------------------------

    def details(self, query_id: int) -> list[dict]:
        """The topics a logged query saw: kept ones with their release name, dropped ones with
        why. Kept for the newest queries only."""
        with self._sessions() as s:
            rows = s.scalars(
                select(QueryResultRow)
                .where(QueryResultRow.query_id == query_id)
                .order_by(QueryResultRow.release.is_(None), QueryResultRow.id)
            )
            return [
                {
                    "topic_id": r.topic_id,
                    "title": r.title,
                    "forum": r.forum,
                    "release": r.release,
                    "reason": r.reason,
                }
                for r in rows
            ]

    def dropped(self, reason: str = "", limit: int = 100) -> list[dict]:
        """Topics searches saw but dropped, newest first, one row per topic and reason."""
        last = func.max(QueryRow.at)
        with self._sessions() as s:
            q = (
                select(
                    QueryResultRow.topic_id, QueryResultRow.title, QueryResultRow.forum,
                    QueryResultRow.reason, func.count(), last, func.max(QueryRow.query),
                )
                .join(QueryRow, QueryRow.id == QueryResultRow.query_id)
                .where(QueryResultRow.release.is_(None), QueryResultRow.reason.is_not(None))
                .group_by(QueryResultRow.topic_id, QueryResultRow.reason)
                .order_by(last.desc())
                .limit(limit)
            )  # fmt: skip
            if reason:
                q = q.where(QueryResultRow.reason.like(f"{reason}%"))
            return [
                {
                    "topic_id": t,
                    "title": title,
                    "forum": forum,
                    "reason": why,
                    "times": n,
                    "last_seen": _utc(at).isoformat(),
                    "last_query": query,
                }
                for t, title, forum, why, n, at, query in s.execute(q).all()
            ]

    def events(self, limit: int = 20, exclude: tuple[str, ...] = ()) -> list[Event]:
        with self._sessions() as s:
            q = select(EventRow).order_by(EventRow.id.desc()).limit(limit)
            if exclude:
                q = q.where(EventRow.kind.not_in(exclude))
            rows = s.scalars(q)
            return [Event(_utc(r.at), r.kind, r.level, r.message, r.topic_id) for r in rows]

    def queries(
        self, limit: int = 20, errors_only: bool = False, empty_only: bool = False
    ) -> list[Query]:
        with self._sessions() as s:
            q = select(QueryRow).order_by(QueryRow.id.desc()).limit(limit)
            if errors_only:
                q = q.where(QueryRow.error.is_not(None))
            if empty_only:
                q = q.where(QueryRow.results == 0, QueryRow.error.is_(None))
            return [
                Query(
                    r.id, _utc(r.at), r.caller, r.kind, r.query, r.results, r.rutracker_requests,
                    r.duration_ms, r.error,
                )
                for r in s.scalars(q)
            ]  # fmt: skip

    def count(self, kind: str, hours: float) -> int:
        """Events of a kind in the last `hours`."""
        since = datetime.now(UTC) - timedelta(hours=hours)
        with self._sessions() as s:
            return int(
                s.scalar(select(func.count()).where(EventRow.kind == kind, EventRow.at >= since))
                or 0
            )

    def stats(self, hours: float) -> dict[str, Any]:
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
