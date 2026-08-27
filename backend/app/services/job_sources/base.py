"""JobSource abstraction: pluggable providers of raw job listings.

Phase 4 aggregation:

    JobDiscoveryAgent → JobSourceManager → [ProviderAdapter × N]

Core application code never imports a concrete provider; everything is wired
through configuration (ENABLE_* flags / credentials).
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

from app.config import get_settings
from app.schemas.jobs import JobSearchPreferences, ProviderStatus, RawJob


class JobSourceError(Exception):
    """Raised when a job source fails or is misconfigured."""


@runtime_checkable
class JobSource(Protocol):
    """Any provider of raw jobs."""

    name: str

    def search_jobs(
        self,
        query: JobSearchPreferences,
        strategy_queries: list[str],
    ) -> list[RawJob]:
        """Return raw jobs matching the strategy. May return fewer than asked."""
        ...


class ProviderAdapter:
    """Uniform wrapper adding retries and error capture per provider."""

    def __init__(self, name: str, display_name: str, source_type: str,
                 enabled: bool, search_fn) -> None:
        self.name = name
        self.display_name = display_name
        self.source_type = source_type
        self.enabled = enabled
        self._search_fn = search_fn

    def run(self, preferences: JobSearchPreferences,
            strategy_queries: list[str]) -> tuple[list[RawJob], ProviderStatus]:
        settings = get_settings()
        attempts = max(1, 1 + settings.max_provider_retries)
        for attempt in range(attempts):
            try:
                jobs = self._search_fn(preferences, strategy_queries)
                status_value = "success" if jobs else "empty"
                return jobs, ProviderStatus(
                    name=self.display_name,
                    source_type=self.source_type,
                    status=status_value,
                    count=len(jobs),
                    enabled=True,
                )
            except Exception:  # noqa: BLE001 - isolation is the point
                if attempt < attempts - 1:
                    time.sleep(0.5 * (2 ** attempt))
        return [], ProviderStatus(
            name=self.display_name,
            source_type=self.source_type,
            status="error",
            count=0,
            enabled=True,
            message="Some job sources are temporarily unavailable.",
        )


__all__ = ["JobSource", "JobSourceError", "ProviderAdapter"]
