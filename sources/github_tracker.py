"""GitHub repository tracker for job listings."""

import re
from dataclasses import dataclass
from typing import Optional

import requests

from config import GITHUB_REPOS, TARGET_COMPANIES, PREFERRED_LOCATIONS


@dataclass
class Job:
    """Represents a job listing."""
    company: str
    title: str
    url: str
    location: str
    source: str
    date_posted: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "source": self.source,
            "date_posted": self.date_posted,
        }

    @property
    def unique_id(self) -> str:
        """Generate a unique ID for deduplication."""
        return f"{self.company}|{self.title}|{self.url}"


class GitHubTracker:
    """Tracks job listings from GitHub repositories."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "JobTracker/1.0",
        })

    def fetch_jobs(self) -> list[Job]:
        """Fetch all jobs from configured GitHub repositories."""
        all_jobs = []

        for repo_config in GITHUB_REPOS:
            jobs = self._fetch_from_repo(repo_config)
            all_jobs.extend(jobs)

        return all_jobs

    def _fetch_from_repo(self, repo_config: dict) -> list[Job]:
        """Fetch jobs from a single GitHub repository."""
        owner = repo_config["owner"]
        repo = repo_config["repo"]
        file_path = repo_config["file"]

        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            content = response.text

            return self._parse_simplify_readme(content)
        except requests.RequestException as e:
            print(f"Error fetching from {owner}/{repo}: {e}")
            return []

    def _parse_simplify_readme(self, content: str) -> list[Job]:
        """Parse the SimplifyJobs README.md format."""
        jobs = []

        # The SimplifyJobs README has a markdown table format like:
        # | Company | Role | Location | Application/Link | Date Posted |
        # Find the table section
        lines = content.split("\n")
        in_table = False

        for line in lines:
            line = line.strip()

            # Skip empty lines and header separator
            if not line or line.startswith("|--") or line.startswith("| --"):
                continue

            # Check if this looks like a table row
            if line.startswith("|") and line.endswith("|"):
                parts = [p.strip() for p in line.split("|")[1:-1]]  # Remove empty first/last

                if len(parts) >= 4:
                    # Check if this is a header row
                    if "company" in parts[0].lower() or "role" in parts[0].lower():
                        in_table = True
                        continue

                    if in_table:
                        job = self._parse_table_row(parts)
                        if job and self._matches_criteria(job):
                            jobs.append(job)

        return jobs

    def _parse_table_row(self, parts: list[str]) -> Optional[Job]:
        """Parse a single table row into a Job object."""
        try:
            company = self._extract_text(parts[0])
            title = self._extract_text(parts[1])
            location = self._extract_text(parts[2]) if len(parts) > 2 else ""

            # Extract URL from markdown link
            url = self._extract_url(parts[3]) if len(parts) > 3 else ""
            date_posted = self._extract_text(parts[4]) if len(parts) > 4 else ""

            if not company or not url:
                return None

            return Job(
                company=company,
                title=title,
                url=url,
                location=location,
                source="SimplifyJobs/New-Grad-Positions",
                date_posted=date_posted,
            )
        except (IndexError, ValueError):
            return None

    def _extract_text(self, text: str) -> str:
        """Extract plain text from markdown, removing links and formatting."""
        # Remove markdown links [text](url) -> text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Remove bold/italic
        text = re.sub(r"\*+([^*]+)\*+", r"\1", text)
        # Remove images
        text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
        return text.strip()

    def _extract_url(self, text: str) -> str:
        """Extract URL from markdown link."""
        match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", text)
        if match:
            return match.group(2)
        # Check for plain URL
        match = re.search(r"https?://[^\s<>\"]+", text)
        if match:
            return match.group(0)
        return ""

    def _matches_criteria(self, job: Job) -> bool:
        """Check if a job matches our filtering criteria."""
        # Check if company is in our target list
        company_lower = job.company.lower()
        company_match = any(
            target in company_lower
            for target in TARGET_COMPANIES
        )

        if not company_match:
            return False

        # Check location if we have preferred locations
        if PREFERRED_LOCATIONS:
            location_lower = job.location.lower()
            location_match = (
                not location_lower or  # Accept if no location specified
                any(loc in location_lower for loc in PREFERRED_LOCATIONS)
            )
            if not location_match:
                return False

        return True
