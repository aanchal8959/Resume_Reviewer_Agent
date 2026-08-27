"""Truthfulness validator tests."""

from app.services.truthfulness import ResumeTruthfulnessValidator

ORIGINAL = """John Doe
john@example.com

SUMMARY
AI Engineer with 2 years of experience.

EXPERIENCE
- Built a RAG chatbot using Python and FastAPI
- Deployed services with Docker

EDUCATION
B.Tech Computer Science, 2021
"""


def test_unsupported_technology_flagged():
    validator = ResumeTruthfulnessValidator(ORIGINAL)
    tailored = ORIGINAL + "\n- Built production Kubernetes clusters"
    report = validator.validate(tailored)
    flagged = {claim.claim for claim in report.unsupported}
    assert "Kubernetes" in flagged


def test_supported_rephrase_not_flagged():
    validator = ResumeTruthfulnessValidator(ORIGINAL)
    tailored = (
        "- Developed a retrieval augmented generation chatbot using Python "
        "and FastAPI for semantic document retrieval"
    )
    report = validator.validate(tailored)
    assert report.is_clean, [c.claim for c in report.unsupported]


def test_experience_inflation_flagged():
    validator = ResumeTruthfulnessValidator(ORIGINAL)
    tailored = "AI Engineer with 8 years of experience."
    report = validator.validate(tailored)
    kinds = {claim.kind for claim in report.unsupported}
    assert "experience" in kinds


def test_unknown_employer_flagged():
    validator = ResumeTruthfulnessValidator(ORIGINAL)
    tailored = "- Senior Engineer at Pinecone Labs building vector databases"
    report = validator.validate(tailored)
    kinds = {claim.kind for claim in report.unsupported}
    assert "company" in kinds


def test_clean_tailoring_passes():
    validator = ResumeTruthfulnessValidator(ORIGINAL)
    report = validator.validate(
        "- Developed the RAG chatbot using Python and FastAPI with Docker"
    )
    assert report.is_clean
