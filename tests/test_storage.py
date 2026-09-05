"""Tests for storage.py."""

import sqlite3

import pytest

from models import Job
from storage import JobStorage


@pytest.fixture
def db(tmp_path):
    return JobStorage(db_path=str(tmp_path / "test.db"))


def _make_job(company="TestCo", title="Software Engineer", url="https://example.com/1"):
    return Job(
        company=company,
        title=title,
        url=url,
        location="Seattle, WA",
        source="test",
    )


class TestInsertAndDedup:
    def test_batch_returns_new_jobs_once_and_preserves_notification_state(self, db):
        seen = _make_job(url="https://example.com/seen")
        new = _make_job(url="https://example.com/new")
        db.add_jobs([seen], notified=True)
        assert db.add_jobs([seen, new, new]) == [new]
        assert db.add_jobs([seen, new]) == []
        assert [row["url"] for row in db.get_unnotified()] == [new.url]
        assert db.get_stats()["total_jobs"] == 2

    def test_invalid_batch_rolls_back_all_inserts(self, db):
        invalid = _make_job(company=None)
        with pytest.raises(sqlite3.IntegrityError):
            db.add_jobs([_make_job(), invalid])
        assert db.get_stats()["total_jobs"] == 0


class TestMarkNotified:
    def test_mark_notified(self, db):
        job = _make_job()
        db.add_jobs([job], notified=False)
        assert len(db.get_unnotified()) == 1
        db.mark_notified([job])
        assert len(db.get_unnotified()) == 0


class TestGetUnnotified:
    def test_returns_only_unnotified(self, db):
        job1 = _make_job(url="https://example.com/1")
        job2 = _make_job(url="https://example.com/2")
        db.add_jobs([job1], notified=True)
        db.add_jobs([job2], notified=False)
        unnotified = db.get_unnotified()
        assert len(unnotified) == 1
        assert unnotified[0]["url"] == "https://example.com/2"

    def test_orders_oldest_first(self, db):
        job1 = _make_job(url="https://example.com/1")
        job2 = _make_job(url="https://example.com/2")
        db.add_jobs([job1], notified=False)
        db.add_jobs([job2], notified=False)

        with sqlite3.connect(db.db_path) as conn:
            conn.execute(
                "UPDATE seen_jobs SET first_seen = '2026-01-01 00:00:00' WHERE unique_id = ?",
                (job1.unique_id,),
            )
            conn.execute(
                "UPDATE seen_jobs SET first_seen = '2026-01-02 00:00:00' WHERE unique_id = ?",
                (job2.unique_id,),
            )
            conn.commit()

        unnotified = db.get_unnotified()
        assert [job["url"] for job in unnotified] == [
            "https://example.com/1",
            "https://example.com/2",
        ]


class TestGetRecent:
    def test_limit(self, db):
        for i in range(5):
            db.add_jobs([_make_job(url=f"https://example.com/{i}")])
        recent = db.get_recent(limit=3)
        assert len(recent) == 3

    def test_ordered_by_newest(self, db):
        db.add_jobs([_make_job(title="First", url="https://example.com/1")])
        db.add_jobs([_make_job(title="Second", url="https://example.com/2")])
        recent = db.get_recent(limit=2)
        assert recent[0]["title"] == "Second"


class TestGetStats:
    def test_stats(self, db):
        db.add_jobs([_make_job(company="A", url="https://example.com/1")], notified=True)
        db.add_jobs([_make_job(company="A", url="https://example.com/2")], notified=False)
        db.add_jobs([_make_job(company="B", url="https://example.com/3")], notified=True)
        failures, threshold = db.record_company_failure("Google", "parse failure", [3])
        assert (failures, threshold) == (1, None)
        stats = db.get_stats()
        assert stats["total_jobs"] == 3
        assert stats["notified_jobs"] == 2
        assert stats["pending_notification"] == 1
        assert stats["oldest_unnotified_first_seen"] is not None
        assert isinstance(stats["oldest_unnotified_age_hours"], int)
        assert stats["failing_priority_companies"][0]["company"] == "Google"
        assert stats["by_company"]["A"] == 2
        assert stats["by_company"]["B"] == 1


