"""Jobicy public remote-jobs API adapter.

- Endpoint : https://jobicy.com/api/v2/remote-jobs
- Auth     : none (public, documented, free)
- Fields   : id, url, jobTitle, companyName, jobGeo, jobLevel, jobType,
             jobDescription, pubDate
Enable with ENABLE_JOBICY=true.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.services.job_sources.arbeitnow_source import (
    _is_json,
    _keyword_matches,
)
from app.schemas.jobs import RawJob
from app.services.job_sources.base import JobSourceError


class JobicyJobSource:
    name = "jobicy"
    source_type = "REAL"

    API_URL = "https://jobicy.com/api/v2/remote-jobs"

    def __init__(self, max_results_per_query: int = 25,
                 timeout_seconds: float = 10.0) -> None:
        self._max_results_per_query = max_results_per_query
        self._timeout_seconds = timeout_seconds

    def search_jobs(self, query, strategy_queries) -> list[RawJob]:
        keywords = strategy_queries or query.keywords or ["developer"]
        results: list[RawJob] = []
        seen: set[str] = set()
        with httpx.Client(timeout=self._timeout_seconds) as client:
            for keyword in keywords:
                if len(results) >= self._max_results_per_query:
                    break
                try:
                    response = client.get(
                        self.API_URL,
                        params={"count": min(50, self._max_results_per_query)},
                        headers={"Accept": "application/json"},
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise JobSourceError(f"Jobicy request failed: {exc}") from exc
                payload = response.json() if _is_json(response) else {}
                for item in payload.get("jobs", []):
                    raw = self._to_raw(item)
                    if raw is None or not _keyword_matches(raw, keyword):
                        continue
                    key = f"{raw.source}:{raw.source_job_id}"
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(raw)
        return results[: self._max_results_per_query]

    @staticmethod
    def _to_raw(item: dict) -> RawJob | None:
        title = (item.get("jobTitle") or "").strip()
        company = (item.get("companyName") or "").strip()
        if not title or not company:
            return None
        posted_at = None
        pub_date = item.get("pubDate")
        if isinstance(pub_date, str) and pub_date:
            try:
                posted_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        description_html = str(item.get("jobDescription") or "")
        import re

        description = re.sub(r"<[^>]+>", " ", description_html)
        description = re.sub(r"\s{2,}", " ", description).strip()
        salary_text = None
        if item.get("annualSalaryMin") is not None and \
                item.get("annualSalaryMax") is not None:
            salary_text = (
                f"{item['annualSalaryMin']}-{item['annualSalaryMax']} "
                f"{item.get('annualSalaryCurrency') or 'USD'}"
            )
        return RawJob(
            source="jobicy",
            source_type="REAL",
            source_job_id=str(item.get("id") or ""),
            title=title,
            company=company,
            description=description[:6000],
            location=item.get("jobGeo") or "Remote",
            work_mode="remote",
            employment_type=(
                str(item.get("jobType")).lower() if item.get("jobType") else None
            ),
            experience_level=item.get("jobLevel"),
            salary_text=salary_text,
            url=item.get("url") or None,
            posted_at=posted_at,
        )


__all__ = ["JobicyJobSource"]
