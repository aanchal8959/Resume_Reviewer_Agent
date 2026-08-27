"""Arbeitnow public job-board API adapter.

- Endpoint : https://www.arbeitnow.com/api/job-board-api
- Auth     : none (public, documented, free)
- Rate info: fair-use; we cap results and use short timeouts
- Fields   : slug, company_name, title, description, remote, url, tags,
             job_types, location, created_at (unix)
Enable with ENABLE_ARBEITNOW=true.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.schemas.jobs import RawJob
from app.services.job_sources.base import JobSourceError


class ArbeitnowJobSource:
    name = "arbeitnow"
    source_type = "REAL"

    API_URL = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self, max_results_per_query: int = 25,
                 timeout_seconds: float = 10.0) -> None:
        self._max_results_per_query = max_results_per_query
        self._timeout_seconds = timeout_seconds

    def search_jobs(self, query, strategy_queries) -> list[RawJob]:
        keywords = strategy_queries or query.keywords or ["software"]
        results: list[RawJob] = []
        seen: set[str] = set()
        with httpx.Client(timeout=self._timeout_seconds) as client:
            for keyword in keywords:
                if len(results) >= self._max_results_per_query:
                    break
                try:
                    response = client.get(
                        self.API_URL,
                        params={"page": 1},
                        headers={"Accept": "application/json"},
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise JobSourceError(f"Arbeitnow request failed: {exc}") from exc
                payload = response.json() if _is_json(response) else {}
                for item in payload.get("data", []):
                    raw = self._to_raw(item)
                    if raw is None:
                        continue
                    if not _keyword_matches(raw, keyword):
                        continue
                    key = f"{raw.source}:{raw.source_job_id}"
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(raw)
        return results[: self._max_results_per_query]

    @staticmethod
    def _to_raw(item: dict) -> RawJob | None:
        title = (item.get("title") or "").strip()
        company = (item.get("company_name") or "").strip()
        if not title or not company:
            return None
        posted_at = None
        created = item.get("created_at")
        if isinstance(created, (int, float)):
            posted_at = datetime.fromtimestamp(created, tz=timezone.utc)
        elif isinstance(created, str):
            try:
                posted_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        job_types = [str(t) for t in (item.get("job_types") or [])]
        remote = bool(item.get("remote"))
        description_html = str(item.get("description") or "")
        import re

        description = re.sub(r"<[^>]+>", " ", description_html)
        description = re.sub(r"\s{2,}", " ", description).strip()
        return RawJob(
            source="arbeitnow",
            source_type="REAL",
            source_job_id=str(item.get("slug") or ""),
            title=title,
            company=company,
            description=description[:6000],
            location=(item.get("location") or None),
            work_mode="remote" if remote else None,
            employment_type=job_types[0] if job_types else None,
            url=item.get("url") or None,
            posted_at=posted_at,
        )


def _is_json(response: httpx.Response) -> bool:
    try:
        response.json()
        return True
    except Exception:  # noqa: BLE001 - malformed responses must not crash
        return False


def _keyword_matches(job: RawJob, keyword: str) -> bool:
    from app.services.matching import tokenize

    haystack = f"{job.title} {job.company} {job.description}".lower()
    tokens = tokenize(keyword)
    return not tokens or all(token in haystack for token in tokens)


__all__ = ["ArbeitnowJobSource", "_is_json", "_keyword_matches"]
