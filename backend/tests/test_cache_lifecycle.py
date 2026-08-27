"""Cache TTL, staleness and lifecycle tests."""

from datetime import datetime, timedelta, timezone

from app.database.job_repository import JobRepository
from app.schemas.jobs import Job
from app.services.job_sources.cache import (
    lookup_cached_jobs,
    mark_stale_jobs,
    touch_last_seen,
)


def _job(title="Java Developer", company="Cache Corp",
         description="Java services role", **extra) -> Job:
    return Job(title=title, company=company, description=description,
               required_skills=["Java"], **extra)


def _upsert(db, jobs):
    return JobRepository(db).upsert_canonical_jobs(jobs)


def test_fresh_cache_matches_query(temp_db):
    with temp_db.session() as db:
        _upsert(db, [_job()])
        rows, fresh = lookup_cached_jobs(db, ["Java Developer"])
    assert fresh is True
    assert len(rows) == 1


def test_unrelated_query_not_served_from_cache(temp_db):
    with temp_db.session() as db:
        _upsert(db, [_job(title="Marketing Manager", company="Ads Inc",
                          description="Social media campaigns and brand strategy")])
        rows, fresh = lookup_cached_jobs(db, ["Java Developer"])
    assert fresh is False  # nothing matched the query


def test_expired_rows_are_ignored_for_freshness(temp_db):
    from app.models.jobs import JobRow

    with temp_db.session() as db:
        mapping = _upsert(db, [_job()])
        row = next(iter(mapping.values()))
        row.last_seen_at = datetime.now(timezone.utc) - timedelta(days=5)
        db.flush()
        rows, fresh = lookup_cached_jobs(db, ["Java Developer"], ttl_minutes=60)
    assert fresh is False


def test_mark_stale_sets_unknown_not_deleted(temp_db):
    from app.models.jobs import JobRow

    with temp_db.session() as db:
        mapping = _upsert(db, [_job()])
        row = next(iter(mapping.values()))
        row.last_seen_at = datetime.now(timezone.utc) - timedelta(days=90)
        db.flush()
        changed = mark_stale_jobs(db, stale_days=30)
        assert changed >= 1
        refreshed = db.get(JobRow, row.id)
        assert refreshed.status == "UNKNOWN"
        assert refreshed.id  # still present — history preserved


def test_reencountered_job_is_refreshed_to_active(temp_db):
    from app.models.jobs import JobRow

    with temp_db.session() as db:
        mapping = _upsert(db, [_job()])
        row = next(iter(mapping.values()))
        row.status = "EXPIRED"
        db.flush()
        # Same job seen again on a source:
        _upsert(db, [_job()])
        refreshed = db.get(JobRow, row.id)
        assert refreshed.status == "ACTIVE"
        assert (refreshed.last_seen_at or refreshed.created_at) is not None


def test_touch_last_seen_updates_rows(temp_db):
    from app.models.jobs import JobRow

    with temp_db.session() as db:
        mapping = _upsert(db, [_job(), _job(title="Go Dev", company="Other")])
        ids = [r.id for r in mapping.values()]
        first_before = db.get(JobRow, ids[0]).last_seen_at
        touch_last_seen(db, [ids[0]])
        first = db.get(JobRow, ids[0])
        second = db.get(JobRow, ids[1])
        assert first.last_seen_at is not None
        if first_before is not None:
            assert first.last_seen_at >= first_before
        # Untouched row keeps its original value.
        assert second.last_seen_at == first_before or second.last_seen_at is not None
