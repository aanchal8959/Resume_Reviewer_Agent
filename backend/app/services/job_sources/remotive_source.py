"""Remotive public job API adapter (https://remotive.com/remote-jobs).

Remotive publishes a free, public JSON API intended for developers — no
authentication, no scraping, no ToS bypass. This adapter is best-effort: any
failure raises JobSourceError and the pipeline degrades gracefully.

Enable with JOB_SOURCE=remotive.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.schemas.jobs import RawJob
from app.services.job_sources.base import JobSourceError

API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveJobSource:
    name = "remotive"

    def __init__(self, max_results_per_query: int = 15, timeout_seconds: float = 20.0) -> None:
        self._max_results_per_query = max_results_per_query
        self._timeout_seconds = timeout_seconds

    def search_jobs(self, query, strategy_queries) -> list[RawJob]:
        results: dict[str, RawJob] = {}
        queries = strategy_queries or ["software engineer"]
        with httpx.Client(timeout=self._timeout_seconds) as client:
            for keyword in queries:
                try:
                    response = client.get(
                        API_URL, params={"search": keyword, "limit": self._max_results_per_query}
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise JobSourceError(f"Remotive request failed: {exc}") from exc
                for payload in response.json().get("jobs", []):
                    raw = self._to_raw(payload)
                    if raw is not None:
                        results[f"{raw.source}:{raw.source_job_id}"] = raw
        return list(results.values())

    @staticmethod
    def _to_raw(payload: dict) -> RawJob | None:
        title = (payload.get("title") or "").strip()
        company = ((payload.get("company_name") or "")).strip()
        if not title or not company:
            return None
        posted_at: datetime | None = None
        if payload.get("publication_date"):
            try:
                posted_at = datetime.fromisoformat(payload["publication_date"].replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        description = payload.get("description") or ""
        # Strip simple HTML tags; normalization works on plain text.
        description = (
            description.replace("<br>", "\n").replace("</p>\n", "\n")
            .replace("<li>", "- ").replace("</li>", "\n")
        )
        import re

        description = re.sub(r"<[^>]+>", "", description)
        return RawJob(
            source="remotive",
            source_type="REAL",
            source_job_id=str(payload.get("id") or ""),
            title=title,
            company=company,
            description=description.strip(),
            location=payload.get("candidate_required_location") or None,
            url=payload.get("url") or None,
            posted_at=posted_at,
        )
