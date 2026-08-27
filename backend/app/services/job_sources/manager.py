"""JobSourceManager: multi-provider aggregation with independent failure.

Queries every enabled provider, isolates failures, merges results and reports
per-provider status. A failing provider never fails the search. With no
providers configured the search simply returns zero results plus statuses.
"""

from __future__ import annotations

from app.config import get_settings
from app.schemas.jobs import JobSearchPreferences, ProviderStatus, RawJob


class JobSourceManager:
    """Loads enabled providers and aggregates their results."""

    def __init__(self, adapters: list | None = None) -> None:
        self._settings = get_settings()
        self.adapters = adapters if adapters is not None \
            else self._build_adapters(self._settings)
        # In-process health registry (name -> last success timestamp).
        self.last_success_at: dict[str, float] = {}

    @classmethod
    def _build_adapters(cls, settings) -> list:
        from app.services.job_sources.base import ProviderAdapter

        adapters: list = []

        def add(name: str, display_name: str, source) -> None:
            adapters.append(ProviderAdapter(
                name, display_name, "REAL", True,
                source.search_jobs,
            ))

        if settings.enable_remotive:
            from app.services.job_sources.remotive_source import RemotiveJobSource

            add("remotive", "Remotive", RemotiveJobSource(
                max_results_per_query=settings.job_search_results_per_query,
                timeout_seconds=settings.provider_timeout_seconds,
            ))
        if settings.enable_arbeitnow:
            from app.services.job_sources.arbeitnow_source import ArbeitnowJobSource

            add("arbeitnow", "Arbeitnow", ArbeitnowJobSource(
                max_results_per_query=settings.job_search_results_per_query,
                timeout_seconds=settings.provider_timeout_seconds,
            ))
        if settings.enable_jobicy:
            from app.services.job_sources.jobicy_source import JobicyJobSource

            add("jobicy", "Jobicy", JobicyJobSource(
                max_results_per_query=settings.job_search_results_per_query,
                timeout_seconds=settings.provider_timeout_seconds,
            ))
        adzuna = cls._adzuna(settings)
        if adzuna is not None:
            add("adzuna", "Adzuna", adzuna)
        greenhouse = cls._greenhouse(settings)
        if greenhouse is not None:
            add("greenhouse", "Company Career Boards", greenhouse)
        return adapters

    @staticmethod
    def _adzuna(settings):
        if not settings.adzuna_app_id or not settings.adzuna_api_key:
            return None
        from app.services.job_sources.adzuna_source import AdzunaJobSource

        try:
            return AdzunaJobSource.from_settings(settings)
        except Exception:  # noqa: BLE001 - misconfigured providers are skipped
            return None

    @staticmethod
    def _greenhouse(settings):
        if not (settings.greenhouse_companies or "").strip():
            return None
        from app.services.job_sources.greenhouse_source import GreenhouseCompanySource

        try:
            return GreenhouseCompanySource.from_settings(settings)
        except Exception:  # noqa: BLE001
            return None

    @property
    def provider_names(self) -> list[str]:
        return [a.display_name for a in self.adapters]

    def search(
        self,
        preferences: JobSearchPreferences,
        strategy_queries: list[str],
    ) -> tuple[list[RawJob], list[ProviderStatus]]:
        merged: list[RawJob] = []
        seen: set[tuple[str, str]] = set()
        statuses: list[ProviderStatus] = []
        for adapter in self.adapters:
            jobs, status = adapter.run(preferences, strategy_queries)
            statuses.append(status)
            if status.status == "success":
                import time as _time

                self.last_success_at[adapter.name] = _time.time()
            for raw in jobs:
                key = (raw.source, str(raw.source_job_id))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(raw)
        return merged, statuses

    def health(self) -> list[dict]:
        import time as _time

        now = _time.time()
        report: list[dict] = []
        for adapter in self.adapters:
            last = self.last_success_at.get(adapter.name)
            healthy = None
            if last is not None:
                healthy = (now - last) < 3600
            report.append({
                "name": adapter.display_name,
                "source": adapter.name,
                "source_type": adapter.source_type,
                "enabled": adapter.enabled,
                "healthy": healthy,
                "status": (
                    "healthy" if healthy
                    else "unknown"
                ),
            })
        return report


def get_job_source_manager() -> JobSourceManager:
    return JobSourceManager()


__all__ = ["JobSourceManager", "get_job_source_manager"]
