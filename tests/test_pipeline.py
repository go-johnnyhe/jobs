"""Tests for baselining, two-channel delivery, and end-to-end runs of main()."""

from collections import Counter
import json
import re
import sqlite3
import sys

import pytest

import main
import screening
from assistant_notifier import AssistantNotifier, DeliveryResult
from models import Job, ScrapeResult
from storage import DELIVERED, PENDING, SUPPRESSED, JobStorage
from tests.postings import load_posting
from tests.test_assistant_notifier import WebhookServer

SIMPLIFY = "SimplifyJobs/New-Grad-Positions"
SPEEDY = "speedyapply/2027-SWE-College-Jobs"


def make_job(n, source=SIMPLIFY, company="Acme", **kwargs):
    return Job(
        company=company,
        title=kwargs.pop("title", f"Software Engineer {n}"),
        url=kwargs.pop("url", f"https://boards.greenhouse.io/{company.lower()}/jobs/{n}"),
        location="Seattle, WA",
        source=source,
        **kwargs,
    )


@pytest.fixture
def storage(tmp_path):
    return JobStorage(str(tmp_path / "jobs.db"))


# ---------------------------------------------------------------------------
# Baselining
# ---------------------------------------------------------------------------

def classify(jobs, baselined=(), fresh=False, skip=False, threshold=5):
    return main._classify_new_jobs(
        jobs,
        baselined_units=set(baselined),
        fresh_install=fresh,
        threshold=threshold,
        skip_baseline=skip,
    )


def test_fresh_install_baselines_everything():
    jobs = [make_job(1), make_job(2, source="career_page")]
    deliver, baseline, counts = classify(jobs, fresh=True)
    assert deliver == []
    assert baseline == jobs
    assert counts == {SIMPLIFY: 1, "careers:Acme": 1}


def test_known_units_deliver_any_number_of_jobs():
    jobs = [make_job(n) for n in range(20)]
    deliver, baseline, _ = classify(jobs, baselined=[SIMPLIFY])
    assert deliver == jobs
    assert baseline == []


def test_new_unit_with_few_jobs_is_delivered_but_large_one_is_baselined():
    new_company = [make_job(n, source="career_page", company="Remitly") for n in range(2)]
    new_list = [make_job(n, source=SPEEDY) for n in range(10, 16)]
    deliver, baseline, counts = classify(new_company + new_list, baselined=[SIMPLIFY])
    assert deliver == new_company
    assert baseline == new_list
    assert counts == {SPEEDY: 6}


def test_baselined_batch_still_delivers_jobs_posted_in_the_last_48_hours():
    from datetime import datetime, timezone
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    posted = {
        1: "2026-10-14", 2: "2026-10-12", 3: "2026-10-11", 4: "Posted Today",
        5: "2026-10-13T08:00:00Z", 6: "Posted 30+ Days Ago", 7: None, 8: "soon",
    }
    jobs = [make_job(n, source=SPEEDY, date_posted=value) for n, value in posted.items()]
    deliver, baseline, counts = main._classify_new_jobs(
        jobs, baselined_units={SIMPLIFY}, fresh_install=False, threshold=5,
        skip_baseline=False, now=now,
    )
    assert [job.title for job in deliver] == [
        "Software Engineer 1", "Software Engineer 2", "Software Engineer 4", "Software Engineer 5",
    ]
    assert counts == {SPEEDY: 4}
    assert len(baseline) == 4


def test_skip_baseline_delivers_everything():
    jobs = [make_job(n, source=SPEEDY) for n in range(10)]
    deliver, baseline, _ = classify(jobs, fresh=True, skip=True)
    assert deliver == jobs
    assert baseline == []


# ---------------------------------------------------------------------------
# _process_scan
# ---------------------------------------------------------------------------

