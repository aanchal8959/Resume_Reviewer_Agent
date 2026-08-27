"""Adzuna official API adapter (requires free developer credentials).

- Endpoint : https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
- Auth     : app_id + app_key (free tier at developer.adzuna.com)
- Free tier: yes, with daily quota
- Fields   : id, title, company.display_name, location.display_name,
             description, redirect_url, created, salary_min/max, contract_time

Disabled unless ADZUNA_APP_ID and ADZUNA_API_KEY are both configured — the
adapter never runs with invented credentials.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.schemas.jobs import RawJob
from app.services.job_sources.arbeitnow_source import (
    _is_json,
    _keyword_matches,
)
from app.services.job_sources.base import JobSourceError


class AdzunaJobSource:
    name = "adzuna"
    source_type = "REAL"

    API_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

    def __init__(self, app_id: str, api_key: str, country: str = "in",
                 max_results_per_query: int = 20, timeout_seconds: float = 10.0) -> None:
        self._app_id = app_id
        self._api_key = api_key
        self._country = country
        self._max_results_per_query = max_results_per_query
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings) -> "AdzunaJobSource | None":
        if not settings.adzuna_app_id or not settings.adzuna_api_key:
            return None
        return cls(app_id=settings.adzuna_app_id, api_key=settings.adzuna_api_key)

    def search_jobs(self, query, strategy_queries) -> list[RawJob]:
        keywords = strategy_queries or query.keywords or ["developer"]
        location = next(iter(query.locations), None)
        results: list[RawJob] = []
        seen: set[str] = set()
        with httpx.Client(timeout=self._timeout_seconds) as client:
            for keyword in keywords:
                if len(results) >= self._max_results_per_query:
                    break
                try:
                    response = client.get(
                        self.API_URL.format(country=self._country, page=1),
                        params={
                            "app_id": self._app_id,
                            "app_key": self._api_key,
                            "what": keyword,
                            **({"where": location} if location else {}),
                            "results_per_page": min(50, self._max_results_per_query),
                        },
                        headers={"Accept": "application/json"},
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise JobSourceError(f"Adzuna request failed: {exc}") from exc
                payload = response.json() if _is_json(response) else {}
                for item in payload.get("results", []):
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
        title = (item.get("title") or "").strip()
        company = ((item.get("company") or {}).get("display_name") or "").strip()
        if not title or not company:
            return None
        posted_at = None
        created = item.get("created")
        if isinstance(created, str) and created:
            try:
                posted_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        salary_text = None
        if item.get("salary_min") is not None or item.get("salary_max") is not None:
            lo = item.get("salary_min")
            hi = item.get("salary_max")
            salary_text = f"{lo:g}-{hi:g}" if lo is not None and hi is not None else str(lo or hi)
        return RawJob(
            source="adzuna",
            source_type="REAL",
            source_job_id=str(item.get("id") or ""),
            title=title,
            company=company,
            description=str(item.get("description") or "")[:6000],
            location=(item.get("location") or {}).get("display_name"),
            employment_type=item.get("contract_time"),
            salary_text=salary_text,
            url=item.get("redirect_url") or None,
            posted_at=posted_at,
        )


__all__ = ["AdzunaJobSource"]
