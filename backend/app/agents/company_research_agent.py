"""Company Research Agent: company name -> info + role-specific insights."""

from __future__ import annotations

from app.schemas.applications import CompanyInfo, CompanyInsights
from app.services.company_research.base import (
    CompanyResearchError,
    CompanyResearchSource,
)
from app.services.copilot_templates import build_company_insights


class UnknownCompanyError(CompanyResearchError):
    """Company not present in the configured source."""


class CompanyResearchAgent:
    def __init__(self, source: CompanyResearchSource) -> None:
        self._source = source

    def research(
        self,
        company_name: str,
        job_title: str,
        job_skills: list[str],
        prep_areas: list[str],
    ) -> tuple[CompanyInfo, CompanyInsights]:
        try:
            info = self._source.get_company_info(company_name)
        except KeyError as exc:
            raise UnknownCompanyError(
                f"No public information available for '{company_name}' in the "
                "configured source."
            ) from exc
        except Exception as exc:  # noqa: BLE001 - sources may fail in many ways
            raise CompanyResearchError(f"Company research failed: {exc}") from exc

        insights = build_company_insights(info, job_title, job_skills, prep_areas)
        return info, CompanyInsights(**insights)
