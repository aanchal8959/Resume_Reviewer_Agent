"""LangGraph orchestration of the Job Switch Agent pipeline.

Graph:
    START -> process_documents -> [candidate_agent, job_agent] (parallel)
          -> skill_gap_agent -> match_scorer -> roadmap_agent -> END

State flows between nodes as structured dicts; every agent output is a
validated Pydantic model serialized into the state.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.base import AgentError
from app.agents.candidate_agent import CandidateProfileAgent
from app.agents.job_agent import JobAnalysisAgent
from app.agents.roadmap_agent import RoadmapAgent
from app.agents.skill_gap_agent import SkillGapAgent
from app.config import get_settings
from app.schemas.analysis import SkillGapAnalysis
from app.services.llm_service import LLMProvider, get_llm_provider
from app.services.match_scorer import DEFAULT_WEIGHTS, compute_match_score

MAX_TEXT_CHARS = 60_000


class JobSwitchState(TypedDict):
    session_id: str
    resume_text: str
    job_description_text: str

    candidate_profile: dict | None
    job_profile: dict | None

    matched_skills: list[str]
    missing_skills: list[str]
    partial_skills: list[str]

    skill_gap: dict | None
    match_score: dict | None
    roadmap: dict | None

    errors: Annotated[list[str], operator.add]


class Orchestrator:
    """Builds and executes the analysis graph."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self._provider = provider or get_llm_provider()
        self._weights = weights or get_settings().match_weights or DEFAULT_WEIGHTS
        self._candidate_agent = CandidateProfileAgent(self._provider)
        self._job_agent = JobAnalysisAgent(self._provider)
        self._skill_gap_agent = SkillGapAgent(self._provider)
        self._roadmap_agent = RoadmapAgent(self._provider)
        self._graph = self._build_graph()

    # -- graph construction --------------------------------------------------
    def _build_graph(self) -> StateGraph:
        builder: StateGraph = StateGraph(JobSwitchState)
        builder.add_node("process_documents", self._node_process_documents)
        builder.add_node("candidate_agent", self._node_candidate_profile)
        builder.add_node("job_agent", self._node_job_analysis)
        builder.add_node("skill_gap_agent", self._node_skill_gap)
        builder.add_node("match_scorer", self._node_match_score)
        builder.add_node("roadmap_agent", self._node_roadmap)

        builder.add_edge(START, "process_documents")
        builder.add_conditional_edges(
            "process_documents",
            self._route_after_documents,
            ["candidate_agent", "job_agent"],
        )
        builder.add_edge("candidate_agent", "skill_gap_agent")
        builder.add_edge("job_agent", "skill_gap_agent")
        builder.add_edge("skill_gap_agent", "match_scorer")
        builder.add_edge("match_scorer", "roadmap_agent")
        builder.add_edge("roadmap_agent", END)
        return builder.compile()

    @staticmethod
    def _route_after_documents(state: JobSwitchState) -> list[str]:
        """Fan out to both agents, or terminate early on document errors."""
        return [] if state.get("errors") else ["candidate_agent", "job_agent"]

    # -- nodes -----------------------------------------------------------------
    def _node_process_documents(self, state: JobSwitchState) -> dict:
        updates: dict = {}
        errors: list[str] = []
        for key, label in (
            ("resume_text", "Resume"),
            ("job_description_text", "Job description"),
        ):
            text = (state.get(key) or "").strip()
            if not text:
                errors.append(f"{label} document contains no extractable text.")
            else:
                updates[key] = text[:MAX_TEXT_CHARS]
        if errors:
            updates["errors"] = errors
        return updates

    def _node_candidate_profile(self, state: JobSwitchState) -> dict:
        try:
            profile = self._candidate_agent.run(state["resume_text"])
            return {"candidate_profile": profile.model_dump()}
        except AgentError as exc:
            return {"candidate_profile": None, "errors": [str(exc)]}

    def _node_job_analysis(self, state: JobSwitchState) -> dict:
        try:
            profile = self._job_agent.run(state["job_description_text"])
            return {"job_profile": profile.model_dump()}
        except AgentError as exc:
            return {"job_profile": None, "errors": [str(exc)]}

    def _node_skill_gap(self, state: JobSwitchState) -> dict:
        candidate_raw, job_raw = state.get("candidate_profile"), state.get("job_profile")
        if candidate_raw is None or job_raw is None:
            return {"matched_skills": [], "missing_skills": [], "partial_skills": []}
        from app.schemas.candidate import CandidateProfile
        from app.schemas.job import JobProfile

        candidate = CandidateProfile.model_validate(candidate_raw)
        job = JobProfile.model_validate(job_raw)
        try:
            gap = self._skill_gap_agent.run(candidate, job)
        except AgentError as exc:
            return {"errors": [str(exc)], "matched_skills": [], "missing_skills": [],
                    "partial_skills": []}
        return {
            "matched_skills": gap.matched,
            "missing_skills": gap.missing,
            "partial_skills": gap.partial,
            "skill_gap": gap.model_dump(),
        }

    def _node_match_score(self, state: JobSwitchState) -> dict:
        candidate_raw, job_raw = state.get("candidate_profile"), state.get("job_profile")
        if candidate_raw is None or job_raw is None:
            return {}
        from app.schemas.candidate import CandidateProfile
        from app.schemas.job import JobProfile

        score = compute_match_score(
            CandidateProfile.model_validate(candidate_raw),
            JobProfile.model_validate(job_raw),
            weights=self._weights,
        )
        return {"match_score": score.model_dump()}

    def _node_roadmap(self, state: JobSwitchState) -> dict:
        gap_raw = state.get("skill_gap")
        if not gap_raw:
            return {"errors": ["Roadmap skipped: no skill gap analysis available."]}
        gap = SkillGapAnalysis.model_validate(gap_raw)
        score_model = None
        if state.get("match_score"):
            from app.schemas.analysis import MatchScore

            score_model = MatchScore.model_validate(state["match_score"])
        roadmap = self._roadmap_agent.run(gap, score_model)
        return {"roadmap": roadmap.model_dump()}

    # -- execution ---------------------------------------------------------------
    def run(
        self,
        resume_text: str,
        job_description_text: str,
        session_id: str = "adhoc",
    ) -> JobSwitchState:
        initial: JobSwitchState = {
            "session_id": session_id,
            "resume_text": resume_text,
            "job_description_text": job_description_text,
            "candidate_profile": None,
            "job_profile": None,
            "matched_skills": [],
            "missing_skills": [],
            "partial_skills": [],
            "match_score": None,
            "roadmap": None,
            "errors": [],
        }
        final: JobSwitchState = self._graph.invoke(
            initial,
            config={
                "metadata": {"session_id": session_id},
                "run_name": "phase1-analysis",
                "tags": ["phase1", "analysis"],
            },
        )
        return final
