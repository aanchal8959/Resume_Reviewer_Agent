"""JobSourceManager tests: isolation, merging, statuses."""

from app.config import get_settings
from app.schemas.jobs import JobSearchPreferences, RawJob
from app.services.job_sources.base import ProviderAdapter
from app.services.job_sources.manager import JobSourceManager

PREFS = JobSearchPreferences(keywords=["Java Developer"])


def _raw(source: str, job_id: str, title: str = "Java Developer") -> RawJob:
    return RawJob(source=source, source_type="REAL", source_job_id=job_id,
                  title=title, company="ABC Corp", description="Java role")


def _adapter(name: str, fn) -> ProviderAdapter:
    return ProviderAdapter(name, name.title(), "REAL", True, fn)


def _settings():
    return get_settings()


def _manager(adapters):
    return JobSourceManager(adapters=adapters)


def test_failing_provider_does_not_break_search():
    def boom(prefs, queries):
        raise TimeoutError("provider down")

    ok_jobs = [_raw("provider_b", "b1")]
    good = _adapter("provider_b", lambda prefs, queries: ok_jobs)
    bad = _adapter("provider_a", boom)
    merged, statuses = _manager([bad, good]).search(PREFS, ["Java Developer"])

    assert [job.source_job_id for job in merged] == ["b1"]
    by_name = {status.name.lower(): status for status in statuses}
    assert by_name["provider_a"].status == "error"
    assert by_name["provider_a"].count == 0
    assert by_name["provider_b"].status == "success"
    # Sanitized user-safe message, never a raw traceback/secret.
    assert by_name["provider_a"].message and "provider down" not in \
        by_name["provider_a"].message.lower()


def test_results_are_merged_across_providers():
    a = _adapter("a", lambda p, q: [_raw("a", "1"), _raw("a", "2")])
    b = _adapter("b", lambda p, q: [_raw("b", "3")])
    merged, statuses = _manager([a, b]).search(PREFS, ["java"])
    assert len(merged) == 3
    assert all(status.status == "success" for status in statuses)


def test_malformed_records_are_dropped_by_pipeline_not_manager():
    """Manager passes raw records through; normalization drops bad ones later."""
    weird = RawJob(source="weird", source_job_id="x", title="", company="")
    a = _adapter("a", lambda p, q: [weird])
    merged, _statuses = _manager([a]).search(PREFS, ["java"])
    assert len(merged) == 1  # untouched at manager level


def test_empty_provider_reports_empty_status():
    empty = _adapter("empty", lambda p, q: [])
    other = _adapter("other", lambda p, q: [_raw("other", "9")])
    _merged, statuses = _manager([empty, other]).search(PREFS, ["java"])
    by_name = {s.name.lower(): s for s in statuses}
    assert by_name["empty"].status == "empty"
    assert by_name["other"].status == "success"


def test_health_report_has_no_secrets():
    adapter = _adapter("secret_source", lambda p, q: [])
    manager = JobSourceManager(adapters=[adapter])
    report = manager.health()
    text = str(report)
    assert "api_key" not in text and "app_id" not in text
    assert {entry["source"] for entry in report} == {"secret_source"}
    assert report[0]["enabled"] is True
