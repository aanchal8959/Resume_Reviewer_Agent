"""Phase 4 search API tests: quick GET search, pagination, sources metadata,
search quality, and Phase 3 integration with externally-styled jobs."""


def _search(client, session_id, **overrides):
    payload = {
        "session_id": session_id,
        "keywords": ["Java Developer"],
        "locations": [],
        "remote": None,
        "min_match_percent": 0,
    }
    payload.update(overrides)
    return client.post("/api/jobs/search", json=payload)


def test_quick_get_search_returns_jobs_and_metadata(client, analyzed_session):
    # Seed via the personalized POST flow first (mock providers).
    started = _search(client, analyzed_session, refresh=True)
    assert started.status_code == 200
    assert started.json()["status"] == "completed"

    response = client.get("/api/jobs/search", params={"q": "Java Developer"})
    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body and "pagination" in body and "sources" in body
    pagination = body["pagination"]
    assert {"page", "limit", "total", "has_next"} <= set(pagination)

    # Search quality: Java-related jobs surface; unrelated ones do not.
    titles = " ".join(job["title"].lower() for job in body["jobs"])
    descriptions = " ".join(
        (job["title"] + " " + job["description"]).lower() for job in body["jobs"]
    )
    assert "java" in descriptions or "backend" in descriptions
    assert "marketing manager" not in titles


def test_quick_search_pagination(client):
    first = client.get("/api/jobs/search", params={"q": "developer", "limit": 2}).json()
    second = client.get("/api/jobs/search",
                        params={"q": "developer", "limit": 2, "page": 2}).json()
    assert first["pagination"]["page"] == 1
    if first["pagination"]["has_next"]:
        assert second["pagination"]["page"] == 2


def test_search_response_includes_sources_and_metadata(client, analyzed_session):
    started = _search(client, analyzed_session, refresh=True).json()
    assert isinstance(started["sources"], list) and started["sources"]
    source_entry = started["sources"][0]
    assert {"name", "status", "count", "source_type"} <= set(source_entry)
    metadata = started["metadata"]
    assert "live_results" in metadata or "cached_results" in metadata


def test_cache_serves_second_search_without_refresh(client, analyzed_session):
    import time

    first = _search(client, analyzed_session, refresh=True).json()
    time.sleep(0.05)
    second_response = _search(client, analyzed_session)
    second = second_response.json()
    assert first["status"] == "completed", first
    assert second.get("status") == "completed", second
    # Second search should be served from the local cache.
    names = [s.get("name", "") for s in second.get("sources", [])]
    if names:
        assert any("cache" in name.lower() for name in names)


def test_provider_health_endpoint(client):
    response = client.get("/api/jobs/providers")
    assert response.status_code == 200
    providers = response.json()["providers"]
    assert providers
    for entry in providers:
        assert {"name", "enabled", "status", "source_type"} <= set(entry)


def test_phase3_prepare_application_with_real_style_job(client, analyzed_session):
    """A REAL-sourced job (external-style fields) flows through Phase 3."""
    from app.database.database import get_database
    from app.database.job_repository import JobRepository
    from app.schemas.jobs import Job

    real_job = Job(
        source="remotive", source_type="REAL", source_job_id="ext-123",
        title="Senior Backend Engineer - Java",
        company="Orbit Commerce",
        description=(
            "Senior Java developer role.\nREQUIREMENTS:\n"
            "- 5+ years of professional experience\n"
            "- Hands-on experience with Java\n"
            "- Experience with Microservices\n"
            "PREFERRED / NICE TO HAVE:\n- Kubernetes exposure"
        ),
        location="Remote",
        work_mode="remote",
        employment_type="full-time",
        salary_min=30.0, salary_max=45.0, salary_currency="INR",
        required_skills=["Java", "Microservices"],
        preferred_skills=["Kubernetes"],
        application_url="https://jobs.example-orbit.com/apply/123",
    )
    with get_database().session() as db:
        mapping = JobRepository(db).upsert_canonical_jobs([real_job])
        job_id = next(iter(mapping.values())).id

    created = client.post("/api/applications", json={
        "job_id": job_id, "resume_session_id": analyzed_session,
    })
    assert created.status_code == 201
    app_id = created.json()["application_id"]

    prepared = client.post(f"/api/applications/{app_id}/prepare")
    assert prepared.status_code == 200
    detail = prepared.json()
    assert detail["job"]["id"] == job_id
    assert detail["tailored_resume"]["content_markdown"]
    assert detail["cover_letter"]["content_text"]

    status_response = client.patch(
        f"/api/applications/{app_id}/status", json={"status": "APPLIED"}
    )
    assert status_response.status_code == 200
    timeline_events = {e["event"] for e in status_response.json()["timeline"]}
    assert "JOB_SAVED" in timeline_events and "RESUME_TAILORED" in timeline_events


def test_job_detail_shows_lifecycle_fields(client, recommended_job):
    detail = client.get(f"/api/jobs/{recommended_job['id']}").json()
    job = detail["job"]
    for field in ("source_type", "status", "url_status"):
        assert field in job
