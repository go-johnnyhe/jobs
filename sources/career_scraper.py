"""Direct career page scraper for job listings."""

import concurrent.futures
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import (
    CAREER_CONTENT_EXCLUSIONS,
    CAREER_ENTRY_LEVEL_KEYWORDS,
    CAREERS_MAX_WORKERS,
    COMPANIES,
    ROLE_KEYWORDS,
    CAREERS_MIN_HEALTHY_SUCCESS_RATE,
    CAREERS_MIN_HEALTHY_SUCCESSES,
)
from filters import matches_job_criteria
from http_client import create_session
from models import Job, ScrapeResult


class CareerScraper:
    """Scrapes job listings directly from company career pages."""

    def __init__(self):
        # Career sources are checked hourly; one retry is enough to absorb a
        # transient failure without letting a blocked site stall the run.
        self.session = create_session(retries=1)
        self.generic_session = create_session(retries=0)
        self.last_errors: list[str] = []
        self.last_attempted_companies = 0
        self.last_successful_companies = 0
        self.last_company_results: dict[str, ScrapeResult] = {}
        self._run_request_errors: list[str] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self.session.headers.update(headers)
        self.generic_session.headers.update(headers)

    def fetch_jobs(self) -> list[Job]:
        """Fetch all jobs from configured company career pages."""
        jobs, _, _ = self.fetch_jobs_with_status()
        return jobs

    def fetch_jobs_with_status(self) -> tuple[list[Job], bool, str]:
        """Fetch jobs and return (jobs, healthy, error_summary)."""
        all_jobs = []
        self.last_errors = []
        self.last_attempted_companies = 0
        self.last_successful_companies = 0
        self.last_company_results = {}
        self._run_request_errors = []

        company_items = list(COMPANIES.items())
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(CAREERS_MAX_WORKERS, len(company_items) or 1)
        ) as executor:
            result_pairs = executor.map(
                lambda item: (item[0], self._scrape_company(item[0], item[1])),
                company_items,
            )

        for company_name, result in result_pairs:
            self.last_attempted_companies += 1
            print(f"Scraped {company_name}...")
            self.last_company_results[company_name] = result
            all_jobs.extend(result.jobs)
            if result.healthy:
                self.last_successful_companies += 1
                print(
                    f"  Found {len(result.jobs)} matching jobs "
                    f"from {result.candidate_count} candidate(s)"
                )
            else:
                self.last_errors.append(result.error)
                print(f"  Error scraping {company_name}: {result.error}")

        if self.last_attempted_companies == 0:
            healthy = True
        else:
            success_rate = self.last_successful_companies / self.last_attempted_companies
            healthy = (
                self.last_successful_companies >= CAREERS_MIN_HEALTHY_SUCCESSES
                and success_rate >= CAREERS_MIN_HEALTHY_SUCCESS_RATE
            )

        error_summary = "; ".join(self.last_errors[:3])
        if not healthy and not error_summary:
            error_summary = (
                f"Low careers scrape success rate: "
                f"{self.last_successful_companies}/{self.last_attempted_companies}"
            )
        return all_jobs, healthy, error_summary

    def _scrape_company(self, company_name: str, config: dict) -> ScrapeResult:
        """Scrape a single company's career page."""
        ats = config.get("ats", "internal")
        url = config["url"]

        try:
            if ats == "greenhouse":
                return self._scrape_greenhouse(
                    company_name,
                    url,
                    board_id=config.get("ats_id"),
                )
            elif ats == "lever":
                return self._scrape_lever(
                    company_name,
                    url,
                    lever_company=config.get("ats_id"),
                )
            elif ats == "ashby":
                return self._scrape_ashby(
                    company_name,
                    url,
                    board_name=config.get("ats_id"),
                )
            elif ats == "amazon":
                return self._scrape_amazon(
                    company_name,
                    search_queries=config.get("search_queries", []),
                )
            elif ats == "smartrecruiters":
                return self._scrape_smartrecruiters(
                    company_name,
                    company_id=config.get("ats_id"),
                )
            elif ats == "workday":
                return self._scrape_workday(company_name, url)
            return self._scrape_generic(company_name, url)
        except Exception as e:
            return ScrapeResult(
                status="request_failure",
                error=f"{company_name} ({url}): {e}",
            )

    def _scrape_greenhouse(
        self,
        company_name: str,
        url: str,
        board_id: Optional[str] = None,
    ) -> ScrapeResult:
        """Scrape jobs from Greenhouse-powered career pages."""
        jobs = []

        # Try to find the Greenhouse board ID and use JSON API
        # Greenhouse API endpoint pattern: https://boards-api.greenhouse.io/v1/boards/{board}/jobs
        board_id = board_id or self._extract_greenhouse_board(url)

        if board_id:
            api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs"
            try:
                response = self.session.get(
                    api_url,
                    params={"mode": "json"},
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                postings = data.get("jobs", [])

                for job_data in postings:
                    job = self._parse_greenhouse_job(company_name, job_data, board_id)
                    if job and self._matches_criteria(job):
                        jobs.append(job)
                return self._success_result(jobs, len(postings))
            except requests.RequestException as e:
                request_error = self._record_request_error(company_name, api_url, e)
                # Fall back to HTML scraping
                fallback_result = self._scrape_generic(company_name, url)
                if fallback_result.healthy:
                    return fallback_result
                return ScrapeResult(
                    status="request_failure",
                    error=request_error,
                )
            except ValueError as e:
                return ScrapeResult(
                    status="parse_failure",
                    error=f"{company_name} ({api_url}): invalid JSON response ({e})",
                )
        return self._scrape_generic(company_name, url)

    def _extract_greenhouse_board(self, url: str) -> Optional[str]:
        """Extract Greenhouse board ID from URL or page."""
        # Common patterns
        patterns = [
            r"boards\.greenhouse\.io/(?!embed\b)([\w-]+)",
            r"boards\.greenhouse\.io/embed/job_board\?(?:token|for)=([\w-]+)",
            r"greenhouse\.io/embed/job_board\?(?:token|for)=([\w-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # Try to find it from the career page
        try:
            response = self.generic_session.get(url, timeout=15)
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
            "cockroachlabs": "cockroachlabs",
            "robinhood": "robinhood",
            "chime": "chime",
            "sofi": "sofi",
            "digitalocean": "digitalocean98",
            "instacart": "instacart",
            "epicgames": "epicgames",
            "doordash": "doordashusa",
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

    def _scrape_lever(
        self,
        company_name: str,
        url: str,
        lever_company: Optional[str] = None,
    ) -> ScrapeResult:
        """Scrape jobs from Lever-powered career pages."""
        jobs = []

        # Try Lever JSON API
        # Pattern: https://api.lever.co/v0/postings/{company}
        lever_company = lever_company or self._extract_lever_company(url)

        if lever_company:
            api_url = f"https://api.lever.co/v0/postings/{lever_company}"
            try:
                response = self.session.get(
                    api_url,
                    params={"mode": "json"},
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                for job_data in data:
                    job = self._parse_lever_job(company_name, job_data)
                    if job and self._matches_criteria(job):
                        jobs.append(job)
                return self._success_result(jobs, len(data))
            except requests.RequestException as e:
                request_error = self._record_request_error(company_name, api_url, e)
                fallback_result = self._scrape_generic(company_name, url)
                if fallback_result.healthy:
                    return fallback_result
                return ScrapeResult(
                    status="request_failure",
                    error=request_error,
                )
            except ValueError as e:
                return ScrapeResult(
                    status="parse_failure",
                    error=f"{company_name} ({api_url}): invalid JSON response ({e})",
                )
        return self._scrape_generic(company_name, url)

    def _scrape_ashby(
        self,
        company_name: str,
        url: str,
        board_name: Optional[str] = None,
    ) -> ScrapeResult:
        """Scrape jobs from Ashby's public job-board API."""
        if not board_name:
            match = re.search(r"jobs\.ashbyhq\.com/([\w-]+)", url, re.IGNORECASE)
            board_name = match.group(1) if match else None
        if not board_name:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): missing Ashby board name",
            )

        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board_name}"
        try:
            response = self.session.get(api_url, timeout=30)
            response.raise_for_status()
            data = response.json()
            postings = data.get("jobs", [])
            jobs = []
            for posting in postings:
                job = self._parse_ashby_job(company_name, posting)
                if job and self._matches_criteria(job):
                    jobs.append(job)
            return self._success_result(jobs, len(postings))
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except ValueError as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid JSON response ({e})",
            )

    def _parse_ashby_job(self, company_name: str, job_data: dict) -> Optional[Job]:
        """Parse a public Ashby job-board record."""
        title = job_data.get("title", "")
        url = job_data.get("jobUrl") or job_data.get("applyUrl") or ""
        location = job_data.get("location", "")
        if not title or not url:
            return None
        return Job(
            company=company_name,
            title=title,
            url=url,
            location=location,
            source="career_page",
            date_posted=job_data.get("publishedAt"),
        )

    def _scrape_amazon(
        self,
        company_name: str,
        search_queries: list[str],
    ) -> ScrapeResult:
        """Scrape targeted roles from Amazon's public career-search API."""
        api_url = "https://www.amazon.jobs/en/search.json"
        postings_by_id = {}
        try:
            for query in search_queries:
                response = self.session.get(
                    api_url,
                    params={
                        "base_query": query,
                        "offset": 0,
                        "result_limit": 100,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                for posting in data.get("jobs", []):
                    posting_id = posting.get("id") or posting.get("job_path")
                    if posting_id:
                        postings_by_id[posting_id] = posting
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except ValueError as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid JSON response ({e})",
            )

        jobs = []
        for posting in postings_by_id.values():
            job = self._parse_amazon_job(company_name, posting)
            if job and self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings_by_id))

    def _parse_amazon_job(self, company_name: str, job_data: dict) -> Optional[Job]:
        """Parse an Amazon public search result."""
        title = job_data.get("title", "")
        job_path = job_data.get("job_path", "")
        if not title or not job_path:
            return None
        return Job(
            company=company_name,
            title=title,
            url=self._normalize_url(job_path, "https://www.amazon.jobs"),
            location=(
                job_data.get("normalized_location")
                or job_data.get("location")
                or ""
            ),
            source="career_page",
            date_posted=job_data.get("posted_date"),
        )

    def _scrape_smartrecruiters(
        self,
        company_name: str,
        company_id: Optional[str],
    ) -> ScrapeResult:
        """Scrape a company's public SmartRecruiters postings with pagination."""
        if not company_id:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name}: missing SmartRecruiters company identifier",
            )
        api_url = (
            f"https://api.smartrecruiters.com/v1/companies/"
            f"{company_id}/postings"
        )
        postings = []
        offset = 0
        limit = 100
        try:
            while True:
                response = self.session.get(
                    api_url,
                    params={"limit": limit, "offset": offset},
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                page = data.get("content", [])
                postings.extend(page)
                offset += len(page)
                total = data.get("totalFound", len(postings))
                if not page or offset >= total:
                    break
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except ValueError as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid JSON response ({e})",
            )

        jobs = []
        for posting in postings:
            job = self._parse_smartrecruiters_job(
                company_name,
                company_id,
                posting,
            )
            if job and self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings))

    def _parse_smartrecruiters_job(
        self,
        company_name: str,
        company_id: str,
        job_data: dict,
    ) -> Optional[Job]:
        """Parse a SmartRecruiters posting-list record."""
        title = job_data.get("name", "")
        job_id = job_data.get("id", "")
        if not title or not job_id:
            return None
        location = job_data.get("location") or {}
        return Job(
            company=company_name,
            title=title,
            url=f"https://jobs.smartrecruiters.com/{company_id}/{job_id}",
            location=location.get("fullLocation", ""),
            source="career_page",
            date_posted=job_data.get("releasedDate"),
        )

    def _extract_lever_company(self, url: str) -> Optional[str]:
        """Extract Lever company ID from URL."""
        patterns = [
            r"jobs\.lever\.co/([\w-]+)",
            r"lever\.co/([\w-]+)",
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

    def _scrape_generic(self, company_name: str, url: str) -> ScrapeResult:
        """Generic HTML scraper for career pages."""
        jobs = []
        candidate_count = 0

        try:
            response = self.generic_session.get(url, timeout=15)
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
                    candidate_count += 1
                    job = Job(
                        company=company_name,
                        title=text,
                        url=self._normalize_url(href, url),
                        location="",  # Hard to extract reliably
                        source="career_page",
                    )

                    if self._matches_criteria(job):
                        jobs.append(job)
            if candidate_count == 0:
                return ScrapeResult(
                    status="parse_failure",
                    error=f"{company_name} ({url}): no candidate job links found",
                )
            status = "degraded_success" if jobs else "degraded_empty"
            return ScrapeResult(
                jobs=jobs,
                candidate_count=candidate_count,
                status=status,
                error=(
                    f"{company_name} ({url}): generic HTML fallback; "
                    "complete job coverage cannot be verified"
                ),
            )
        except requests.RequestException as e:
            request_error = self._record_request_error(company_name, url, e)
            print(f"  Error fetching {url}: {e}")
            return ScrapeResult(
                status="request_failure",
                error=request_error,
            )

    def _scrape_workday(self, company_name: str, url: str) -> ScrapeResult:
        """Scrape jobs from Workday-powered career pages (CXS API)."""
        jobs = []
        candidate_count = 0

        tenant_site = self._extract_workday_tenant_site(url)
        if not tenant_site:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): unable to extract Workday tenant/site",
            )

        tenant, site, base = tenant_site
        api_url = f"{base}/wday/cxs/{tenant}/{site}/jobs"

        # Most tenants accept 100, which avoids dozens of requests. A few
        # enforce a smaller page size, so retry the first page at 20 on 400.
        limit = 100
        offset = 0
        total = None

        while True:
            payload = {
                "limit": limit,
                "offset": offset,
            }

            try:
                response = self.session.post(
                    api_url,
                    json=payload,
                    timeout=30,
                    headers={"Content-Type": "application/json"},
                )
                if (
                    getattr(response, "status_code", None) == 400
                    and offset == 0
                    and limit > 20
                ):
                    limit = 20
                    continue
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                request_error = self._record_request_error(company_name, api_url, e)
                print(f"  Error fetching Workday API for {company_name}: {e}")
                return ScrapeResult(
                    status="request_failure",
                    error=request_error,
                )
            except ValueError as e:
                return ScrapeResult(
                    status="parse_failure",
                    error=f"{company_name} ({api_url}): invalid JSON response ({e})",
                )

            postings = data.get("jobPostings") or data.get("jobPostingsV2") or []
            if not postings:
                break

            candidate_count += len(postings)
            for posting in postings:
                job = self._parse_workday_job(company_name, posting, base)
                if job and self._matches_criteria(job):
                    jobs.append(job)

            if total is None:
                total = data.get("total", None)

            offset += len(postings)
            if total is not None and offset >= total:
                break

        return self._success_result(jobs, candidate_count)

    def _extract_workday_tenant_site(self, url: str) -> Optional[tuple[str, str, str]]:
        """Extract Workday tenant and site from a Workday jobs URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.netloc
            if not host.endswith(".myworkdayjobs.com"):
                return None

            # Host is usually like "{tenant}.wd5.myworkdayjobs.com"
            tenant = host.split(".")[0]
            path_parts = [p for p in parsed.path.split("/") if p]
            if not path_parts:
                return None

            # First path segment is the site (e.g., "Zillow_Group_External")
            site = path_parts[0]
            base = f"https://{host}"
            return tenant, site, base
        except Exception:
            return None

    def _parse_workday_job(self, company_name: str, posting: dict, base_url: str) -> Optional[Job]:
        """Parse a Workday job posting from CXS API."""
        title = posting.get("title") or posting.get("jobTitle") or ""
        url_path = posting.get("externalPath") or posting.get("externalUrl") or ""
        location = (
            posting.get("locationsText")
            or posting.get("location")
            or posting.get("primaryLocation")
            or ""
        )

        if not title or not url_path:
            return None

        from urllib.parse import urljoin
        url = urljoin(base_url, url_path)

        return Job(
            company=company_name,
            title=title,
            url=url,
            location=location,
            source="career_page",
        )

    def _looks_like_job_link(self, href: str, text: str) -> bool:
        """Check if a link appears to be a job posting."""
        href_lower = href.lower()
        text_lower = text.lower()

        # Skip obvious non-job links
        skip_patterns = [
            "login",
            "sign",
            "about",
            "contact",
            "privacy",
            "terms",
            "blog",
            "article",
            "stories",
            "news",
            "events",
        ]
        if any(p in href_lower or p in text_lower for p in skip_patterns):
            return False

        if self._is_career_content_page(href_lower, text_lower):
            return False

        # Check for job-related patterns in URL
        job_url_patterns = ["/job/", "/jobs/", "/position", "/opening", "/apply"]
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

    def _record_request_error(self, company_name: str, url: str, error: Exception) -> str:
        """Record a request failure for source health reporting."""
        message = f"{company_name} ({url}): {error}"
        self._run_request_errors.append(message)
        return message

    def _success_result(self, jobs: list[Job], candidate_count: int) -> ScrapeResult:
        """Create a healthy scrape result."""
        status = "success" if jobs else "empty"
        return ScrapeResult(
            jobs=jobs,
            candidate_count=candidate_count,
            status=status,
        )

    def _matches_criteria(self, job: Job) -> bool:
        """Check if a job matches our filtering criteria."""
        title_lower = job.title.lower()
        if not any(kw in title_lower for kw in ROLE_KEYWORDS):
            return False
        if self._is_career_content_page(job.url.lower(), title_lower):
            return False
        if not any(
            re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", title_lower)
            for kw in CAREER_ENTRY_LEVEL_KEYWORDS
        ):
            return False
        return matches_job_criteria(job, require_location=True)

    def _is_career_content_page(self, href_lower: str, text_lower: str) -> bool:
        """Reject career-site articles, stories, and other non-opening content."""
        return any(
            pattern in href_lower or pattern in text_lower
            for pattern in CAREER_CONTENT_EXCLUSIONS
        )
