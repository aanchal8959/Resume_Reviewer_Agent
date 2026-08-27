"""Job Analysis Agent: job description text -> validated JobProfile."""

from __future__ import annotations

from app.agents.base import EXTRACTION_RULES, AgentError
from app.schemas.job import JobProfile
from app.services.llm_service import LLMError, LLMProvider

_SYSTEM_PROMPT = (
    "You are a precise technical recruiter. You extract structured requirements "
    "from job descriptions.\n" + EXTRACTION_RULES +
    "5. Clearly distinguish REQUIRED skills from PREFERRED (nice-to-have) skills; "
    "never merge them.\n"
)


def build_user_prompt(job_description_text: str) -> str:
    return (
        "Extract the structured job profile from the following job description.\n\n"
        f"<job_description>\n{job_description_text}\n</job_description>"
    )


class JobAnalysisAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def run(self, job_description_text: str) -> JobProfile:
        try:
            return self._provider.generate_structured(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=build_user_prompt(job_description_text),
                response_model=JobProfile,
                context={"job_description_text": job_description_text},
            )
        except LLMError as exc:
            raise AgentError(f"Job analysis failed: {exc}") from exc
