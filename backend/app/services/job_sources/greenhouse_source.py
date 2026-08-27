"""Greenhouse ATS public job-board adapter (Company Career Source pattern).

Many companies publish their job boards publicly via Greenhouse:

    https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

This is a documented, public, read-only feed intended for embedding job
boards — no auth, no scraping of HTML pages. Configure the boards you care
about with GREENHOUSE_COMPANIES as `token` or `token:Display Name`
entries, e.g. `stripe:Stripe Inc,duolingo`.

Enable by listing at least one company; otherwise the provider is skipped.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx

from app.schemas.jobs import RawJob
from app.services.job_sources.base import JobSourceError


class GreenhouseCompanySource:
    name = "greenhouse"
    source_type = "REAL"

    API_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"

    def __init__(self, boards: list[tuple[str, str]],
                 max_results_per_board: int = 20,
                 timeout_seconds: float = 10.0) -> None:
        self._boards = boards  # [(token, display_name)]
        self._max_results_per_board = max_results_per_board
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings) -> "GreenhouseCompanySource | None":
        raw = (settings.greenhouse_companies or "").strip()
        if not raw:
            return None
        boards: list[tuple[str, str]] = []
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" in entry:
                token, display = entry.split(":", 1)
                boards.append((token.strip(), display.strip()))
            else:
                boards.append((entry, entry.replace("-", " ").title()))
        return cls(boards=boards) if boards else None

    def search_jobs(self, query, strategy_queries) -> list[RawJob]:
        from app.services.matching import tokenize

        keywords = strategy_queries or query.keywords or []
        token_sets = [tokenize(k) for k in keywords if k.strip()]
        results: list[RawJob] = []
        seen: set[str] = set()
        with httpx.Client(timeout=self._timeout_seconds) as client:
            for token, display_name in self._boards:
                try:
                    response = client.get(
                        self.API_URL.format(token=token),
                        params={"content": "true"},
                        headers={"Accept": "application/json"},
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise JobSourceError(
                        f"Greenhouse board '{token}' request failed: {exc}"
                    ) from exc
                payload = response.json()
                for item in payload.get("jobs", [])[: self._max_results_per_board]:
                    raw = self._to_raw(item, display_name)
                    if raw is None:
                        continue
                    if token_sets:
                        haystack = f"{raw.title} {raw.description}".lower()
                        if not any(ts <= set(tokenize(haystack)) for ts in token_sets):
                            continue
                    key = f"{raw.source}:{raw.source_job_id}"
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(raw)
        return results

    @staticmethod
    def _to_raw(item: dict, company_name: str) -> RawJob | None:
        title = (item.get("title") or "").strip()
        if not title or not company_name:
            return None
        posted_at = None
        updated = item.get("updated_at")
        if isinstance(updated, str) and updated:
            try:
                posted_at = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        content_html = str(item.get("content") or "")
        description = re.sub(r"<[^>]+>", " ", content_html)
        description = re.sub(r"\s{2,}", " ", description).strip()
        location = ((item.get("location") or {}).get("name") or "").strip() or None
        return RawJob(
            source="greenhouse",
            source_type="REAL",
            source_job_id=str(item.get("id") or ""),
            title=title,
            company=company_name,
            description=description[:6000],
            location=location,
            url=item.get("absolute_url") or None,
            posted_at=posted_at or datetime.now(timezone.utc),
        )


__all__ = ["GreenhouseCompanySource"]
