"""GitHub repository tracker for job listings."""

from collections import Counter
from typing import Optional

import requests

from config import GITHUB_REPOS, TARGET_COMPANIES
from filters import compact_company_names, company_matches, has_role_keyword, matches_job_criteria
from http_client import create_session
from models import Job, ScrapeResult
from posted_dates import normalize_posted_date
from screening import screen_job
from sources.list_parsers import ListingRow, best_url, parse_listing_tables


class GitHubTracker:
    """Tracks job listings from GitHub repositories."""

    def __init__(self):
        self.session = create_session()
        self.last_errors: list[str] = []
        self.last_attempted_repos = 0
        self.last_successful_repos = 0
        self.last_repo_results: dict[str, ScrapeResult] = {}
        self.screen_counts: Counter = Counter()
        self.targets = compact_company_names(TARGET_COMPANIES)
        self.session.headers.update({
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "JobTracker/1.0",
        })

    def fetch_jobs_with_status(self) -> tuple[list[Job], bool, str]:
        """Fetch jobs and return (jobs, healthy, error_summary).

        The source is healthy when at least one repository parsed. Per-list
        health is in last_repo_results, which main.py records and alerts on
        separately for each list.
        """
        all_jobs = []
        self.last_errors = []
        self.last_attempted_repos = 0
        self.last_successful_repos = 0
        self.last_repo_results = {}
        self.screen_counts = Counter()

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

        healthy = self.last_successful_repos > 0
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
        """Parse a job-list README (HTML or Markdown tables)."""
        jobs = []
        rows = parse_listing_tables(content)

        for row in rows:
            job = self._job_from_row(row, source=repo_name)
            if job and self._matches_criteria(job):
                jobs.append(job)

        if not rows:
            return ScrapeResult(
                status="parse_failure",
                error=f"{repo_name}: no candidate job rows found",
            )

        return ScrapeResult(
            jobs=jobs,
            candidate_count=len(rows),
            status="success" if jobs else "empty",
        )

    def _job_from_row(self, row: ListingRow, *, source: str) -> Optional[Job]:
        """Build a job from an open row; the parser resolves continuation rows."""
        if not row.company or not row.title or row.closed:
            return None
        url = best_url(row)
        if not url:
            return None
        return Job(
            company=row.company,
            title=row.title,
            url=url,
            location=row.location,
            source=source,
            date_posted=normalize_posted_date(row.age) if row.age else "",
            list_markers=row.markers,
        )

    def _matches_criteria(self, job: Job) -> bool:
        """Check company, role, shared filters, then sponsorship screening."""
        if not company_matches(job.company, self.targets):
            return False

        if not (has_role_keyword(job.title) and matches_job_criteria(job)):
            return False

        drop_reason = screen_job(job)
        if drop_reason:
            self.screen_counts[drop_reason] += 1
            return False
        return True
