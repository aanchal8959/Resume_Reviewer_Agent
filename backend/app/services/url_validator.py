"""Opportunistic, rate-respecting application-URL verification.

Rules:
  * only URLs whose last_verified_at is older than URL_VERIFY_TTL_HOURS;
  * at most url_verify_max_per_search verifications per cycle;
  * HTTP >=400 -> INVALID; network errors leave status UNKNOWN (an unreachable
    site is not proof a posting is gone);
  * success -> VALID + last_verified_at=now.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import get_settings
from app.models.jobs import JobRow


def verify_stale_urls(db: OrmSession) -> int:
    """Verify up to N stale URLs; returns how many were checked."""
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=settings.url_verify_ttl_hours
    )
    rows = db.scalars(
        select(JobRow).where(
            JobRow.application_url.is_not(None),
            JobRow.status == "ACTIVE",
        )
    ).all()
    pending = []
    for row in rows:
        reference = row.last_verified_at
        if reference is not None and reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        if (reference or datetime.min.replace(tzinfo=timezone.utc)) < cutoff:
            pending.append(row)
    budget = max(0, settings.url_verify_max_per_search)
    checked = 0
    with httpx.Client(timeout=min(settings.provider_timeout_seconds, 8.0),
                      follow_redirects=True) as client:
        for row in pending:
            if checked >= budget:
                break
            url = row.application_url or ""
            try:
                response = client.head(url)
                if response.status_code == 405:
                    # HEAD not supported by the host; skip without penalty.
                    continue
                row.url_status = "VALID" if response.status_code < 400 else "INVALID"
            except httpx.HTTPError:
                row.url_status = "UNKNOWN"
            row.last_verified_at = datetime.now(timezone.utc)
            checked += 1
    if checked:
        db.flush()
    return checked


__all__ = ["verify_stale_urls"]
