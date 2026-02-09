"""SQLite storage for tracking seen job listings."""

import sqlite3
from typing import Optional, Sequence

from config import DATABASE_PATH, SOURCE_FAILURE_ALERT_THRESHOLDS


class JobStorage:
    """SQLite-based storage for tracking job listings."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DATABASE_PATH
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_jobs (
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
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_unique_id ON seen_jobs(unique_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notified ON seen_jobs(notified)
            """)
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
                CREATE TABLE IF NOT EXISTS source_health (
                    source TEXT PRIMARY KEY,
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
                for row in conn.execute("PRAGMA table_info(source_health)")
            }
            if "pending_recovery_after" not in columns:
                conn.execute("""
                    ALTER TABLE source_health
                    ADD COLUMN pending_recovery_after INTEGER NOT NULL DEFAULT 0
                """)
            conn.commit()

    def _normalize_thresholds(self, thresholds: Optional[Sequence[int]]) -> list[int]:
        values = thresholds if thresholds is not None else SOURCE_FAILURE_ALERT_THRESHOLDS
        normalized = sorted({t for t in values if t > 0})
        if not normalized:
            raise ValueError("At least one positive alert threshold is required")
        return normalized

    def is_new(self, job) -> bool:
        """Check if a job has been seen before."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM seen_jobs WHERE unique_id = ?",
                (job.unique_id,)
            )
            return cursor.fetchone() is None

    def mark_seen(self, job, notified: bool = False):
        """Mark a job as seen in the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR IGNORE INTO seen_jobs
                (unique_id, company, title, url, location, source, date_posted, notified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.unique_id,
                job.company,
                job.title,
                job.url,
                job.location,
                job.source,
                job.date_posted,
                1 if notified else 0,
            ))
            conn.commit()

    def mark_notified(self, job):
        """Mark a job as having been notified."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE seen_jobs SET notified = 1 WHERE unique_id = ?",
                (job.unique_id,)
            )
            conn.commit()

    def get_unnotified(self) -> list[dict]:
        """Get all jobs that haven't been notified yet."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM seen_jobs
                WHERE notified = 0
                ORDER BY first_seen DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Get the most recently seen jobs."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM seen_jobs
                ORDER BY first_seen DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict:
        """Get statistics about stored jobs."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
            notified = conn.execute(
                "SELECT COUNT(*) FROM seen_jobs WHERE notified = 1"
            ).fetchone()[0]

            by_company = {}
            cursor = conn.execute("""
                SELECT company, COUNT(*) as count
                FROM seen_jobs
                GROUP BY company
                ORDER BY count DESC
            """)
            for row in cursor:
                by_company[row[0]] = row[1]

            return {
                "total_jobs": total,
                "notified_jobs": notified,
                "pending_notification": total - notified,
                "by_company": by_company,
            }

    def clear_old_jobs(self, days: int = 30):
        """Remove jobs older than specified days."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                DELETE FROM seen_jobs
                WHERE first_seen < datetime('now', ? || ' days')
            """, (f"-{days}",))
            conn.commit()

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
        thresholds = self._normalize_thresholds(alert_thresholds)

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT consecutive_failures, last_alert_failure_count
                FROM source_health
                WHERE source = ?
                """,
                (source,),
            ).fetchone()

            previous_failures = row[0] if row else 0
            stored_alert_failure_count = row[1] if row else 0
            # Rearm thresholds after any successful run (new streak starts at 1).
            last_alert_failure_count = 0 if previous_failures == 0 else stored_alert_failure_count
            consecutive_failures = previous_failures + 1

            eligible_thresholds = [
                t for t in thresholds
                if t <= consecutive_failures and t > last_alert_failure_count
            ]
            alert_threshold = max(eligible_thresholds) if eligible_thresholds else None

            conn.execute(
                """
                INSERT INTO source_health
                (source, consecutive_failures, last_error, last_failure_at, last_alert_failure_count, pending_recovery_after)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, 0)
                ON CONFLICT(source) DO UPDATE SET
                    consecutive_failures = excluded.consecutive_failures,
                    last_error = excluded.last_error,
                    last_failure_at = excluded.last_failure_at,
                    last_alert_failure_count = excluded.last_alert_failure_count,
                    pending_recovery_after = 0
                """,
                (source, consecutive_failures, error, last_alert_failure_count),
            )
            conn.commit()

        return consecutive_failures, alert_threshold

    def confirm_source_failure_alert(self, source: str, alert_failure_count: int):
        """Persist that a failure alert was successfully sent up to this threshold."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE source_health
                SET last_alert_failure_count = CASE
                    WHEN last_alert_failure_count < ? THEN ?
                    ELSE last_alert_failure_count
                END
                WHERE source = ?
                """,
                (alert_failure_count, alert_failure_count, source),
            )
            conn.commit()

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
        thresholds = self._normalize_thresholds(alert_thresholds)
        min_threshold = min(thresholds)

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT consecutive_failures, last_alert_failure_count, pending_recovery_after
                FROM source_health
                WHERE source = ?
                """,
                (source,),
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
                """
                INSERT INTO source_health
                (source, consecutive_failures, last_error, last_success_at, last_alert_failure_count, pending_recovery_after)
                VALUES (?, 0, NULL, CURRENT_TIMESTAMP, 0, ?)
                ON CONFLICT(source) DO UPDATE SET
                    consecutive_failures = 0,
                    last_error = NULL,
                    last_success_at = excluded.last_success_at,
                    last_alert_failure_count = 0,
                    pending_recovery_after = excluded.pending_recovery_after
                """,
                (source, recovery_after),
            )
            conn.commit()

        return recovery_after

    def confirm_source_recovery_alert(self, source: str):
        """Clear pending recovery alert state after successful notification."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE source_health
                SET pending_recovery_after = 0
                WHERE source = ?
                """,
                (source,),
            )
            conn.commit()
