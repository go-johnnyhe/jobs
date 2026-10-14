"""SQLite storage for tracking seen job listings."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Iterable, Optional, Sequence

from job_keys import dedupe_key
from models import Job

from config import DATABASE_PATH, PRIORITY_COMPANIES, SOURCE_FAILURE_ALERT_THRESHOLDS

# Per-channel delivery state. A job is DELIVERED only after the channel
# accepted it. SUPPRESSED jobs were intentionally never sent (baseline scans,
# screened out after a description fetch, or retired from a stale backlog);
# suppressed_reason records why.
PENDING = 0
DELIVERED = 1
SUPPRESSED = 2

CHANNEL_COLUMNS = {
    "discord": "notified",
    "assistant": "assistant_notified",
}

STATE_FORMAT = "job-tracker-state"
STATE_VERSION = 1

_JOB_COLUMNS = {
    "unique_id": "TEXT UNIQUE NOT NULL",
    "company": "TEXT NOT NULL",
    "title": "TEXT NOT NULL",
    "url": "TEXT NOT NULL",
    "location": "TEXT",
    "source": "TEXT",
    "date_posted": "TEXT",
    "first_seen": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "notified": "INTEGER DEFAULT 0",
    "assistant_notified": "INTEGER NOT NULL DEFAULT 0",
    "dedupe_key": "TEXT",
    "last_seen": "TEXT",
    "sponsorship": "TEXT NOT NULL DEFAULT 'unknown'",
    "seniority_flag": "TEXT NOT NULL DEFAULT 'none'",
    "min_years_experience": "INTEGER",
    "screening_notes": "TEXT NOT NULL DEFAULT '[]'",
    "suppressed_reason": "TEXT",
}
_HEALTH_COLUMNS = [
    "consecutive_failures",
    "last_error",
    "last_failure_at",
    "last_success_at",
    "last_alert_failure_count",
    "pending_recovery_after",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sqlite_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def unit_key_for_row(source: Optional[str], company: str) -> str:
    """Scan-unit key for a stored row; mirrors Job.unit_key."""
    if source == "career_page":
        return f"careers:{company}"
    return source or ""


class JobStorage:
    """SQLite-based storage for tracking job listings."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DATABASE_PATH
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initialize the database schema and migrate older databases."""
        with closing(self._connect()) as conn, conn:
            existing_tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            column_sql = ",\n".join(
                f"{name} {definition}" for name, definition in _JOB_COLUMNS.items()
            )
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {column_sql}
                )
            """)
            self._migrate_seen_jobs(conn)
            # UNIQUE already indexes unique_id; the composite notification
            # index also supports queries on notified alone. Migrate old DBs.
            conn.execute("DROP INDEX IF EXISTS idx_unique_id")
            conn.execute("DROP INDEX IF EXISTS idx_notified")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_company ON seen_jobs(company)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_first_seen ON seen_jobs(first_seen)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notified_first_seen ON seen_jobs(notified, first_seen)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_assistant_first_seen
                ON seen_jobs(assistant_notified, first_seen)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dedupe_key ON seen_jobs(dedupe_key)
            """)
            self._ensure_health_table(conn, "source_health", "source")
            self._ensure_health_table(conn, "company_health", "company")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS source_baselines (
                    unit TEXT PRIMARY KEY,
                    baselined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS state_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            if "state_meta" not in existing_tables:
                job_count = conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
                if job_count:
                    # Database from before baselines existed: every unit that
                    # already produced jobs has effectively been baselined.
                    units = {
                        unit_key_for_row(source, company)
                        for source, company in conn.execute(
                            "SELECT DISTINCT source, company FROM seen_jobs"
                        )
                    }
                    conn.executemany(
                        "INSERT OR IGNORE INTO source_baselines (unit) VALUES (?)",
                        ((unit,) for unit in units if unit),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO state_meta (key, value) VALUES ('migrated_legacy_db', ?)",
                        (_sqlite_timestamp(_utc_now()),),
                    )
                else:
                    conn.execute(
                        "INSERT OR REPLACE INTO state_meta (key, value) VALUES ('fresh_install', '1')"
                    )

    def _migrate_seen_jobs(self, conn: sqlite3.Connection):
        """Add columns introduced after the original schema."""
        columns = {row[1] for row in conn.execute("PRAGMA table_info(seen_jobs)")}
        added = []
        for name, definition in _JOB_COLUMNS.items():
            if name not in columns:
                definition = definition.replace(" UNIQUE", "")
                conn.execute(f"ALTER TABLE seen_jobs ADD COLUMN {name} {definition}")
                added.append(name)
        if "assistant_notified" in added:
            # Jobs already handled by Discord before the assistant channel
            # existed were never sent to it; do not replay that history.
            conn.execute("""
                UPDATE seen_jobs
                SET assistant_notified = CASE WHEN notified = 0 THEN 0 ELSE 2 END,
                    suppressed_reason = CASE
                        WHEN notified = 0 THEN suppressed_reason
                        ELSE 'before_assistant_channel'
                    END
            """)
        if "dedupe_key" in added:
            rows = conn.execute("SELECT id, url, title FROM seen_jobs").fetchall()
            conn.executemany(
                "UPDATE seen_jobs SET dedupe_key = ? WHERE id = ?",
                ((dedupe_key(url, title), row_id) for row_id, url, title in rows),
            )
        if "last_seen" in added:
            conn.execute("UPDATE seen_jobs SET last_seen = date(first_seen)")

    def _ensure_health_table(self, conn: sqlite3.Connection, table: str, key_column: str):
        """Create or migrate a health-tracking table."""
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                {key_column} TEXT PRIMARY KEY,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                last_failure_at TIMESTAMP,
                last_success_at TIMESTAMP,
                last_alert_failure_count INTEGER NOT NULL DEFAULT 0,
                pending_recovery_after INTEGER NOT NULL DEFAULT 0
            )
        """)
        columns = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table})")
        }
        if "pending_recovery_after" not in columns:
            conn.execute(f"""
                ALTER TABLE {table}
                ADD COLUMN pending_recovery_after INTEGER NOT NULL DEFAULT 0
            """)

    def _normalize_thresholds(self, thresholds: Optional[Sequence[int]]) -> list[int]:
        values = thresholds if thresholds is not None else SOURCE_FAILURE_ALERT_THRESHOLDS
        normalized = sorted({t for t in values if t > 0})
        if not normalized:
            raise ValueError("At least one positive alert threshold is required")
        return normalized

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def _is_known(self, conn: sqlite3.Connection, job: Job) -> bool:
        return conn.execute(
            "SELECT 1 FROM seen_jobs WHERE unique_id = ? OR dedupe_key = ? LIMIT 1",
            (job.unique_id, dedupe_key(job.url, job.title)),
        ).fetchone() is not None

    def partition_new(self, jobs: Iterable[Job]) -> tuple[list[Job], list[Job]]:
        """Split a scan into (new, already known) without writing.

        A job is known when its unique_id or its posting key (see
        job_keys.dedupe_key) is stored, so a posting first seen on one list is
        not reported again when another list links to it.
        """
        new_jobs, known_jobs = [], []
        batch_keys = set()
        with closing(self._connect()) as conn:
            for job in jobs:
                key = dedupe_key(job.url, job.title)
                if key in batch_keys or job.unique_id in batch_keys or self._is_known(conn, job):
                    known_jobs.append(job)
                else:
                    new_jobs.append(job)
                batch_keys.update((key, job.unique_id))
        return new_jobs, known_jobs

    def add_jobs(
        self,
        jobs: Iterable[Job],
        notified: bool = False,
        *,
        discord_state: Optional[int] = None,
        assistant_state: Optional[int] = None,
        suppressed_reason: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> list[Job]:
        """Insert a scan in one transaction and return only newly stored jobs.

        Already-known jobs only have last_seen refreshed. notified=True is a
        shorthand for both channels DELIVERED.
        """
        default_state = DELIVERED if notified else PENDING
        discord_value = default_state if discord_state is None else discord_state
        assistant_value = default_state if assistant_state is None else assistant_state
        seen_date = (now or _utc_now()).date().isoformat()
        new_jobs = []
        with closing(self._connect()) as conn, conn:
            for job in jobs:
                key = dedupe_key(job.url, job.title)
                if self._is_known(conn, job):
                    conn.execute(
                        "UPDATE seen_jobs SET last_seen = ? WHERE unique_id = ? OR dedupe_key = ?",
                        (seen_date, job.unique_id, key),
                    )
                    continue
                conn.execute("""
                    INSERT INTO seen_jobs
                    (unique_id, company, title, url, location, source, date_posted,
                     notified, assistant_notified, dedupe_key, last_seen,
                     sponsorship, seniority_flag, min_years_experience,
                     screening_notes, suppressed_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job.unique_id, job.company, job.title, job.url,
                    job.location, job.source, job.date_posted,
                    discord_value, assistant_value, key, seen_date,
                    job.sponsorship, job.seniority_flag, job.min_years_experience,
                    json.dumps(job.screening_notes, ensure_ascii=False),
                    suppressed_reason,
                ))
                new_jobs.append(job)
        return new_jobs

    def _channel_column(self, channel: str) -> str:
        try:
            return CHANNEL_COLUMNS[channel]
        except KeyError:
            raise ValueError(f"Unknown delivery channel: {channel}") from None

    def get_pending(self, channel: str) -> list[dict]:
        """Jobs not yet delivered to a channel, oldest first."""
        column = self._channel_column(channel)
        with closing(self._connect()) as conn, conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(f"""
                SELECT * FROM seen_jobs
                WHERE {column} = {PENDING}
                ORDER BY first_seen ASC, id ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def mark_delivered(self, channel: str, jobs: Iterable[Job | dict]):
        """Persist one batch the channel accepted, in one transaction."""
        column = self._channel_column(channel)
        with closing(self._connect()) as conn, conn:
            conn.executemany(
                f"UPDATE seen_jobs SET {column} = {DELIVERED} WHERE unique_id = ?",
                ((job.unique_id if isinstance(job, Job) else job["unique_id"],)
                 for job in jobs),
            )

    def get_unnotified(self) -> list[dict]:
        """Get all jobs that haven't been sent to Discord yet."""
        return self.get_pending("discord")

    def mark_notified(self, jobs: Iterable[Job | dict]):
        """Persist one successfully sent Discord batch in one transaction."""
        self.mark_delivered("discord", jobs)

    def retire_stale_pending(
        self,
        channel: str,
        max_age_hours: Optional[float],
        now: Optional[datetime] = None,
    ) -> int:
        """Suppress pending jobs first seen more than max_age_hours ago."""
        if max_age_hours is None:
            return 0
        column = self._channel_column(channel)
        cutoff = _sqlite_timestamp((now or _utc_now()) - timedelta(hours=max_age_hours))
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(f"""
                UPDATE seen_jobs
                SET {column} = {SUPPRESSED}, suppressed_reason = ?
                WHERE {column} = {PENDING} AND first_seen < ?
            """, (f"{channel}_backlog_expired", cutoff))
            return cursor.rowcount

    def prune(self, retention_days: int, now: Optional[datetime] = None) -> int:
        """Delete jobs not listed for retention_days that no channel is waiting on."""
        cutoff = ((now or _utc_now()) - timedelta(days=retention_days)).date().isoformat()
        pending_checks = " OR ".join(f"{column} = {PENDING}" for column in CHANNEL_COLUMNS.values())
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(f"""
                DELETE FROM seen_jobs
                WHERE COALESCE(last_seen, date(first_seen)) < ?
                  AND NOT ({pending_checks})
            """, (cutoff,))
            return cursor.rowcount

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Get the most recently seen jobs."""
        with closing(self._connect()) as conn, conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM seen_jobs
                ORDER BY first_seen DESC, id DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Baselines and metadata
    # ------------------------------------------------------------------

    def baselined_units(self) -> set[str]:
        with closing(self._connect()) as conn:
            return {row[0] for row in conn.execute("SELECT unit FROM source_baselines")}

    def mark_baselined(self, units: Iterable[str]):
        with closing(self._connect()) as conn, conn:
            conn.executemany(
                "INSERT OR IGNORE INTO source_baselines (unit) VALUES (?)",
                ((unit,) for unit in units if unit),
            )

    def get_meta(self, key: str) -> Optional[str]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT value FROM state_meta WHERE key = ?", (key,)).fetchone()
            return row[0] if row else None

    def set_meta(self, key: str, value: Optional[str]):
        with closing(self._connect()) as conn, conn:
            if value is None:
                conn.execute("DELETE FROM state_meta WHERE key = ?", (key,))
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO state_meta (key, value) VALUES (?, ?)",
                    (key, value),
                )

    # ------------------------------------------------------------------
    # Durable state export/import
    # ------------------------------------------------------------------

    def export_state(self) -> dict:
        """Return every table needed to resume tracking, as plain JSON data."""
        job_columns = list(_JOB_COLUMNS)
        with closing(self._connect()) as conn:
            jobs = [
                dict(zip(job_columns, row))
                for row in conn.execute(
                    f"SELECT {', '.join(job_columns)} FROM seen_jobs ORDER BY first_seen, id"
                )
            ]
            health = {}
            for table, key_column in (("source_health", "source"), ("company_health", "company")):
                columns = [key_column, *_HEALTH_COLUMNS]
                health[table] = [
                    dict(zip(columns, row))
                    for row in conn.execute(
                        f"SELECT {', '.join(columns)} FROM {table} ORDER BY {key_column}"
                    )
                ]
            baselines = dict(conn.execute(
                "SELECT unit, baselined_at FROM source_baselines ORDER BY unit"
            ).fetchall())
            meta = dict(conn.execute("SELECT key, value FROM state_meta ORDER BY key").fetchall())
        for job in jobs:
            job["screening_notes"] = json.loads(job["screening_notes"] or "[]")
        return {
            "format": STATE_FORMAT,
            "version": STATE_VERSION,
            "meta": meta,
            "baselines": baselines,
            "source_health": health["source_health"],
            "company_health": health["company_health"],
            "jobs": jobs,
        }

    def import_state(self, state: dict):
        """Replace all tracking data with an exported state, in one transaction."""
        if state.get("format") != STATE_FORMAT:
            raise ValueError("Not a job tracker state file")
        if state.get("version") != STATE_VERSION:
            raise ValueError(f"Unsupported state version: {state.get('version')}")
        job_columns = list(_JOB_COLUMNS)
        with closing(self._connect()) as conn, conn:
            for table in ("seen_jobs", "source_health", "company_health", "source_baselines", "state_meta"):
                conn.execute(f"DELETE FROM {table}")
            rows = []
            for job in state.get("jobs", []):
                record = dict(job)
                record["screening_notes"] = json.dumps(
                    record.get("screening_notes") or [], ensure_ascii=False,
                )
                record.setdefault("dedupe_key", dedupe_key(record["url"], record.get("title", "")))
                record.setdefault("notified", PENDING)
                record.setdefault("assistant_notified", PENDING)
                record.setdefault("sponsorship", "unknown")
                record.setdefault("seniority_flag", "none")
                rows.append(tuple(record.get(column) for column in job_columns))
            placeholders = ", ".join("?" for _ in job_columns)
            conn.executemany(
                f"INSERT INTO seen_jobs ({', '.join(job_columns)}) VALUES ({placeholders})",
                rows,
            )
            for table, key_column in (("source_health", "source"), ("company_health", "company")):
                columns = [key_column, *_HEALTH_COLUMNS]
                conn.executemany(
                    f"INSERT INTO {table} ({', '.join(columns)}) "
                    f"VALUES ({', '.join('?' for _ in columns)})",
                    (
                        tuple(record.get(column, 0 if column in {
                            "consecutive_failures",
                            "last_alert_failure_count",
                            "pending_recovery_after",
                        } else None) for column in columns)
                        for record in state.get(table, [])
                    ),
                )
            conn.executemany(
                "INSERT INTO source_baselines (unit, baselined_at) VALUES (?, ?)",
                state.get("baselines", {}).items(),
            )
            conn.executemany(
                "INSERT INTO state_meta (key, value) VALUES (?, ?)",
                state.get("meta", {}).items(),
            )

    def get_stats(self) -> dict:
        """Get statistics about stored jobs."""
        with closing(self._connect()) as conn, conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
            counts = {}
            for channel, column in CHANNEL_COLUMNS.items():
                for state_name, value in (
                    ("pending", PENDING),
                    ("delivered", DELIVERED),
                    ("suppressed", SUPPRESSED),
                ):
                    counts[f"{channel}_{state_name}"] = conn.execute(
                        f"SELECT COUNT(*) FROM seen_jobs WHERE {column} = ?", (value,),
                    ).fetchone()[0]
            oldest_unnotified = conn.execute(f"""
                SELECT
                    first_seen,
                    CAST((julianday('now') - julianday(first_seen)) * 24 AS INTEGER) AS age_hours
                FROM seen_jobs
                WHERE notified = {PENDING}
                ORDER BY first_seen ASC, id ASC
                LIMIT 1
            """).fetchone()

            by_company = {}
            cursor = conn.execute("""
                SELECT company, COUNT(*) as count
                FROM seen_jobs
                GROUP BY company
                ORDER BY count DESC
            """)
            for row in cursor:
                by_company[row[0]] = row[1]

            failing_priority_companies: list[dict] = []
            if PRIORITY_COMPANIES:
                placeholders = ", ".join("?" for _ in PRIORITY_COMPANIES)
                failing_rows = conn.execute(f"""
                    SELECT company, consecutive_failures, last_error, last_failure_at, last_success_at
                    FROM company_health
                    WHERE company IN ({placeholders})
                      AND consecutive_failures > 0
                    ORDER BY consecutive_failures DESC, company ASC
                """, PRIORITY_COMPANIES).fetchall()
                failing_priority_companies = [dict(row) for row in failing_rows]

            return {
                "total_jobs": total,
                "notified_jobs": counts["discord_delivered"],
                "pending_notification": counts["discord_pending"],
                "suppressed_jobs": counts["discord_suppressed"],
                "assistant_delivered": counts["assistant_delivered"],
                "assistant_pending": counts["assistant_pending"],
                "assistant_suppressed": counts["assistant_suppressed"],
                "oldest_unnotified_first_seen": (
                    oldest_unnotified["first_seen"] if oldest_unnotified else None
                ),
                "oldest_unnotified_age_hours": (
                    oldest_unnotified["age_hours"] if oldest_unnotified else None
                ),
                "failing_priority_companies": failing_priority_companies,
                "by_company": by_company,
            }

    def record_source_failure(
        self,
        source: str,
        error: str,
        alert_thresholds: Optional[Sequence[int]] = None,
    ) -> tuple[int, Optional[int]]:
        """
        Record a source failure and return (consecutive_failures, alert_threshold).

        alert_threshold is the threshold value that should be alerted now, or None.
        Alert state is not confirmed until confirm_source_failure_alert() is called.
        """
        return self._record_health_failure(
            table="source_health",
            key_column="source",
            key_value=source,
            error=error,
            alert_thresholds=alert_thresholds,
        )

    def confirm_source_failure_alert(self, source: str, alert_failure_count: int):
        """Persist that a failure alert was successfully sent up to this threshold."""
        self._confirm_health_failure_alert(
            table="source_health",
            key_column="source",
            key_value=source,
            alert_failure_count=alert_failure_count,
        )

    def record_source_success(
        self,
        source: str,
        alert_thresholds: Optional[Sequence[int]] = None,
    ) -> int:
        """
        Record source success and return failed-run count for recovery alert.

        Recovery alert state remains pending until confirm_source_recovery_alert()
        is called, so transient notifier failures do not lose alerts.
        """
        return self._record_health_success(
            table="source_health",
            key_column="source",
            key_value=source,
            alert_thresholds=alert_thresholds,
        )

    def confirm_source_recovery_alert(self, source: str):
        """Clear pending recovery alert state after successful notification."""
        self._confirm_health_recovery_alert(
            table="source_health",
            key_column="source",
            key_value=source,
        )

    def record_company_failure(
        self,
        company: str,
        error: str,
        alert_thresholds: Optional[Sequence[int]] = None,
    ) -> tuple[int, Optional[int]]:
        """Record a company scrape failure and return alerting state."""
        return self._record_health_failure(
            table="company_health",
            key_column="company",
            key_value=company,
            error=error,
            alert_thresholds=alert_thresholds,
        )

    def confirm_company_failure_alert(self, company: str, alert_failure_count: int):
        """Persist that a company failure alert was successfully sent."""
        self._confirm_health_failure_alert(
            table="company_health",
            key_column="company",
            key_value=company,
            alert_failure_count=alert_failure_count,
        )

    def record_company_success(
        self,
        company: str,
        alert_thresholds: Optional[Sequence[int]] = None,
    ) -> int:
        """Record a company scrape success and return recovery alert state."""
        return self._record_health_success(
            table="company_health",
            key_column="company",
            key_value=company,
            alert_thresholds=alert_thresholds,
        )

    def confirm_company_recovery_alert(self, company: str):
        """Clear pending company recovery alert state after notification."""
        self._confirm_health_recovery_alert(
            table="company_health",
            key_column="company",
            key_value=company,
        )

    def _record_health_failure(
        self,
        table: str,
        key_column: str,
        key_value: str,
        error: str,
        alert_thresholds: Optional[Sequence[int]] = None,
    ) -> tuple[int, Optional[int]]:
        """Record a health failure for a source or company."""
        thresholds = self._normalize_thresholds(alert_thresholds)

        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                f"""
                SELECT consecutive_failures, last_alert_failure_count
                FROM {table}
                WHERE {key_column} = ?
                """,
                (key_value,),
            ).fetchone()

            previous_failures = row[0] if row else 0
            stored_alert_failure_count = row[1] if row else 0
            last_alert_failure_count = 0 if previous_failures == 0 else stored_alert_failure_count
            consecutive_failures = previous_failures + 1

            eligible_thresholds = [
                threshold for threshold in thresholds
                if threshold <= consecutive_failures and threshold > last_alert_failure_count
            ]
            alert_threshold = max(eligible_thresholds) if eligible_thresholds else None

            conn.execute(
                f"""
                INSERT INTO {table}
                ({key_column}, consecutive_failures, last_error, last_failure_at, last_alert_failure_count, pending_recovery_after)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, 0)
                ON CONFLICT({key_column}) DO UPDATE SET
                    consecutive_failures = excluded.consecutive_failures,
                    last_error = excluded.last_error,
                    last_failure_at = excluded.last_failure_at,
                    last_alert_failure_count = excluded.last_alert_failure_count,
                    pending_recovery_after = 0
                """,
                (key_value, consecutive_failures, error, last_alert_failure_count),
            )

        return consecutive_failures, alert_threshold

    def _confirm_health_failure_alert(
        self,
        table: str,
        key_column: str,
        key_value: str,
        alert_failure_count: int,
    ):
        """Persist that a failure alert was sent for a health record."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                f"""
                UPDATE {table}
                SET last_alert_failure_count = CASE
                    WHEN last_alert_failure_count < ? THEN ?
                    ELSE last_alert_failure_count
                END
                WHERE {key_column} = ?
                """,
                (alert_failure_count, alert_failure_count, key_value),
            )

    def _record_health_success(
        self,
        table: str,
        key_column: str,
        key_value: str,
        alert_thresholds: Optional[Sequence[int]] = None,
    ) -> int:
        """Record a health success for a source or company."""
        thresholds = self._normalize_thresholds(alert_thresholds)
        min_threshold = min(thresholds)

        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                f"""
                SELECT consecutive_failures, last_alert_failure_count, pending_recovery_after
                FROM {table}
                WHERE {key_column} = ?
                """,
                (key_value,),
            ).fetchone()

            previous_failures = row[0] if row else 0
            last_alert_failure_count = row[1] if row else 0
            pending_recovery_after = row[2] if row else 0

            if pending_recovery_after > 0:
                recovery_after = pending_recovery_after
            elif previous_failures >= min_threshold and last_alert_failure_count > 0:
                recovery_after = previous_failures
            else:
                recovery_after = 0

            conn.execute(
                f"""
                INSERT INTO {table}
                ({key_column}, consecutive_failures, last_error, last_success_at, last_alert_failure_count, pending_recovery_after)
                VALUES (?, 0, NULL, CURRENT_TIMESTAMP, 0, ?)
                ON CONFLICT({key_column}) DO UPDATE SET
                    consecutive_failures = 0,
                    last_error = NULL,
                    last_success_at = excluded.last_success_at,
                    last_alert_failure_count = 0,
                    pending_recovery_after = excluded.pending_recovery_after
                """,
                (key_value, recovery_after),
            )

        return recovery_after

    def _confirm_health_recovery_alert(
        self,
        table: str,
        key_column: str,
        key_value: str,
    ):
        """Clear pending recovery alert state after successful notification."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                f"""
                UPDATE {table}
                SET pending_recovery_after = 0
                WHERE {key_column} = ?
                """,
                (key_value,),
            )
