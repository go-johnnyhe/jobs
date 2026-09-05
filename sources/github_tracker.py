"""GitHub repository tracker for job listings."""

from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import GITHUB_REPOS, TARGET_COMPANIES
from filters import has_role_keyword, matches_job_criteria
from http_client import create_session
from models import Job, ScrapeResult


class GitHubTracker:
    """Tracks job listings from GitHub repositories."""

    def __init__(self):
        self.session = create_session()
        self.last_errors: list[str] = []
        self.last_attempted_repos = 0
        self.last_successful_repos = 0
        self.last_repo_results: dict[str, ScrapeResult] = {}
        self.session.headers.update({
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "JobTracker/1.0",
        })

    def fetch_jobs_with_status(self) -> tuple[list[Job], bool, str]:
        """Fetch jobs and return (jobs, healthy, error_summary)."""
        all_jobs = []
        self.last_errors = []
        self.last_attempted_repos = 0
        self.last_successful_repos = 0
        self.last_repo_results = {}

        for repo_config in GITHUB_REPOS:
            self.last_attempted_repos += 1
            result = self._fetch_from_repo(repo_config)
            repo_key = f"{repo_config['owner']}/{repo_config['repo']}"
            self.last_repo_results[repo_key] = result
            all_jobs.extend(result.jobs)
            if result.healthy:
                self.last_successful_repos += 1
            elif result.error:
                self.last_errors.append(result.error)

        healthy = self.last_attempted_repos == 0 or self.last_successful_repos > 0
        error_summary = "; ".join(self.last_errors[:3])
        return all_jobs, healthy, error_summary

    def _fetch_from_repo(self, repo_config: dict) -> ScrapeResult:
        """Fetch jobs from a single GitHub repository."""
        owner = repo_config["owner"]
        repo = repo_config["repo"]
        branch = repo_config.get("branch", "main")
        file_path = repo_config["file"]

        # The unauthenticated GitHub Contents API is limited to 60 requests per
        # hour per runner IP. Raw content is the same authoritative branch data
        # without making the hourly tracker share that small API quota.
        url = (
            f"https://raw.githubusercontent.com/{owner}/{repo}/"
            f"{branch}/{file_path}"
        )

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            content = response.text

            return self._parse_simplify_readme(content, repo_name=f"{owner}/{repo}")
        except requests.RequestException as e:
            print(f"Error fetching from {owner}/{repo}: {e}")
            return ScrapeResult(
                status="request_failure",
                error=f"{owner}/{repo}: {e}",
            )

    def _parse_simplify_readme(self, content: str, *, repo_name: str) -> ScrapeResult:
        """Parse the SimplifyJobs README.md format (HTML tables)."""
        jobs = []
        candidate_count = 0
        soup = BeautifulSoup(content, "html.parser")

        for table in soup.find_all("table"):
            company = ""
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue
                candidate_count += 1
                company_text = cells[0].get_text(" ", strip=True)
                if company_text not in {"", "↳", "↪"}:
                    company = company_text
                job = self._parse_html_row(cells, company=company, source=repo_name)
                if job and self._matches_criteria(job):
                    jobs.append(job)

        if candidate_count == 0:
            return ScrapeResult(
                status="parse_failure",
                error=f"{repo_name}: no candidate job rows found",
            )

        return ScrapeResult(
            jobs=jobs,
            candidate_count=candidate_count,
            status="success" if jobs else "empty",
        )

    def _parse_html_row(self, cells, *, company: str, source: str) -> Optional[Job]:
        """Parse a complete row; the caller resolves repeated company cells."""
        title = cells[1].get_text(" ", strip=True)
        location = cells[2].get_text("; ", strip=True)
        if not company or not title or "🔒" in cells[3].get_text():
            return None
        links = [
            link["href"] for link in cells[3].find_all("a", href=True)
            if link["href"].startswith(("https://", "http://"))
        ]
        if not links:
            return None
        url = next((href for href in links if "simplify.jobs" not in href), links[0])
        return Job(
            company=company,
            title=title,
            url=url,
            location=location,
            source=source,
            date_posted=cells[4].get_text(strip=True) if len(cells) > 4 else "",
        )

    def _matches_criteria(self, job: Job) -> bool:
        """Check if a job matches our filtering criteria."""
        # Check if company is in our target list
        # Short targets (len <= 2) require exact match to avoid false positives
        # (e.g. "f5" matching "Flexport")
        company_lower = job.company.lower()
        company_match = any(
            (company_lower == target if len(target) <= 2 else target in company_lower)
            for target in TARGET_COMPANIES
        )

        if not company_match:
            return False

        return has_role_keyword(job.title) and matches_job_criteria(job)
