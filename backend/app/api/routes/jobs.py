"""Phase 2 endpoints: job discovery, recommendations, and analyze-this-job."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user_optional
from app.models.user import User

from app.agents.candidate_agent import CandidateProfileAgent
from app.agents.job_discovery_orchestrator import JobDiscoveryPipeline
from app.config import get_settings
from app.database.database import get_database
from app.database.job_repository import JobRepository, fingerprint_for
from app.database.repository import NotFoundError, SessionRepository
from app.schemas.analysis import StartAnalysisResponse
from app.schemas.jobs import (
    Job,
    JobMatch,
    JobSearchPreferences,
    JobSearchRequest,
    RankedRecommendations,
    Recommendation,
)
from app.services.analysis_runner import AnalysisRunError, run_and_store_analysis
from app.services.llm_service import LLMUnavailableError

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class AnalyzeJobRequest(BaseModel):
    resume_session_id: str = Field(min_length=6)


def _load_candidate_for_session(resume_session_id: str) -> tuple[str, dict]:
    """Return (resume_text, candidate_profile_dict), reusing cached profiles."""
    database = get_database()
    with database.session() as db:
        repo = SessionRepository(db)
        try:
            resume_doc = repo.get_document(resume_session_id, "resume")
        except NotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No resume found in session '{resume_session_id}'.",
            ) from exc
        existing = repo.get_result(resume_session_id)
        resume_text = resume_doc.text_content
        cached_profile = existing.candidate_profile if existing else None

    if cached_profile is None:
        from app.services.llm_service import get_llm_provider

        provider = get_llm_provider(get_settings())
        try:
            profile = CandidateProfileAgent(provider).run(resume_text)
        except Exception as exc:  # noqa: BLE001 - surfaced to the client
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Candidate profile extraction failed: {exc}",
            ) from exc
        cached_profile = profile.model_dump()
        with database.session() as db:
            SessionRepository(db).save_result(
                resume_session_id,
                candidate_profile=cached_profile,
                job_profile=None,
                skill_gap=None,
                match_score=None,
                roadmap=None,
                errors=[],
            )
    return resume_text, cached_profile


@router.post("/search")
def search_jobs(
    request: JobSearchRequest, current_user: User | None = Depends(get_current_user_optional)
) -> dict:
    """Discover + normalize + dedupe + match + rank jobs for a candidate."""
    _, candidate_profile = _load_candidate_for_session(request.session_id)

    database = get_database()
    from app.schemas.jobs import JobSearchPreferences

    preferences = JobSearchPreferences.model_validate(
        request.model_dump(exclude={"session_id"})
    )
    with database.session() as db:
        repo = JobRepository(db)
        search_row = repo.create_search_session(
            request.session_id,
            preferences.model_dump(mode="json"),
            user_id=current_user.id if current_user else None,
        )
        search_id = search_row.id
        repo.set_search_status(search_id, "processing")

    import time as _time

    started = _time.perf_counter()
    try:
        from app.schemas.candidate import CandidateProfile

        pipeline = JobDiscoveryPipeline(refresh=request.refresh)
        final_state = pipeline.run(
            CandidateProfile.model_validate(candidate_profile),
            preferences,
            search_id,
        )
    except Exception as exc:  # noqa: BLE001 - persist every failure
        message = f"Job discovery failed: {exc}"
        with database.session() as db:
            JobRepository(db).set_search_status(search_id, "failed", error=message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message
        ) from exc
    duration_ms = int((_time.perf_counter() - started) * 1000)

    errors = list(final_state.get("errors") or [])
    if errors and not final_state.get("recommendations"):
        message = "; ".join(errors) or "No jobs discovered for this query."
        with database.session() as db:
            JobRepository(db).set_search_status(search_id, "failed", error=message)
        return {
            "search_id": search_id,
            "status": "failed",
            "message": message,
            "sources": final_state.get("sources_status") or [],
            "metadata": {"live_results": False, "cached_results": False},
        }

    _persist_pipeline_output(search_id, request.session_id, final_state)
    metadata = dict(final_state.get("metadata") or {})
    metadata["duplicates_removed"] = max(
        0, len(final_state.get("raw_jobs") or [])
        - len(final_state.get("canonical_jobs") or [])
    )
    metadata["duration_ms"] = duration_ms
    response = {
        "search_id": search_id,
        "status": "completed",
        "message": (
            f"Found {len(final_state.get('raw_jobs') or [])} jobs; "
            f"{len(final_state.get('canonical_jobs') or [])} after deduplication; "
            f"{len(final_state.get('recommendations') or [])} ranked."
        ),
        "sources": final_state.get("sources_status") or [],
        "metadata": metadata,
        "warnings": errors,
    }
    if errors:
        response["warnings"] = errors
    return response


def _persist_pipeline_output(search_id: str, candidate_session_id: str,
                             state: dict) -> None:
    """Store canonical jobs, matches (with caching) and the ranked order."""
    database = get_database()
    from app.schemas.jobs import JobMatch

    with database.session() as db:
        repo = JobRepository(db)
        repo.save_strategy(search_id, state.get("strategy") or {})
        rows_by_fingerprint = repo.upsert_canonical_jobs(
            [Job.model_validate(payload) for payload in state.get("canonical_jobs", [])]
        )

        ordered_recommendations: list[dict] = []
        top_score: float | None = None
        for rec in state.get("recommendations", []):
            job_payload = rec["job"]
            fingerprint = fingerprint_for(Job.model_validate(job_payload))
            row = rows_by_fingerprint.get(fingerprint)

            # Cross-search cache: same candidate + same job => reuse stored match.
            cached = repo.find_cached_match(candidate_session_id, fingerprint)
            payload = cached if cached is not None else rec["match"]
            overall = float(payload.get("overall_match", 0.0))
            if row is not None:
                repo.save_match(search_id, candidate_session_id, row.id, payload, overall)
            ordered_recommendations.append({
                "rank": rec["rank"], "job_id": row.id if row else None,
                "overall_match": overall,
                "adjusted_score": float(rec.get("adjusted_score") or overall),
            })
            if top_score is None:
                top_score = overall

        repo.save_recommendations(
            search_id,
            ordered_recommendations,
            discovered=len(state.get("raw_jobs", [])),
            unique=len(state.get("canonical_jobs", [])),
            top_score=top_score,
        )
        repo.set_search_status(search_id, "completed")


@router.get("/search/{search_id}")
def get_search(
    search_id: str, current_user: User | None = Depends(get_current_user_optional)
) -> dict:
    database = get_database()
    with database.session() as db:
        repo = JobRepository(db)
        try:
            row = repo.get_search_session(search_id)
            if row.user_id and (not current_user or row.user_id != current_user.id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        except NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return {
            "search_id": row.id,
            "status": row.status,
            "created_at": row.created_at,
            "query": row.query_json,
            "strategy": row.strategy_json,
            "discovered_count": row.discovered_count,
            "unique_count": row.unique_count,
            "error": row.error,
        }


@router.get("/search", tags=["jobs"])
def quick_search(
    q: str = "",
    location: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> dict:
    """Convenience GET search (no personalization): normalized + deduped jobs.

    Uses the same provider/cache pipeline; returns raw normalized jobs ordered
    by posting freshness. Use the POST search for personalized ranking.
    """
    from datetime import datetime, timezone
    import time as _time

    from app.services.job_sources.cache import lookup_cached_jobs
    from app.services.job_sources.manager import JobSourceManager
    from app.services.job_normalizer import JobNormalizer

    preferences = JobSearchPreferences(
        keywords=[q] if q else [],
        locations=[location] if location else [],
        remote=None,
    )
    strategy_queries = [q] if q else []
    started = _time.perf_counter()
    manager = JobSourceManager()
    live_used = False
    sources: list[dict] = []
    with get_database().session() as db:
        cached_rows, fresh = lookup_cached_jobs(db, strategy_queries, preferences)
        if fresh and len(cached_rows) >= 5:
            rows = cached_rows
            sources = [{
                "name": "Local cache", "source_type": "REAL",
                "status": "success", "count": len(rows),
            }]
        else:
            merged, statuses = manager.search(preferences, strategy_queries)
            normalizer = JobNormalizer(_provider(), _skill_normalizer())
            jobs: list[Job] = []
            for raw in merged:
                try:
                    jobs.append(normalizer.normalize(raw))
                except Exception:  # noqa: BLE001
                    continue
            repo = JobRepository(db)
            mapping = repo.upsert_canonical_jobs(jobs)
            from app.services.url_validator import verify_stale_urls

            verify_stale_urls(db)
            rows = list(mapping.values())
            sources = [s.model_dump() for s in statuses]
            live_used = True

    total = len(rows)
    start = max(0, (page - 1) * limit)
    page_rows = rows[start : start + limit]
    duration_ms = int((_time.perf_counter() - started) * 1000)
    return {
        "jobs": [_row_to_job(r).model_dump(mode="json") for r in page_rows],
        "pagination": {
            "page": page, "limit": limit, "total": total,
            "has_next": start + limit < total,
        },
        "sources": sources,
        "metadata": {
            "live_results": live_used,
            "cached_results": not live_used,
            "total": total,
            "duration_ms": duration_ms,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/providers")
def provider_status() -> dict:
    """Provider health for the configuration UI (no secrets exposed)."""
    from app.services.job_sources.manager import JobSourceManager

    return {"providers": JobSourceManager().health()}


def _provider():
    try:
        from app.services.llm_service import get_llm_provider

        return get_llm_provider(get_settings())
    except Exception:  # noqa: BLE001 - normalization must work without LLM config
        from app.services.llm_service import LLMError, LLMProvider

        class _NullProvider(LLMProvider):
            name = "unavailable"

            def generate_structured(self, *args, **kwargs):  # noqa: ANN002, ANN003
                raise LLMError("LLM unavailable for normalization assist")

        return _NullProvider()


def _skill_normalizer():
    from app.services.skill_normalizer import get_skill_normalizer

    return get_skill_normalizer()



@router.get("/recommendations/{search_id}")
def get_recommendations(
    search_id: str,
    min_match: float | None = None,
    page: int = 1,
    limit: int = 20,
    current_user: User | None = Depends(get_current_user_optional),
) -> dict:
    database = get_database()
    with database.session() as db:
        job_repo = JobRepository(db)
        try:
            search_row = job_repo.get_search_session(search_id)
            if search_row.user_id and (not current_user or search_row.user_id != current_user.id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        except NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

        ordered = [
            entry for entry in (search_row.recommendations_json or [])
            if entry.get("job_id")
        ]
        recommendations: list[Recommendation] = []
        matcher = _build_matcher()
        rank = 1
        for entry in ordered:
            if min_match is not None and entry.get("overall_match", 0) < min_match:
                continue
            try:
                job_row = job_repo.get_job_row(entry["job_id"])
            except NotFoundError:
                continue
            match_rows = [m for m in job_repo.get_matches(search_id) if m.job_id == job_row.id]
            if not match_rows:
                continue
            from app.schemas.jobs import JobMatch

            job = _row_to_job(job_row)
            match = JobMatch.model_validate(match_rows[0].payload)
            recommendations.append(
                Recommendation(
                    rank=rank,
                    job=job,
                    match=match,
                    explanation=matcher.explain(job, match),
                    adjusted_score=float(entry.get("adjusted_score") or entry.get("overall_match") or 0.0),
                )
            )
            rank += 1

    total = len(recommendations)
    start = max(0, (page - 1) * limit)
    page_items = recommendations[start : start + limit]
    return {
        "search_id": search_id,
        "status": search_row.status,
        "total_jobs": total,
        "recommendations": [r.model_dump(mode="json") for r in page_items],
        "pagination": {
            "page": page, "limit": limit, "total": total,
            "has_next": start + limit < total,
        },
    }


@router.get("/{job_id}")
def get_job(job_id: str) -> dict:
    database = get_database()
    from sqlalchemy import select

    from app.models.jobs import JobMatchRow

    with database.session() as db:
        repo = JobRepository(db)
        try:
            row = repo.get_job_row(job_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        job = _row_to_job(row)
        provenance = [
            {"source": rec.source, "source_job_id": rec.source_job_id,
             "title": rec.raw_title, "url": rec.url}
            for rec in row.source_records
        ]
        latest_match_row = db.scalars(
            select(JobMatchRow)
            .where(JobMatchRow.job_id == job_id)
            .order_by(JobMatchRow.created_at.desc())
        ).first()
        match_payload = latest_match_row.payload if latest_match_row else None
    response = {"job": job.model_dump(mode="json"), "sources": provenance}
    if match_payload is not None:
        matcher = _build_matcher()
        from app.schemas.jobs import JobMatch

        match_model = JobMatch.model_validate(match_payload)
        response["match"] = match_payload
        response["explanation"] = matcher.explain(job, match_model).model_dump()
    return response


@router.post("/{job_id}/analyze", response_model=StartAnalysisResponse)
def analyze_job(job_id: str, body: AnalyzeJobRequest) -> StartAnalysisResponse:
    """Feed a discovered job into the EXISTING Phase 1 analysis pipeline."""

    database = get_database()
    with database.session() as db:
        repo = JobRepository(db)
        try:
            job_row = repo.get_job_row(job_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        job_text = _render_job_as_text(job_row)

    resume_text, _profile = _load_candidate_for_session(body.resume_session_id)

    with database.session() as db:
        session_repo = SessionRepository(db)
        new_session = session_repo.create_session()
        new_session_id = new_session.id
        session_repo.add_document(new_session_id, "resume", "resume.pdf",
                                  "application/pdf", resume_text)
        session_repo.add_document(new_session_id, "job_description",
                                  f"{job_row.title} - {job_row.company}.txt",
                                  "text/plain", job_text)
        session_repo.set_status(new_session_id, "processing")

    try:
        result_status, error_message = run_and_store_analysis(
            new_session_id, resume_text, job_text
        )
    except AnalysisRunError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return StartAnalysisResponse(
        session_id=new_session_id,
        status=result_status,
        message=error_message or ("Analysis completed." if result_status == "completed" else None),
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _row_to_job(row) -> Job:
    return Job(
        id=row.id,
        source=row.first_source,
        source_type=getattr(row, "source_type", None) or "REAL",
        source_job_id=row.source_job_id,
        title=row.title,
        company=row.company,
        description=row.description or "",
        location=row.location,
        work_mode=row.work_mode or "unknown",
        employment_type=row.employment_type,
        experience_min=row.experience_min,
        experience_max=row.experience_max,
        experience_level=getattr(row, "experience_level", None),
        salary_min=row.salary_min,
        salary_max=row.salary_max,
        salary_currency=row.salary_currency,
        required_skills=list(row.required_skills or []),
        preferred_skills=list(row.preferred_skills or []),
        posted_at=row.posted_at,
        application_url=row.application_url,
        created_at=row.created_at,
        status=getattr(row, "status", None) or "ACTIVE",
        last_seen_at=getattr(row, "last_seen_at", None),
        last_verified_at=getattr(row, "last_verified_at", None),
        url_status=getattr(row, "url_status", None) or "UNKNOWN",
    )


def _render_job_as_text(row) -> str:
    lines = [
        f"{row.title}",
        f"Company: {row.company}",
    ]
    if row.location:
        lines.append(f"Location: {row.location} ({row.work_mode})")
    if row.experience_min is not None or row.experience_max is not None:
        low = row.experience_min if row.experience_min is not None else "?"
        high = row.experience_max if row.experience_max is not None else low
        lines.append(f"Required experience: {low} to {high} years")
    if row.salary_min is not None:
        currency = row.salary_currency or "INR"
        lines.append(f"Salary: {row.salary_min:g} - {row.salary_max:g} LPA ({currency})")
    if row.required_skills:
        lines.append("REQUIREMENTS:")
        lines.extend(f"- Hands-on experience with {skill}" for skill in row.required_skills)
    if row.preferred_skills:
        lines.append("PREFERRED / NICE TO HAVE:")
        lines.extend(f"- Exposure to {skill}" for skill in row.preferred_skills)
    if row.description:
        lines.append("")
        lines.append(row.description)
    if row.application_url:
        lines.append("")
        lines.append(f"Apply at: {row.application_url}")
    return "\n".join(lines)


def _build_matcher():
    from app.services.job_matcher import JobMatchingService

    return JobMatchingService(_get_skill_normalizer())


def _get_skill_normalizer():
    from app.services.skill_normalizer import get_skill_normalizer

    return get_skill_normalizer()



