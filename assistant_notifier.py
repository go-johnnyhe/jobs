"""JSON webhook delivery of new jobs to Johnny's AI assistant."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from typing import Callable, Optional

import requests

from config import (
    ASSISTANT_BACKOFF_SECONDS,
    ASSISTANT_BATCH_SIZE,
    ASSISTANT_MAX_ATTEMPTS,
    ASSISTANT_MAX_RETRY_AFTER_SECONDS,
    ASSISTANT_TIMEOUT_SECONDS,
    ASSISTANT_WEBHOOK_KEY,
    ASSISTANT_WEBHOOK_URL,
    LIST_MARKERS,
)
from http_client import create_session, describe_request_error
from models import Job
from posted_dates import normalize_posted_date

PAYLOAD_SCHEMA = "job-tracker.new-jobs.v1"
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
# Statuses that reject the content of a batch rather than the request itself
# (auth, URL, method). Rejected batches are split to isolate the bad job.
CONTENT_REJECTED_STATUS = {400, 413, 422}


@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    status: Optional[int] = None

    @property
    def content_rejected(self) -> bool:
        return not self.ok and self.status in CONTENT_REJECTED_STATUS
_DISPLAY_MARKERS = tuple(LIST_MARKERS) + ("🔥", "🔒")


def _display(value: str) -> str:
    text = str(value or "")
    for marker in _DISPLAY_MARKERS:
        text = text.replace(marker, " ")
    return re.sub(r"\s+", " ", text).strip()


def _iso_timestamp(value) -> Optional[str]:
    """Convert a SQLite UTC timestamp or datetime to ISO 8601 with Z."""
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value
    else:
        text = str(value).strip()
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def job_id(unique_id: str) -> str:
    """Stable short identifier the receiver can use to deduplicate jobs."""
    return hashlib.sha256(unique_id.encode("utf-8")).hexdigest()[:20]


def job_payload(job) -> dict:
    """Serialize a stored job row (dict) or a Job for the assistant."""
    if isinstance(job, Job):
        record = {
            "unique_id": job.unique_id,
            "company": job.company,
            "title": job.title,
            "location": job.location,
            "url": job.url,
            "source": job.source,
            "date_posted": job.date_posted,
            "first_seen": None,
            "sponsorship": job.sponsorship,
            "seniority_flag": job.seniority_flag,
            "min_years_experience": job.min_years_experience,
            "screening_notes": job.screening_notes,
        }
    else:
        record = dict(job)
    notes = record.get("screening_notes") or []
    if isinstance(notes, str):
        try:
            notes = json.loads(notes)
        except ValueError:
            notes = [notes]
    first_seen = _iso_timestamp(record.get("first_seen"))
    reference = None
    if first_seen and first_seen.endswith("Z"):
        reference = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
    return {
        "id": job_id(record["unique_id"]),
        "title": _display(record.get("title")),
        "company": _display(record.get("company")),
        "location": record.get("location") or "",
        "url": record.get("url") or "",
        "source": record.get("source") or "",
        "posted_date": normalize_posted_date(record.get("date_posted"), now=reference),
        "first_seen": first_seen,
        "sponsorship": record.get("sponsorship") or "unknown",
        "seniority_flag": record.get("seniority_flag") or "none",
        "min_years_experience": record.get("min_years_experience"),
        "screening_notes": list(notes),
    }


class AssistantNotifier:
    """POSTs batches of jobs as JSON to ASSISTANT_WEBHOOK_URL."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        webhook_key: Optional[str] = None,
        *,
        batch_size: int = ASSISTANT_BATCH_SIZE,
        max_attempts: int = ASSISTANT_MAX_ATTEMPTS,
        backoff_seconds: float = ASSISTANT_BACKOFF_SECONDS,
        max_retry_after_seconds: float = ASSISTANT_MAX_RETRY_AFTER_SECONDS,
        timeout: float = ASSISTANT_TIMEOUT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.webhook_url = (ASSISTANT_WEBHOOK_URL if webhook_url is None else webhook_url).strip()
        self.webhook_key = (ASSISTANT_WEBHOOK_KEY if webhook_key is None else webhook_key).strip()
        self.batch_size = max(1, batch_size)
        self.max_attempts = max(1, max_attempts)
        self.backoff_seconds = backoff_seconds
        self.max_retry_after_seconds = max_retry_after_seconds
        self.timeout = timeout
        self.sleep = sleep
        # Retries are handled here so Retry-After and the attempt count are
        # explicit; the batch idempotency key lets the receiver drop repeats.
        self.session = create_session(retries=0, status_forcelist=())

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url)

    def headers(self, idempotency_key: str) -> dict:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "JobTracker/1.0 (+assistant-webhook)",
            "Idempotency-Key": idempotency_key,
        }
        if self.webhook_key:
            headers["Authorization"] = f"Bearer {self.webhook_key}"
            headers["X-Webhook-Key"] = self.webhook_key
        return headers

    def build_payload(
        self,
        jobs: list,
        *,
        run_timestamp: str,
        batch_index: int,
        batch_count: int,
        total_jobs: int,
        pending_after_run: int = 0,
    ) -> dict:
        serialized = [job_payload(job) for job in jobs]
        batch_id = hashlib.sha256(
            "|".join(job["id"] for job in serialized).encode("utf-8")
        ).hexdigest()[:24]
        return {
            "schema": PAYLOAD_SCHEMA,
            "event": "new_jobs",
            "run_timestamp": run_timestamp,
            "batch": {
                "id": batch_id,
                "index": batch_index,
                "count": batch_count,
                "size": len(serialized),
                "total_jobs": total_jobs,
                "pending_after_run": pending_after_run,
            },
            "jobs": serialized,
        }

    def batches(self, jobs: list) -> list[list]:
        return [
            jobs[start:start + self.batch_size]
            for start in range(0, len(jobs), self.batch_size)
        ]

    def send_payload(self, payload: dict, *, dry_run: bool = False) -> bool:
        return self.deliver(payload, dry_run=dry_run).ok

    def deliver(self, payload: dict, *, dry_run: bool = False) -> "DeliveryResult":
        """POST one payload, retrying transient failures with exponential backoff.

        Logs show only the exception type and HTTP status: exception messages
        contain the URL, and response bodies may echo request details.
        """
        if dry_run:
            print("Dry run - would send assistant webhook payload:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return DeliveryResult(ok=True)
        if not self.configured:
            return DeliveryResult(ok=False)

        idempotency_key = payload.get("batch", {}).get("id") or payload.get("event", "")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        status = None
        for attempt in range(1, self.max_attempts + 1):
            delay = self.backoff_seconds * (2 ** (attempt - 1))
            try:
                response = self.session.post(
                    self.webhook_url,
                    data=body,
                    headers=self.headers(idempotency_key),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                status = None
                error = describe_request_error(exc)
            else:
                status = response.status_code
                if 200 <= status < 300:
                    return DeliveryResult(ok=True, status=status)
                error = f"HTTP {status}"
                if status not in RETRYABLE_STATUS:
                    print(f"Assistant webhook rejected batch (not retrying): {error}")
                    return DeliveryResult(ok=False, status=status)
                retry_after = self._retry_after(response)
                if retry_after is not None:
                    delay = retry_after
            if attempt == self.max_attempts:
                print(f"Assistant webhook failed after {attempt} attempt(s): {error}")
                return DeliveryResult(ok=False, status=status)
            print(f"Assistant webhook attempt {attempt} failed ({error}); retrying in {delay:.1f}s")
            self.sleep(delay)
        return DeliveryResult(ok=False, status=status)

    def _retry_after(self, response) -> Optional[float]:
        value = response.headers.get("Retry-After")
        if not value:
            return None
        try:
            seconds = float(value)
        except ValueError:
            return None
        return max(0.0, min(seconds, self.max_retry_after_seconds))

    def send_test(self, *, dry_run: bool = False) -> bool:
        payload = {
            "schema": PAYLOAD_SCHEMA,
            "event": "test",
            "run_timestamp": _iso_timestamp(datetime.now(timezone.utc)),
            "batch": {
                "id": "test",
                "index": 0,
                "count": 1,
                "size": 0,
                "total_jobs": 0,
                "pending_after_run": 0,
            },
            "jobs": [],
        }
        if not self.configured and not dry_run:
            print("No assistant webhook URL configured (ASSISTANT_WEBHOOK_URL)")
            return False
        sent = self.send_payload(payload, dry_run=dry_run)
        if sent and not dry_run:
            print("Assistant webhook test payload accepted")
        return sent
