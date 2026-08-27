"""Curated skill vocabulary shared across matching, normalization and
truthfulness validation. This is canonical product data, not demo content."""

from __future__ import annotations

import re

KNOWN_SKILLS: tuple[str, ...] = (
    # Languages
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Go", "Rust", "SQL", "Bash",
    # Web / frameworks
    "FastAPI", "Django", "Flask", "Spring Boot", "React", "Next.js", "Node.js", "Angular",
    "Vue.js", "GraphQL", "REST API", "HTML", "CSS", "Tailwind CSS",
    # Cloud / devops
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform", "Jenkins", "CI/CD",
    "GitHub Actions", "Linux", "Git",
    # Data engineering
    "Spark", "Airflow", "dbt", "Snowflake", "Kafka", "Redis", "Elasticsearch",
    "PostgreSQL", "MySQL", "MongoDB", "DynamoDB", "BigQuery",
    # AI/ML
    "Machine Learning", "Deep Learning", "NLP", "Computer Vision", "PyTorch", "TensorFlow",
    "scikit-learn", "Pandas", "NumPy", "LangChain", "LangGraph", "LlamaIndex", "RAG",
    "LLM", "GenAI", "Vector Databases", "FAISS", "Pinecone", "ChromaDB", "Hugging Face",
    "Transformers", "Vertex AI", "OpenAI API", "Prompt Engineering", "MLOps", "MLflow",
    "Weights & Biases", "Fine-tuning", "Embeddings", "Semantic Search",
    # Practices
    "System Design", "Microservices", "Agile", "Unit Testing", "Data Pipelines", "ETL",
)

_SKILL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (_skill, re.compile(r"(?<![a-z0-9+#])" + re.escape(_skill.lower()) + r"(?![a-z0-9+#])"))
    for _skill in KNOWN_SKILLS
]


def find_known_skills(text: str) -> list[str]:
    """Skills from the curated vocabulary that literally appear in the text."""
    lowered = text.lower()
    found: list[str] = []
    for skill, pattern in _SKILL_PATTERNS:
        if pattern.search(lowered):
            found.append(skill)
    return found


__all__ = ["KNOWN_SKILLS", "find_known_skills"]
