"""SQLite storage for tracking seen job listings."""

import sqlite3
from datetime import datetime
from typing import Optional

from config import DATABASE_PATH


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
            conn.commit()

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