def test_process_scan_stores_each_outcome(storage, monkeypatch):
    storage.set_meta("fresh_install", None)
    storage.mark_baselined({SIMPLIFY, "careers:Acme"})
    known = make_job(1)
    storage.add_jobs([known], notified=True)

    needs_fetch = make_job(
        2, source="career_page",
        description_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs/2",
    )
    keep_after_fetch = make_job(
        3, source="career_page",
        description_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs/3",
    )
    plain = make_job(4)
    duplicate = make_job(4, source=SPEEDY, title="SWE 4 duplicate")
    new_list = [make_job(n, source=SPEEDY, company="Other") for n in range(100, 106)]

    def fake_enrich(jobs, *, max_fetches):
        descriptions = {
            needs_fetch.url: "We are unable to sponsor visas for this role.",
            keep_after_fetch.url: "We sponsor visas. 2+ years of experience.",
        }
        for job in jobs:
            if job.url in descriptions:
                job.description = descriptions[job.url]
        return {"candidates": 2, "fetched": 2, "failed": 0, "skipped": 0}

    monkeypatch.setattr(main, "enrich_descriptions", fake_enrich)
    summary = {}
    queued = main._process_scan(
        storage,
        [make_job(1, title="Renamed"), needs_fetch, keep_after_fetch, plain, duplicate, *new_list],
        scanned_units={SIMPLIFY, SPEEDY, "careers:Acme"},
        skip_baseline=False,
        summary=summary,
    )

    assert [job.title for job in queued] == ["Software Engineer 3", "Software Engineer 4"]
    assert queued[0].sponsorship == "yes"
    assert queued[0].seniority_flag == "borderline"
    assert summary["duplicates_in_scan"] == 1
    assert summary["already_known"] == 1
    assert summary["new"] == 9
    assert summary["baselined"] == {SPEEDY: 6}
    assert summary["screened_after_fetch"] == {"no_sponsorship": 1}
    assert summary["queued"] == 2

    rows = {row["title"]: row for row in storage.get_recent(50)}
    assert rows["Software Engineer 2"]["notified"] == SUPPRESSED
    assert rows["Software Engineer 2"]["suppressed_reason"] == "screened_out:no_sponsorship"
    assert rows["Software Engineer 3"]["assistant_notified"] == PENDING
    assert json.loads(rows["Software Engineer 3"]["screening_notes"])[0].startswith("sponsorship offered")
    assert rows["Software Engineer 100"]["suppressed_reason"] == "baseline"
    assert storage.baselined_units() == {SIMPLIFY, SPEEDY, "careers:Acme"}

    again = main._process_scan(
        storage, list(new_list) + [make_job(106, source=SPEEDY, company="Other")],
        scanned_units={SPEEDY}, skip_baseline=False, summary={},
    )
    assert [job.title for job in again] == ["Software Engineer 106"]


def _elastic_job():
    posting = load_posting("elastic_analytics_engineer_us")
    job = make_job(
        8244449, source="career_page", company="Elastic", title=posting.title,
        description_url="https://boards-api.greenhouse.io/v1/boards/elastic/jobs/8244449",
    )
    return job, posting.text


def test_rule_change_rescreens_past_drops(storage, monkeypatch):
    storage.set_meta("fresh_install", None)
    storage.mark_baselined({"careers:Elastic"})
    fetched = []

    def fake_enrich(jobs, *, max_fetches):
        for job in jobs:
            fetched.append(job.title)
            job.description = text
        return {"candidates": len(jobs), "fetched": len(jobs), "failed": 0, "skipped": 0}

    monkeypatch.setattr(main, "enrich_descriptions", fake_enrich)
    # The rules before this fix: any "polygraph", including the EPPA poster footer.
    original_clearance = screening._CLEARANCE_RE
    monkeypatch.setattr(
        screening, "_CLEARANCE_RE", [*original_clearance, re.compile(r"\bpolygraph\b", re.I)],
    )
    monkeypatch.setattr(main, "SCREENING_VERSION", "old-rules")
    job, text = _elastic_job()
    assert main._process_scan(
        storage, [job], scanned_units={"careers:Elastic"}, skip_baseline=False, summary={},
    ) == []
    row = storage.get_recent(1)[0]
    assert row["suppressed_reason"] == "screened_out:clearance_required"
    assert row["screening_version"] == "old-rules"
    with sqlite3.connect(storage.db_path) as conn:
        conn.execute("UPDATE seen_jobs SET first_seen = '2020-01-01 00:00:00'")

    # The next scan with fixed rules re-fetches, re-screens, and queues it.
    monkeypatch.setattr(screening, "_CLEARANCE_RE", original_clearance)
    monkeypatch.setattr(main, "SCREENING_VERSION", "new-rules")
    job, _ = _elastic_job()
    summary = {}
    queued = main._process_scan(
        storage, [job], scanned_units={"careers:Elastic"}, skip_baseline=False, summary=summary,
    )
    assert [j.title for j in queued] == [job.title]
    assert summary["requeued"] == 1
    row = storage.get_recent(1)[0]
    assert (row["notified"], row["assistant_notified"]) == (PENDING, PENDING)
    assert row["suppressed_reason"] is None
    assert row["screening_version"] == "new-rules"
    assert row["queued_at"]
    # Backlog expiry counts from when it was queued again, not from first_seen.
    assert storage.retire_stale_pending("assistant", 168) == 0

    # Same rules on the next scan: no re-fetch, no second queueing.
    fetched.clear()
    job, _ = _elastic_job()
    assert main._process_scan(
        storage, [job], scanned_units={"careers:Elastic"}, skip_baseline=False, summary={},
    ) == []
    assert fetched == []


