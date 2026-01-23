"""Direct career page scraper for job listings."""

import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import COMPANIES, TITLE_KEYWORDS, ROLE_KEYWORDS
from filters import matches_job_criteria, matches_location, is_senior_level, has_new_grad_indicator
from .github_tracker import Job


class CareerScraper:
    """Scrapes job listings directly from company career pages."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def fetch_jobs(self) -> list[Job]:
        """Fetch all jobs from configured company career pages."""
        all_jobs = []

        for company_name, config in COMPANIES.items():
            print(f"Scraping {company_name}...")
            try:
                jobs = self._scrape_company(company_name, config)
                all_jobs.extend(jobs)
                print(f"  Found {len(jobs)} matching jobs")
            except Exception as e:
                print(f"  Error scraping {company_name}: {e}")

        return all_jobs

    def _scrape_company(self, company_name: str, config: dict) -> list[Job]:
        """Scrape a single company's career page."""
        ats = config.get("ats", "internal")
        url = config["url"]

        if ats == "greenhouse":
            return self._scrape_greenhouse(company_name, url)
        elif ats == "lever":
            return self._scrape_lever(company_name, url)
        else:
            return self._scrape_generic(company_name, url)

    def _scrape_greenhouse(self, company_name: str, url: str) -> list[Job]:
        """Scrape jobs from Greenhouse-powered career pages."""
        jobs = []

        # Try to find the Greenhouse board ID and use JSON API
        # Greenhouse API endpoint pattern: https://boards-api.greenhouse.io/v1/boards/{board}/jobs
        board_id = self._extract_greenhouse_board(url)

        if board_id:
            api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs"
            try:
                response = self.session.get(api_url, timeout=30)
                response.raise_for_status()
                data = response.json()

                for job_data in data.get("jobs", []):
                    job = self._parse_greenhouse_job(company_name, job_data, board_id)
                    if job and self._matches_criteria(job):
                        jobs.append(job)
            except requests.RequestException:
                # Fall back to HTML scraping
                jobs = self._scrape_generic(company_name, url)
        else:
            jobs = self._scrape_generic(company_name, url)

        return jobs

    def _extract_greenhouse_board(self, url: str) -> Optional[str]:
        """Extract Greenhouse board ID from URL or page."""
        # Common patterns
        patterns = [
            r"boards\.greenhouse\.io/(\w+)",
            r"greenhouse\.io/embed/job_board\?token=(\w+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # Try to find it from the career page
        try:
            response = self.session.get(url, timeout=30)
            for pattern in patterns:
                match = re.search(pattern, response.text)
                if match:
                    return match.group(1)
        except requests.RequestException:
            pass

        # Known board IDs for our target companies
        known_boards = {
            "airbnb": "airbnb",
            "rubrik": "rubrik",
        }

        for company, board in known_boards.items():
            if company in url.lower():
                return board

        return None

    def _parse_greenhouse_job(self, company_name: str, job_data: dict, board_id: str) -> Optional[Job]:
        """Parse a Greenhouse API job response."""
        title = job_data.get("title", "")
        job_id = job_data.get("id", "")
        location = job_data.get("location", {}).get("name", "")

        if not title or not job_id:
            return None

        url = f"https://boards.greenhouse.io/{board_id}/jobs/{job_id}"

        return Job(
            company=company_name,
            title=title,
            url=url,
            location=location,
            source="career_page",
        )

    def _scrape_lever(self, company_name: str, url: str) -> list[Job]:
        """Scrape jobs from Lever-powered career pages."""
        jobs = []

        # Try Lever JSON API
        # Pattern: https://api.lever.co/v0/postings/{company}
        lever_company = self._extract_lever_company(url)

        if lever_company:
            api_url = f"https://api.lever.co/v0/postings/{lever_company}"
            try:
                response = self.session.get(api_url, timeout=30)
                response.raise_for_status()
                data = response.json()

                for job_data in data:
                    job = self._parse_lever_job(company_name, job_data)
                    if job and self._matches_criteria(job):
                        jobs.append(job)
            except requests.RequestException:
                jobs = self._scrape_generic(company_name, url)
        else:
            jobs = self._scrape_generic(company_name, url)

        return jobs

    def _extract_lever_company(self, url: str) -> Optional[str]:
        """Extract Lever company ID from URL."""
        patterns = [
            r"jobs\.lever\.co/(\w+)",
            r"lever\.co/(\w+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # Known Lever companies
        known_companies = {
            "netflix": "netflix",
        }

        for company, lever_id in known_companies.items():
            if company in url.lower():
                return lever_id

        return None

    def _parse_lever_job(self, company_name: str, job_data: dict) -> Optional[Job]:
        """Parse a Lever API job response."""
        title = job_data.get("text", "")
        url = job_data.get("hostedUrl", "")

        categories = job_data.get("categories", {})
        location = categories.get("location", "")

        if not title or not url:
            return None

        return Job(
            company=company_name,
            title=title,
            url=url,
            location=location,
            source="career_page",
        )

    def _scrape_generic(self, company_name: str, url: str) -> list[Job]:
        """Generic HTML scraper for career pages."""
        jobs = []

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Look for common job listing patterns
            # This is a best-effort approach since each site is different

            # Look for links that might be job postings
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)

                # Check if this looks like a job link
                if self._looks_like_job_link(href, text):
                    job = Job(
                        company=company_name,
                        title=text,
                        url=self._normalize_url(href, url),
                        location="",  # Hard to extract reliably
                        source="career_page",
                    )

                    if self._matches_criteria(job):
                        jobs.append(job)
        except requests.RequestException as e:
            print(f"  Error fetching {url}: {e}")

        return jobs

    def _looks_like_job_link(self, href: str, text: str) -> bool:
        """Check if a link appears to be a job posting."""
        href_lower = href.lower()
        text_lower = text.lower()

        # Skip obvious non-job links
        skip_patterns = ["login", "sign", "about", "contact", "privacy", "terms", "blog"]
        if any(p in href_lower or p in text_lower for p in skip_patterns):
            return False

        # Check for job-related patterns in URL
        job_url_patterns = ["/job", "/position", "/opening", "/career", "/apply"]
        if any(p in href_lower for p in job_url_patterns):
            return True

        # Check text for role keywords
        if any(kw in text_lower for kw in ROLE_KEYWORDS):
            return True

        return False

    def _normalize_url(self, href: str, base_url: str) -> str:
        """Convert relative URLs to absolute."""
        if href.startswith("http"):
            return href

        from urllib.parse import urljoin
        return urljoin(base_url, href)

    def _matches_criteria(self, job: Job) -> bool:
        """Check if a job matches our filtering criteria."""
        title_lower = job.title.lower()

        # Check for role keywords
        has_role_keyword = any(kw in title_lower for kw in ROLE_KEYWORDS)
        if not has_role_keyword:
            return False

        # Check for new grad / entry level keywords
        is_new_grad = has_new_grad_indicator(title_lower)

        # If title has new grad keyword, still check seniority and location
        if is_new_grad:
            # Even new grad roles should pass seniority check (avoid "Senior - New Grad Program")
            if is_senior_level(title_lower):
                return False
            # Check location with word boundaries
            if job.location and not matches_location(job.location):
                return False
            return True

        # For non-explicit new grad roles, apply full filtering
        # Must not be senior level
        if is_senior_level(title_lower):
            return False

        # Check location with word boundaries
        if job.location and not matches_location(job.location):
            return False

        return True
