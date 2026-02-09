"""Tests for storage.py."""

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
    def test_new_job_is_new(self, db):
        job = _make_job()
        assert db.is_new(job) is True

    def test_seen_job_not_new(self, db):
        job = _make_job()
        db.mark_seen(job)
        assert db.is_new(job) is False

    def test_duplicate_insert_ignored(self, db):
        job = _make_job()
        db.mark_seen(job)
        db.mark_seen(job)  # should not raise
        stats = db.get_stats()
        assert stats["total_jobs"] == 1


class TestMarkNotified:
    def test_mark_notified(self, db):
        job = _make_job()
        db.mark_seen(job, notified=False)
        assert len(db.get_unnotified()) == 1
        db.mark_notified(job)
        assert len(db.get_unnotified()) == 0


class TestGetUnnotified:
    def test_returns_only_unnotified(self, db):
        job1 = _make_job(url="https://example.com/1")
        job2 = _make_job(url="https://example.com/2")
        db.mark_seen(job1, notified=True)
        db.mark_seen(job2, notified=False)
        unnotified = db.get_unnotified()
        assert len(unnotified) == 1
        assert unnotified[0]["url"] == "https://example.com/2"


class TestGetRecent:
    def test_limit(self, db):
        for i in range(5):
            db.mark_seen(_make_job(url=f"https://example.com/{i}"))
        recent = db.get_recent(limit=3)
        assert len(recent) == 3

    def test_ordered_by_newest(self, db):
        db.mark_seen(_make_job(title="First", url="https://example.com/1"))
        db.mark_seen(_make_job(title="Second", url="https://example.com/2"))
        recent = db.get_recent(limit=2)
        assert recent[0]["title"] == "Second"


class TestGetStats:
    def test_stats(self, db):
        db.mark_seen(_make_job(company="A", url="https://example.com/1"), notified=True)
        db.mark_seen(_make_job(company="A", url="https://example.com/2"), notified=False)
        db.mark_seen(_make_job(company="B", url="https://example.com/3"), notified=True)
        stats = db.get_stats()
        assert stats["total_jobs"] == 3
        assert stats["notified_jobs"] == 2
        assert stats["pending_notification"] == 1
        assert stats["by_company"]["A"] == 2
        assert stats["by_company"]["B"] == 1