def test_rescreen_that_still_drops_or_cannot_fetch(storage, monkeypatch):
    storage.set_meta("fresh_install", None)
    storage.mark_baselined({"careers:Acme"})
    drop = make_job(1, source="career_page", description_url="https://api.example/1")
    unfetched = make_job(2, source="career_page", description_url="https://api.example/2")
    storage.add_jobs(
        [drop, unfetched], discord_state=SUPPRESSED, assistant_state=SUPPRESSED,
        suppressed_reason="screened_out:no_sponsorship", screening_version="old-rules",
    )

    def fake_enrich(jobs, *, max_fetches):
        for job in jobs:
            if job.url == drop.url:
                job.description = "We are unable to sponsor visas for this role."
        return {"candidates": 2, "fetched": 1, "failed": 1, "skipped": 0}

    monkeypatch.setattr(main, "enrich_descriptions", fake_enrich)
    assert main._process_scan(
        storage,
        [make_job(1, source="career_page", description_url=drop.description_url),
         make_job(2, source="career_page", description_url=unfetched.description_url)],
        scanned_units={"careers:Acme"}, skip_baseline=False, summary={},
    ) == []
    rows = {row["title"]: row for row in storage.get_recent(10)}
    assert rows[drop.title]["screening_version"] == main.SCREENING_VERSION
    assert rows[drop.title]["notified"] == SUPPRESSED
    assert rows[unfetched.title]["screening_version"] == "old-rules"
    assert rows[unfetched.title]["notified"] == SUPPRESSED


def test_failed_units_are_not_marked_scanned(storage):
    summary = {}
    main._process_scan(storage, [], scanned_units=set(), skip_baseline=False, summary=summary)
    assert storage.baselined_units() == set()


def test_scanned_units_ignore_failed_sources():
    class Tracker:
        last_repo_results = {
            SIMPLIFY: ScrapeResult(status="success", jobs=[make_job(1)]),
            SPEEDY: ScrapeResult(status="request_failure", error="x"),
        }

    class Scraper:
        last_company_results = {
            "Acme": ScrapeResult(status="empty"),
            "Beta": ScrapeResult(status="parse_failure", error="x"),
            "Gamma": ScrapeResult(status="degraded_partial", jobs=[]),
        }

    assert main._scanned_units(Tracker(), Scraper()) == {SIMPLIFY, "careers:Acme", "careers:Gamma"}
    assert main._scanned_units(None, None) == set()


# ---------------------------------------------------------------------------
# Delivery channels
# ---------------------------------------------------------------------------

class RecordingDiscord:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.batches = []

    def send_job_batch(self, jobs, *, total_jobs, batch_index, dry_run, queued_after=0):
        self.batches.append([job["title"] for job in jobs])
        return self.results.pop(0) if self.results else True

    def notify_source_failure(self, *_args, **_kwargs):
        return True

    def notify_source_recovery(self, *_args, **_kwargs):
        return True

    def notify_company_failure(self, *_args, **_kwargs):
        return True


class RecordingAssistant(AssistantNotifier):
    """results: True (accepted), False (endpoint down), an int status, or a
    callable taking the payload and returning one of those."""

    def __init__(self, results=None, configured=True, batch_size=25):
        super().__init__("https://assistant.example/hook" if configured else "", "", batch_size=batch_size)
        self.results = list(results or [])
        self.payloads = []

    def deliver(self, payload, *, dry_run=False):
        self.payloads.append(payload)
        outcome = self.results.pop(0) if self.results else True
        if callable(outcome):
            outcome = outcome(payload)
        if outcome is True:
            return DeliveryResult(ok=True, status=200)
        return DeliveryResult(ok=False, status=503 if outcome is False else outcome)


