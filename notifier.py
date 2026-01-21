"""Discord webhook notifier for job alerts."""

import json
from typing import Optional

import requests

from config import DISCORD_WEBHOOK_URL


class DiscordNotifier:
    """Sends job notifications via Discord webhook."""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or DISCORD_WEBHOOK_URL
        self.session = requests.Session()

    def notify(self, jobs: list, dry_run: bool = False) -> bool:
        """Send job notifications to Discord."""
        if not jobs:
            print("No jobs to notify about")
            return True

        if not self.webhook_url:
            print("No Discord webhook URL configured")
            return False

        # Build the message embeds (Discord allows up to 10 embeds per message)
        embeds = []
        for job in jobs[:10]:  # Limit to 10 jobs per message
            embed = self._build_embed(job)
            embeds.append(embed)

        payload = {
            "content": f"**New Job Alert!** Found {len(jobs)} new position(s)",
            "embeds": embeds,
        }

        if dry_run:
            print("Dry run - would send:")
            print(json.dumps(payload, indent=2))
            return True

        try:
            response = self.session.post(
                self.webhook_url,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            print(f"Successfully sent notification for {len(jobs)} jobs")

            # If there are more than 10 jobs, send additional messages
            if len(jobs) > 10:
                for i in range(10, len(jobs), 10):
                    batch = jobs[i:i+10]
                    self._send_batch(batch)

            return True
        except requests.RequestException as e:
            print(f"Error sending Discord notification: {e}")
            return False

    def _send_batch(self, jobs: list) -> bool:
        """Send a batch of jobs as a separate message."""
        embeds = [self._build_embed(job) for job in jobs]

        payload = {
            "content": f"(continued) {len(jobs)} more position(s):",
            "embeds": embeds,
        }

        try:
            response = self.session.post(
                self.webhook_url,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return True
        except requests.RequestException:
            return False

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
