"""GitHub repository tracker for job listings."""

import re
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import GITHUB_REPOS, TARGET_COMPANIES
from filters import matches_job_criteria


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
        """Parse the SimplifyJobs README.md format (HTML tables)."""
        jobs = []
        soup = BeautifulSoup(content, "html.parser")

        # Find all table rows
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            job = self._parse_html_row(cells)
            if job and self._matches_criteria(job):
                jobs.append(job)

        return jobs

    def _parse_html_row(self, cells) -> Optional[Job]:
        """Parse an HTML table row into a Job object."""
        try:
            # Cell 0: Company (with link)
            company_cell = cells[0]
            company_link = company_cell.find("a")
            company = company_link.get_text(strip=True) if company_link else company_cell.get_text(strip=True)

            # Cell 1: Role/Title
            title = cells[1].get_text(strip=True)

            # Cell 2: Location
            location = cells[2].get_text(strip=True) if len(cells) > 2 else ""

            # Cell 3: Application link - find the first actual job link (not simplify.jobs)
            url = ""
            if len(cells) > 3:
                for link in cells[3].find_all("a", href=True):
                    href = link.get("href", "")
                    # Skip simplify.jobs links, get the actual application link
                    if href and "simplify.jobs" not in href:
                        url = href
                        break
                # If only simplify link found, use it as fallback
                if not url:
                    first_link = cells[3].find("a", href=True)
                    if first_link:
                        url = first_link.get("href", "")

            # Cell 4: Date/Age
            date_posted = cells[4].get_text(strip=True) if len(cells) > 4 else ""

            if not company or not url:
                return None

            # Skip closed positions (marked with 🔒)
            if "🔒" in str(cells[3]):
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

        # Use shared filter for seniority and location checks
        return matches_job_criteria(job)
