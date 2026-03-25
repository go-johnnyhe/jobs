"""Tests for career scraper health signaling."""

import requests

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

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())

    result = scraper._scrape_company(
        "Google",
        {"ats": "internal", "url": "https://example.com/jobs"},
    )

    assert result.status == "parse_failure"
    assert result.candidate_count == 0


def test_generic_candidates_with_zero_matches_is_healthy(monkeypatch):
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

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(scraper, "_matches_criteria", lambda _job: False)

    result = scraper._scrape_company(
        "Google",
        {"ats": "internal", "url": "https://example.com/jobs"},
    )

    assert result.healthy is True
    assert result.status == "empty"
    assert result.candidate_count == 2
