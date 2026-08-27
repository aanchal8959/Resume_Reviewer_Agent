"""Regenerate the sample PDFs in sample_data/ (uses the backend's PDF writer).

Usage:
    cd backend
    python ..\\scripts\\generate_sample_data.py
"""

from __future__ import annotations

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.pdf_parser import build_fake_pdf  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "sample_data"

RESUME = """Priya Sharma
Bengaluru, India | priya.sharma@example.com | +91 98765 43210

SUMMARY
AI Engineer with 3 years of experience building GenAI products and RAG systems.

EXPERIENCE
Current role: AI Engineer at Nimbus Software
- Built an enterprise RAG chatbot using Python, FastAPI, LangChain and GCP Vertex AI
- Designed retrieval pipelines with FAISS and PostgreSQL pgvector
- Deployed containerized services with Docker and Cloud Run
- Collaborated across teams with strong communication and mentoring

Previous role: Software Engineer at Infoedge Solutions
- Developed REST APIs in Python and SQL databases
- Wrote unit tests and practiced Agile development

EDUCATION
B.Tech Computer Science, VTU, 2021

SKILLS
Python, FastAPI, Flask, LangChain, RAG, LLM, GCP, Vertex AI, Docker, SQL,
PostgreSQL, FAISS, Git, REST API, communication, teamwork, problem-solving

PROJECTS
Enterprise RAG System: Retrieval augmented generation chatbot for support teams.
Technologies: Python, Vertex AI, FAISS, FastAPI, Docker
Data Pipeline Dashboard: ETL dashboard for sales analytics.
Technologies: Python, Pandas, PostgreSQL

CERTIFICATIONS
Google Cloud Associate Engineer
"""

JOB = """Acme AI Technologies
Role: GenAI Engineer

Company: Acme AI Technologies builds production LLM platforms.

About the role:
We are looking for a GenAI Engineer to design and ship LLM-powered products.

RESPONSIBILITIES:
- Design and ship RAG pipelines and agent workflows
- Build scalable APIs with Python and FastAPI
- Deploy and operate services on GCP and Kubernetes
- Apply system design best practices for distributed systems

REQUIREMENTS:
- 2+ years of professional experience with Python
- Strong hands-on RAG and LLM application development
- Experience with GCP cloud services
- Kubernetes fundamentals and containerized deployments
- Solid system design for distributed systems

PREFERRED / NICE TO HAVE:
- MLOps practices and tooling
- LangGraph or multi-agent orchestration
- Terraform infrastructure as code

EDUCATION:
Bachelor degree in Computer Science or related field.
"""


def main() -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    (SAMPLE_DIR / "sample_resume.pdf").write_bytes(build_fake_pdf(RESUME.splitlines()))
    (SAMPLE_DIR / "sample_job_description.pdf").write_bytes(build_fake_pdf(JOB.splitlines()))
    print(f"Wrote sample PDFs to {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
