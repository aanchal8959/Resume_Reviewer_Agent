"""Wikipedia REST summary API adapter for company research.

- Endpoint : https://en.wikipedia.org/api/rest_v1/page/summary/{title}
- Auth     : none (public, documented, keyless)
- Fields   : extract (description), type, description... Industry/technology
  areas are NOT published by Wikipedia; those fields stay "Not available"
  rather than being inferred.
"""

from __future__ import annotations

import re

import httpx

from app.schemas.applications import CompanyInfo
from app.services.job_sources.arbeitnow_source import _is_json


class WikipediaCompanySource:
    name = "wikipedia"

    API_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    def get_company_info(self, company_name: str) -> CompanyInfo:
        title = self._to_title(company_name)
        if not title:
            raise KeyError(company_name)
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.get(
                    self.API_URL.format(title=title.replace(" ", "_")),
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            from app.services.company_research.base import CompanyResearchError

            raise CompanyResearchError(f"Wikipedia request failed: {exc}") from exc

        if response.status_code == 404:
            raise KeyError(company_name)
        if response.status_code != 200 or not _is_json(response):
            from app.services.company_research.base import CompanyResearchError

            raise CompanyResearchError(
                f"Wikipedia returned {response.status_code}."
            )

        payload = response.json()
        if payload.get("type") not in ("standard", "disambiguation"):
            raise KeyError(company_name)
        description = re.sub(r"\s+", " ", str(payload.get("extract") or "")).strip()
        if not description:
            raise KeyError(company_name)

        verified = ["description"]
        return CompanyInfo(
            name=company_name.strip(),
            industry=None,
            description=description,
            products_services=[],
            company_size=None,
            headquarters=payload.get("description") or None,
            technology_areas=[],
            recent_news=[],
            website=(payload.get("content_urls") or {}).get("desktop", {}).get("page"),
            source=self.name,
            is_mock=False,
            verified_fields=verified,
            inferred_fields=[],
        )

    @staticmethod
    def _to_title(company_name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9&. \-]", " ", company_name).strip()
        cleaned = re.sub(r"\s+(Inc|Corp|Corporation|Ltd|LLC|GmbH|Pvt)$", "", cleaned,
                         flags=re.IGNORECASE)
        return cleaned.strip()


__all__ = ["WikipediaCompanySource"]