def seed_pending(storage, count):
    jobs = [make_job(n) for n in range(count)]
    storage.add_jobs(jobs)
    return jobs


def test_assistant_unconfigured_is_skipped_quietly(storage):
    seed_pending(storage, 3)
    assistant = RecordingAssistant(configured=False)
    assert main._send_assistant_notifications(
        storage, assistant, dry_run=False, run_timestamp="2026-10-14T00:00:00Z",
    ) is True
    assert assistant.payloads == []
    assert len(storage.get_pending("assistant")) == 3


def test_assistant_sends_batches_of_25_and_marks_each(storage):
    seed_pending(storage, 60)
    assistant = RecordingAssistant()
    assert main._send_assistant_notifications(
        storage, assistant, dry_run=False, run_timestamp="2026-10-14T00:00:00Z",
    ) is True
    assert [p["batch"]["size"] for p in assistant.payloads] == [25, 25, 10]
    assert [p["batch"]["index"] for p in assistant.payloads] == [0, 1, 2]
    assert {p["batch"]["count"] for p in assistant.payloads} == {3}
    assert {p["run_timestamp"] for p in assistant.payloads} == {"2026-10-14T00:00:00Z"}
    assert storage.get_pending("assistant") == []
    assert len(storage.get_pending("discord")) == 60


def test_assistant_failure_keeps_unsent_batches_pending(storage):
    seed_pending(storage, 60)
    assistant = RecordingAssistant(results=[True, False])
    assert main._send_assistant_notifications(
        storage, assistant, dry_run=False, run_timestamp="t",
    ) is False
    pending = storage.get_pending("assistant")
    assert len(pending) == 35
    assert pending[0]["title"] == "Software Engineer 25"


def test_assistant_per_run_cap_reports_remaining(storage, monkeypatch):
    seed_pending(storage, 30)
    monkeypatch.setattr(main, "ASSISTANT_MAX_JOBS_PER_RUN", 20)
    assistant = RecordingAssistant(batch_size=10)
    main._send_assistant_notifications(storage, assistant, dry_run=False, run_timestamp="t")
    assert [p["batch"]["pending_after_run"] for p in assistant.payloads] == [10, 10]
    assert {p["batch"]["total_jobs"] for p in assistant.payloads} == {20}
    assert len(storage.get_pending("assistant")) == 10


def test_assistant_dry_run_marks_nothing(storage):
    seed_pending(storage, 3)
    assistant = RecordingAssistant(configured=False)
    assert main._send_assistant_notifications(storage, assistant, dry_run=True, run_timestamp="t") is True
    assert len(assistant.payloads) == 1
    assert len(storage.get_pending("assistant")) == 3


def test_assistant_retires_week_old_backlog(storage):
    seed_pending(storage, 2)
    with sqlite3.connect(storage.db_path) as conn:
        conn.execute("UPDATE seen_jobs SET first_seen = '2020-01-01 00:00:00' WHERE title LIKE '%0'")
    assistant = RecordingAssistant()
    main._send_assistant_notifications(storage, assistant, dry_run=False, run_timestamp="t")
    assert [len(p["jobs"]) for p in assistant.payloads] == [1]
    assert len(storage.get_pending("discord")) == 2


def _reject_job(title, status=422):
    def outcome(payload):
        return status if any(job["title"] == title for job in payload["jobs"]) else True
    return outcome


def test_rejected_batch_is_split_and_only_the_bad_job_stays_pending(storage):
    seed_pending(storage, 25)
    bad = "Software Engineer 13"
    assistant = RecordingAssistant(results=[_reject_job(bad)] * 50)
    assert main._send_assistant_notifications(
        storage, assistant, dry_run=False, run_timestamp="t",
    ) is False
    assert [row["title"] for row in storage.get_pending("assistant")] == [bad]
    delivered = [
        job["title"] for p in assistant.payloads if bad not in [j["title"] for j in p["jobs"]]
        for job in p["jobs"]
    ]
    assert len(delivered) == 24 and len(set(delivered)) == 24
    # Bisecting 25 jobs isolates the bad one in a handful of requests.
    assert len(assistant.payloads) <= 12
    assert [bad] in [[job["title"] for job in p["jobs"]] for p in assistant.payloads]
    assert storage.get_pending("assistant")[0]["assistant_attempts"] == 1


