"""Phase 2 API tests: search -> recommendations -> job details -> analyze."""

from app.services.pdf_parser import build_fake_pdf


def _search(client, session_id: str, **overrides) -> dict:
    payload = {
        "session_id": session_id,
        "keywords": ["GenAI Engineer"],
        "locations": ["Bangalore", "Pune", "Remote"],
        "remote": True,
        "experience_min": 2,
        "experience_max": 4,
        "min_match_percent": 50,
    }
    payload.update(overrides)
    return client.post("/api/jobs/search", json=payload)


def _upload_resume(client):
    from tests.conftest import SAMPLE_RESUME_TEXT

    response = client.post(
        "/api/documents/upload",
        files={
            "resume": ("resume.pdf",
                       build_fake_pdf(SAMPLE_RESUME_TEXT.splitlines()),
                       "application/pdf"),
            "job_description": ("jd.txt", b"placeholder", "text/plain"),
        },
    )
    assert response.status_code == 200
    return response.json()["session_id"]


def test_full_discovery_flow(client):
    resume_session = _upload_resume(client)
    started = _search(client, resume_session)
    assert started.status_code == 200
    body = started.json()
    assert body["status"] == "completed"
    search_id = body["search_id"]

    summary = client.get(f"/api/jobs/search/{search_id}")
    assert summary.status_code == 200
    assert summary.json()["status"] == "completed"

    recs = client.get(f"/api/jobs/recommendations/{search_id}").json()
    assert recs["status"] == "completed"
    assert recs["recommendations"], "expected ranked recommendations"
    top = recs["recommendations"][0]
    assert top["rank"] == 1
    ranks = [rec["rank"] for rec in recs["recommendations"]]
    assert ranks == sorted(ranks)
    # Ranked order comes from adjusted_score (match + freshness); verify the
    # top-ranked recommendation really is the best-adjusted one.
    adjusted = [rec.get("adjusted_score", rec["match"]["overall_match"])
                for rec in recs["recommendations"]]
    assert adjusted == sorted(adjusted, reverse=True)

    # Duplicates from the mock dataset must be merged.
    titles_companies = {
        (rec["job"]["title"].lower(), rec["job"]["company"].lower())
        for rec in recs["recommendations"]
    }
    assert len(titles_companies) == len(recs["recommendations"])

    job_id = top["job"]["id"]
    detail = client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    job_payload = detail.json()["job"]
    assert job_payload["title"]
    assert isinstance(job_payload["required_skills"], list)

    # Analyze This Job -> runs the Phase 1 pipeline end to end.
    analysis = client.post(
        f"/api/jobs/{job_id}/analyze",
        json={"resume_session_id": resume_session},
    )
    assert analysis.status_code == 200
    new_session = analysis.json()["session_id"]
    result = client.get(f"/api/analysis/{new_session}").json()
    assert result["status"] == "completed"
    assert result["candidate_profile"]["name"] == "John Doe"
    assert result["roadmap"], "Phase 1 roadmap should be produced"


def test_search_unknown_resume_session_404(client):
    response = client.post(
        "/api/jobs/search",
        json={"session_id": "missing-session", "keywords": []},
    )
    assert response.status_code == 404


def test_recommendations_min_match_filter(client):
    resume_session = _upload_resume(client)
    search_id = _search(client, resume_session).json()["search_id"]
    strict = client.get(
        f"/api/jobs/recommendations/{search_id}", params={"min_match": 99}
    ).json()
    assert strict["recommendations"] == []


def test_job_detail_404(client):
    assert client.get("/api/jobs/does-not-exist").status_code == 404


def test_analyze_requires_existing_job(client):
    response = client.post(
        "/api/jobs/nope/analyze", json={"resume_session_id": "whatever"}
    )
    assert response.status_code == 404
