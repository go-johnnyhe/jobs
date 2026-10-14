"""Tests for description enrichment and career-source screening."""

import requests

import config
from enrichment import enrich_descriptions, extract_description
from models import Job
from sources import career_scraper as cs


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.headers = {}
        self.requested = []

    def get(self, url, **_kwargs):
        self.requested.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def job(n, description_url="", description=""):
    return Job(
        company="Acme",
        title=f"Software Engineer {n}",
        url=f"https://boards.greenhouse.io/acme/jobs/{n}",
        location="Seattle, WA",
        source="career_page",
        description=description,
        description_url=description_url,
    )


def test_extract_description_formats():
    assert extract_description({"content": "&lt;p&gt;We sponsor visas.&lt;/p&gt;"}) == "We sponsor visas."
    assert extract_description(
        {"jobPostingInfo": {"jobDescription": "<p>Must be a <b>U.S. citizen</b>.</p>"}}
    ) == "Must be a U.S. citizen ."
    assert extract_description({"descriptionPlain": "plain"}) == "plain"
    assert extract_description({}) == ""
    assert extract_description(["not", "a", "dict"]) == ""


def test_enrich_fetches_only_missing_descriptions_up_to_limit():
    jobs = [
        job(1, "https://api.example/1"),
        job(2, "https://api.example/2"),
        job(3, "https://api.example/3", description="already have it"),
        job(4),
        job(5, "https://api.example/5"),
    ]
    session = FakeSession({
        "https://api.example/1": FakeResponse({"content": "&lt;p&gt;We do not sponsor visas.&lt;/p&gt;"}),
        "https://api.example/2": FakeResponse(status=404),
        "https://api.example/5": FakeResponse({"content": "unused"}),
    })
    counts = enrich_descriptions(jobs, max_fetches=2, session=session, workers=2)

    assert counts == {"candidates": 3, "fetched": 1, "failed": 1, "skipped": 1}
    assert sorted(session.requested) == ["https://api.example/1", "https://api.example/2"]
    assert jobs[0].description == "We do not sponsor visas."
    assert jobs[1].description == ""
    assert jobs[1].screening_notes == ["description unavailable: HTTP 404"]
    assert jobs[2].description == "already have it"
    assert jobs[4].description == ""


def test_enrich_handles_network_errors_and_bad_json():
    jobs = [job(1, "https://api.example/1"), job(2, "https://api.example/2")]
    session = FakeSession({
        "https://api.example/1": requests.ConnectionError("reset"),
        "https://api.example/2": FakeResponse(ValueError("not json")),
    })
    counts = enrich_descriptions(jobs, max_fetches=10, session=session)
    assert counts["failed"] == 2
    assert all(j.screening_notes[0].startswith("description unavailable") for j in jobs)


def test_enrich_with_no_candidates_makes_no_requests():
    session = FakeSession({})
    assert enrich_descriptions([job(1)], max_fetches=5, session=session)["candidates"] == 0
    assert session.requested == []


def test_greenhouse_jobs_carry_description_url_and_posted_date():
    scraper = cs.CareerScraper()
    parsed = scraper._parse_greenhouse_job("Acme", {
        "id": 123,
        "title": "Software Engineer, New Grad",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
        "location": {"name": "Seattle, WA"},
        "first_published": "2026-10-10T09:00:00-04:00",
    }, "acme")
    assert parsed.description_url == "https://boards-api.greenhouse.io/v1/boards/acme/jobs/123"
    assert parsed.date_posted == "2026-10-10T09:00:00-04:00"


def test_lever_description_is_screened_at_source(monkeypatch):
    scraper = cs.CareerScraper()
    postings = [
        {
            "text": "Software Engineer, New Grad",
            "hostedUrl": "https://jobs.lever.co/acme/aaaaaaaa-0000-0000-0000-000000000001",
            "categories": {"location": "Seattle, WA"},
            "descriptionPlain": "Build things.",
            "lists": [{"text": "Requirements", "content": "<li>We are unable to sponsor visas.</li>"}],
            "createdAt": 1760400000000,
        },
        {
            "text": "Software Engineer I",
            "hostedUrl": "https://jobs.lever.co/acme/aaaaaaaa-0000-0000-0000-000000000002",
            "categories": {"location": "Seattle, WA"},
            "descriptionPlain": "We sponsor H-1B visas. 2+ years of experience.",
        },
    ]
    monkeypatch.setattr(scraper.session, "get", lambda *_a, **_k: FakeResponse(postings))
    result = scraper._scrape_company("Acme", {"ats": "lever", "url": "https://jobs.lever.co/acme"})

    assert [j.title for j in result.jobs] == ["Software Engineer I"]
    kept = result.jobs[0]
    assert kept.sponsorship == "yes"
    assert kept.seniority_flag == "borderline"
    assert dict(scraper.screen_counts) == {"no_sponsorship": 1}


def test_lever_posted_date_from_created_at():
    scraper = cs.CareerScraper()
    parsed = scraper._parse_lever_job("Acme", {
        "text": "SWE", "hostedUrl": "https://jobs.lever.co/acme/x", "createdAt": 1760400000000,
    })
    assert parsed.date_posted == "2025-10-14"


