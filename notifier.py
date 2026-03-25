"""Discord webhook notifier for job alerts."""

import json
from typing import Optional

import requests

from config import DISCORD_WEBHOOK_URL
from http_client import create_session

MAX_EMBEDS_PER_MESSAGE = 10


class DiscordNotifier:
    """Sends job notifications via Discord webhook."""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or DISCORD_WEBHOOK_URL
        # Disable all POST retries for Discord webhooks to avoid
        # duplicate messages (Discord may process POST before returning error,
        # and connection/timeout retries on POST can also duplicate)
        self.session = create_session(status_forcelist=(), allowed_methods=("GET",))

    def notify(self, jobs: list, dry_run: bool = False) -> bool:
        """Send job notifications to Discord."""
        if not jobs:
            print("No jobs to notify about")
            return True

        if not self.webhook_url:
            print("No Discord webhook URL configured")
            return False

        for batch_index, start in enumerate(range(0, len(jobs), MAX_EMBEDS_PER_MESSAGE)):
            batch = jobs[start:start + MAX_EMBEDS_PER_MESSAGE]
            sent = self.send_job_batch(
                batch,
                total_jobs=len(jobs),
                batch_index=batch_index,
                dry_run=dry_run,
            )
            if not sent:
                return False

        return True

    def send_job_batch(
        self,
        jobs: list,
        *,
        total_jobs: Optional[int] = None,
        batch_index: int = 0,
        dry_run: bool = False,
    ) -> bool:
        """Send a single Discord message containing up to 10 job embeds."""
        if not jobs:
            return True

        if len(jobs) > MAX_EMBEDS_PER_MESSAGE:
            raise ValueError(
                f"Discord batches are limited to {MAX_EMBEDS_PER_MESSAGE} jobs"
            )

        if not self.webhook_url:
            print("No Discord webhook URL configured")
            return False

        payload = self._build_job_batch_payload(
            jobs,
            total_jobs=total_jobs or len(jobs),
            batch_index=batch_index,
        )

        if dry_run:
            print("Dry run - would send:")
            print(json.dumps(payload, indent=2))
            return True

        try:
            self._send_payload(payload)
            print(
                f"Successfully sent batch {batch_index + 1} "
                f"with {len(jobs)} job(s)"
            )
            return True
        except requests.RequestException as e:
            print(f"Error sending Discord notification batch {batch_index + 1}: {e}")
            return False

    def notify_source_failure(
        self,
        source: str,
        consecutive_failures: int,
        error: Optional[str],
        dry_run: bool = False,
    ) -> bool:
        """Send an alert when a source has repeated failures."""
        return self._send_health_alert(
            subject_type="Source",
            name=source,
            consecutive_failures=consecutive_failures,
            error=error,
            dry_run=dry_run,
        )

    def notify_source_recovery(
        self,
        source: str,
        recovered_after: int,
        dry_run: bool = False,
    ) -> bool:
        """Send an alert when a previously failing source recovers."""
        return self._send_recovery_alert(
            subject_type="Source",
            name=source,
            recovered_after=recovered_after,
            dry_run=dry_run,
        )

    def notify_company_failure(
        self,
        company: str,
        consecutive_failures: int,
        error: Optional[str],
        dry_run: bool = False,
    ) -> bool:
        """Send an alert when a priority company scrape repeatedly fails."""
        return self._send_health_alert(
            subject_type="Company",
            name=company,
            consecutive_failures=consecutive_failures,
            error=error,
            dry_run=dry_run,
        )

    def notify_company_recovery(
        self,
        company: str,
        recovered_after: int,
        dry_run: bool = False,
    ) -> bool:
        """Send an alert when a priority company scrape recovers."""
        return self._send_recovery_alert(
            subject_type="Company",
            name=company,
            recovered_after=recovered_after,
            dry_run=dry_run,
        )

    def _send_health_alert(
        self,
        *,
        subject_type: str,
        name: str,
        consecutive_failures: int,
        error: Optional[str],
        dry_run: bool,
    ) -> bool:
        """Send a repeated-failure alert for a source or company."""
        if not self.webhook_url:
            print("No Discord webhook URL configured")
            return False

        payload = {
            "content": f"[{subject_type} alert] `{name}` has repeated failures",
            "embeds": [
                {
                    "title": f"Job {subject_type} Failure",
                    "color": 0xED4245,
                    "fields": [
                        {
                            "name": subject_type,
                            "value": name,
                            "inline": True,
                        },
                        {
                            "name": "Consecutive failures",
                            "value": str(consecutive_failures),
                            "inline": True,
                        },
                        {
                            "name": "Last error",
                            "value": (error or "Unknown error")[:1024],
                            "inline": False,
                        },
                    ],
                }
            ],
        }

        if dry_run:
            print(f"Dry run - would send {subject_type.lower()} failure alert:")
            print(json.dumps(payload, indent=2))
            return True

        try:
            self._send_payload(payload)
            print(
                f"Sent {subject_type.lower()} failure alert for {name} "
                f"({consecutive_failures} consecutive)"
            )
            return True
        except requests.RequestException as e:
            print(f"Error sending {subject_type.lower()} failure alert: {e}")
            return False

    def _send_recovery_alert(
        self,
        *,
        subject_type: str,
        name: str,
        recovered_after: int,
        dry_run: bool,
    ) -> bool:
        """Send a recovery alert for a source or company."""
        if not self.webhook_url:
            print("No Discord webhook URL configured")
            return False

        payload = {
            "content": f"[{subject_type} recovery] `{name}` is healthy again",
            "embeds": [
                {
                    "title": f"Job {subject_type} Recovery",
                    "color": 0x57F287,
                    "fields": [
                        {
                            "name": subject_type,
                            "value": name,
                            "inline": True,
                        },
                        {
                            "name": "Recovered after",
                            "value": f"{recovered_after} failed run(s)",
                            "inline": True,
                        },
                    ],
                }
            ],
        }

        if dry_run:
            print(f"Dry run - would send {subject_type.lower()} recovery alert:")
            print(json.dumps(payload, indent=2))
            return True

        try:
            self._send_payload(payload)
            print(f"Sent {subject_type.lower()} recovery alert for {name}")
            return True
        except requests.RequestException as e:
            print(f"Error sending {subject_type.lower()} recovery alert: {e}")
            return False

    def _send_payload(self, payload: dict):
        """Send a Discord webhook payload and raise on failure."""
        response = self.session.post(
            self.webhook_url,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()

    def _build_job_batch_payload(
        self,
        jobs: list,
        *,
        total_jobs: int,
        batch_index: int,
    ) -> dict:
        """Build the payload for a single job-notification batch."""
        embeds = [self._build_embed(job) for job in jobs]
        if batch_index == 0:
            content = f"**New Job Alert!** Sending {len(jobs)} of {total_jobs} position(s)"
        else:
            content = (
                f"(continued) Sending batch {batch_index + 1} "
                f"with {len(jobs)} more position(s)"
            )

        return {
            "content": content,
            "embeds": embeds,
        }

    def _build_embed(self, job) -> dict:
        """Build a Discord embed for a job listing."""
        # Handle both Job objects and dicts
        if hasattr(job, "company"):
            company = job.company
            title = job.title
            url = job.url
            location = job.location or "Not specified"
            source = job.source
        else:
            company = job.get("company", "Unknown")
            title = job.get("title", "Unknown")
            url = job.get("url", "")
            location = job.get("location", "") or "Not specified"
            source = job.get("source", "")

        # Choose color based on company
        color = self._get_company_color(company)

        embed = {
            "title": f"{company} - {title}",
            "url": url,
            "color": color,
            "fields": [
                {
                    "name": "Location",
                    "value": location,
                    "inline": True,
                },
                {
                    "name": "Source",
                    "value": source,
                    "inline": True,
                },
            ],
        }

        return embed

    def _get_company_color(self, company: str) -> int:
        """Get a color code for a company."""
        colors = {
            "google": 0x4285F4,      # Google Blue
            "meta": 0x0866FF,        # Meta Blue
            "facebook": 0x1877F2,    # Facebook Blue
            "amazon": 0xFF9900,      # Amazon Orange
            "apple": 0xA2AAAD,       # Apple Silver
            "netflix": 0xE50914,     # Netflix Red
            "airbnb": 0xFF5A5F,      # Airbnb Red
            "rubrik": 0x00A3E0,      # Rubrik Blue
            "microsoft": 0x00A4EF,   # Microsoft Blue
            "stripe": 0x635BFF,      # Stripe Purple
        }

        company_lower = company.lower()
        for name, color in colors.items():
            if name in company_lower:
                return color

        return 0x5865F2  # Discord Blurple default

    def send_test(self) -> bool:
        """Send a test notification."""
        if not self.webhook_url:
            print("No Discord webhook URL configured")
            return False

        payload = {
            "content": "Job Tracker Test Notification",
            "embeds": [
                {
                    "title": "Test Job Alert",
                    "description": "If you see this, your Discord webhook is working correctly!",
                    "color": 0x00FF00,  # Green
                    "fields": [
                        {
                            "name": "Status",
                            "value": "Connected",
                            "inline": True,
                        },
                    ],
                }
            ],
        }

        try:
            response = self.session.post(
                self.webhook_url,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            print("Test notification sent successfully!")
            return True
        except requests.RequestException as e:
            print(f"Error sending test notification: {e}")
            return False
