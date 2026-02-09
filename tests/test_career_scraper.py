"""Tests for career scraper health signaling."""

import requests

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
        "A": ([], False, "err-a"),
        "B": ([], False, "err-b"),
        "C": ([], False, "err-c"),
        "D": ([], True, ""),
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
    monkeypatch.setattr(scraper, "_scrape_generic", lambda _company, _url: [])

    def fail_get(*_args, **_kwargs):
        raise requests.RequestException("api down")

    monkeypatch.setattr(scraper.session, "get", fail_get)

    jobs, success, error = scraper._scrape_company(
        "Acme",
        {"ats": "greenhouse", "url": "https://acme.example/jobs"},
    )
    assert jobs == []
    assert success is False
    assert "api down" in error
