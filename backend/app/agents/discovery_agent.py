"""Job Discovery Agent: candidate profile + preferences -> search strategy.

Generates a bounded set of query strings (configurable via
JOB_SEARCH_MAX_QUERIES) from the candidate's target role plus role aliases
and skill-flavored variants.
"""

from __future__ import annotations

from app.config import get_settings
from app.schemas.candidate import CandidateProfile
from app.schemas.jobs import JobSearchPreferences, SearchStrategy

_ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "genai engineer": ("GenAI Engineer", "Generative AI Engineer", "LLM Engineer"),
    "generative ai engineer": ("Generative AI Engineer", "GenAI Engineer"),
    "ai engineer": ("AI Engineer", "Machine Learning Engineer"),
    "llm engineer": ("LLM Engineer", "GenAI Engineer"),
    "machine learning engineer": ("Machine Learning Engineer", "ML Engineer"),
    "ml engineer": ("ML Engineer", "Machine Learning Engineer"),
    "java developer": ("Java Developer", "Backend Engineer"),
    "python developer": ("Python Developer", "Backend Engineer"),
    "backend engineer": ("Backend Engineer", "Python Developer"),
    "backend developer": ("Backend Developer", "Java Developer"),
    "frontend developer": ("Frontend Developer", "Software Engineer"),
    "data scientist": ("Data Scientist", "Machine Learning Engineer"),
    "data engineer": ("Data Engineer", "Big Data Engineer"),
    "devops engineer": ("DevOps Engineer", "Site Reliability Engineer"),
    "cloud engineer": ("Cloud Engineer", "DevOps Engineer"),
    "software engineer": ("Software Engineer", "Backend Engineer"),
}


def build_strategy(
    candidate: CandidateProfile,
    preferences: JobSearchPreferences,
) -> SearchStrategy:
    settings = get_settings()
    keywords = [k.strip() for k in preferences.keywords if k.strip()]
    base_role = keywords[0] if keywords else (candidate.current_role or "")

    queries: list[str] = []
    for alias in _ROLE_ALIASES.get(base_role.lower(), ()):
        queries.append(alias)
    if base_role and base_role not in queries:
        queries.insert(0, base_role)
    # Skill-flavored variants add recall without exploding query count.
    top_skills = list(candidate.all_skills()[:2])
    for skill in top_skills:
        variant = f"{base_role} {skill}".strip()
        if variant and variant not in queries:
            queries.append(variant)
    queries = queries[: max(1, settings.job_search_max_queries)]

    locations = preferences.locations or []
    rationale = (
        f"Derived from target role '{base_role or 'unknown'}' with "
        f"{len(queries)} bounded queries"
    )
    return SearchStrategy(queries=queries, locations=locations, rationale=rationale)


__all__ = ["build_strategy"]
