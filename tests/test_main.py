"""Tests for main.py notification replay behavior."""

import main

from models import Job, ScrapeResult
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

    def mark_notified(self, jobs):
        self.marked.extend(job["unique_id"] for job in jobs)


class FakeNotifier:
    def __init__(self, batch_results, summary_result=True):
        self.batch_results = list(batch_results)
        self.summary_result = summary_result
        self.calls = []
        self.summary_calls = []

    def notify_backlog_skipped(self, skipped_count, sent_count, dry_run):
        self.summary_calls.append(
            {
                "skipped_count": skipped_count,
                "sent_count": sent_count,
                "dry_run": dry_run,
            }
        )
        return self.summary_result

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


def test_scan_deduplication_prefers_direct_career_record():
    repository_job = Job(
        "🔥 Stripe",
        "Software Engineer New Grad",
        "https://stripe.com/jobs/search?gh_jid=8128744&utm_source=Simplify&ref=Simplify",
        "Seattle, WA",
        "SimplifyJobs/New-Grad-Positions",
    )
    career_job = Job(
        "Stripe",
        "Software Engineer, New Grad",
        "https://stripe.com/jobs/search?gh_jid=8128744",
        "San Francisco, Seattle, New York",
        "career_page",
    )

    assert main._deduplicate_scan_jobs([repository_job, career_job]) == [career_job]


def test_scan_deduplication_normalizes_lever_apply_suffix():
    repository_job = Job(
        "Palantir",
        "Software Engineer, New Grad",
        "https://jobs.lever.co/palantir/abc/apply?utm_source=Simplify",
        "New York, NY",
        "repository",
    )
    career_job = Job(
        "Palantir",
        "Software Engineer, New Grad",
        "https://jobs.lever.co/palantir/abc",
        "New York, NY",
        "career_page",
    )

    assert main._deduplicate_scan_jobs([repository_job, career_job]) == [career_job]


def test_scan_deduplication_keeps_distinct_apply_urls():
    first = Job("Uber", "Software Engineer I", "https://example.com/1", "New York", "career_page")
    second = Job("Uber", "Software Engineer I", "https://example.com/2", "Seattle", "career_page")

    assert main._deduplicate_scan_jobs([first, second]) == [first, second]

def test_pending_backlog_is_sent_even_without_new_jobs():
    storage = FakeStorage([_make_pending_job(1), _make_pending_job(2)])
    notifier = FakeNotifier([True])

    success = main._send_pending_notifications(storage, notifier, dry_run=False)

    assert success is True
    assert notifier.calls[0]["ids"] == ["job-1", "job-2"]
    assert storage.marked == ["job-1", "job-2"]


def test_successful_batches_mark_each_batch_individually():
    pending_jobs = [_make_pending_job(index) for index in range(15)]
    storage = FakeStorage(pending_jobs)
    notifier = FakeNotifier([True, True])

    success = main._send_pending_notifications(storage, notifier, dry_run=False)

    assert success is True
    assert [len(call["ids"]) for call in notifier.calls] == [10, 5]
    assert storage.marked == [job["unique_id"] for job in pending_jobs]


def test_failed_later_batch_leaves_unsent_jobs_pending():
    pending_jobs = [_make_pending_job(index) for index in range(15)]
    storage = FakeStorage(pending_jobs)
    notifier = FakeNotifier([True, False])

    success = main._send_pending_notifications(storage, notifier, dry_run=False)

    assert success is False
    assert [len(call["ids"]) for call in notifier.calls] == [10, 5]
    assert storage.marked == [job["unique_id"] for job in pending_jobs[:10]]


