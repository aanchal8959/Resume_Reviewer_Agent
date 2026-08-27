"""CompanyResearchSource abstraction (real public data only).

Current provider: Wikipedia REST summary API — public, documented, keyless.
When a company has no article, the source raises UnknownCompanyError and the
application degrades gracefully per spec ("Company research unavailable...").
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.applications import CompanyInfo


class CompanyResearchError(Exception):
    """Raised when a company source fails or is misconfigured."""


@runtime_checkable
class CompanyResearchSource(Protocol):
    name: str

    def get_company_info(self, company_name: str) -> CompanyInfo:
        """Return structured public info; unknown companies raise
        CompanyResearchError so callers degrade gracefully."""
        ...


def get_company_source() -> CompanyResearchSource:
    from app.services.company_research.wikipedia_source import WikipediaCompanySource

    return WikipediaCompanySource()


__all__ = ["CompanyResearchError", "CompanyResearchSource", "get_company_source"]