def test_job_rejected_on_three_runs_is_retired_with_a_reason(storage):
    seed_pending(storage, 3)
    bad = "Software Engineer 1"
    for run in range(3):
        assistant = RecordingAssistant(results=[_reject_job(bad, 400)] * 10)
        assert main._send_assistant_notifications(
            storage, assistant, dry_run=False, run_timestamp="t",
        ) is False
        pending = [row["title"] for row in storage.get_pending("assistant")]
        assert pending == ([bad] if run < 2 else [])
    row = next(r for r in storage.get_recent(10) if r["title"] == bad)
    assert row["assistant_notified"] == SUPPRESSED
    assert row["suppressed_reason"] == "assistant_rejected:HTTP 400"
    assert row["notified"] == PENDING

    # Later runs are unaffected.
    storage.add_jobs([make_job(50)])
    assistant = RecordingAssistant()
    assert main._send_assistant_notifications(storage, assistant, dry_run=False, run_timestamp="t") is True
    assert [job["title"] for p in assistant.payloads for job in p["jobs"]] == ["Software Engineer 50"]


@pytest.mark.parametrize("status", [401, 403, 404, 503])
def test_endpoint_errors_stop_without_counting_rejections(storage, status):
    seed_pending(storage, 30)
    assistant = RecordingAssistant(results=[True, status])
    assert main._send_assistant_notifications(storage, assistant, dry_run=False, run_timestamp="t") is False
    assert len(assistant.payloads) == 2
    pending = storage.get_pending("assistant")
    assert len(pending) == 5
    assert {row["assistant_attempts"] for row in pending} == {0}


def test_channels_fail_independently(storage):
    seed_pending(storage, 3)
    assistant_down = RecordingAssistant(results=[False])
    discord = RecordingDiscord()
    assert main._send_assistant_notifications(storage, assistant_down, dry_run=False, run_timestamp="t") is False
    assert main._send_pending_notifications(storage, discord, dry_run=False) is True
    assert storage.get_pending("discord") == []
    assert len(storage.get_pending("assistant")) == 3

    storage.add_jobs([make_job(99)])
    discord_down = RecordingDiscord(results=[False])
    assert main._send_pending_notifications(storage, discord_down, dry_run=False) is False
    assert main._send_assistant_notifications(storage, RecordingAssistant(), dry_run=False, run_timestamp="t") is True
    assert storage.get_pending("assistant") == []
    assert [row["title"] for row in storage.get_pending("discord")] == ["Software Engineer 99"]


def test_discord_overflow_never_marks_unsent_jobs(storage):
    seed_pending(storage, 75)
    discord = RecordingDiscord()
    main._send_pending_notifications(storage, discord, dry_run=False)
    assert sum(len(batch) for batch in discord.batches) == 50
    stats = storage.get_stats()
    assert stats["notified_jobs"] == 50
    assert stats["pending_notification"] == 25
    assert stats["suppressed_jobs"] == 0


# ---------------------------------------------------------------------------
# End-to-end main()
# ---------------------------------------------------------------------------

class Feeds:
    """Mutable job feeds returned by the fake sources."""

    def __init__(self):
        self.lists = {SIMPLIFY: [], SPEEDY: []}
        self.failing_lists = set()
        self.careers = {"Acme": []}
        self.careers_healthy = True
        self.career_calls = 0