def test_large_backlog_sends_summary_and_newest_jobs_only():
    backlog_size = main.MAX_PENDING_JOBS_TO_NOTIFY + 5
    pending_jobs = [_make_pending_job(index) for index in range(backlog_size)]
    storage = FakeStorage(pending_jobs)
    notifier = FakeNotifier(
        [True] * ((main.MAX_PENDING_JOBS_TO_NOTIFY + 9) // 10)
    )

    success = main._send_pending_notifications(storage, notifier, dry_run=False)

    assert success is True
    assert notifier.summary_calls == [
        {
            "skipped_count": 5,
            "sent_count": main.MAX_PENDING_JOBS_TO_NOTIFY,
            "dry_run": False,
        }
    ]
    sent_ids = [job_id for call in notifier.calls for job_id in call["ids"]]
    assert sent_ids == [f"job-{index}" for index in range(5, backlog_size)]
    assert storage.marked == [
        *[f"job-{index}" for index in range(5, backlog_size)],
        *[f"job-{index}" for index in range(5)],
    ]


def test_large_backlog_keeps_pending_if_summary_fails():
    backlog_size = main.MAX_PENDING_JOBS_TO_NOTIFY + 5
    pending_jobs = [_make_pending_job(index) for index in range(backlog_size)]
    storage = FakeStorage(pending_jobs)
    notifier = FakeNotifier([True, True], summary_result=False)

    success = main._send_pending_notifications(storage, notifier, dry_run=False)

    assert success is False
    assert notifier.summary_calls == [
        {
            "skipped_count": 5,
            "sent_count": main.MAX_PENDING_JOBS_TO_NOTIFY,
            "dry_run": False,
        }
    ]
    assert notifier.calls == []
    assert storage.marked == []


def test_large_backlog_keeps_skipped_pending_if_job_batch_fails():
    backlog_size = main.MAX_PENDING_JOBS_TO_NOTIFY + 5
    pending_jobs = [_make_pending_job(index) for index in range(backlog_size)]
    storage = FakeStorage(pending_jobs)
    notifier = FakeNotifier([True, False])

    success = main._send_pending_notifications(storage, notifier, dry_run=False)

    assert success is False
    assert [call["ids"] for call in notifier.calls] == [
        [f"job-{index}" for index in range(5, 15)],
        [f"job-{index}" for index in range(15, 25)],
    ]
    assert storage.marked == [f"job-{index}" for index in range(5, 15)]


def test_no_pending_notifications_succeeds():
    storage = FakeStorage([])
    notifier = FakeNotifier([])

    success = main._send_pending_notifications(storage, notifier, dry_run=False)

    assert success is True
    assert notifier.calls == []
    assert storage.marked == []


def test_company_alerts_can_be_disabled(monkeypatch, tmp_path):
    storage = JobStorage(db_path=str(tmp_path / "test.db"))
    notifier = FakeCompanyNotifier()
    result = ScrapeResult(
        status="parse_failure",
        error="Meta: no candidate job links found",
    )
    monkeypatch.setattr(main, "ENABLE_COMPANY_HEALTH_ALERTS", False)

    for _ in range(12):
        main._update_company_health(
            storage,
            notifier,
            {"Meta": result},
            notify=True,
            dry_run=False,
        )

    assert notifier.company_failures == []


def test_company_alerts_can_be_enabled(monkeypatch, tmp_path):
    storage = JobStorage(db_path=str(tmp_path / "test.db"))
    notifier = FakeCompanyNotifier()
    result = ScrapeResult(
        status="parse_failure",
        error="Meta: no candidate job links found",
    )
    monkeypatch.setattr(main, "ENABLE_COMPANY_HEALTH_ALERTS", True)

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


def test_company_recovery_alerts_are_never_sent(monkeypatch, tmp_path):
    storage = JobStorage(db_path=str(tmp_path / "test.db"))
    notifier = FakeCompanyNotifier()
    failure = ScrapeResult(status="parse_failure", error="temporary failure")
    success = ScrapeResult(status="empty")
    monkeypatch.setattr(main, "ENABLE_COMPANY_HEALTH_ALERTS", True)

    for _ in range(3):
        main._update_company_health(
            storage,
            notifier,
            {"NVIDIA": failure},
            notify=True,
            dry_run=False,
        )

    main._update_company_health(
        storage,
        notifier,
        {"NVIDIA": success},
        notify=True,
        dry_run=False,
    )

    assert not hasattr(notifier, "notify_company_recovery")
    assert storage.record_company_success("NVIDIA", [3]) == 0


def test_dry_run_keeps_all_pending_jobs():
    storage = FakeStorage([_make_pending_job(i) for i in range(55)])
    notifier = FakeNotifier([True] * 5)
    assert main._send_pending_notifications(storage, notifier, dry_run=True)
    assert storage.marked == []
    assert all(call["dry_run"] for call in notifier.calls + notifier.summary_calls)


def test_list_recent_zero_does_not_scrape(monkeypatch, tmp_path):
    storage = JobStorage(str(tmp_path / "test.db"))
    monkeypatch.setattr(main, "JobStorage", lambda: storage)
    monkeypatch.setattr(main.sys, "argv", ["main.py", "--list-recent", "0"])
    def unexpected_scrape():
        raise AssertionError("list command must not scrape")
    monkeypatch.setattr(main, "GitHubTracker", unexpected_scrape)
    monkeypatch.setattr(main, "CareerScraper", unexpected_scrape)
    main.main()


def test_failed_batch_is_replayed_from_real_database(tmp_path):
    from models import Job
    storage = JobStorage(str(tmp_path / "test.db"))
    jobs = [Job("Acme", "Software Engineer", f"https://example.com/{i}", "Seattle, WA", "test")
            for i in range(15)]
    storage.add_jobs(jobs)
    assert not main._send_pending_notifications(storage, FakeNotifier([True, False]), dry_run=False)
    assert [row["url"] for row in storage.get_unnotified()] == [job.url for job in jobs[10:]]
    assert storage.add_jobs(jobs) == []
    assert main._send_pending_notifications(storage, FakeNotifier([True]), dry_run=False)
    assert storage.get_unnotified() == []
