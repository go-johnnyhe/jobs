"""Direct career page scraper for job listings."""

import concurrent.futures
from datetime import datetime, timezone
import json
import re
from typing import Optional
from xml.etree import ElementTree

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
            elif ats == "jibe":
                return self._scrape_jibe(
                    company_name,
                    api_url=config.get("api_url"),
                    category=config.get("search_category"),
                )
            elif ats == "eightfold":
                return self._scrape_eightfold(
                    company_name,
                    url,
                    domain=config.get("ats_id"),
                    search_queries=config.get("search_queries", []),
                    location=config.get("search_location", "United States"),
                )
            elif ats == "eightfold_apply":
                return self._scrape_eightfold_apply(
                    company_name,
                    url,
                    domain=config.get("ats_id"),
                    search_queries=config.get("search_queries", []),
                )
            elif ats == "salesforce":
                return self._scrape_salesforce(company_name, url)
            elif ats == "phenom":
                return self._scrape_phenom(
                    company_name,
                    url,
                    search_queries=config.get("search_queries", []),
                    country=config.get("search_country", "us"),
                    locale=config.get("search_locale", "en_us"),
                    posting_company_names=config.get("posting_company_names", []),
                    required_posting_terms=config.get("required_posting_terms", []),
                )
            elif ats == "meta":
                return self._scrape_meta(company_name, url)
            elif ats == "oracle_ce":
                return self._scrape_oracle_ce(
                    company_name,
                    url,
                    api_url=config.get("api_url"),
                    site_number=config.get("site_number"),
                )
            elif ats == "ibm_search":
                return self._scrape_ibm_search(
                    company_name,
                    query=config.get("search_query", ""),
                    required_term=config.get("required_posting_term", ""),
                )
            elif ats == "jane_street":
                return self._scrape_jane_street(company_name)
            elif ats == "two_sigma":
                return self._scrape_two_sigma(company_name, url)
            elif ats == "de_shaw":
                return self._scrape_de_shaw(company_name, url)
            elif ats == "etsy":
                return self._scrape_etsy(company_name, url)
            elif ats == "rippling":
                return self._scrape_rippling(
                    company_name,
                    index_name=config.get("ats_id"),
                    app_id=config.get("algolia_app_id"),
                    search_key=config.get("algolia_public_search_key"),
                )
            elif ats == "apple":
                return self._scrape_apple(
                    company_name,
                    search_queries=config.get("search_queries", []),
                )
            elif ats == "workable":
                return self._scrape_workable(
                    company_name,
                    account=config.get("ats_id"),
                )
            elif ats == "google":
                return self._scrape_google(company_name, url)
            elif ats == "structured_html":
                return self._scrape_structured_html(
                    company_name,
                    url,
                    parser_name=config.get("site_parser"),
                )
            elif ats == "atom":
                return self._scrape_atom(
                    company_name,
                    config.get("feed_url") or url,
                )
            elif ats == "miro":
                return self._scrape_miro(company_name, url)
            elif ats == "spotify":
                return self._scrape_spotify(company_name)
            elif ats == "optiver":
                return self._scrape_optiver(company_name)
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
                advertised_total = data.get("meta", {}).get("total")
                if not isinstance(postings, list):
                    raise ValueError("missing Greenhouse jobs")
                if (
                    advertised_total is not None
                    and len(postings) != int(advertised_total)
                ):
                    return ScrapeResult(
                        status="parse_failure",
                        candidate_count=len(postings),
                        error=(
                            f"{company_name} ({api_url}): parsed "
                            f"{len(postings)}/{advertised_total} advertised jobs"
                        ),
                    )

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

        url = (
            job_data.get("absolute_url")
            or f"https://boards.greenhouse.io/{board_id}/jobs/{job_id}"
        )

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
            if not isinstance(postings, list):
                raise ValueError("missing Ashby jobs")
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

    def _scrape_jibe(
        self,
        company_name: str,
        api_url: Optional[str],
        category: Optional[str],
    ) -> ScrapeResult:
        """Scrape a Jibe/iCIMS public jobs API with verified pagination."""
        if not api_url:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name}: missing Jibe jobs API URL",
            )

        postings = []
        page_number = 1
        total = None
        limit = 100
        try:
            while total is None or len(postings) < total:
                params = {"limit": limit, "page": page_number}
                if category:
                    params["categories"] = category
                response = self.session.get(api_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                page = data.get("jobs")
                if not isinstance(page, list):
                    raise ValueError("missing Jibe jobs")
                page_total = data.get("totalCount")
                if not isinstance(page_total, int):
                    raise ValueError("missing Jibe totalCount")
                if total is not None and page_total != total:
                    raise ValueError("Jibe totalCount changed during pagination")
                total = page_total
                if not page and len(postings) < total:
                    raise ValueError(
                        f"pagination ended at {len(postings)}/{total} jobs"
                    )
                postings.extend(page)
                page_number += 1
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                candidate_count=len(postings),
                error=f"{company_name} ({api_url}): invalid Jibe response ({e})",
            )

        if len(postings) != total:
            return ScrapeResult(
                status="parse_failure",
                candidate_count=len(postings),
                error=(
                    f"{company_name} ({api_url}): parsed "
                    f"{len(postings)}/{total} advertised jobs"
                ),
            )

        postings_by_url = {}
        for wrapper in postings:
            posting = wrapper.get("data") if isinstance(wrapper, dict) else None
            if not isinstance(posting, dict):
                return ScrapeResult(
                    status="parse_failure",
                    candidate_count=len(postings_by_url),
                    error=f"{company_name} ({api_url}): malformed Jibe job record",
                )
            title = str(posting.get("title") or "").strip()
            job_url = str(posting.get("apply_url") or "").strip()
            if not title or not job_url:
                return ScrapeResult(
                    status="parse_failure",
                    candidate_count=len(postings_by_url),
                    error=f"{company_name} ({api_url}): Jibe job missing title or URL",
                )
            postings_by_url[job_url] = posting

        if len(postings_by_url) != len(postings):
            return ScrapeResult(
                status="parse_failure",
                candidate_count=len(postings_by_url),
                error=f"{company_name} ({api_url}): duplicate Jibe pagination records",
            )

        jobs = []
        for job_url, posting in postings_by_url.items():
            title = str(posting["title"]).strip()
            job = Job(
                company=company_name,
                title=title,
                url=job_url,
                location=str(
                    posting.get("location_name")
                    or posting.get("full_location")
                    or ""
                ),
                source="career_page",
                date_posted=posting.get("posted_date"),
            )
            if self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings_by_url))

    def _scrape_eightfold(
        self,
        company_name: str,
        url: str,
        domain: Optional[str],
        search_queries: list[str],
        location: str,
    ) -> ScrapeResult:
        """Scrape an Eightfold PCS career site through its public search API."""
        if not domain:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): missing Eightfold domain",
            )
        if not search_queries:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): missing Eightfold search queries",
            )

        base_url = url.rstrip("/")
        api_url = f"{base_url}/api/pcsx/search"
        postings_by_id = {}
        try:
            for query in search_queries:
                start = 0
                while True:
                    response = self.session.get(
                        api_url,
                        params={
                            "domain": domain,
                            "query": query,
                            "location": location,
                            "start": start,
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                    data = response.json().get("data", {})
                    page = data.get("positions", [])
                    for posting in page:
                        posting_id = posting.get("id") or posting.get("atsJobId")
                        if posting_id:
                            postings_by_id[str(posting_id)] = posting

                    total = data.get("count", start + len(page))
                    start += len(page)
                    if not page or start >= total:
                        break
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid JSON response ({e})",
            )

        jobs = []
        for posting in postings_by_id.values():
            job = self._parse_eightfold_job(company_name, base_url, posting)
            if job and self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings_by_id))

    def _parse_eightfold_job(
        self,
        company_name: str,
        base_url: str,
        job_data: dict,
    ) -> Optional[Job]:
        """Parse a posting from an Eightfold PCS search response."""
        title = job_data.get("name", "")
        position_url = job_data.get("positionUrl", "")
        if not title or not position_url:
            return None

        locations = (
            job_data.get("standardizedLocations")
            or job_data.get("locations")
            or []
        )
        if isinstance(locations, str):
            location = locations
        else:
            location = "; ".join(str(item) for item in locations if item)

        date_posted = None
        posted_timestamp = job_data.get("postedTs")
        if posted_timestamp:
            try:
                date_posted = datetime.fromtimestamp(
                    int(posted_timestamp),
                    tz=timezone.utc,
                ).date().isoformat()
            except (TypeError, ValueError, OSError):
                pass

        return Job(
            company=company_name,
            title=title,
            url=self._normalize_url(position_url, base_url),
            location=location,
            source="career_page",
            date_posted=date_posted,
        )

    def _scrape_eightfold_apply(
        self,
        company_name: str,
        url: str,
        domain: Optional[str],
        search_queries: list[str],
    ) -> ScrapeResult:
        """Scrape the older Eightfold Apply v2 public jobs API."""
        if not domain or not search_queries:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): incomplete Eightfold Apply config",
            )

        base_url = url.rstrip("/")
        api_url = f"{base_url}/api/apply/v2/jobs"
        postings_by_id = {}
        try:
            for query in search_queries:
                start = 0
                while True:
                    response = self.session.get(
                        api_url,
                        params={
                            "domain": domain,
                            "query": query,
                            "start": start,
                            "num": 10,
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                    data = response.json()
                    page = data.get("positions", [])
                    for posting in page:
                        posting_id = posting.get("id") or posting.get("ats_job_id")
                        if posting_id:
                            postings_by_id[str(posting_id)] = posting

                    start += len(page)
                    total = data.get("count", start)
                    if not page or start >= total:
                        break
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid JSON response ({e})",
            )

        jobs = []
        for posting in postings_by_id.values():
            normalized = {
                "name": posting.get("name") or posting.get("posting_name"),
                "positionUrl": posting.get("canonicalPositionUrl"),
                "locations": posting.get("locations") or posting.get("location"),
                "postedTs": posting.get("t_create"),
            }
            job = self._parse_eightfold_job(company_name, base_url, normalized)
            if job and self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings_by_id))

    def _scrape_salesforce(self, company_name: str, url: str) -> ScrapeResult:
        """Scrape Salesforce's first-party static careers feed."""
        api_url = (
            "https://a.sfdcstatic.com/digital/xsf/careers/prod/jobs_1.json"
        )
        try:
            response = self.session.get(api_url, timeout=30)
            response.raise_for_status()
            postings = response.json().get("Report_Entry", [])
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid JSON response ({e})",
            )

        jobs = []
        for posting in postings:
            job = self._parse_salesforce_job(company_name, posting)
            if job and self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings))

    def _parse_salesforce_job(
        self,
        company_name: str,
        job_data: dict,
    ) -> Optional[Job]:
        """Parse one record from Salesforce's public careers feed."""
        title = job_data.get("Job_Posting_Title", "")
        url = job_data.get("External_Job_Posting_Site", "")
        location = job_data.get("Job_Requisition_Primary_Location", "")
        if not title or not url:
            return None
        return Job(
            company=company_name,
            title=title,
            url=url,
            location=location,
            source="career_page",
            date_posted=job_data.get("External_Job_Posting_Start_Date"),
        )

    def _scrape_phenom(
        self,
        company_name: str,
        url: str,
        search_queries: list[str],
        country: str,
        locale: str,
        posting_company_names: Optional[list[str]] = None,
        required_posting_terms: Optional[list[str]] = None,
    ) -> ScrapeResult:
        """Scrape a Phenom career site through its public widget API."""
        if not search_queries:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): missing Phenom search queries",
            )

        api_url = f"{url.rstrip('/')}/widgets"
        allowed_companies = {
            name.strip().casefold()
            for name in (posting_company_names or [])
            if name.strip()
        }
        required_terms = [
            term.strip().casefold()
            for term in (required_posting_terms or [])
            if term.strip()
        ]
        postings_by_id = {}
        try:
            for query in search_queries:
                offset = 0
                while True:
                    payload = {
                        "lang": locale,
                        "deviceType": "desktop",
                        "country": country,
                        "pageName": "search-results",
                        "ddoKey": "refineSearch",
                        "sortBy": "",
                        "subsearch": "",
                        "from": offset,
                        "jobs": True,
                        "counts": True,
                        "all_fields": ["category", "country", "state", "city"],
                        "size": 100,
                        "clearAll": False,
                        "jdsource": "facets",
                        "isSliderEnable": False,
                        "pageId": "page16",
                        "siteType": "external",
                        "keywords": query,
                        "global": True,
                        "selected_fields": {},
                    }
                    response = self.session.post(
                        api_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=30,
                    )
                    response.raise_for_status()
                    result = response.json().get("refineSearch")
                    if not isinstance(result, dict):
                        raise ValueError("missing refineSearch result")
                    data = result.get("data")
                    if not isinstance(data, dict):
                        raise ValueError("missing refineSearch data")
                    page = data.get("jobs")
                    if not isinstance(page, list):
                        raise ValueError("missing refineSearch jobs")
                    total = int(result.get("totalHits", len(page)))
                    if not page and offset < total:
                        raise ValueError(
                            f"empty page before {total} advertised jobs"
                        )
                    for posting in page:
                        posting_company = str(posting.get("companyName") or "")
                        if (
                            allowed_companies
                            and posting_company.strip().casefold() not in allowed_companies
                        ):
                            continue
                        posting_text = " ".join(
                            str(posting.get(field) or "")
                            for field in (
                                "title",
                                "descriptionTeaser",
                                "companyName",
                                "category",
                                "department",
                            )
                        ).casefold()
                        if required_terms and not all(
                            term in posting_text for term in required_terms
                        ):
                            continue
                        posting_id = (
                            posting.get("jobSeqNo")
                            or posting.get("jobId")
                            or posting.get("reqId")
                            or posting.get("applyUrl")
                        )
                        if posting_id:
                            postings_by_id[str(posting_id)] = posting

                    offset += len(page)
                    if not page or offset >= total:
                        break
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid JSON response ({e})",
            )

        jobs = []
        for posting in postings_by_id.values():
            job = self._parse_phenom_job(company_name, posting)
            if job and self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings_by_id))

    def _scrape_meta(self, company_name: str, url: str) -> ScrapeResult:
        """Scrape Meta's official university-grad results via public GraphQL."""
        api_url = "https://www.metacareers.com/api/graphql/"
        grad_team = "University Grad - Engineering, Tech & Design"
        try:
            page_response = self.session.get(url, timeout=30)
            page_response.raise_for_status()
            token_match = re.search(
                r'LSD",\[\],\{"token":"([^"]+)',
                page_response.text,
            )
            if not token_match:
                return ScrapeResult(
                    status="parse_failure",
                    error=f"{company_name} ({url}): missing GraphQL request token",
                )

            query_id = None
            soup = BeautifulSoup(page_response.text, "html.parser")
            for script in soup.find_all("script", src=True):
                script_url = self._normalize_url(script["src"], url)
                if "static.xx.fbcdn.net" not in script_url:
                    continue
                script_response = self.session.get(script_url, timeout=30)
                script_response.raise_for_status()
                query_match = re.search(
                    r"CareersJobSearchResultsDataQuery[^0-9]{0,500}(\d{12,})",
                    script_response.text,
                )
                if query_match:
                    query_id = query_match.group(1)
                    break
            if not query_id:
                return ScrapeResult(
                    status="parse_failure",
                    error=f"{company_name} ({url}): missing careers query ID",
                )

            lsd = token_match.group(1)
            variables = {
                "isLoggedIn": False,
                "search_input": {
                    "results_per_page": None,
                },
                "viewasUserID": None,
            }
            response = self.session.post(
                api_url,
                data={
                    "av": "0",
                    "__user": "0",
                    "__a": "1",
                    "lsd": lsd,
                    "fb_api_caller_class": "RelayModern",
                    "fb_api_req_friendly_name": (
                        "CareersJobSearchResultsDataQuery"
                    ),
                    "variables": json.dumps(variables, separators=(",", ":")),
                    "doc_id": query_id,
                },
                headers={"x-fb-lsd": lsd, "Referer": url},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid JSON response ({e})",
            )

        result = payload.get("data", {}).get("job_search_with_featured_jobs")
        if result is None:
            result = payload.get("data", {}).get("job_search_with_featured_jobs_v2")
        if not isinstance(result, dict) or not isinstance(result.get("all_jobs"), list):
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): missing complete job results",
            )

        postings = result["all_jobs"]
        if not postings:
            return ScrapeResult(
                status="parse_failure",
                error=(
                    f"{company_name} ({api_url}): broad careers query "
                    "returned no jobs"
                ),
            )
        jobs = []
        for posting in postings:
            posting_id = posting.get("id")
            title = str(posting.get("title") or "").strip()
            teams = posting.get("teams") or []
            locations = posting.get("locations") or []
            if not posting_id or not title or grad_team not in teams:
                continue
            job = Job(
                company=company_name,
                title=title,
                url=f"https://www.metacareers.com/jobs/{posting_id}/",
                location="; ".join(str(item) for item in locations if item),
                source="career_page",
            )
            if self._matches_criteria(job, explicit_entry_level=True):
                jobs.append(job)
        return self._success_result(jobs, len(postings))

    def _scrape_oracle_ce(
        self,
        company_name: str,
        url: str,
        api_url: Optional[str],
        site_number: Optional[str],
    ) -> ScrapeResult:
        """Scrape an Oracle Candidate Experience site's complete public feed."""
        if not api_url or not site_number:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): incomplete Oracle careers config",
            )

        postings_by_id = {}
        offset = 0
        total = None
        try:
            while total is None or offset < total:
                response = self.session.get(
                    api_url,
                    params={
                        "finder": (
                            f"findReqs;siteNumber={site_number},limit=200,"
                            f"offset={offset}"
                        ),
                        "expand": "requisitionList",
                        "onlyData": "true",
                    },
                    headers={
                        "Accept": "application/json",
                        "REST-Framework-Version": "4",
                    },
                    timeout=30,
                )
                response.raise_for_status()
                outer_items = response.json().get("items", [])
                if not outer_items:
                    raise ValueError("missing requisition result container")
                container = outer_items[0]
                page = container.get("requisitionList", {}).get("items", [])
                total = int(container.get("TotalJobsCount", 0))
                if not page and offset < total:
                    raise ValueError(f"empty page before {total} advertised jobs")
                for posting in page:
                    posting_id = posting.get("Id")
                    if posting_id:
                        postings_by_id[str(posting_id)] = posting
                offset += len(page)
                if not page:
                    break
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid job response ({e})",
            )

        # Oracle's advertised total counts result rows, which can contain the
        # same requisition ID more than once (for example, location variants).
        # Validate that every row was paged through, then deduplicate alerts by
        # requisition ID.
        if total is not None and offset < total:
            return ScrapeResult(
                status="parse_failure",
                candidate_count=len(postings_by_id),
                error=(
                    f"{company_name} ({api_url}): parsed "
                    f"{offset}/{total} advertised rows"
                ),
            )

        site_root = url.rstrip("/")
        if site_root.endswith("/jobs"):
            site_root = site_root[:-len("/jobs")]

        jobs = []
        for posting_id, posting in postings_by_id.items():
            title = str(posting.get("Title") or "").strip()
            if not title:
                continue
            job = Job(
                company=company_name,
                title=title,
                url=f"{site_root}/job/{posting_id}",
                location=str(posting.get("PrimaryLocation") or ""),
                source="career_page",
                date_posted=posting.get("PostedDate"),
            )
            if self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings_by_id))

    def _scrape_ibm_search(
        self,
        company_name: str,
        query: str,
        required_term: str,
    ) -> ScrapeResult:
        """Scrape IBM careers search for current HashiCorp-branded roles."""
        api_url = (
            "https://www-api.ibm.com/search/api/v1/ibmcom/"
            "appid/careers/responseFormat/json"
        )
        if not query or not required_term:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name}: incomplete IBM careers search config",
            )

        postings_by_id = {}
        total = None
        offset = 0
        try:
            while total is None or offset < total:
                response = self.session.get(
                    api_url,
                    params={
                        "scope": "careers2",
                        "rmdt": "ALL",
                        "appid": "careers",
                        "sortby": "",
                        "query": query,
                        "nr": 100,
                        "fr": offset,
                        "page": (offset // 100) + 1,
                        "lang": "en",
                        "cc": "us",
                    },
                    timeout=30,
                )
                response.raise_for_status()
                results = response.json().get("resultset", {}).get(
                    "searchresults", {}
                )
                page = results.get("searchresultlist", [])
                total = int(results.get("totalresults", 0))
                if not isinstance(page, list):
                    raise ValueError("missing search result list")
                if not page and offset < total:
                    raise ValueError(f"empty page before {total} advertised jobs")
                for posting in page:
                    posting_id = posting.get("id") or posting.get("url")
                    if posting_id:
                        postings_by_id[str(posting_id)] = posting
                offset += len(page)
                if not page:
                    break
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid job response ({e})",
            )

        required_lower = required_term.casefold()
        jobs = []
        branded_count = 0
        for posting in postings_by_id.values():
            attributes = {}
            for item in posting.get("docattributes") or []:
                if isinstance(item, dict):
                    attributes.update(item)
            posting_text = " ".join(
                str(value or "")
                for value in (
                    posting.get("title"),
                    posting.get("description"),
                    attributes.get("raw_body"),
                )
            ).casefold()
            if required_lower not in posting_text:
                continue
            branded_count += 1
            title = str(posting.get("title") or "").strip()
            posting_url = str(posting.get("url") or "").strip()
            if not title or not posting_url:
                continue
            location = str(
                attributes.get("field_keyword_19")
                or attributes.get("field_keyword_05")
                or ""
            )
            experience = str(attributes.get("field_keyword_18") or "").casefold()
            job = Job(
                company=company_name,
                title=title,
                url=posting_url,
                location=location,
                source="career_page",
                date_posted=(
                    attributes.get("effectivedate") or attributes.get("dcdate")
                ),
            )
            if self._matches_criteria(
                job,
                explicit_entry_level=experience == "entry level",
            ):
                jobs.append(job)
        return self._success_result(jobs, branded_count)

    def _scrape_jane_street(self, company_name: str) -> ScrapeResult:
        """Scrape Jane Street's complete first-party open-position feed."""
        jobs_url = "https://www.janestreet.com/jobs/main.json"
        open_ids_url = "https://www.janestreet.com/static/position-directories.json"
        try:
            jobs_response = self.session.get(jobs_url, timeout=30)
            jobs_response.raise_for_status()
            ids_response = self.session.get(open_ids_url, timeout=30)
            ids_response.raise_for_status()
            all_postings = jobs_response.json()
            open_ids = ids_response.json()
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, jobs_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({jobs_url}): invalid JSON response ({e})",
            )

        if not isinstance(all_postings, list) or not isinstance(open_ids, list):
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({jobs_url}): invalid feed structure",
            )
        postings_by_id = {
            str(posting.get("id")): posting
            for posting in all_postings
            if isinstance(posting, dict) and posting.get("id") is not None
        }
        unique_open_ids = {str(posting_id) for posting_id in open_ids}
        missing_ids = unique_open_ids - postings_by_id.keys()
        if missing_ids:
            return ScrapeResult(
                status="parse_failure",
                candidate_count=len(unique_open_ids) - len(missing_ids),
                error=(
                    f"{company_name} ({jobs_url}): "
                    f"{len(missing_ids)} open position(s) missing from feed"
                ),
            )

        city_names = {
            "NYC": "New York, NY, United States",
            "CHI": "Chicago, IL, United States",
            "PHL": "Philadelphia, PA, United States",
            "SF": "San Francisco, CA, United States",
            "ATX": "Austin, TX, United States",
            "LDN": "London, United Kingdom",
            "HKG": "Hong Kong",
            "AMS": "Amsterdam, Netherlands",
            "SGP": "Singapore",
            "MUM": "Mumbai, India",
            "SHA": "Shanghai, China",
            "NYC/HKG": "New York, NY, United States / Hong Kong",
        }
        jobs = []
        for posting_id in unique_open_ids:
            posting = postings_by_id[posting_id]
            if posting.get("availability") != "Full-Time: New Grad":
                continue
            title = str(posting.get("position") or "").strip()
            if not title:
                continue
            # Jane Street labels FPGA, Linux, and operations openings as
            # new-grad engineering too. Keep this tracker scoped to software.
            if not any(
                keyword in title.casefold()
                for keyword in (
                    "software",
                    "developer",
                    "swe",
                    "backend",
                    "frontend",
                    "full stack",
                    "fullstack",
                )
            ):
                continue
            city = str(posting.get("city") or "").strip()
            job = Job(
                company=company_name,
                title=title,
                url=(
                    "https://www.janestreet.com/join-jane-street/"
                    f"position/{posting_id}/"
                ),
                location=city_names.get(city, city),
                source="career_page",
            )
            if self._matches_criteria(job, explicit_entry_level=True):
                jobs.append(job)
        return self._success_result(jobs, len(unique_open_ids))

    def _scrape_two_sigma(self, company_name: str, url: str) -> ScrapeResult:
        """Scrape Two Sigma's complete first-party paginated job portal."""
        postings_by_url: dict[str, tuple[Job, bool]] = {}
        offset = 0
        page_size = 10
        visited_offsets = set()
        try:
            while offset not in visited_offsets:
                visited_offsets.add(offset)
                response = self.session.get(
                    url,
                    params={
                        "jobRecordsPerPage": page_size,
                        "jobOffset": offset,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.select("article.article--result")
                if not cards and offset == 0:
                    raise ValueError("no Two Sigma job records found")

                page_urls = set()
                for card in cards:
                    link = card.select_one(
                        "h3.article__header__text__title a[href*='/careers/JobDetail/']"
                    )
                    if not link:
                        raise ValueError("Two Sigma job is missing its detail link")
                    title = link.get_text(" ", strip=True)
                    job_url = self._normalize_url(link.get("href", ""), url)
                    location_node = card.select_one(
                        ".article__header__content__text > span"
                    )
                    if not title or not job_url:
                        raise ValueError("Two Sigma job is missing its title or URL")
                    if job_url in page_urls or job_url in postings_by_url:
                        raise ValueError("duplicate Two Sigma pagination record")
                    page_urls.add(job_url)
                    card_text = card.get_text(" ", strip=True).casefold()
                    postings_by_url[job_url] = (
                        Job(
                            company=company_name,
                            title=title,
                            url=job_url,
                            location=(
                                location_node.get_text(" ", strip=True)
                                if location_node
                                else ""
                            ),
                            source="career_page",
                        ),
                        "early careers" in card_text,
                    )

                next_link = next(
                    (
                        link for link in soup.find_all("a", href=True)
                        if link.get_text(" ", strip=True).casefold().startswith("next")
                    ),
                    None,
                )
                if not next_link:
                    break
                from urllib.parse import parse_qs, urlparse
                next_values = parse_qs(urlparse(next_link["href"]).query).get(
                    "jobOffset"
                )
                if not next_values:
                    raise ValueError("Two Sigma next page is missing jobOffset")
                offset = int(next_values[0])
            else:
                raise ValueError("Two Sigma pagination loop detected")
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                candidate_count=len(postings_by_url),
                error=f"{company_name} ({url}): invalid jobs response ({e})",
            )

        jobs = [
            job
            for job, is_early_career in postings_by_url.values()
            if self._matches_criteria(
                job,
                explicit_entry_level=is_early_career,
            )
        ]
        return self._success_result(jobs, len(postings_by_url))

    def _scrape_de_shaw(self, company_name: str, url: str) -> ScrapeResult:
        """Scrape D. E. Shaw's complete public jobs embedded in Next.js data."""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            data_node = soup.select_one("#__NEXT_DATA__")
            if not data_node or not data_node.string:
                raise ValueError("missing __NEXT_DATA__")
            page_props = json.loads(data_node.string)["props"]["pageProps"]
            if page_props.get("jobsFetchingError") is not False:
                raise ValueError("embedded jobs fetch failed")
            regular_jobs = page_props.get("regularJobs")
            internships = page_props.get("internships")
            if not isinstance(regular_jobs, list) or not isinstance(internships, list):
                raise ValueError("missing public job collections")
            public_postings = regular_jobs + internships
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, url, e),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): invalid embedded jobs data ({e})",
            )

        postings_by_id = {}
        for wrapper in public_postings:
            posting = wrapper.get("data") if isinstance(wrapper, dict) else None
            if not isinstance(posting, dict) or posting.get("id") is None:
                return ScrapeResult(
                    status="parse_failure",
                    candidate_count=len(postings_by_id),
                    error=f"{company_name} ({url}): malformed public job record",
                )
            postings_by_id[str(posting["id"])] = posting

        if len(postings_by_id) != len(public_postings) or not postings_by_id:
            return ScrapeResult(
                status="parse_failure",
                candidate_count=len(postings_by_id),
                error=f"{company_name} ({url}): duplicate or empty public job data",
            )

        jobs = []
        for posting in postings_by_id.values():
            title = str(posting.get("displayName") or "").strip()
            job_path = str(posting.get("jobUrl") or "").strip()
            metadata = posting.get("jobMetadata") or {}
            locations = metadata.get("jobLocations") or []
            location = "; ".join(
                str(item.get("name"))
                for item in locations
                if isinstance(item, dict) and item.get("name")
            )
            if not title or not job_path:
                return ScrapeResult(
                    status="parse_failure",
                    candidate_count=len(postings_by_id),
                    error=f"{company_name} ({url}): public job missing title or URL",
                )
            job = Job(
                company=company_name,
                title=title,
                url=self._normalize_url(f"careers/{job_path}", url),
                location=location,
                source="career_page",
                date_posted=posting.get("validFromDate"),
            )
            seeker_categories = {
                str(value).casefold()
                for value in (metadata.get("jobSeekerCategories") or [])
            }
            explicit_entry_level = bool(
                metadata.get("forRecentGraduates")
                or "student" in seeker_categories
            )
            if self._matches_criteria(
                job,
                explicit_entry_level=explicit_entry_level,
            ):
                jobs.append(job)
        return self._success_result(jobs, len(postings_by_id))

    def _scrape_etsy(self, company_name: str, url: str) -> ScrapeResult:
        """Scrape Etsy's complete first-party Clinch jobs search."""
        postings_by_url = {}
        page_number = 1
        total_pages = None
        try:
            while total_pages is None or page_number <= total_pages:
                response = self.session.get(
                    url,
                    params={"page": page_number},
                    timeout=30,
                )
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.select("article.job-search-results-card-col")
                if not cards:
                    raise ValueError(f"no Etsy records on page {page_number}")

                page_urls = set()
                for card in cards:
                    link = card.select_one("h3.job-search-results-card-title a[href]")
                    if not link:
                        raise ValueError("Etsy job is missing its detail link")
                    title = link.get_text(" ", strip=True)
                    job_url = self._normalize_url(link.get("href", ""), url)
                    location_node = card.select_one(".job-component-location")
                    workplace_node = card.select_one(".job-component-workplace-type")
                    location_parts = []
                    for node in (workplace_node, location_node):
                        value = node.get_text(" ", strip=True) if node else ""
                        if value and value not in location_parts:
                            location_parts.append(value)
                    if not title or not job_url:
                        raise ValueError("Etsy job is missing its title or URL")
                    if job_url in page_urls or job_url in postings_by_url:
                        raise ValueError("duplicate Etsy pagination record")
                    page_urls.add(job_url)
                    postings_by_url[job_url] = Job(
                        company=company_name,
                        title=title,
                        url=job_url,
                        location="; ".join(location_parts),
                        source="career_page",
                    )

                if total_pages is None:
                    from urllib.parse import parse_qs, urlparse
                    page_values = [page_number]
                    for link in soup.find_all("a", href=True):
                        values = parse_qs(urlparse(link["href"]).query).get("page")
                        if values and values[0].isdigit():
                            page_values.append(int(values[0]))
                    total_pages = max(page_values)
                page_number += 1
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                candidate_count=len(postings_by_url),
                error=f"{company_name} ({url}): invalid jobs response ({e})",
            )

        jobs = [
            job for job in postings_by_url.values() if self._matches_criteria(job)
        ]
        return self._success_result(jobs, len(postings_by_url))

    def _scrape_rippling(
        self,
        company_name: str,
        index_name: Optional[str],
        app_id: Optional[str],
        search_key: Optional[str],
    ) -> ScrapeResult:
        """Scrape Rippling's complete public Algolia careers index."""
        if not index_name or not app_id or not search_key:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name}: incomplete Algolia careers config",
            )
        api_url = f"https://{app_id}-dsn.algolia.net/1/indexes/{index_name}/query"
        headers = {
            "x-algolia-application-id": app_id,
            "x-algolia-api-key": search_key,
            "Content-Type": "application/json",
        }
        raw_postings = []
        page_number = 0
        total_hits = None
        total_pages = None
        try:
            while total_pages is None or page_number < total_pages:
                params = f"query=&hitsPerPage=1000&page={page_number}"
                response = self.session.post(
                    api_url,
                    json={"params": params},
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                page = data.get("hits")
                if not isinstance(page, list):
                    raise ValueError("missing Algolia hits")
                total_hits = int(data.get("nbHits", 0))
                total_pages = int(data.get("nbPages", 0))
                raw_postings.extend(page)
                page_number += 1
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid job response ({e})",
            )

        if total_hits is None or len(raw_postings) != total_hits:
            return ScrapeResult(
                status="parse_failure",
                candidate_count=len(raw_postings),
                error=(
                    f"{company_name} ({api_url}): parsed "
                    f"{len(raw_postings)}/{total_hits or 0} advertised records"
                ),
            )

        postings_by_id = {}
        locations_by_id: dict[str, set[str]] = {}
        for posting in raw_postings:
            posting_id = posting.get("jobId") or posting.get("objectID")
            if not posting_id:
                continue
            posting_id = str(posting_id)
            postings_by_id.setdefault(posting_id, posting)
            locations = locations_by_id.setdefault(posting_id, set())
            for location in posting.get("locationNames") or []:
                if location:
                    locations.add(str(location))
            for location in posting.get("locations") or []:
                if isinstance(location, dict) and location.get("name"):
                    locations.add(str(location["name"]))

        jobs = []
        for posting_id, posting in postings_by_id.items():
            title = str(posting.get("name") or "").strip()
            posting_url = str(posting.get("url") or "").strip()
            if not title or not posting_url:
                continue
            job = Job(
                company=company_name,
                title=title,
                url=posting_url,
                location="; ".join(sorted(locations_by_id[posting_id])),
                source="career_page",
            )
            if self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings_by_id))

    def _parse_phenom_job(
        self,
        company_name: str,
        job_data: dict,
    ) -> Optional[Job]:
        """Parse a Phenom refineSearch job record."""
        title = job_data.get("title", "")
        url = job_data.get("applyUrl", "")
        location = (
            job_data.get("cityStateCountry")
            or job_data.get("location")
            or job_data.get("address")
            or ""
        )
        if not title or not url:
            return None
        return Job(
            company=company_name,
            title=title,
            url=url,
            location=location,
            source="career_page",
            date_posted=job_data.get("postedDate"),
        )

    def _scrape_apple(
        self,
        company_name: str,
        search_queries: list[str],
    ) -> ScrapeResult:
        """Scrape targeted roles from Apple's CSRF-protected public search API."""
        if not search_queries:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name}: missing Apple search queries",
            )

        base_url = "https://jobs.apple.com"
        token_url = f"{base_url}/api/v1/CSRFToken"
        api_url = f"{base_url}/api/v1/search"
        postings_by_id = {}
        try:
            token_response = self.session.get(
                token_url,
                headers={"Accept": "application/json"},
                timeout=30,
            )
            token_response.raise_for_status()
            csrf_token = token_response.headers.get("X-Apple-CSRF-Token")
            if not csrf_token:
                return ScrapeResult(
                    status="parse_failure",
                    error=f"{company_name} ({token_url}): missing CSRF token",
                )

            for query in search_queries:
                page_number = 1
                while True:
                    payload = {
                        "query": "",
                        "filters": {"keywords": [query]},
                        "page": page_number,
                        "locale": "en-us",
                        "sort": "newest",
                        "format": {
                            "longDate": "MMMM D, YYYY",
                            "mediumDate": "MMM D, YYYY",
                        },
                    }
                    response = self.session.post(
                        api_url,
                        json=payload,
                        headers={
                            "Accept": "application/json",
                            "Content-Type": "application/json",
                            "locale": "en-us",
                            "browserLocale": "en-US",
                            "X-Apple-CSRF-Token": csrf_token,
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                    result = response.json().get("res", {})
                    page = result.get("searchResults", [])
                    for posting in page:
                        posting_id = posting.get("positionId") or posting.get("id")
                        if posting_id:
                            postings_by_id[str(posting_id)] = posting

                    fetched = page_number * 20
                    total = result.get("totalRecords", fetched)
                    if not page or fetched >= total:
                        break
                    page_number += 1
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid JSON response ({e})",
            )

        jobs = []
        for posting in postings_by_id.values():
            job = self._parse_apple_job(company_name, base_url, posting)
            if job and self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings_by_id))

    def _parse_apple_job(
        self,
        company_name: str,
        base_url: str,
        job_data: dict,
    ) -> Optional[Job]:
        """Parse a record from Apple's public careers search response."""
        title = job_data.get("postingTitle", "")
        position_id = job_data.get("positionId", "")
        slug = job_data.get("transformedPostingTitle", "")
        if not title or not position_id or not slug:
            return None

        location_parts = []
        for location in job_data.get("locations", []):
            if not isinstance(location, dict):
                continue
            display = location.get("name") or ", ".join(
                part
                for part in (
                    location.get("city"),
                    location.get("stateProvince"),
                    location.get("countryName"),
                )
                if part
            )
            if display:
                location_parts.append(display)

        team = job_data.get("team") or {}
        team_code = team.get("teamCode", "") if isinstance(team, dict) else ""
        path = f"/en-us/details/{position_id}/{slug}"
        if team_code:
            path = f"{path}?team={team_code}"
        return Job(
            company=company_name,
            title=title,
            url=self._normalize_url(path, base_url),
            location="; ".join(location_parts),
            source="career_page",
            date_posted=(
                job_data.get("postDateInGMT") or job_data.get("postingDate")
            ),
        )

    def _scrape_workable(
        self,
        company_name: str,
        account: Optional[str],
    ) -> ScrapeResult:
        """Scrape all jobs from Workable's public account widget feed."""
        if not account:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name}: missing Workable account identifier",
            )
        api_url = f"https://apply.workable.com/api/v1/widget/accounts/{account}"
        try:
            response = self.session.get(
                api_url,
                headers={"Accept": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            postings = response.json().get("jobs", [])
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid JSON response ({e})",
            )

        jobs = []
        for posting in postings:
            job = self._parse_workable_job(company_name, posting)
            if job and self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings))

    def _parse_workable_job(
        self,
        company_name: str,
        job_data: dict,
    ) -> Optional[Job]:
        """Parse a Workable public widget job record."""
        title = job_data.get("title", "")
        url = job_data.get("url") or job_data.get("shortlink") or ""
        if not title or not url:
            return None

        location_parts = [
            job_data.get("city"),
            job_data.get("state"),
            job_data.get("country"),
        ]
        location = ", ".join(part for part in location_parts if part)
        if job_data.get("telecommuting"):
            location = f"Remote - {location}" if location else "Remote"
        return Job(
            company=company_name,
            title=title,
            url=url,
            location=location,
            source="career_page",
            date_posted=job_data.get("published_on") or job_data.get("created_at"),
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

    def _scrape_google(self, company_name: str, url: str) -> ScrapeResult:
        """Scrape Google's server-rendered, early-career search pages."""
        jobs = []
        candidate_count = 0
        total = None
        page = 1
        detail_base = url.split("jobs/results", 1)[0]

        try:
            while True:
                response = self.session.get(
                    url,
                    params={"page": page},
                    timeout=30,
                )
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.select("li.lLd3Je")

                if total is None:
                    total_match = re.search(
                        r"Showing\s+\d+\s+to\s+\d+\s+of\s+([\d,]+)\s+rows",
                        soup.get_text(" ", strip=True),
                        re.IGNORECASE,
                    )
                    if not total_match:
                        return ScrapeResult(
                            status="parse_failure",
                            error=(
                                f"{company_name} ({url}): missing Google result "
                                "total; pagination completeness cannot be verified"
                            ),
                        )
                    total = int(total_match.group(1).replace(",", ""))

                if not cards and candidate_count < total:
                    return ScrapeResult(
                        status="parse_failure",
                        error=(
                            f"{company_name} ({url}): Google pagination ended at "
                            f"{candidate_count}/{total} jobs"
                        ),
                    )

                for card in cards:
                    title_node = card.select_one("h3.QJPWVe")
                    link = card.select_one("a[href*='jobs/results/']")
                    if not title_node or not link:
                        continue
                    locations = []
                    for node in card.select(".wVoYLb span.r0wTof"):
                        location = node.get_text(" ", strip=True)
                        if location and location not in locations:
                            locations.append(location)
                    job = Job(
                        company=company_name,
                        title=title_node.get_text(" ", strip=True),
                        url=self._normalize_url(link.get("href", ""), detail_base),
                        location="; ".join(locations),
                        source="career_page",
                    )
                    if self._matches_criteria(job):
                        jobs.append(job)

                candidate_count += len(cards)
                if candidate_count >= total:
                    break
                page += 1
                if page > 100:
                    return ScrapeResult(
                        status="parse_failure",
                        error=f"{company_name} ({url}): excessive Google pagination",
                    )
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, url, e),
            )

        return self._success_result(jobs, candidate_count)

    def _scrape_structured_html(
        self,
        company_name: str,
        url: str,
        parser_name: Optional[str],
    ) -> ScrapeResult:
        """Scrape complete first-party, server-rendered job lists."""
        parsers = {
            "stripe": self._parse_stripe_html,
            "confluent": self._parse_confluent_html,
            "railway": self._parse_railway_html,
            "plaid": self._parse_plaid_html,
            "retool": self._parse_retool_html,
            "shopify": self._parse_shopify_html,
        }
        parser = parsers.get(parser_name or "")
        if not parser:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): unknown structured HTML parser",
            )

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            postings, expected_total = parser(company_name, soup, url)
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, url, e),
            )

        postings_by_url = {job.url: job for job in postings if job.url}
        candidate_count = len(postings_by_url)
        if candidate_count == 0:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): no structured job records found",
            )
        if expected_total is not None and candidate_count != expected_total:
            return ScrapeResult(
                status="parse_failure",
                candidate_count=candidate_count,
                error=(
                    f"{company_name} ({url}): parsed {candidate_count}/"
                    f"{expected_total} advertised jobs"
                ),
            )

        jobs = [
            job for job in postings_by_url.values() if self._matches_criteria(job)
        ]
        return self._success_result(jobs, candidate_count)

    def _parse_stripe_html(self, company_name, soup, url):
        jobs = []
        for row in soup.select("tr.TableRow"):
            link = row.select_one("a.JobsListings__link[href]")
            location = row.select_one(".JobsListings__locationDisplayName")
            if link and location:
                jobs.append(Job(
                    company=company_name,
                    title=link.get_text(" ", strip=True),
                    url=self._normalize_url(link.get("href", ""), url),
                    location=location.get_text(" ", strip=True),
                    source="career_page",
                ))
        return jobs, None

    def _parse_confluent_html(self, company_name, soup, url):
        jobs = []
        for link in soup.select("a[href*='/jobs/job/']"):
            card = link.parent
            location = card.find("p", recursive=False) if card else None
            if location:
                jobs.append(Job(
                    company=company_name,
                    title=link.get_text(" ", strip=True),
                    url=self._normalize_url(link.get("href", ""), url),
                    location=location.get_text(" ", strip=True),
                    source="career_page",
                ))
        return jobs, None

    def _parse_railway_html(self, company_name, soup, url):
        jobs = []
        for link in soup.select("a[href^='/careers/']"):
            paragraphs = link.find_all("p", recursive=False)
            if len(paragraphs) == 2:
                jobs.append(Job(
                    company=company_name,
                    title=paragraphs[0].get_text(" ", strip=True),
                    url=self._normalize_url(link.get("href", ""), url),
                    location=paragraphs[1].get_text(" ", strip=True),
                    source="career_page",
                ))
        return jobs, None

    def _parse_plaid_html(self, company_name, soup, url):
        jobs = []
        for link in soup.select("a[href*='/careers/openings/']"):
            card = link.parent
            paragraphs = card.find_all("p") if card else []
            if len(paragraphs) >= 2:
                jobs.append(Job(
                    company=company_name,
                    title=paragraphs[1].get_text(" ", strip=True),
                    url=self._normalize_url(link.get("href", ""), url),
                    location=paragraphs[0].get_text(" ", strip=True),
                    source="career_page",
                ))
        return jobs, None

    def _parse_retool_html(self, company_name, soup, url):
        jobs = []
        embedded_total = None
        for link in soup.select("a[href^='/careers/'][href*='--']"):
            paragraphs = link.find_all("p", recursive=False)
            if len(paragraphs) == 2:
                jobs.append(Job(
                    company=company_name,
                    title=paragraphs[0].get_text(" ", strip=True),
                    url=self._normalize_url(link.get("href", ""), url),
                    location=paragraphs[1].get_text(" ", strip=True),
                    source="career_page",
                ))

        # Next.js streams the authoritative Gem job records as escaped JSON.
        # Plain HTTP clients receive this payload even when the link cards are
        # rendered only after hydration.
        if not jobs:
            for script in soup.find_all("script"):
                script_text = script.string or ""
                if "jobs\\\":[" not in script_text:
                    continue
                push_match = re.search(
                    r"self\.__next_f\.push\((.*)\)\s*;?\s*$",
                    script_text,
                    re.DOTALL,
                )
                if not push_match:
                    continue
                try:
                    payload = json.loads(push_match.group(1))
                except (TypeError, ValueError):
                    continue
                if not isinstance(payload, list) or len(payload) < 2:
                    continue
                decoded = payload[1]
                if not isinstance(decoded, str):
                    continue
                jobs_match = re.search(r'"jobs":(\[.*?\])', decoded, re.DOTALL)
                if not jobs_match:
                    continue
                try:
                    records = json.loads(jobs_match.group(1))
                except (TypeError, ValueError):
                    continue
                embedded_total = len(records)
                for record in records:
                    title = record.get("title", "")
                    job_url = record.get("link", "")
                    if title and job_url:
                        jobs.append(Job(
                            company=company_name,
                            title=title.strip(),
                            url=job_url,
                            location=record.get("location", ""),
                            source="career_page",
                            date_posted=record.get("updatedAt"),
                        ))
                break

        total_match = re.search(
            r"\b(\d+)\s+roles\s+across\b",
            soup.get_text(" ", strip=True),
            re.IGNORECASE,
        )
        expected_total = (
            embedded_total
            if embedded_total is not None
            else int(total_match.group(1)) if total_match else None
        )
        return jobs, expected_total

    def _parse_shopify_html(self, company_name, soup, url):
        jobs = []
        for link in soup.select("a[href^='/careers/']"):
            href = link.get("href", "")
            if not re.search(r"_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", href):
                continue
            title = link.find("h4")
            location = link.select_one(".location")
            if title and location:
                jobs.append(Job(
                    company=company_name,
                    title=title.get_text(" ", strip=True),
                    url=self._normalize_url(href, url),
                    location=location.get_text(" ", strip=True),
                    source="career_page",
                ))
        return jobs, None

    def _scrape_atom(self, company_name: str, feed_url: str) -> ScrapeResult:
        """Scrape a company's authoritative Atom job feed."""
        try:
            response = self.session.get(feed_url, timeout=30)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, feed_url, e),
            )
        except ElementTree.ParseError as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({feed_url}): invalid Atom feed ({e})",
            )

        if root.tag.rsplit("}", 1)[-1] != "feed":
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({feed_url}): unexpected feed root",
            )

        entries = [node for node in root if node.tag.rsplit("}", 1)[-1] == "entry"]
        jobs = []
        for entry in entries:
            children = {child.tag.rsplit("}", 1)[-1]: child for child in entry}
            title_node = children.get("title")
            link_node = children.get("link")
            location_node = children.get("location")
            title = title_node.text.strip() if title_node is not None and title_node.text else ""
            job_url = link_node.get("href", "") if link_node is not None else ""
            location = (
                location_node.text.strip()
                if location_node is not None and location_node.text
                else ""
            )
            if title and job_url:
                job = Job(
                    company=company_name,
                    title=title,
                    url=job_url,
                    location=location,
                    source="career_page",
                )
                if self._matches_criteria(job):
                    jobs.append(job)
        return self._success_result(jobs, len(entries))

    def _scrape_miro(self, company_name: str, url: str) -> ScrapeResult:
        """Scrape Miro's complete Greenhouse data embedded in Next.js props."""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            data_node = soup.select_one("#__NEXT_DATA__")
            if not data_node or not data_node.string:
                raise ValueError("missing __NEXT_DATA__")
            postings = json.loads(data_node.string)["props"]["pageProps"]["jobs"]
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, url, e),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): invalid embedded jobs data ({e})",
            )

        jobs = []
        for posting in postings:
            job_id = posting.get("id")
            title = posting.get("title", "")
            if not job_id or not title:
                continue
            job = Job(
                company=company_name,
                title=title,
                url=f"https://miro.com/careers/vacancy/{job_id}?gh_jid={job_id}",
                location=posting.get("location", ""),
                source="career_page",
            )
            if self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings))

    def _scrape_spotify(self, company_name: str) -> ScrapeResult:
        """Scrape Spotify's first-party WordPress jobs API."""
        api_url = "https://api.lifeatspotify.com/wp-json/animal/v1/job/search"
        try:
            response = self.session.get(
                api_url,
                params={"c": "engineering"},
                timeout=30,
            )
            response.raise_for_status()
            postings = response.json().get("result", [])
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid JSON response ({e})",
            )

        jobs = []
        for posting in postings:
            job_id = posting.get("id", "")
            title = posting.get("text", "")
            locations = posting.get("locations") or []
            location = "; ".join(
                item.get("location", "")
                for item in locations
                if isinstance(item, dict) and item.get("location")
            )
            if title and job_id:
                job = Job(
                    company=company_name,
                    title=title,
                    url=f"https://www.lifeatspotify.com/jobs/{job_id}",
                    location=location,
                    source="career_page",
                )
                if self._matches_criteria(job):
                    jobs.append(job)
        return self._success_result(jobs, len(postings))

    def _scrape_optiver(self, company_name: str) -> ScrapeResult:
        """Scrape Optiver's first-party jobs API with verified pagination."""
        api_url = "https://www.optiver.com/en/api/v1/jobs"
        postings = []
        offset = 0
        size = 100
        total = None
        try:
            while total is None or offset < total:
                response = self.session.get(
                    api_url,
                    params={"from": offset, "size": size},
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                page = data.get("items", [])
                total = data.get("totalCount")
                if not isinstance(total, int):
                    raise ValueError("missing totalCount")
                if not page and offset < total:
                    raise ValueError(f"pagination ended at {offset}/{total}")
                postings.extend(page)
                offset += len(page)
        except requests.RequestException as e:
            return ScrapeResult(
                status="request_failure",
                error=self._record_request_error(company_name, api_url, e),
            )
        except (TypeError, ValueError) as e:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({api_url}): invalid jobs response ({e})",
            )

        jobs = []
        for posting in postings:
            title = posting.get("title", "")
            href = posting.get("href", "")
            if title and href:
                job = Job(
                    company=company_name,
                    title=title,
                    url=self._normalize_url(href, "https://www.optiver.com"),
                    location=posting.get("location", ""),
                    source="career_page",
                )
                if self._matches_criteria(job):
                    jobs.append(job)
        return self._success_result(jobs, len(postings))

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
        postings_by_url = {}
        records_seen = 0

        tenant_site = self._extract_workday_tenant_site(url)
        if not tenant_site:
            return ScrapeResult(
                status="parse_failure",
                error=f"{company_name} ({url}): unable to extract Workday tenant/site",
            )

        tenant, site, base = tenant_site
        api_url = f"{base}/wday/cxs/{tenant}/{site}/jobs"
        detail_base = url.split("?", 1)[0].rstrip("/") + "/"

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
            page_total = data.get("total")
            if not isinstance(page_total, int):
                return ScrapeResult(
                    status="parse_failure",
                    candidate_count=len(postings_by_url),
                    error=f"{company_name} ({api_url}): missing Workday total",
                )
            # Some Workday tenants report the total only on the first page and
            # return zero afterward. Keep the established total in that case,
            # but honor later positive changes while the feed is being scanned.
            if total is None or page_total > 0:
                total = page_total
            if not postings:
                if records_seen < total:
                    return ScrapeResult(
                        status="parse_failure",
                        candidate_count=len(postings_by_url),
                        error=(
                            f"{company_name} ({api_url}): Workday pagination "
                            f"ended at {records_seen}/{total} jobs"
                        ),
                    )
                break

            for posting in postings:
                posting_url = (
                    posting.get("externalPath")
                    or posting.get("externalUrl")
                    or ""
                )
                if not posting_url:
                    return ScrapeResult(
                        status="parse_failure",
                        candidate_count=len(postings_by_url),
                        error=f"{company_name} ({api_url}): Workday job missing URL",
                    )
                postings_by_url[str(posting_url)] = posting

            offset += len(postings)
            records_seen += len(postings)
            if records_seen >= total:
                break

        if len(postings_by_url) != total:
            return ScrapeResult(
                status="parse_failure",
                candidate_count=len(postings_by_url),
                error=(
                    f"{company_name} ({api_url}): parsed "
                    f"{len(postings_by_url)}/{total} unique Workday jobs"
                ),
            )

        jobs = []
        for posting in postings_by_url.values():
            job = self._parse_workday_job(company_name, posting, detail_base)
            if not job:
                return ScrapeResult(
                    status="parse_failure",
                    candidate_count=len(postings_by_url),
                    error=f"{company_name} ({api_url}): malformed Workday job record",
                )
            if self._matches_criteria(job):
                jobs.append(job)
        return self._success_result(jobs, len(postings_by_url))

    def _extract_workday_tenant_site(self, url: str) -> Optional[tuple[str, str, str]]:
        """Extract Workday tenant and site from a Workday jobs URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.netloc
            path_parts = [p for p in parsed.path.split("/") if p]
            if host.endswith(".myworkdayjobs.com"):
                # Host is usually like "{tenant}.wd5.myworkdayjobs.com".
                tenant = host.split(".")[0]
                if not path_parts:
                    return None
                site = path_parts[0]
            elif host.endswith(".myworkdaysite.com"):
                # Newer Workday sites use /recruiting/{tenant}/{site}.
                if len(path_parts) < 3 or path_parts[0] != "recruiting":
                    return None
                tenant, site = path_parts[1:3]
            else:
                return None
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
        if url_path.startswith(("https://", "http://")):
            url = url_path
        else:
            url = urljoin(base_url, url_path.lstrip("/"))

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

    def _matches_criteria(
        self,
        job: Job,
        explicit_entry_level: bool = False,
    ) -> bool:
        """Check if a job matches our filtering criteria."""
        title_lower = job.title.lower()
        if not any(kw in title_lower for kw in ROLE_KEYWORDS):
            return False
        if self._is_career_content_page(job.url.lower(), title_lower):
            return False
        if not explicit_entry_level and not any(
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
