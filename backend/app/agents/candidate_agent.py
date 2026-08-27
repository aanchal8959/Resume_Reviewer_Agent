"""Candidate Profile Agent: resume text -> validated CandidateProfile."""

from __future__ import annotations

from app.agents.base import EXTRACTION_RULES, AgentError
from app.schemas.candidate import CandidateProfile
from app.services.llm_service import LLMError, LLMProvider

_SYSTEM_PROMPT = (
    "You are a precise recruitment analyst. You extract structured candidate "
    "profiles from resumes.\n" + EXTRACTION_RULES
)


def build_user_prompt(resume_text: str) -> str:
    return (
        "Extract the candidate profile from the following resume.\n\n"
        f"<resume>\n{resume_text}\n</resume>"
    )


class CandidateProfileAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def run(self, resume_text: str) -> CandidateProfile:
        try:
            return self._provider.generate_structured(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=build_user_prompt(resume_text),
                response_model=CandidateProfile,
                context={"resume_text": resume_text},
            )
        except LLMError as exc:
            raise AgentError(f"Candidate profile extraction failed: {exc}") from exc
