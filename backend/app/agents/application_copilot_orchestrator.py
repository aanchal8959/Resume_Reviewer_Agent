"""Phase 3 LangGraph pipeline: full application preparation.

Composes the existing services as graph nodes:
    load_context → [tailor_resume, research_company] → generate_cover_letter
                 → generate_questions → finalize

Degraded company research must not fail the run (explicit product rule).
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.schemas.applications import ApplicationDetail


class CopilotState(TypedDict):
    application_id: str

    tailored: bool
    researched: bool
    cover_letter_ready: bool
    questions_ready: bool

    detail: dict | None
    errors: Annotated[list[str], operator.add]


class ApplicationCopilotPipeline:
    """Runs the complete preparation workflow for one application."""

    def __init__(self, service) -> None:
        self._service = service
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        builder: StateGraph = StateGraph(CopilotState)
        builder.add_node("tailor_resume", self._node_tailor)
        builder.add_node("research_company", self._node_research)
        builder.add_node("generate_cover_letter", self._node_cover_letter)
        builder.add_node("generate_questions", self._node_questions)
        builder.add_node("finalize", self._node_finalize)

        builder.add_edge(START, "tailor_resume")
        builder.add_edge("tailor_resume", "research_company")
        builder.add_edge("research_company", "generate_cover_letter")
        builder.add_edge("generate_cover_letter", "generate_questions")
        builder.add_edge("generate_questions", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile()

    def _node_tailor(self, state: CopilotState) -> dict:
        try:
            self._service.tailor_resume(state["application_id"])
            return {"tailored": True}
        except Exception as exc:  # noqa: BLE001 - surfaced in errors channel
            return {"errors": [f"Resume tailoring failed: {exc}"]}

    def _node_research(self, state: CopilotState) -> dict:
        from app.services.company_research.base import CompanyResearchError

        try:
            self._service.research_company(state["application_id"])
            return {"researched": True}
        except CompanyResearchError as exc:
            return {"researched": False,
                    "errors": [f"Company research unavailable ({exc}). You can "
                               "still prepare using the job description."]}
        except Exception as exc:  # noqa: BLE001
            return {"researched": False,
                    "errors": [f"Company research failed: {exc}"]}

    def _node_cover_letter(self, state: CopilotState) -> dict:
        try:
            self._service.generate_cover_letter(
                state["application_id"],
                regenerate=state.get("cover_letter_ready", False),
            )
            return {"cover_letter_ready": True}
        except Exception as exc:  # noqa: BLE001
            return {"errors": [f"Cover letter generation failed: {exc}"]}

    def _node_questions(self, state: CopilotState) -> dict:
        try:
            self._service.generate_questions(
                state["application_id"],
                regenerate=state.get("questions_ready", False),
            )
            return {"questions_ready": True}
        except Exception as exc:  # noqa: BLE001
            return {"errors": [f"Question generation failed: {exc}"]}

    def _node_finalize(self, state: CopilotState) -> dict:
        try:
            detail = self._service.get_detail(state["application_id"])
            return {"detail": detail.model_dump(mode="json")}
        except Exception as exc:  # noqa: BLE001
            return {"errors": [f"Failed to assemble result: {exc}"]}

    def run(self, application_id: str) -> tuple[ApplicationDetail | None, list[str]]:
        final: CopilotState = self._graph.invoke({
            "application_id": application_id,
            "tailored": False,
            "researched": False,
            "cover_letter_ready": False,
            "questions_ready": False,
            "detail": None,
            "errors": [],
        })
        detail = None
        if final.get("detail"):
            detail = ApplicationDetail.model_validate(final["detail"])
        return detail, list(final.get("errors") or [])
