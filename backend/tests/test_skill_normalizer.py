"""SkillNormalizer tests."""

import pytest

from app.services.skill_normalizer import (
    SkillNormalizer,
    get_skill_normalizer,
    reset_skill_normalizer,
)


@pytest.fixture(autouse=True)
def fresh_normalizer():
    reset_skill_normalizer()
    yield
    reset_skill_normalizer()


def test_spec_examples():
    normalizer = SkillNormalizer()
    assert normalizer.canonical_key("GCP") == "gcp"
    assert normalizer.canonical_key("Google Cloud") == "gcp"
    assert normalizer.canonical_key("K8s") == "kubernetes"
    assert normalizer.canonical_key("LLM") == "llm"


def test_display_names_are_human_friendly():
    normalizer = get_skill_normalizer()
    for surface in ("rag", "RAG", "Retrieval Augmented Generation"):
        assert normalizer.display_name(surface) == "RAG"
    assert normalizer.display_name("natural language processing") == "NLP"
    assert normalizer.display_name("genai") == "GenAI"


def test_normalize_list_dedupes_synonyms():
    normalizer = SkillNormalizer()
    merged = normalizer.normalize_list(
        ["Python", "python", "GCP", "Google Cloud", "K8s"]
    )
    lowered = [s.lower() for s in merged]
    assert lowered.count("python") == 1
    assert "gcp" in lowered
    assert "kubernetes" in [s.lower() for s in merged]


def test_keys_collapse_variants():
    normalizer = SkillNormalizer()
    keys = normalizer.keys_for_list(["Generative AI", "gen ai", "GenAI"])
    assert len(keys) == 1


def test_unknown_skills_pass_through():
    normalizer = SkillNormalizer()
    assert normalizer.canonical_key("Obcureframework") == "obcureframework"
    assert normalizer.display_name("Obcureframework") == "Obcureframework"
