"""Tests for delivery state, legacy migration, and the durable state file."""

from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from models import Job
from state_store import format_state, load_state_file, merge_states, save_state_file
from storage import DELIVERED, PENDING, SUPPRESSED, JobStorage

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def make_job(n=1, company="Acme", source="SimplifyJobs/New-Grad-Positions", **kwargs):
    return Job(
        company=company,
        title=kwargs.pop("title", f"Software Engineer {n}"),
        url=kwargs.pop("url", f"https://boards.greenhouse.io/acme/jobs/{1000 + n}"),
        location="Seattle, WA",
        source=source,
        **kwargs,
    )


@pytest.fixture
def storage(tmp_path):
    return JobStorage(str(tmp_path / "jobs.db"))


def legacy_db(path, rows):
    """Create a database with the schema used before this change."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE seen_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_id TEXT UNIQUE NOT NULL,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            location TEXT,
            source TEXT,
            date_posted TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified INTEGER DEFAULT 0
        );
        CREATE INDEX idx_unique_id ON seen_jobs(unique_id);
        CREATE INDEX idx_notified ON seen_jobs(notified);
        CREATE TABLE source_health (
            source TEXT PRIMARY KEY,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            last_failure_at TIMESTAMP,
            last_success_at TIMESTAMP,
            last_alert_failure_count INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.executemany(
        "INSERT INTO seen_jobs (unique_id, company, title, url, location, source, first_seen, notified)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.execute(
        "INSERT INTO source_health (source, consecutive_failures, last_error) VALUES ('careers', 2, 'boom')"
    )
    conn.commit()
    conn.close()


class TestFreshInstallAndMigration:
    def test_empty_database_is_marked_fresh(self, storage):
        assert storage.get_meta("fresh_install") == "1"
        assert storage.baselined_units() == set()

    def test_legacy_database_is_migrated_in_place(self, tmp_path):
        path = str(tmp_path / "legacy.db")
        legacy_db(path, [
            ("Acme|SWE|https://boards.greenhouse.io/acme/jobs/1", "Acme", "SWE",
             "https://boards.greenhouse.io/acme/jobs/1?utm_source=Simplify", "Seattle, WA",
             "SimplifyJobs/New-Grad-Positions", "2026-10-01 10:00:00", 1),
            ("Beta|SWE|https://beta.example/careers", "Beta", "SWE",
             "https://beta.example/careers", "Seattle, WA", "career_page", "2026-10-02 10:00:00", 0),
        ])

        storage = JobStorage(path)

        rows = {row["company"]: row for row in storage.get_recent(10)}
        assert rows["Acme"]["notified"] == DELIVERED
        assert rows["Acme"]["assistant_notified"] == SUPPRESSED
        assert rows["Acme"]["suppressed_reason"] == "before_assistant_channel"
        assert rows["Acme"]["dedupe_key"] == "greenhouse:1"
        assert rows["Acme"]["last_seen"] == "2026-10-01"
        # Jobs Discord was still waiting on are also queued for the assistant.
        assert rows["Beta"]["notified"] == PENDING
        assert rows["Beta"]["assistant_notified"] == PENDING
        assert rows["Beta"]["dedupe_key"] == "https://beta.example/careers#swe"

        assert storage.get_meta("fresh_install") is None
        assert storage.get_meta("migrated_legacy_db")
        assert storage.baselined_units() == {
            "SimplifyJobs/New-Grad-Positions",
            "careers:Beta",
        }
        health = storage.export_state()["source_health"]
        assert health[0]["source"] == "careers"
        assert health[0]["consecutive_failures"] == 2
        assert health[0]["pending_recovery_after"] == 0

    def test_migration_runs_once(self, tmp_path):
        path = str(tmp_path / "legacy.db")
        legacy_db(path, [
            ("Acme|SWE|u", "Acme", "SWE", "https://acme.example/1", "Seattle, WA",
             "SimplifyJobs/New-Grad-Positions", "2026-10-01 10:00:00", 1),
        ])
        JobStorage(path).set_meta("migrated_legacy_db", "kept")
        storage = JobStorage(path)
        assert storage.get_meta("migrated_legacy_db") == "kept"
        assert storage.get_recent(1)[0]["assistant_notified"] == SUPPRESSED


class TestChannels:
    def test_new_jobs_are_pending_on_both_channels(self, storage):
        storage.add_jobs([make_job(1)])
        assert len(storage.get_pending("discord")) == 1
        assert len(storage.get_pending("assistant")) == 1

    def test_delivery_is_tracked_per_channel(self, storage):
        jobs = [make_job(n) for n in range(3)]
        storage.add_jobs(jobs)
        storage.mark_delivered("assistant", jobs[:2])
        storage.mark_notified(jobs[1:])

        discord = [row["title"] for row in storage.get_pending("discord")]
        assistant = [row["title"] for row in storage.get_pending("assistant")]
        assert discord == ["Software Engineer 0"]
        assert assistant == ["Software Engineer 2"]
        stats = storage.get_stats()
        assert stats["notified_jobs"] == 2
        assert stats["pending_notification"] == 1
        assert stats["assistant_delivered"] == 2
        assert stats["assistant_pending"] == 1

    def test_suppressed_jobs_are_never_pending(self, storage):
        storage.add_jobs(
            [make_job(1)],
            discord_state=SUPPRESSED,
            assistant_state=SUPPRESSED,
            suppressed_reason="baseline",
        )
        assert storage.get_pending("discord") == []
        assert storage.get_pending("assistant") == []
        assert storage.get_recent(1)[0]["suppressed_reason"] == "baseline"
        assert storage.get_stats()["suppressed_jobs"] == 1

    def test_pending_is_oldest_first(self, storage):
        storage.add_jobs([make_job(2)])
        storage.add_jobs([make_job(1)])
        with sqlite3.connect(storage.db_path) as conn:
            conn.execute("UPDATE seen_jobs SET first_seen = '2026-01-01 00:00:00' WHERE title LIKE '%2'")
        assert [row["title"] for row in storage.get_pending("assistant")] == [
            "Software Engineer 2",
            "Software Engineer 1",
        ]

    def test_unknown_channel_is_rejected(self, storage):
        with pytest.raises(ValueError):
            storage.get_pending("email")

    def test_retire_stale_pending_only_touches_one_channel(self, storage):
        storage.add_jobs([make_job(1), make_job(2)])
        with sqlite3.connect(storage.db_path) as conn:
            conn.execute("UPDATE seen_jobs SET first_seen = '2026-10-01 00:00:00' WHERE title LIKE '%1'")
            conn.execute("UPDATE seen_jobs SET first_seen = '2026-10-14 11:00:00' WHERE title LIKE '%2'")

        assert storage.retire_stale_pending("assistant", 168, now=NOW) == 1
        assert storage.retire_stale_pending("assistant", None, now=NOW) == 0
        assert [row["title"] for row in storage.get_pending("assistant")] == ["Software Engineer 2"]
        assert len(storage.get_pending("discord")) == 2
        retired = [row for row in storage.get_recent(5) if row["assistant_notified"] == SUPPRESSED]
        assert retired[0]["suppressed_reason"] == "assistant_backlog_expired"


class TestDedupe:
    def test_same_posting_from_another_list_is_known(self, storage):
        storage.add_jobs([make_job(
            1, url="https://boards.greenhouse.io/acme/jobs/1001?utm_source=Simplify",
        )])
        other_list = make_job(
            1,
            title="SWE New Grad",
            url="https://job-boards.greenhouse.io/acme/jobs/1001",
            source="speedyapply/2027-SWE-College-Jobs",
        )
        career_page = make_job(
            1, url="https://acme.example/careers?gh_jid=1001", source="career_page",
        )
        new, known = storage.partition_new([other_list, career_page, make_job(2)])
        assert [job.title for job in new] == ["Software Engineer 2"]
        assert known == [other_list, career_page]

    def test_partition_dedupes_within_one_scan(self, storage):
        first = make_job(1)
        duplicate = make_job(1, title="Different title", source="speedyapply/2027-SWE-College-Jobs")
        new, known = storage.partition_new([first, duplicate])
        assert new == [first]
        assert known == [duplicate]

    def test_known_jobs_refresh_last_seen_without_changing_state(self, storage):
        job = make_job(1)
        storage.add_jobs([job], now=NOW - timedelta(days=10))
        storage.mark_notified([job])
        again = make_job(1, title="Renamed", source="career_page")
        assert storage.add_jobs([again], now=NOW) == []
        row = storage.get_recent(1)[0]
        assert row["last_seen"] == "2026-10-14"
        assert row["notified"] == DELIVERED
        assert row["title"] == "Software Engineer 1"


class TestPrune:
    def test_prunes_old_delivered_jobs_but_never_pending_ones(self, storage):
        old_delivered, old_pending, recent = make_job(1), make_job(2), make_job(3)
        storage.add_jobs([old_delivered, old_pending], now=NOW - timedelta(days=200))
        storage.add_jobs([recent], now=NOW)
        storage.mark_notified([old_delivered, recent])
        storage.mark_delivered("assistant", [old_delivered, old_pending, recent])

        assert storage.prune(180, now=NOW) == 1
        titles = {row["title"] for row in storage.get_recent(10)}
        assert titles == {"Software Engineer 2", "Software Engineer 3"}

    def test_jobs_still_listed_are_kept(self, storage):
        job = make_job(1)
        storage.add_jobs([job], notified=True, now=NOW - timedelta(days=400))
        storage.add_jobs([job], now=NOW)
        assert storage.prune(180, now=NOW) == 0


class TestStateFile:
    def populate(self, storage):
        jobs = [
            make_job(1, sponsorship="yes", screening_notes=["sponsorship offered: 'we sponsor visas'"]),
            make_job(2, seniority_flag="borderline", min_years_experience=2),
            make_job(3, company="Beta", source="career_page", url="https://beta.example/careers"),
        ]
        storage.add_jobs(jobs)
        storage.mark_notified(jobs[:1])
        storage.mark_delivered("assistant", jobs[:2])
        storage.add_jobs(
            [make_job(4)], discord_state=SUPPRESSED, assistant_state=SUPPRESSED,
            suppressed_reason="screened_out:no_sponsorship",
        )
        storage.mark_baselined({"SimplifyJobs/New-Grad-Positions", "careers:Beta"})
        storage.set_meta("last_full_scan_at", "2026-10-14T10:00:00Z")
        storage.set_meta("fresh_install", None)
        storage.record_source_failure("github", "HTTP 500", alert_thresholds=[3])
        storage.record_company_failure("Beta", "404", alert_thresholds=[3])
        return jobs

    def test_round_trip_preserves_everything(self, storage, tmp_path):
        self.populate(storage)
        path = tmp_path / "state" / "state.json"
        save_state_file(str(path), storage)

        restored = JobStorage(str(tmp_path / "fresh.db"))
        assert restored.get_meta("fresh_install") == "1"
        assert load_state_file(str(path), restored) is True

        assert restored.export_state() == storage.export_state()
        assert restored.get_meta("fresh_install") is None
        assert restored.get_meta("last_full_scan_at") == "2026-10-14T10:00:00Z"
        assert [row["title"] for row in restored.get_pending("discord")] == [
            "Software Engineer 2", "Software Engineer 3",
        ]
        assert [row["title"] for row in restored.get_pending("assistant")] == ["Software Engineer 3"]
        rows = {row["title"]: row for row in restored.get_recent(10)}
        assert json.loads(rows["Software Engineer 1"]["screening_notes"]) == [
            "sponsorship offered: 'we sponsor visas'"
        ]
        assert rows["Software Engineer 2"]["min_years_experience"] == 2
        assert rows["Software Engineer 4"]["suppressed_reason"] == "screened_out:no_sponsorship"
        assert restored.baselined_units() == {"SimplifyJobs/New-Grad-Positions", "careers:Beta"}
        assert restored.export_state()["source_health"][0]["consecutive_failures"] == 1
        new, _known = restored.partition_new([make_job(1, title="Renamed")])
        assert new == []

    def test_import_replaces_stale_local_database(self, storage, tmp_path):
        self.populate(storage)
        path = tmp_path / "state.json"
        save_state_file(str(path), storage)
        stale = JobStorage(str(tmp_path / "stale.db"))
        stale.add_jobs([make_job(99)])
        load_state_file(str(path), stale)
        assert "Software Engineer 99" not in {row["title"] for row in stale.get_recent(10)}

    def test_missing_state_file_returns_false(self, storage, tmp_path):
        assert load_state_file(str(tmp_path / "missing.json"), storage) is False

    def test_rejects_unknown_format_and_version(self, storage):
        with pytest.raises(ValueError):
            storage.import_state({"format": "other", "version": 1})
        with pytest.raises(ValueError):
            storage.import_state({"format": "job-tracker-state", "version": 99})

    def test_invalid_import_leaves_existing_data(self, storage):
        storage.add_jobs([make_job(1)])
        with pytest.raises(sqlite3.IntegrityError):
            storage.import_state({
                "format": "job-tracker-state",
                "version": 1,
                "jobs": [
                    {"unique_id": "a", "company": "A", "title": "T", "url": "https://a"},
                    {"unique_id": "a", "company": "A", "title": "T", "url": "https://a"},
                ],
            })
        assert [row["title"] for row in storage.get_recent(5)] == ["Software Engineer 1"]

    def test_file_is_stable_and_one_job_per_line(self, storage, tmp_path):
        self.populate(storage)
        first = tmp_path / "a.json"
        second = tmp_path / "b.json"
        save_state_file(str(first), storage)
        save_state_file(str(second), storage)
        text = first.read_text(encoding="utf-8")
        assert text == second.read_text(encoding="utf-8")
        job_lines = [line for line in text.splitlines() if '"unique_id"' in line]
        assert len(job_lines) == 4
        assert all(json.loads(line.strip().rstrip(",")) for line in job_lines)
        assert json.loads(text)["format"] == "job-tracker-state"

    def test_empty_state_formats_as_valid_json(self, storage):
        text = format_state(storage.export_state())
        assert json.loads(text)["jobs"] == []

    def test_atomic_write_leaves_no_temp_files(self, storage, tmp_path):
        path = tmp_path / "state.json"
        save_state_file(str(path), storage)
        save_state_file(str(path), storage)
        assert sorted(p.name for p in tmp_path.iterdir()) == ["jobs.db", "state.json"]


# ---------------------------------------------------------------------------
# Merging two runs' states
# ---------------------------------------------------------------------------

def _state(tmp_path, name, setup):
    storage = JobStorage(str(tmp_path / f"{name}.db"))
    setup(storage)
    return storage.export_state()


def test_merge_never_makes_a_handled_job_pending_again(tmp_path):
    jobs = [make_job(n) for n in range(4)]

    def base(storage):
        storage.add_jobs(jobs)

    def ours(storage):
        base(storage)
        storage.mark_delivered("assistant", [jobs[0]])
        storage.retire_stale_pending("discord", 0, now=NOW + timedelta(days=1))
        storage.add_jobs([make_job(9)])

    def theirs(storage):
        base(storage)
        storage.mark_delivered("discord", [jobs[0], jobs[1]])
        storage.add_jobs([make_job(8)], discord_state=SUPPRESSED, assistant_state=SUPPRESSED,
                         suppressed_reason="baseline")
        storage.mark_baselined({"careers:Acme"})
        storage.set_meta("fresh_install", None)

    merged = merge_states(_state(tmp_path, "ours", ours), _state(tmp_path, "theirs", theirs))
    rows = {job["title"]: job for job in merged["jobs"]}
    assert set(rows) == {f"Software Engineer {n}" for n in (0, 1, 2, 3, 8, 9)}
    # Delivered beats suppressed beats pending, per channel.
    assert (rows["Software Engineer 0"]["notified"], rows["Software Engineer 0"]["assistant_notified"]) == (
        DELIVERED, DELIVERED,
    )
    assert rows["Software Engineer 1"]["notified"] == DELIVERED
    assert rows["Software Engineer 2"]["notified"] == SUPPRESSED
    assert rows["Software Engineer 2"]["suppressed_reason"] == "discord_backlog_expired"
    assert rows["Software Engineer 8"]["suppressed_reason"] == "baseline"
    assert "careers:Acme" in merged["baselines"]
    assert "fresh_install" not in merged["meta"]
    json.loads(format_state(merged))


@pytest.mark.parametrize("pending_is_ours", [True, False])
def test_merge_keeps_old_screening_version_when_suppress_beats_requeued_pending(
    tmp_path, pending_is_ours,
):
    """A re-screened pending job must not keep its new version if suppress wins.

    Otherwise stale_screened_out sees the current version and never re-fetches.
    """
    job = make_job(1)

    def as_pending(storage):
        storage.add_jobs(
            [job], discord_state=PENDING, assistant_state=PENDING,
            screening_version="new-rules",
        )

    def as_suppressed(storage):
        storage.add_jobs(
            [job], discord_state=SUPPRESSED, assistant_state=SUPPRESSED,
            suppressed_reason="screened_out:no_sponsorship",
            screening_version="old-rules",
        )

    ours, theirs = (as_pending, as_suppressed) if pending_is_ours else (as_suppressed, as_pending)
    merged = merge_states(_state(tmp_path, "ours", ours), _state(tmp_path, "theirs", theirs))
    row = merged["jobs"][0]
    assert (row["notified"], row["assistant_notified"]) == (SUPPRESSED, SUPPRESSED)
    assert row["screening_version"] == "old-rules"
    assert row["suppressed_reason"] == "screened_out:no_sponsorship"


def test_merge_keeps_the_latest_full_scan_and_rejects_foreign_files(tmp_path):
    ours = _state(tmp_path, "a", lambda s: s.set_meta("last_full_scan_at", "2026-10-14T10:00:00Z"))
    theirs = _state(tmp_path, "b", lambda s: s.set_meta("last_full_scan_at", "2026-10-14T11:00:00Z"))
    assert merge_states(ours, theirs)["meta"]["last_full_scan_at"] == "2026-10-14T11:00:00Z"
    with pytest.raises(ValueError):
        merge_states(ours, {"jobs": []})
    with pytest.raises(ValueError):
        merge_states(ours, {**theirs, "version": 99})


def test_health_success_is_day_granular_so_quiet_runs_do_not_change_state(storage):
    storage.record_source_success("github")
    before = format_state(storage.export_state())
    storage.record_source_success("github")
    assert format_state(storage.export_state()) == before
    assert len(storage.export_state()["source_health"][0]["last_success_at"]) == len("2026-10-14")
