"""Tests for career scraper health signaling."""

import requests

from models import Job
from models import ScrapeResult
from sources import career_scraper as cs


def test_health_requires_min_success_ratio_and_count(monkeypatch):
    scraper = cs.CareerScraper()

    monkeypatch.setattr(
        cs,
        "COMPANIES",
        {
            "A": {"url": "https://a.example", "ats": "internal"},
            "B": {"url": "https://b.example", "ats": "internal"},
            "C": {"url": "https://c.example", "ats": "internal"},
            "D": {"url": "https://d.example", "ats": "internal"},
        },
    )
    monkeypatch.setattr(cs, "CAREERS_MIN_HEALTHY_SUCCESS_RATE", 0.5)
    monkeypatch.setattr(cs, "CAREERS_MIN_HEALTHY_SUCCESSES", 2)

    outcomes = {
        "A": ScrapeResult(status="request_failure", error="err-a"),
        "B": ScrapeResult(status="request_failure", error="err-b"),
        "C": ScrapeResult(status="request_failure", error="err-c"),
        "D": ScrapeResult(status="empty", candidate_count=2),
    }

    def fake_scrape_company(company_name, config):
        return outcomes[company_name]

    monkeypatch.setattr(scraper, "_scrape_company", fake_scrape_company)

    jobs, healthy, error_summary = scraper.fetch_jobs_with_status()
    assert jobs == []
    assert healthy is False
    assert "err-a" in error_summary


def test_greenhouse_api_failure_kept_when_fallback_empty(monkeypatch):
    scraper = cs.CareerScraper()

    monkeypatch.setattr(scraper, "_extract_greenhouse_board", lambda _url: "acme")
    monkeypatch.setattr(
        scraper,
        "_scrape_generic",
        lambda _company, _url: ScrapeResult(
            status="parse_failure",
            error="fallback empty",
        ),
    )

    def fail_get(*_args, **_kwargs):
        raise requests.RequestException("api down")

    monkeypatch.setattr(scraper.session, "get", fail_get)

    result = scraper._scrape_company(
        "Acme",
        {"ats": "greenhouse", "url": "https://acme.example/jobs"},
    )
    assert result.jobs == []
    assert result.healthy is False
    assert "api down" in result.error


def test_generic_zero_candidates_is_parse_failure(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        text = "<html><body><a href='/about'>About</a></body></html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        scraper.generic_session,
        "get",
        lambda *_args, **_kwargs: Response(),
    )

    result = scraper._scrape_company(
        "Google",
        {"ats": "internal", "url": "https://example.com/jobs"},
    )

    assert result.status == "parse_failure"
    assert result.candidate_count == 0


def test_generic_candidates_with_zero_matches_is_degraded(monkeypatch):
    scraper = cs.CareerScraper()

    html = """
    <html><body>
      <a href="/jobs/1">Software Engineer</a>
      <a href="/jobs/2">Backend Engineer</a>
    </body></html>
    """

    class Response:
        text = html

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        scraper.generic_session,
        "get",
        lambda *_args, **_kwargs: Response(),
    )
    monkeypatch.setattr(scraper, "_matches_criteria", lambda _job: False)

    result = scraper._scrape_company(
        "Google",
        {"ats": "internal", "url": "https://example.com/jobs"},
    )

    assert result.healthy is False
    assert result.status == "degraded_empty"
    assert result.candidate_count == 2


def test_explicit_greenhouse_id_skips_page_discovery(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"jobs": []}

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(
        scraper,
        "_extract_greenhouse_board",
        lambda _url: (_ for _ in ()).throw(AssertionError("should not discover")),
    )

    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "greenhouse",
            "ats_id": "acme",
            "url": "https://acme.example/careers",
        },
    )
    assert result.healthy is True


def test_ashby_parser_and_filter(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jobs": [
                    {
                        "title": "Software Engineer, New Grad",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                        "location": "Seattle, WA",
                        "publishedAt": "2026-07-01T00:00:00Z",
                    }
                ]
            }

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "ashby",
            "ats_id": "acme",
            "url": "https://acme.example/careers",
        },
    )
    assert result.healthy is True
    assert result.candidate_count == 1
    assert result.jobs[0].location == "Seattle, WA"
    assert result.jobs[0].date_posted == "2026-07-01T00:00:00Z"


def test_amazon_public_search_adapter(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jobs": [
                    {
                        "id": "1",
                        "title": "Software Development Engineer - 2026",
                        "job_path": "/en/jobs/1/software-development-engineer-2026",
                        "normalized_location": "Seattle, Washington, USA",
                        "posted_date": "July 1, 2026",
                    }
                ]
            }

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Amazon",
        {
            "ats": "amazon",
            "url": "https://www.amazon.jobs/en/search",
            "search_queries": ["Software Development Engineer 2026"],
        },
    )
    assert result.healthy is True
    assert result.candidate_count == 1
    assert result.jobs[0].url.startswith("https://www.amazon.jobs/en/jobs/1/")


def test_smartrecruiters_adapter_paginates_and_parses(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "totalFound": 1,
                "content": [
                    {
                        "id": "1",
                        "name": "Associate Software Engineer",
                        "location": {
                            "fullLocation": "San Francisco, California, United States"
                        },
                        "releasedDate": "2026-07-01T00:00:00Z",
                    }
                ],
            }

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "ServiceNow",
        {
            "ats": "smartrecruiters",
            "ats_id": "ServiceNow",
            "url": "https://careers.servicenow.com/jobs",
        },
    )
    assert result.healthy is True
    assert result.candidate_count == 1
    assert result.jobs[0].url == "https://jobs.smartrecruiters.com/ServiceNow/1"


def test_generic_rejects_career_article_links():
    scraper = cs.CareerScraper()

    assert scraper._looks_like_job_link(
        "/en/careers/blog/early-in-career-as-a-software-engineer",
        "Early-in-Career as a Software Engineer at Palo Alto Networks in India",
    ) is False


def test_career_criteria_requires_entry_level_signal():
    scraper = cs.CareerScraper()
    job = Job(
        company="DoorDash",
        title="Software Engineer, Data Platform (All Teams)",
        url="https://boards.greenhouse.io/doordashusa/jobs/1",
        location="Seattle, WA",
        source="career_page",
    )

    assert scraper._matches_criteria(job) is False


def test_career_criteria_allows_new_grad_swe():
    scraper = cs.CareerScraper()
    job = Job(
        company="Stripe",
        title="Software Engineer - New Grad",
        url="https://stripe.com/jobs/1",
        location="Seattle, WA",
        source="career_page",
    )

    assert scraper._matches_criteria(job) is True


def test_career_criteria_rejects_intern_substring():
    scraper = cs.CareerScraper()
    job = Job(
        company="Notion",
        title="Software Engineer Intern (Fall 2026)",
        url="https://jobs.ashbyhq.com/notion/1",
        location="San Francisco, CA",
        source="career_page",
    )

    assert scraper._matches_criteria(job) is False


def test_career_criteria_rejects_principal_and_systems_roles():
    scraper = cs.CareerScraper()
    principal = Job(
        company="DoorDash",
        title="Principle Software Engineer - Ads",
        url="https://boards.greenhouse.io/doordashusa/jobs/1",
        location="San Francisco, CA",
        source="career_page",
    )
    systems = Job(
        company="Palo Alto Networks",
        title="My First Year as an Associate Systems Engineer",
        url="https://jobs.paloaltonetworks.com/en/blog/my-first-year",
        location="",
        source="career_page",
    )

    assert scraper._matches_criteria(principal) is False
    assert scraper._matches_criteria(systems) is False