def test_ashby_description_is_screened_at_source(monkeypatch):
    scraper = cs.CareerScraper()
    payload = {"jobs": [
        {
            "title": "Software Engineer, New Grad",
            "jobUrl": "https://jobs.ashbyhq.com/acme/1",
            "location": "Seattle, WA",
            "descriptionHtml": "<p>Active TS/SCI clearance required.</p>",
        },
        {
            "title": "New Grad Software Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/acme/2",
            "location": "Seattle, WA",
            "descriptionPlain": "Visa sponsorship is available.",
            "publishedAt": "2026-10-01T00:00:00Z",
        },
    ]}
    monkeypatch.setattr(scraper.session, "get", lambda *_a, **_k: FakeResponse(payload))
    result = scraper._scrape_company("Acme", {"ats": "ashby", "url": "https://jobs.ashbyhq.com/acme"})
    assert [j.url for j in result.jobs] == ["https://jobs.ashbyhq.com/acme/2"]
    assert result.jobs[0].sponsorship == "yes"
    assert result.jobs[0].date_posted == "2026-10-01T00:00:00Z"
    assert dict(scraper.screen_counts) == {"clearance_required": 1}


def test_workday_search_queries_are_merged_and_deduplicated(monkeypatch):
    scraper = cs.CareerScraper()
    feeds = {
        "software": [
            {"title": "Software Engineer, New Grad", "externalPath": "/job/Bellevue/SWE_R1",
             "locationsText": "Bellevue, WA", "postedOn": "Posted Today"},
            {"title": "Associate Software Developer", "externalPath": "/job/Bellevue/Dev_R2",
             "locationsText": "Bellevue, WA"},
        ],
        "engineer": [
            {"title": "Software Engineer, New Grad", "externalPath": "/job/Bellevue/SWE_R1",
             "locationsText": "Bellevue, WA"},
            {"title": "Retail Store Associate", "externalPath": "/job/Bellevue/Retail_R3",
             "locationsText": "Bellevue, WA"},
        ],
    }
    payloads = []

    def fake_post(url, json, **_kwargs):
        payloads.append((url, dict(json)))
        postings = feeds[json["searchText"]]
        page = postings[json["offset"]:json["offset"] + json["limit"]]
        return FakeResponse({"total": len(postings), "jobPostings": page})

    monkeypatch.setattr(scraper.session, "post", fake_post)
    result = scraper._scrape_company("T-Mobile", {
        "ats": "workday",
        "url": "https://tmobile.wd1.myworkdayjobs.com/External",
        "search_queries": ["software", "engineer"],
    })

    assert result.healthy is True
    assert result.candidate_count == 3
    assert {p[1]["searchText"] for p in payloads} == {"software", "engineer"}
    assert all(p[0] == "https://tmobile.wd1.myworkdayjobs.com/wday/cxs/tmobile/External/jobs" for p in payloads)
    titles = sorted(j.title for j in result.jobs)
    assert titles == ["Associate Software Developer", "Software Engineer, New Grad"]
    swe = next(j for j in result.jobs if j.title == "Software Engineer, New Grad")
    assert swe.url == "https://tmobile.wd1.myworkdayjobs.com/External/job/Bellevue/SWE_R1"
    assert swe.description_url == (
        "https://tmobile.wd1.myworkdayjobs.com/wday/cxs/tmobile/External/job/Bellevue/SWE_R1"
    )
    assert swe.date_posted == "Posted Today"


def test_workday_without_queries_sends_no_search_text(monkeypatch):
    scraper = cs.CareerScraper()
    sent = []

    def fake_post(_url, json, **_kwargs):
        sent.append(dict(json))
        return FakeResponse({"total": 0, "jobPostings": []})

    monkeypatch.setattr(scraper.session, "post", fake_post)
    result = scraper._scrape_company("Remitly", {
        "ats": "workday", "url": "https://remitly.wd5.myworkdayjobs.com/Remitly_Careers",
    })
    assert result.healthy is True
    assert "searchText" not in sent[0]


def test_fetch_jobs_resets_screen_counts(monkeypatch):
    scraper = cs.CareerScraper()
    scraper.screen_counts["no_sponsorship"] = 5
    monkeypatch.setattr(cs, "COMPANIES", {})
    scraper.fetch_jobs_with_status()
    assert scraper.screen_counts == {}


def test_seattle_area_companies_are_configured():
    expected = {
        "Remitly": ("workday", "remitly.wd5.myworkdayjobs.com"),
        "T-Mobile": ("workday", "tmobile.wd1.myworkdayjobs.com"),
        "Smartsheet": ("greenhouse", "greenhouse.io"),
        "Snowflake": (None, None),
    }
    for company, (ats, host) in expected.items():
        assert company in config.COMPANIES, company
        if ats:
            assert config.COMPANIES[company]["ats"] == ats
            assert host in config.COMPANIES[company]["url"]
    assert "tmobile" in config.TARGET_COMPANIES
    assert config.COMPANIES["T-Mobile"]["search_queries"]


def test_job_lists_include_speedyapply():
    repos = {(repo["owner"], repo["repo"]): repo for repo in config.GITHUB_REPOS}
    assert ("SimplifyJobs", "New-Grad-Positions") in repos
    speedy = repos[("speedyapply", "2027-SWE-College-Jobs")]
    assert speedy["file"] == "NEW_GRAD_USA.md"