def install_fakes(monkeypatch, feeds, discord, assistant):
    class FakeTracker:
        def __init__(self):
            self.last_repo_results = {}
            self.screen_counts = Counter({"no_sponsorship": 1})

        def fetch_jobs_with_status(self):
            jobs = []
            for repo, repo_jobs in feeds.lists.items():
                if repo in feeds.failing_lists:
                    self.last_repo_results[repo] = ScrapeResult(status="request_failure", error="down")
                    continue
                self.last_repo_results[repo] = ScrapeResult(
                    jobs=list(repo_jobs), candidate_count=len(repo_jobs) + 1, status="success",
                )
                jobs.extend(repo_jobs)
            return jobs, not feeds.failing_lists, ""

    class FakeScraper:
        def __init__(self):
            self.last_company_results = {}
            self.screen_counts = Counter()
            self.last_attempted_companies = len(feeds.careers)
            self.last_successful_companies = len(feeds.careers)

        def fetch_jobs_with_status(self):
            feeds.career_calls += 1
            jobs = []
            for company, company_jobs in feeds.careers.items():
                self.last_company_results[company] = ScrapeResult(
                    jobs=list(company_jobs), candidate_count=5, status="success",
                )
                jobs.extend(company_jobs)
            return jobs, feeds.careers_healthy, "" if feeds.careers_healthy else "too many failures"

    monkeypatch.setattr(main, "GitHubTracker", FakeTracker)
    monkeypatch.setattr(main, "CareerScraper", FakeScraper)
    monkeypatch.setattr(main, "DiscordNotifier", lambda: discord)
    monkeypatch.setattr(main, "AssistantNotifier", lambda: assistant)
    monkeypatch.setitem(main.SCREENING, "fetch_descriptions", False)


def run_main(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["main.py", *args])
    try:
        main.main()
    except SystemExit as exc:
        return exc.code
    return 0


def sent_titles(server):
    return [
        job["title"]
        for request in server.requests if request["status"] == 200
        for job in request["body"]["jobs"]
    ]


def test_end_to_end_runs_with_state_file(monkeypatch, tmp_path):
    feeds = Feeds()
    discord = RecordingDiscord()
    state = str(tmp_path / "state" / "state.json")
    with WebhookServer() as server:
        assistant = AssistantNotifier(server.url, "key", sleep=lambda _s: None, max_attempts=2)
        install_fakes(monkeypatch, feeds, discord, assistant)

        def run(*extra):
            # Each CI run starts from a fresh working database.
            db = str(tmp_path / f"run{run.count}.db")
            run.count += 1
            return run_main(monkeypatch, "--notify", "--db", db, "--state-file", state, *extra)
        run.count = 0

        # Run 1: first install. Existing listings are recorded, not sent.
        feeds.lists[SIMPLIFY] = [make_job(n) for n in range(3)]
        feeds.careers["Acme"] = [make_job(10, source="career_page")]
        assert run("--mode", "auto") == 0
        assert discord.batches == []
        assert server.requests == []
        saved = json.loads(open(state, encoding="utf-8").read())
        assert len(saved["jobs"]) == 4
        assert {job["suppressed_reason"] for job in saved["jobs"]} == {"baseline"}
        assert "fresh_install" not in saved["meta"]
        assert "last_full_scan_at" in saved["meta"]
        assert feeds.career_calls == 1

        # Run 2: auto mode skips career pages (scanned minutes ago); new list job is sent.
        feeds.lists[SIMPLIFY].append(make_job(3))
        feeds.careers["Acme"].append(make_job(11, source="career_page"))
        assert run("--mode", "auto") == 0
        assert feeds.career_calls == 1
        assert discord.batches == [["Software Engineer 3"]]
        assert sent_titles(server) == ["Software Engineer 3"]
        headers = {k.lower(): v for k, v in server.requests[0]["headers"].items()}
        assert headers["authorization"] == "Bearer key"

        # Run 3: assistant is down. Discord still delivers; the run fails so it is visible.
        feeds.lists[SIMPLIFY].append(make_job(4))
        server.responses = [(503, {}, "")] * 2
        assert run("--mode", "fast") == 1
        assert discord.batches[-1] == ["Software Engineer 4"]
        assert sent_titles(server) == ["Software Engineer 3"]
        saved = {job["title"]: job for job in json.loads(open(state, encoding="utf-8").read())["jobs"]}
        assert saved["Software Engineer 4"]["notified"] == DELIVERED
        assert saved["Software Engineer 4"]["assistant_notified"] == PENDING

        # Run 4: assistant recovers and receives only the job it missed.
        assert run("--mode", "full") == 0
        assert feeds.career_calls == 2
        assert sent_titles(server)[-2:] == ["Software Engineer 4", "Software Engineer 11"]
        assert discord.batches[-1] == ["Software Engineer 11"]

        # Run 5: nothing new; nothing is sent again.
        requests_before = len(server.requests)
        batches_before = len(discord.batches)
        assert run("--mode", "full") == 0
        assert len(server.requests) == requests_before
        assert len(discord.batches) == batches_before

        # Run 6: a quiet fast run leaves the state file byte-identical, so the
        # state branch gets no commit.
        before = open(state, encoding="utf-8").read()
        assert run("--mode", "fast") == 0
        assert open(state, encoding="utf-8").read() == before


