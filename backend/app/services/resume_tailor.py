"""Resume Tailoring service.

Rewrites the candidate's resume for one job WITHOUT fabricating anything:
- vague verbs upgraded ("worked on" -> "Developed")
- acronyms expanded once (RAG -> RAG (Retrieval Augmented Generation))
- most relevant bullet gets a relevance clause tied to the target role
- skills regrouped; projects reordered by relevance
Every edit is logged with original/updated/reason/type and then passed through
the Truthfulness Validator; unsupported edits are flagged, never hidden.
"""

from __future__ import annotations

import re

from app.agents.base import AgentError
from app.schemas.applications import (
    ChangeType,
    ResumeChange,
    TailoredResume,
)
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobProfile
from app.services.llm_service import LLMError, LLMProvider
from app.services.skill_vocabulary import find_known_skills
from app.services.skill_normalizer import SkillNormalizer
from app.services.truthfulness import (
    ResumeTruthfulnessValidator,
    mark_changes_support,
)

_VAGUE_VERBS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bworked on\b", re.IGNORECASE), "Developed"),
    (re.compile(r"\bhelped (?:with|to)?\b", re.IGNORECASE), "Contributed to"),
    (re.compile(r"\bassisted (?:with|in)\b", re.IGNORECASE), "Supported delivery of"),
    (re.compile(r"\bresponsible for\b", re.IGNORECASE), "Owned"),
)

_ACRONYM_EXPANSIONS: tuple[tuple[str, str], ...] = (
    ("RAG", "Retrieval Augmented Generation"),
    ("LLM", "Large Language Model"),
    ("GenAI", "Generative AI"),
    ("NLP", "Natural Language Processing"),
)

_SECTION_HEADERS = {
    "summary": ("SUMMARY", "PROFILE", "ABOUT"),
    "experience": ("EXPERIENCE", "WORK EXPERIENCE", "EMPLOYMENT"),
    "education": ("EDUCATION",),
    "skills": ("SKILLS",),
    "projects": ("PROJECTS", "KEY PROJECTS"),
    "certifications": ("CERTIFICATIONS", "CERTIFICATION"),
}


def _split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip().rstrip(":")
        matched_header = None
        for key, headers in _SECTION_HEADERS.items():
            if stripped.upper() in headers:
                matched_header = key
                break
        if matched_header:
            current = matched_header
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
        else:
            sections.setdefault("header", []).append(line)
    return sections


def _expand_acronyms_once(line: str) -> tuple[str, list[str]]:
    expansions: list[str] = []
    result = line
    for acronym, expansion in _ACRONYM_EXPANSIONS:
        pattern = re.compile(rf"\b{acronym}\b(?!\s*\()")
        if pattern.search(result):
            result = pattern.sub(f"{acronym} ({expansion})", result, count=1)
            expansions.append(acronym)
    return result, expansions


def _skill_overlap_count(line: str, wanted: set[str], skills: SkillNormalizer) -> int:
    line_keys = skills.keys_for_list(find_known_skills(line))
    return len(line_keys & wanted)


def _group_skills(skills: list[str]) -> list[tuple[str, list[str]]]:
    groups: dict[str, list[str]] = {
        "Languages": [], "Frameworks": [], "AI / ML": [],
        "Cloud & DevOps": [], "Databases": [], "Other": [],
    }
    buckets = {
        "Languages": {"Python", "Java", "JavaScript", "TypeScript", "Go", "SQL",
                      "Bash", "C++"},
        "Frameworks": {"FastAPI", "Flask", "Django", "React", "Next.js", "Node.js",
                       "LangChain", "LangGraph", "GraphQL"},
        "AI / ML": {"Machine Learning", "Deep Learning", "NLP", "PyTorch",
                    "TensorFlow", "RAG", "LLM", "GenAI", "Vector Databases",
                    "FAISS", "Vertex AI", "Prompt Engineering", "Embeddings"},
        "Cloud & DevOps": {"AWS", "GCP", "Azure", "Docker", "Kubernetes",
                           "Terraform", "CI/CD", "Git"},
        "Databases": {"PostgreSQL", "MySQL", "MongoDB", "Redis", "BigQuery",
                      "Snowflake"},
    }
    for skill in skills:
        placed = False
        for group, members in buckets.items():
            if skill in members:
                groups[group].append(skill)
                placed = True
                break
        if not placed:
            groups["Other"].append(skill)
    return [(name, members) for name, members in groups.items() if members]


class ResumeTailoringService:
    def __init__(self, provider: LLMProvider, skills: SkillNormalizer) -> None:
        self._provider = provider
        self._skills = skills

    def tailor(
        self,
        resume_text: str,
        candidate: CandidateProfile,
        job: JobProfile,
        missing_skills: list[str] | None = None,
    ) -> TailoredResume:
        try:
            tailored = self._provider.generate_structured(
                system_prompt=(
                    "You tailor resumes to a target job description. "
                    "RULES: never invent employers, titles, technologies, "
                    "education or experience; only rephrase, reorder and "
                    "highlight what the original resume already contains. "
                    "Log every edit in `changes` with section/original/"
                    "updated/reason/type."
                ),
                user_prompt=(
                    f"Original resume:\n<resume>\n{resume_text}\n</resume>\n\n"
                    f"Target job:\n<job>\n{job.model_dump_json()}\n</job>\n\n"
                    "Return a complete tailored resume in markdown under "
                    "`content_markdown`, plus `changes` (original vs updated "
                    "per edit), a one-line `summary` and 2-3 `recommendations`."
                ),
                response_model=TailoredResume,
                context={"resume_text": resume_text},
            )
        except LLMError as exc:
            raise AgentError(f"Resume tailoring failed: {exc}") from exc

        report = ResumeTruthfulnessValidator(resume_text).validate(
            tailored.content_markdown
        )
        mark_changes_support(tailored.changes, report)
        recommendations = list(tailored.recommendations)
        if not report.is_clean:
            recommendations.append(
                "Review the flagged statements below — they are NOT supported "
                "by your original resume. Remove them before using this version."
            )
        return tailored.model_copy(update={
            "truthfulness_checked": True,
            "unsupported_claims_count": len(report.unsupported),
            "recommendations": recommendations + [
                f"Close the gap on '{skill}' with a concrete project before "
                "interviews." for skill in (missing_skills or [])[:3]
            ],
        })