class TestSourceHealth:
    def test_failure_threshold_alerts_require_confirmation(self, db):
        thresholds = [2, 4]

        assert db.record_source_failure("github", "timeout", thresholds) == (1, None)
        assert db.record_source_failure("github", "timeout", thresholds) == (2, 2)
        # Alert repeats until confirmation persists alert state.
        assert db.record_source_failure("github", "timeout", thresholds) == (3, 2)
        db.confirm_source_failure_alert("github", 2)
        assert db.record_source_failure("github", "timeout", thresholds) == (4, 4)
        db.confirm_source_failure_alert("github", 4)
        assert db.record_source_failure("github", "timeout", thresholds) == (5, None)

    def test_recovery_alert_pending_until_confirmed(self, db):
        for _ in range(3):
            failures, threshold = db.record_source_failure("careers", "dns", [3])
        assert (failures, threshold) == (3, 3)
        db.confirm_source_failure_alert("careers", 3)

        assert db.record_source_success("careers", [3]) == 3
        # Retry recovery alert on subsequent healthy runs until confirmed.
        assert db.record_source_success("careers", [3]) == 3
        db.confirm_source_recovery_alert("careers")
        assert db.record_source_success("careers", [3]) == 0

    def test_recovery_not_alerted_before_threshold(self, db):
        db.record_source_failure("github", "timeout", [3])
        db.record_source_failure("github", "timeout", [3])

        assert db.record_source_success("github", [3]) == 0

    def test_thresholds_rearm_after_recovery(self, db):
        for _ in range(3):
            failures, threshold = db.record_source_failure("github", "timeout", [3])
        assert (failures, threshold) == (3, 3)
        db.confirm_source_failure_alert("github", 3)

        assert db.record_source_success("github", [3]) == 3
        db.confirm_source_recovery_alert("github")

        assert db.record_source_failure("github", "timeout", [3]) == (1, None)
        assert db.record_source_failure("github", "timeout", [3]) == (2, None)
        assert db.record_source_failure("github", "timeout", [3]) == (3, 3)

    def test_sources_tracked_independently(self, db):
        assert db.record_source_failure("github", "timeout", [2]) == (1, None)
        assert db.record_source_failure("careers", "dns", [2]) == (1, None)
        assert db.record_source_failure("github", "timeout", [2]) == (2, 2)
        assert db.record_source_failure("careers", "dns", [2]) == (2, 2)

    def test_first_time_success_does_not_emit_recovery(self, db):
        assert db.record_source_success("github", [3]) == 0

    def test_multi_threshold_recovery_returns_highest_failure_streak(self, db):
        thresholds = [3, 6]
        for _ in range(3):
            failures, threshold = db.record_source_failure("github", "timeout", thresholds)
        assert (failures, threshold) == (3, 3)
        db.confirm_source_failure_alert("github", 3)

        for _ in range(3):
            failures, threshold = db.record_source_failure("github", "timeout", thresholds)
        assert (failures, threshold) == (6, 6)
        db.confirm_source_failure_alert("github", 6)

        assert db.record_source_success("github", thresholds) == 6

    def test_invalid_thresholds_raise(self, db):
        with pytest.raises(ValueError):
            db.record_source_failure("github", "error", [])


class TestCompanyHealth:
    def test_failure_threshold_alerts_require_confirmation(self, db):
        thresholds = [2, 4]

        assert db.record_company_failure("Google", "timeout", thresholds) == (1, None)
        assert db.record_company_failure("Google", "timeout", thresholds) == (2, 2)
        assert db.record_company_failure("Google", "timeout", thresholds) == (3, 2)
        db.confirm_company_failure_alert("Google", 2)
        assert db.record_company_failure("Google", "timeout", thresholds) == (4, 4)

    def test_recovery_alert_pending_until_confirmed(self, db):
        for _ in range(3):
            failures, threshold = db.record_company_failure("Google", "parse failure", [3])
        assert (failures, threshold) == (3, 3)
        db.confirm_company_failure_alert("Google", 3)

        assert db.record_company_success("Google", [3]) == 3
        assert db.record_company_success("Google", [3]) == 3
        db.confirm_company_recovery_alert("Google")
        assert db.record_company_success("Google", [3]) == 0


def test_existing_database_keeps_jobs_and_health_after_index_cleanup(tmp_path):
    path = str(tmp_path / "existing.db")
    storage = JobStorage(path)
    job = _make_job()
    storage.add_jobs([job], notified=True)
    storage.record_source_failure("github", "timeout", [1])
    storage.confirm_source_failure_alert("github", 1)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE INDEX idx_unique_id ON seen_jobs(unique_id)")
        conn.execute("CREATE INDEX idx_notified ON seen_jobs(notified)")
    reopened = JobStorage(path)
    assert reopened.add_jobs([job]) == []
    assert reopened.get_stats()["notified_jobs"] == 1
    assert reopened.record_source_success("github", [1]) == 1


def test_notification_batch_rolls_back_on_invalid_record(db):
    jobs = [_make_job(url=f"https://example.com/{i}") for i in range(2)]
    db.add_jobs(jobs)
    with pytest.raises(KeyError):
        db.mark_notified([jobs[0], {}])
    assert len(db.get_unnotified()) == 2