def test_state_file_is_checkpointed_after_each_delivered_batch(monkeypatch, tmp_path):
    feeds = Feeds()
    state = tmp_path / "state.json"
    snapshots = []

    class SnapshotDiscord(RecordingDiscord):
        def send_job_batch(self, jobs, **kwargs):
            if self.batches:
                saved = json.loads(state.read_text(encoding="utf-8"))
                snapshots.append(sum(job["notified"] == DELIVERED for job in saved["jobs"]))
            return super().send_job_batch(jobs, **kwargs)

    install_fakes(monkeypatch, feeds, SnapshotDiscord(), RecordingAssistant(configured=False))
    db = str(tmp_path / "a.db")
    storage = JobStorage(db)
    storage.set_meta("fresh_install", None)
    storage.mark_baselined({SIMPLIFY, "careers:Acme"})
    feeds.lists[SIMPLIFY] = [make_job(n) for n in range(25)]
    assert run_main(monkeypatch, "--notify", "--db", db, "--state-file", str(state)) == 0
    # Before batches 2 and 3 are sent, the file already records batches 1 and 2.
    assert snapshots == [10, 20]


def test_new_list_is_baselined_and_failed_list_is_not(monkeypatch, tmp_path):
    feeds = Feeds()
    discord = RecordingDiscord()
    assistant = RecordingAssistant()
    install_fakes(monkeypatch, feeds, discord, assistant)
    state = str(tmp_path / "state.json")

    feeds.lists[SIMPLIFY] = [make_job(1)]
    feeds.failing_lists = {SPEEDY}
    assert run_main(monkeypatch, "--notify", "--db", str(tmp_path / "a.db"), "--state-file", state) == 0
    storage = JobStorage(str(tmp_path / "check.db"))
    main.load_state_file(state, storage)
    assert storage.baselined_units() == {SIMPLIFY, "careers:Acme"}
    health = {row["source"]: row["consecutive_failures"] for row in storage.export_state()["source_health"]}
    assert health == {f"github:{SIMPLIFY}": 0, f"github:{SPEEDY}": 1, "careers": 0}

    # The list comes back with a big backlog: recorded silently.
    feeds.failing_lists = set()
    feeds.lists[SPEEDY] = [make_job(n, source=SPEEDY, company="Other") for n in range(100, 140)]
    feeds.lists[SIMPLIFY].append(make_job(2))
    assert run_main(monkeypatch, "--notify", "--db", str(tmp_path / "b.db"), "--state-file", state) == 0
    assert discord.batches == [["Software Engineer 2"]]
    assert [len(p["jobs"]) for p in assistant.payloads] == [1]


def test_first_run_after_migration_does_not_flood(monkeypatch, tmp_path):
    legacy_path = tmp_path / "jobs.db"
    conn = sqlite3.connect(legacy_path)
    conn.execute("""
        CREATE TABLE seen_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, unique_id TEXT UNIQUE NOT NULL,
            company TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL, location TEXT,
            source TEXT, date_posted TEXT, first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified INTEGER DEFAULT 0
        )
    """)
    old = [make_job(n) for n in range(3)] + [make_job(10, source="career_page")]
    conn.executemany(
        "INSERT INTO seen_jobs (unique_id, company, title, url, location, source, notified)"
        " VALUES (?, ?, ?, ?, ?, ?, 1)",
        [(j.unique_id, j.company, j.title, j.url, j.location, j.source) for j in old],
    )
    conn.commit()
    conn.close()

    feeds = Feeds()
    discord = RecordingDiscord()
    assistant = RecordingAssistant()
    install_fakes(monkeypatch, feeds, discord, assistant)
    feeds.lists[SIMPLIFY] = [make_job(n) for n in range(3)] + [make_job(3)]
    feeds.lists[SPEEDY] = [make_job(n, source=SPEEDY, company="Other") for n in range(200, 230)]
    feeds.careers["Acme"] = [make_job(10, source="career_page")]
    feeds.careers["Remitly"] = [make_job(501, source="career_page", company="Remitly")]

    state = str(tmp_path / "state.json")
    assert run_main(
        monkeypatch, "--notify", "--db", str(legacy_path), "--state-file", state, "--mode", "auto",
    ) == 0
    # Only the genuinely new job on a known list and the small new company are sent.
    assert discord.batches == [["Software Engineer 3", "Software Engineer 501"]]
    assert [job["title"] for p in assistant.payloads for job in p["jobs"]] == [
        "Software Engineer 3", "Software Engineer 501",
    ]
    saved = json.loads(open(state, encoding="utf-8").read())
    assert "migrated_legacy_db" in saved["meta"]
    reasons = Counter(job["suppressed_reason"] for job in saved["jobs"])
    assert reasons["baseline"] == 30
    assert reasons["before_assistant_channel"] == 4


