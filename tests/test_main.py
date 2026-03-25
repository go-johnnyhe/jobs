"""Tests for main.py notification replay behavior."""

import main

from models import ScrapeResult
from storage import JobStorage


def _make_pending_job(index: int) -> dict:
    return {
        "unique_id": f"job-{index}",
        "company": f"Company {index}",
        "title": f"Software Engineer {index}",
        "url": f"https://example.com/{index}",
        "location": "Seattle, WA",
        "source": "test",
    }


class FakeStorage:
    def __init__(self, pending_jobs):
        self.pending_jobs = pending_jobs
        self.marked = []

    def get_unnotified(self):
        return list(self.pending_jobs)

    def mark_notified(self, job):
        self.marked.append(job["unique_id"])


class FakeNotifier:
    def __init__(self, batch_results):
        self.batch_results = list(batch_results)
        self.calls = []

    def send_job_batch(self, jobs, *, total_jobs, batch_index, dry_run):
        self.calls.append(
            {
                "ids": [job["unique_id"] for job in jobs],
                "total_jobs": total_jobs,
                "batch_index": batch_index,
                "dry_run": dry_run,
            }
        )
        return self.batch_results[batch_index]


class FakeCompanyNotifier:
    def __init__(self):
        self.company_failures = []

    def notify_company_failure(self, company, failures, error, dry_run):
        self.company_failures.append((company, failures, error, dry_run))
        return True

    def notify_company_recovery(self, company, recovered_after, dry_run):
        return True


def test_pending_backlog_is_sent_even_without_new_jobs():
    storage = FakeStorage([_make_pending_job(1), _make_pending_job(2)])
    notifier = FakeNotifier([True])

    main._send_pending_notifications(storage, notifier, dry_run=False)

    assert notifier.calls[0]["ids"] == ["job-1", "job-2"]
    assert storage.marked == ["job-1", "job-2"]


def test_successful_batches_mark_each_batch_individually():
    pending_jobs = [_make_pending_job(index) for index in range(15)]
    storage = FakeStorage(pending_jobs)
    notifier = FakeNotifier([True, True])

    main._send_pending_notifications(storage, notifier, dry_run=False)

    assert [len(call["ids"]) for call in notifier.calls] == [10, 5]
    assert storage.marked == [job["unique_id"] for job in pending_jobs]


def test_failed_later_batch_leaves_unsent_jobs_pending():
    pending_jobs = [_make_pending_job(index) for index in range(15)]
    storage = FakeStorage(pending_jobs)
    notifier = FakeNotifier([True, False])

    main._send_pending_notifications(storage, notifier, dry_run=False)

    assert [len(call["ids"]) for call in notifier.calls] == [10, 5]
    assert storage.marked == [job["unique_id"] for job in pending_jobs[:10]]


def test_company_alerts_fire_once_per_failure_streak(tmp_path):
    storage = JobStorage(db_path=str(tmp_path / "test.db"))
    notifier = FakeCompanyNotifier()
    result = ScrapeResult(
        status="parse_failure",
        error="Meta: no candidate job links found",
    )

    for _ in range(12):
        main._update_company_health(
            storage,
            notifier,
            {"Meta": result},
            notify=True,
            dry_run=False,
        )

    assert notifier.company_failures == [
        ("Meta", 3, "Meta: no candidate job links found", False)
    ]
