"""Cover Letter Agent and Application Questions Agent (Gemini-powered)."""

from __future__ import annotations

from app.config import get_settings
from app.schemas.applications import (
    ApplicationQuestionItem,
    CompanyInfo,
    CoverLetterDraft,
    QuestionSet,
)
from app.schemas.candidate import CandidateProfile
from app.services.llm_service import LLMError, LLMProvider


class CoverLetterAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def generate(
        self,
        candidate: CandidateProfile,
        job_title: str,
        company: str,
        matched_skills: list[str],
        company_info: CompanyInfo | None = None,
        tailored_context: str | None = None,
    ) -> CoverLetterDraft:
        try:
            draft = self._provider.generate_structured(
                system_prompt=(
                    "You write concise, personalized cover letters (300-500 "
                    "words). RULES: mention only experience evidenced by the "
                    "candidate profile; no generic filler; never invent skills, "
                    "employers or metrics; do not include contact details."
                ),
                user_prompt=(
                    f"Candidate:\n{candidate.model_dump_json()}\n\n"
                    f"Role: {job_title} at {company}\n"
                    f"Verified matched skills: {', '.join(matched_skills)}\n"
                    + (f"Company notes: {company_info.description}"
                       if company_info else "")
                    + (f"\nTailored resume highlights:\n{tailored_context}"
                       if tailored_context else "")
                ),
                response_model=CoverLetterDraft,
                context={
                    "candidate": candidate,
                    "job_title": job_title,
                    "company": company,
                    "matched_skills": matched_skills,
                    "company_info": company_info,
                },
            )
            if draft.word_count == 0:
                draft = draft.model_copy(update={
                    "word_count": len(draft.content_text.split())
                })
        except LLMError as exc:
            raise LLMError(f"Cover letter generation failed: {exc}") from exc
        return draft


class ApplicationQuestionsAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def generate(
        self,
        candidate: CandidateProfile,
        job_title: str,
        required_skills: list[str],
        missing_skills: list[str],
        salary_text: str | None,
        skill_evidence: dict[str, str] | None = None,
    ) -> list[ApplicationQuestionItem]:
        projects = [
            (p.name, [t for t in p.technologies]) for p in candidate.projects
        ]
        try:
            result = self._provider.generate_structured(
                system_prompt=(
                    "You generate likely job application questions with "
                    "suggested answers grounded STRICTLY in the candidate's "
                    "real profile. Where information is missing, answer with "
                    "clear placeholders for the candidate to fill in. Always "
                    "include at least two technical questions about the key "
                    "required skills."
                ),
                user_prompt=(
                    f"Candidate profile:\n{candidate.model_dump_json()}\n\n"
                    f"Target role: {job_title}\n"
                    f"Key requirements: {required_skills}\n"
                    f"Known gaps: {missing_skills}"
                ),
                response_model=QuestionSet,
                context={
                    "candidate": candidate,
                    "job_title": job_title,
                    "required_skills": required_skills,
                    "missing_skills": missing_skills,
                    "salary_text": salary_text,
                    "candidate_projects": projects,
                    "skill_evidence": skill_evidence or {},
                },
            )
            items = [
                item.model_copy(update={"order_index": index})
                for index, item in enumerate(result.items)
            ]
        except LLMError as exc:
            raise LLMError(f"Question generation failed: {exc}") from exc

        # Guarantee at least one technical question even for skill-light JDs.
        if not any(item.category == "technical" for item in items):
            fallback_skill = (
                required_skills[0] if required_skills
                else next(iter(candidate.all_skills()), "your core stack")
            )
            project_name = projects[0][0] if projects else "my key project"
            items.append(ApplicationQuestionItem(
                question=f"Describe your experience with {fallback_skill}.",
                suggested_answer=(
                    f"My hands-on experience is documented in my resume "
                    f"(see '{project_name}'). I would walk through what I "
                    "built, the problems I hit and how I solved them."
                ),
                category="technical",
                order_index=len(items),
            ))
        return items
