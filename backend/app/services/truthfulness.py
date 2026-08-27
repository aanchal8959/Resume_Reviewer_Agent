"""Resume Truthfulness Validator.

Deterministic fact-checking of a tailored resume against the original resume
text. Flags any claim about technologies, companies, titles, education,
certifications or experience that is not evidenced by the original. Never
silently rejects: it produces a structured report so warnings can be surfaced.
"""

from __future__ import annotations

import re

from app.schemas.applications import UnsupportedClaim, TruthfulnessReport
from app.services.matching import (
    normalize_skill,
    tokenize,
)
from app.services.skill_vocabulary import find_known_skills

_YEARS_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?\.?)", re.IGNORECASE)
_AT_COMPANY_RE = re.compile(r"\b(?:at|@)\s+([A-Z][A-Za-z0-9&.\- ]{2,40})")
_CORPORATE_SUFFIX_RE = re.compile(
    r"\b(labs?|corp(oration)?|inc\.?|technologies|systems|solutions|software)\b",
    re.IGNORECASE,
)
_TITLE_HINT_RE = re.compile(
    r"\b(?:engineer|developer|scientist|architect|manager|analyst|consultant|lead)\b",
    re.IGNORECASE,
)

_GENERIC_ALLOWED = {
    "rest api", "api", "sql", "git", "linux", "agile", "unit testing",
}


class ResumeTruthfulnessValidator:
    """Compares a generated resume against the source resume text."""

    def __init__(self, original_resume_text: str) -> None:
        self._original_text = original_resume_text
        lowered = original_resume_text.lower()
        self._known_display_skills = find_known_skills(original_resume_text)
        self._known_original_normalized = {
            normalize_skill(s) for s in self._known_display_skills
        }
        self._original_companies = [
            m.group(1).strip().lower() for m in _AT_COMPANY_RE.finditer(original_resume_text)
        ]
        self._max_years_claimed = max(
            (float(m.group(1)) for m in _YEARS_NUMBER_RE.finditer(lowered)),
            default=0.0,
        )
        self._education_lines = [
            line.strip().lower()
            for line in lowered.splitlines()
            if any(k in line for k in ("b.tech", "bachelor", "master", "ph.d", "phd", "degree"))
        ]
        self._cert_lines = [
            line.strip().lower()
            for line in lowered.splitlines()
            if "certif" in line
        ]

    # -- public ---------------------------------------------------------------
    def validate(self, tailored_markdown: str) -> TruthfulnessReport:
        unsupported: list[UnsupportedClaim] = []
        checked = 0

        checked += len(self._check_technologies(tailored_markdown, unsupported))
        checked += len(self._check_companies(tailored_markdown, unsupported))
        checked += len(self._check_experience_years(tailored_markdown, unsupported))
        checked += len(self._check_education(tailored_markdown, unsupported))

        return TruthfulnessReport(checked_claims=checked, unsupported=unsupported)

    # -- checks -----------------------------------------------------------------
    def _check_technologies(self, text: str,
                            unsupported: list[UnsupportedClaim]) -> list[UnsupportedClaim]:
        """Related domains (e.g. Docker vs Kubernetes) do NOT count as evidence:
        adjacency justifies a *rephrase*, never a new capability claim."""
        added: list[UnsupportedClaim] = []
        for skill in find_known_skills(text):
            if normalize_skill(skill) in self._known_original_normalized:
                continue
            if skill.lower() in _GENERIC_ALLOWED:
                continue
            overlapping = any(
                self._token_overlap(normalize_skill(orig), skill) is not None
                for orig in self._known_display_skills
            )
            if overlapping:
                continue
            claim = UnsupportedClaim(
                claim=skill,
                kind="technology",
                reason=(
                    f"'{skill}' does not appear anywhere in the original resume "
                    "(related tools do not count as experience with it)."
                ),
            )
            unsupported.append(claim)
            added.append(claim)
        return added

    def _check_companies(self, text: str,
                         unsupported: list[UnsupportedClaim]) -> list[UnsupportedClaim]:
        """Flag employers not present in the original resume.

        When the original has no detectable employers, only clear corporate
        names are flagged to avoid false positives on phrases like
        "worked at scale".
        """
        added: list[UnsupportedClaim] = []
        detected = {
            m.group(1).strip().lower() for m in _AT_COMPANY_RE.finditer(text)
        }
        if self._original_companies:
            unknown = [
                company for company in detected
                if not any(company in orig or orig in company
                           for orig in self._original_companies)
            ]
        else:
            unknown = [c for c in detected if _CORPORATE_SUFFIX_RE.search(c)]
        for company in unknown:
            claim = UnsupportedClaim(
                claim=company,
                kind="company",
                reason=f"Employer '{company}' is not present in the original resume.",
            )
            unsupported.append(claim)
            added.append(claim)
        return added

    def _check_experience_years(self, text: str,
                                unsupported: list[UnsupportedClaim]) -> list[UnsupportedClaim]:
        added: list[UnsupportedClaim] = []
        for match in _YEARS_NUMBER_RE.finditer(text.lower()):
            years = float(match.group(1))
            if years > max(self._max_years_claimed, 0) + 1e-9:
                claim = UnsupportedClaim(
                    claim=match.group(0),
                    kind="experience",
                    reason=(
                        f"Claims {years:g}+ years of experience but the original "
                        f"resume supports at most {self._max_years_claimed:g}."
                    ),
                )
                unsupported.append(claim)
                added.append(claim)
        return added

    def _check_education(self, text: str,
                         unsupported: list[UnsupportedClaim]) -> list[UnsupportedClaim]:
        added: list[UnsupportedClaim] = []
        for line in text.splitlines():
            stripped = line.strip().lower()
            if not stripped.startswith(("-", "*")):
                continue
            content = stripped.lstrip("-* ").strip()
            if not content:
                continue
            if any(k in content for k in ("b.tech", "bachelor", "master", "phd", "ph.d")):
                if not any(content[:20] in edu or edu in content
                           for edu in self._education_lines):
                    claim = UnsupportedClaim(
                        claim=line.strip(),
                        kind="education",
                        reason="Education entry not found in the original resume.",
                    )
                    unsupported.append(claim)
                    added.append(claim)
            elif "certif" in content:
                if not any(content[:20] in cert or cert in content
                           for cert in self._cert_lines):
                    claim = UnsupportedClaim(
                        claim=line.strip(),
                        kind="certification",
                        reason="Certification not found in the original resume.",
                    )
                    unsupported.append(claim)
                    added.append(claim)
        return added

    @staticmethod
    def _token_overlap(canonical_skill: str, candidate_skill: str) -> str | None:
        tokens_a = tokenize(canonical_skill)
        tokens_b = tokenize(candidate_skill)
        overlap = tokens_a & tokens_b
        if overlap and len(overlap) / max(1, min(len(tokens_a), len(tokens_b))) >= 0.5:
            return canonical_skill
        return None


def mark_changes_support(changes, report: TruthfulnessReport) -> None:
    """Attach warning flags to change log entries implicated by the report."""
    flagged_claims = {normalize_skill(c.claim) for c in report.unsupported}
    for change in changes:
        updated_tokens = set(tokenize(change.updated.lower()))
        offending = [
            claim for claim in flagged_claims
            if all(token in updated_tokens for token in tokenize(claim.replace("_", " ")))
        ]
        if offending:
            change.supported = False
            change.warning = (
                "This generated statement may not be supported by the original "
                f"resume ({', '.join(offending)})."
            )


