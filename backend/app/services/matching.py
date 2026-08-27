"""Deterministic skill-matching primitives shared by every mode (LLM or mock).

These functions are pure and unit-testable; they are the anti-hallucination
backbone: any claim that a candidate "has" a skill must survive normalization
against the actual resume-derived vocabulary.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z0-9+#./\-]+")

# Conservative synonym table: canonical -> accepted surface forms.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "kubernetes": ("k8s",),
    "javascript": ("js",),
    "typescript": ("ts",),
    "machine learning": ("ml",),
    "ml": ("machine learning",),
    "deep learning": ("dl",),
    "natural language processing": ("nlp",),
    "nlp": ("natural language processing",),
    "large language model": ("llm", "large language models"),
    "llm": ("large language model", "large language models"),
    "generative ai": ("genai", "gen ai"),
    "genai": ("generative ai", "gen ai"),
    "retrieval augmented generation": ("rag",),
    "rag": ("retrieval augmented generation",),
    "google cloud platform": ("gcp", "google cloud"),
    "gcp": ("google cloud platform", "google cloud"),
    "aws": ("amazon web services",),
    "azure": ("microsoft azure",),
    "postgresql": ("postgres",),
    "mongodb": ("mongo",),
    "kafka": ("apache kafka",),
    "airflow": ("apache airflow",),
    "continuous integration": ("ci/cd", "cicd", "ci cd"),
    "continuous delivery": ("ci/cd", "cicd", "ci cd"),
    "ci/cd": ("cicd", "ci cd", "continuous integration and continuous delivery"),
    "mlops": ("ml ops", "machine learning operations"),
    "vertex ai": ("google vertex ai",),
    "object-oriented programming": ("oop",),
    "rest api": ("rest apis", "restful api", "restful apis", "rest"),
    "microservices": ("microservice architecture", "micro-services"),
    "etl": ("elt",),
}


# Adjacent/related domains: knowing one suggests partial exposure to the other.
RELATED: dict[str, tuple[str, ...]] = {
    "docker": ("kubernetes", "container", "containers"),
    "kubernetes": ("docker", "container", "containers"),
    "container": ("docker", "kubernetes"),
    "langgraph": ("langchain",),
    "langchain": ("langgraph",),
    "vertex ai": ("gcp", "google cloud platform", "google cloud"),
    "gcp": ("vertex ai",),
    "aws": ("terraform",),
    "azure": ("terraform",),
    "mlops": ("mlflow", "ci/cd", "machine learning"),
    "system design": ("microservices", "architecture", "distributed system"),
    "microservices": ("system design", "distributed system"),
    "rest api": ("fastapi", "flask", "django"),
    "fastapi": ("rest api", "flask"),
    "pytorch": ("tensorflow", "deep learning"),
    "tensorflow": ("pytorch", "deep learning"),
}


def _canonical_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, variants in SYNONYMS.items():
        lookup[canonical] = canonical
        for variant in variants:
            lookup[variant] = canonical
    return lookup


_CANONICAL = _canonical_lookup()
_RELATED_LOOKUP: dict[str, set[str]] = {}
for _canonical_key, _related_values in RELATED.items():
    norm_key = _CANONICAL.get(_canonical_key, _canonical_key)
    entry = _RELATED_LOOKUP.setdefault(norm_key, set())
    for value in _related_values:
        norm_value = _CANONICAL.get(value, value)
        entry.add(norm_value)
        _RELATED_LOOKUP.setdefault(norm_value, set()).add(norm_key)


def are_related(a: str, b: str) -> bool:
    """True when two skills belong to adjacent domains (weaker than synonyms)."""
    na, nb = normalize_skill(a), normalize_skill(b)
    return nb in _RELATED_LOOKUP.get(na, set())


def tokenize(text: str) -> set[str]:
    """Lowercase token extraction with punctuation stripping."""
    lowered = text.lower()
    tokens: set[str] = set()
    for raw in _WORD_RE.findall(lowered):
        raw = raw.strip(".-/+#")
        if raw.endswith("s") and len(raw) > 3:
            raw = raw[:-1]
        if raw:
            tokens.add(raw)
    return tokens


def normalize_skill(skill: str) -> str:
    """Canonical form used for comparisons (never shown to users)."""
    cleaned = re.sub(r"\s+", " ", skill.strip().lower())
    cleaned = cleaned.strip(".,;:")
    return _CANONICAL.get(cleaned, cleaned)


def skills_equal(a: str, b: str) -> bool:
    """Exact/synonym match between two skill names."""
    na, nb = normalize_skill(a), normalize_skill(b)
    if na == nb:
        return True
    ta, tb = tokenize(na), tokenize(nb)
    return bool(ta) and ta == tb


def _is_partial_match(candidate: str, requirement: str) -> bool:
    """Weaker signal: meaningful token overlap without a full match."""
    tc, tr = tokenize(candidate), tokenize(requirement)
    if not tc or not tr or tc == tr:
        return False
    overlap = tc & tr
    if not overlap:
        # Multi-word containment, e.g. "spring boot framework" vs "spring boot"
        shorter, longer = (tc, tr) if len(tc) <= len(tr) else (tr, tc)
        joined_longer = " ".join(sorted(longer))
        return any(len(token) >= 4 and token in joined_longer for token in shorter)
    smaller_side = min(len(tc), len(tr))
    return len(overlap) >= 1 and len(overlap) / smaller_side >= 0.5


def find_match(requirement: str, candidates: list[str]) -> str | None:
    """Return the candidate skill exactly/synonym-matching a requirement."""
    for cand in candidates:
        if skills_equal(cand, requirement):
            return cand
    return None


def find_partial(requirement: str, candidates: list[str]) -> str | None:
    """Return a candidate skill partially/related to a requirement."""
    for cand in candidates:
        if skills_equal(cand, requirement):
            continue
        if are_related(cand, requirement) or _is_partial_match(cand, requirement):
            return cand
    return None