def test_state_is_saved_even_when_the_run_crashes(monkeypatch, tmp_path):
    feeds = Feeds()
    install_fakes(monkeypatch, feeds, RecordingDiscord(), RecordingAssistant())

    def boom(*_args, **_kwargs):
        raise RuntimeError("crash in Discord delivery")

    monkeypatch.setattr(main, "_send_pending_notifications", boom)
    feeds.lists[SIMPLIFY] = [make_job(1)]
    state = tmp_path / "state.json"
    with pytest.raises(RuntimeError):
        run_main(monkeypatch, "--notify", "--db", str(tmp_path / "a.db"), "--state-file", str(state))
    assert state.exists()
    assert len(json.loads(state.read_text(encoding="utf-8"))["jobs"]) == 1


def test_assistant_crash_does_not_stop_discord(monkeypatch, tmp_path, capsys):
    feeds = Feeds()
    discord = RecordingDiscord()
    install_fakes(monkeypatch, feeds, discord, RecordingAssistant())
    db = str(tmp_path / "a.db")
    storage = JobStorage(db)
    storage.set_meta("fresh_install", None)
    storage.mark_baselined({SIMPLIFY, "careers:Acme"})

    secret_url = "https://hooks.example/" + "s3cr3t"

    def boom(*_args, **_kwargs):
        raise ValueError(f"bad payload for {secret_url}")

    monkeypatch.setattr(main, "_send_assistant_notifications", boom)
    feeds.lists[SIMPLIFY] = [make_job(1)]
    assert run_main(monkeypatch, "--notify", "--db", db) == 1
    assert discord.batches == [["Software Engineer 1"]]
    out = capsys.readouterr().out
    assert "Assistant delivery crashed (ValueError)" in out
    assert "s3cr3t" not in out
    assert len(storage.get_pending("assistant")) == 1


def test_dry_run_sends_and_marks_nothing(monkeypatch, tmp_path, capsys):
    feeds = Feeds()
    discord = RecordingDiscord()
    assistant = RecordingAssistant(configured=False)
    install_fakes(monkeypatch, feeds, discord, assistant)
    db = str(tmp_path / "a.db")
    storage = JobStorage(db)
    storage.set_meta("fresh_install", None)
    storage.mark_baselined({SIMPLIFY, "careers:Acme"})
    feeds.lists[SIMPLIFY] = [make_job(1)]

    assert run_main(monkeypatch, "--notify", "--dry-run", "--db", db) == 0
    out = capsys.readouterr().out
    assert "Queued for delivery: 1" in out
    assert "Dropped by sponsorship/seniority screening at source: no_sponsorship=1" in out
    assert len(discord.batches) == 1
    assert len(assistant.payloads) == 1
    assert len(storage.get_pending("discord")) == 1
    assert len(storage.get_pending("assistant")) == 1


def test_unhealthy_career_scan_is_retried_on_the_next_auto_run(monkeypatch, tmp_path):
    feeds = Feeds()
    install_fakes(monkeypatch, feeds, RecordingDiscord(), RecordingAssistant())
    state = str(tmp_path / "state.json")

    def run(name):
        return run_main(monkeypatch, "--db", str(tmp_path / f"{name}.db"), "--state-file", state, "--mode", "auto")

    feeds.careers_healthy = False
    assert run("a") == 0
    assert "last_full_scan_at" not in json.loads(open(state, encoding="utf-8").read())["meta"]
    assert run("b") == 0
    assert feeds.career_calls == 2

    feeds.careers_healthy = True
    assert run("c") == 0
    assert run("d") == 0
    assert feeds.career_calls == 3
