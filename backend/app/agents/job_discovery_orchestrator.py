"""Phase 2 LangGraph pipeline: discovery → normalization → dedupe → match → rank.

A separate graph from Phase 1's analysis workflow; both share the same LLM
provider abstraction, skill vocabulary and database layer.
"""

from __future__ import annotations

import operator
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.schemas.candidate import CandidateProfile
from app.schemas.jobs import Job, JobSearchPreferences, RawJob
from app.services.duplicate_detector import DuplicateDetector
from app.services.job_matcher import JobMatchingService
from app.services.job_normalizer import JobNormalizer
from app.services.llm_service import LLMProvider, get_llm_provider
from app.services.ranking import RankingService
from app.services.skill_normalizer import SkillNormalizer, get_skill_normalizer


class JobDiscoveryState(TypedDict):
    search_id: str

    candidate: dict | None
    preferences: dict
    strategy: dict | None

    raw_jobs: Annotated[list, operator.add]
    normalized_jobs: list
    canonical_jobs: list
    matches: list
    recommendations: list

    sources_status: list
    metadata: dict
    errors: Annotated[list[str], operator.add]


class JobDiscoveryPipeline:
    """Builds and executes the Phase 4 search flow for one search session.

    Order per spec: cache first (TTL-based); on miss/staleness query every
    enabled provider through the JobSourceManager; failures are isolated.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        source_manager=None,
        skill_normalizer: SkillNormalizer | None = None,
        refresh: bool = False,
    ) -> None:
        self._provider = provider or get_llm_provider()
        self._source_manager = source_manager
        self._skills = skill_normalizer or get_skill_normalizer()
        self._normalizer = JobNormalizer(self._provider, self._skills)
        self._detector = DuplicateDetector(self._skills)
        self._matcher = JobMatchingService(self._skills)
        self._ranker = RankingService(self._matcher)
        self._refresh = refresh
        if self._source_manager is None:
            from app.services.job_sources.manager import JobSourceManager

            self._source_manager = JobSourceManager()
        self._graph = self._build_graph()

    # -- graph ---------------------------------------------------------------
    def _build_graph(self) -> StateGraph:
        builder: StateGraph = StateGraph(JobDiscoveryState)
        builder.add_node("build_strategy", self._node_build_strategy)
        builder.add_node("discover", self._node_discover)
        builder.add_node("normalize", self._node_normalize)
        builder.add_node("deduplicate", self._node_deduplicate)
        builder.add_node("match", self._node_match)
        builder.add_node("rank", self._node_rank)

        builder.add_edge(START, "build_strategy")
        builder.add_conditional_edges(
            "build_strategy",
            lambda state: [] if state.get("errors") else ["discover"],
            ["discover"],
        )
        builder.add_edge("discover", "normalize")
        builder.add_edge("normalize", "deduplicate")
        builder.add_edge("deduplicate", "match")
        builder.add_edge("match", "rank")
        builder.add_edge("rank", END)
        return builder.compile()

    # -- nodes -----------------------------------------------------------------
    def _node_build_strategy(self, state: JobDiscoveryState) -> dict:
        from app.agents.discovery_agent import build_strategy

        candidate_raw = state.get("candidate")
        if candidate_raw is None:
            return {"errors": ["Candidate profile unavailable; cannot personalize search."]}
        try:
            candidate = CandidateProfile.model_validate(candidate_raw)
            preferences = JobSearchPreferences.model_validate(state["preferences"])
            strategy = build_strategy(candidate, preferences)
        except Exception as exc:  # noqa: BLE001 - validation failures surface to user
            return {"errors": [f"Search strategy failed: {exc}"]}
        return {"strategy": strategy.model_dump()}

    def _node_discover(self, state: JobDiscoveryState) -> dict:
        from datetime import datetime, timezone

        from app.schemas.jobs import RawJob, SearchMetadata
        from app.services.job_sources.cache import lookup_cached_jobs

        strategy = state["strategy"]
        preferences = JobSearchPreferences.model_validate(state["preferences"])
        started = datetime.now(timezone.utc)
        manager: JobSourceManager = self._source_manager or JobSourceManager()

        # 1) Cache first (unless explicit refresh).
        if not self._refresh:
            from app.database.database import get_database

            with get_database().session() as db:
                cached_rows, fresh = lookup_cached_jobs(
                    db, strategy.get("queries") or [], preferences,
                )
            if fresh and len(cached_rows) >= 5:
                raws = [_row_to_raw(row) for row in cached_rows]
                duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
                return {
                    "raw_jobs": [r.model_dump(mode="json") for r in raws],
                    "sources_status": [{
                        "name": "Local cache", "source_type": "REAL",
                        "status": "success", "count": len(raws), "enabled": True,
                    }],
                    "metadata": SearchMetadata(
                        live_results=False, cached_results=True,
                        discovered=len(raws),
                        duration_ms=duration_ms,
                    ).model_dump(),
                }

        # 2) External providers (failures isolated per provider).
        merged, statuses = manager.search(
            preferences, strategy.get("queries") or []
        )

        validated: list[RawJob] = []
        errors: list[str] = []
        for raw in merged:
            try:
                validated.append(RawJob.model_validate(
                    raw if isinstance(raw, dict) else raw.model_dump()
                ))
            except Exception:  # noqa: BLE001 - one bad record must not kill the batch
                errors.append("Discarded an invalid job record")
        duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {
            "raw_jobs": [job.model_dump(mode="json") for job in validated],
            "sources_status": [status.model_dump() for status in statuses],
            "metadata": SearchMetadata(
                live_results=True, cached_results=False,
                discovered=len(validated), duration_ms=duration_ms,
            ).model_dump(),
            "errors": errors,
        }

    def _node_normalize(self, state: JobDiscoveryState) -> dict:
        normalized: list[Job] = []
        errors: list[str] = []
        for payload in state.get("raw_jobs", []):
            try:
                normalized.append(
                    self._normalizer.normalize(RawJob.model_validate(payload))
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Normalization failed for one job: {exc}")
        return {"normalized_jobs": [job.model_dump(mode="json") for job in normalized],
                "errors": errors}

    def _node_deduplicate(self, state: JobDiscoveryState) -> dict:
        jobs = [Job.model_validate(payload) for payload in state.get("normalized_jobs", [])]
        canonical = self._detector.deduplicate(jobs)
        return {"canonical_jobs": [job.model_dump(mode="json") for job in canonical]}

    def _node_match(self, state: JobDiscoveryState) -> dict:
        candidate = CandidateProfile.model_validate(state["candidate"])
        preferences = JobSearchPreferences.model_validate(state["preferences"])
        pairs: list[tuple[Job, object]] = []
        for payload in state.get("canonical_jobs", []):
            job = Job.model_validate(payload)
            match = self._matcher.match(candidate, job, preferences)
            match = RankingService.apply_filters(match)
            pairs.append((job, match))
        return {"matches": [
            {"job": job.model_dump(mode="json"), "match": match.model_dump()}
            for job, match in pairs
        ]}

    def _node_rank(self, state: JobDiscoveryState) -> dict:
        from app.schemas.jobs import JobMatch

        preferences = JobSearchPreferences.model_validate(state["preferences"])
        pairs: list[tuple[Job, JobMatch]] = [
            (Job.model_validate(entry["job"]),
             JobMatch.model_validate(entry["match"]))
            for entry in state.get("matches", [])
        ]
        recommendations = self._ranker.rank(pairs, preferences)
        return {"recommendations": [rec.model_dump(mode="json") for rec in recommendations]}

    # -- execution ---------------------------------------------------------------
    def run(
        self,
        candidate: CandidateProfile,
        preferences: JobSearchPreferences,
        search_id: str,
    ) -> JobDiscoveryState:
        initial: JobDiscoveryState = {
            "search_id": search_id,
            "candidate": candidate.model_dump(),
            "preferences": preferences.model_dump(),
            "strategy": None,
            "raw_jobs": [],
            "normalized_jobs": [],
            "canonical_jobs": [],
            "matches": [],
            "recommendations": [],
            "sources_status": [],
            "metadata": {},
            "errors": [],
        }
        return self._graph.invoke(initial)


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite round-trips naive datetimes; treat them as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _row_to_raw(row) -> RawJob:
    """Convert a cached canonical JobRow back into a RawJob.

    Re-normalization is intentionally idempotent so cached and live jobs flow
    through the exact same normalize -> dedupe -> match -> rank path.
    """
    salary_text = None
    if row.salary_min is not None and row.salary_max is not None:
        currency = row.salary_currency or ""
        salary_text = f"{row.salary_min:g}-{row.salary_max:g} {currency}".strip()
    return RawJob(
        source=row.first_source,
        source_type=(getattr(row, "source_type", None) or "REAL"),
        source_job_id=row.source_job_id,
        title=row.title,
        company=row.company,
        description=row.description or "",
        location=row.location,
        work_mode=row.work_mode or "unknown",
        employment_type=row.employment_type,
        experience_level=getattr(row, "experience_level", None),
        salary_text=salary_text,
        url=row.application_url,
        posted_at=_as_utc(row.posted_at),
    )



