"""Database-backed job cache with TTL-based freshness.

The jobs table doubles as a cache: fresh cached matches satisfy a search
without external calls; stale results trigger a provider refresh. External
jobs are never deleted — they age into UNKNOWN/EXPIRED so Phase 3
applications and analytics keep working.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models.jobs import JobRow
from app.services.matching import tokenize


def _row_matches_query(row: JobRow, token_sets: list[set[str]]) -> bool:
    """Primary: every query token appears. Fallback: any token (recall pass)."""
    if not token_sets:
        return True
    haystack = f"{row.title} {row.company} {row.description}".lower()
    for tokens in token_sets:
        if tokens and all(token in haystack for token in tokens):
            return True
    for tokens in token_sets:
        if tokens and any(token in haystack for token in tokens):
            return True
    return False


def lookup_cached_jobs(
    db: OrmSession,
    strategy_queries: list[str],
    preferences=None,
    ttl_minutes: int | None = None,
) -> tuple[list[JobRow], bool]:
    """Return (cached_rows, cache_is_fresh).

    Freshness = newest last_seen_at among matching rows is within the TTL.
    """
    settings = get_settings()
    ttl = ttl_minutes if ttl_minutes is not None else settings.job_cache_ttl_minutes
    keywords = strategy_queries or (preferences.keywords if preferences else [])
    token_sets = [tokenize(k) for k in keywords if k.strip()]

    rows = list(db.scalars(select(JobRow).order_by(JobRow.created_at.desc())))
    matched = [row for row in rows if _row_matches_query(row, token_sets)]

    now = datetime.now(timezone.utc)
    seen_dates = [
        row.last_seen_at or row.created_at
        for row in matched
        if (row.last_seen_at or row.created_at) is not None
    ]
    newest = max(seen_dates) if seen_dates else None
    if newest is not None and newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    fresh = (
        bool(matched)
        and newest is not None
        and (now - newest) <= timedelta(minutes=ttl)
    )
    return matched, fresh


def touch_last_seen(db: OrmSession, job_ids: list[str]) -> None:
    """Bump last_seen_at for re-encountered jobs."""
    if not job_ids:
        return
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(JobRow).where(JobRow.id.in_(job_ids))).all()
    for row in rows:
        row.last_seen_at = now


def mark_stale_jobs(db: OrmSession, stale_days: int | None = None) -> int:
    """Jobs not seen within the threshold become UNKNOWN (never deleted)."""
    settings = get_settings()
    days = stale_days if stale_days is not None else settings.job_stale_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.scalars(select(JobRow).where(JobRow.status == "ACTIVE")).all()
    changed = 0
    for row in rows:
        reference = row.last_seen_at or row.created_at
        if reference is None:
            continue
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        if reference < cutoff:
            row.status = "UNKNOWN"
            changed += 1
    if changed:
        db.flush()
    return changed


__all__ = ["lookup_cached_jobs", "mark_stale_jobs", "touch_last_seen"]

