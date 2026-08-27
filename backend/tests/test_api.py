"""API integration tests: upload -> start -> get analysis (mock mode)."""

from app.services.pdf_parser import build_fake_pdf


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "gemini"


def test_upload_returns_session(client, uploaded_files):
    response = client.post("/api/documents/upload", files=uploaded_files)
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["resume_document_id"] != body["job_description_document_id"]


def test_upload_rejects_unsupported_type(client):
    response = client.post(
        "/api/documents/upload",
        files={
            "resume": ("resume.png", b"\x89PNG...", "image/png"),
            "job_description": ("jd.pdf", build_fake_pdf(["Python role"]), "application/pdf"),
        },
    )
    assert response.status_code == 415


def test_upload_rejects_invalid_pdf(client):
    response = client.post(
        "/api/documents/upload",
        files={
            "resume": ("resume.pdf", b"not a pdf", "application/pdf"),
            "job_description": ("jd.txt", b"Python role", "text/plain"),
        },
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_upload_rejects_empty_file(client):
    response = client.post(
        "/api/documents/upload",
        files={
            "resume": ("resume.pdf", b"", "application/pdf"),
            "job_description": ("jd.txt", b"Python role", "text/plain"),
        },
    )
    assert response.status_code == 400


def test_full_analysis_flow_mock_mode(client, uploaded_files):
    session_id = client.post("/api/documents/upload", files=uploaded_files).json()["session_id"]

    started = client.post(f"/api/analysis/{session_id}/start")
    assert started.status_code == 200
    assert started.json()["status"] in {"completed", "failed"}
    assert not started.json().get("message") or started.json()["status"] != "failed"

    result = client.get(f"/api/analysis/{session_id}").json()
    assert result["status"] == "completed"
    candidate = result["candidate_profile"]
    job = result["job_profile"]
    skill_gap = result["skill_gap"]
    score = result["match_score"]
    roadmap = result["roadmap"]

    assert candidate["name"] == "John Doe"
    assert "Python" in candidate["programming_languages"]
    assert job["required_skills"], "mock extraction should find required skills"
    matched_lower = [s.lower() for s in skill_gap["matched"]]
    partial_lower = [s.lower() for s in skill_gap["partial"]]
    missing_lower = [s.lower() for s in skill_gap["missing"]]
    assert "python" in matched_lower
    # Resume shows Docker (containerization-adjacent), so Kubernetes is at best
    # a partial match; MLOps/Terraform have no evidence at all.
    assert "kubernetes" in partial_lower + missing_lower
    # Stub JobProfile requires Python/RAG and prefers Kubernetes.
    assert "kubernetes" in missing_lower or "kubernetes" in partial_lower
    assert 0 <= score["overall_score"] <= 100
    assert set(score["breakdown"]) == {
        "required_skills", "preferred_skills", "experience",
        "project_relevance", "education",
    }
    days = [task["day"] for week in roadmap["weeks"] for task in week]
    assert sorted(days) == list(range(1, 31))


def test_analysis_unknown_session_404(client):
    assert client.post("/api/analysis/does-not-exist/start").status_code == 404
    assert client.get("/api/analysis/does-not-exist").status_code == 404


def test_get_documents_for_session(client, uploaded_files):
    session_id = client.post("/api/documents/upload", files=uploaded_files).json()["session_id"]
    listing = client.get(f"/api/documents/{session_id}").json()
    kinds = {doc["kind"] for doc in listing["documents"]}
    assert kinds == {"resume", "job_description"}


