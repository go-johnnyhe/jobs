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


def test_eightfold_adapter_paginates_deduplicates_and_parses(monkeypatch):
    scraper = cs.CareerScraper()
    starts = []

    class Response:
        def __init__(self, start):
            self.start = start

        def raise_for_status(self):
            return None

        def json(self):
            positions = {
                0: [
                    {
                        "id": 101,
                        "name": "Software Engineer I",
                        "positionUrl": "/careers/job/101",
                        "standardizedLocations": ["Redmond, WA, US"],
                        "postedTs": 1782864000,
                    }
                ],
                1: [
                    {
                        "id": 102,
                        "name": "Senior Software Engineer",
                        "positionUrl": "/careers/job/102",
                        "locations": ["United States, Washington, Redmond"],
                    }
                ],
            }
            return {
                "data": {
                    "count": 2,
                    "positions": positions.get(self.start, []),
                }
            }

    def fake_get(_url, params, **_kwargs):
        starts.append(params["start"])
        return Response(params["start"])

    monkeypatch.setattr(scraper.session, "get", fake_get)
    result = scraper._scrape_company(
        "Microsoft",
        {
            "ats": "eightfold",
            "ats_id": "microsoft.com",
            "url": "https://apply.careers.microsoft.com",
            "search_queries": ["software engineer"],
        },
    )

    assert starts == [0, 1]
    assert result.healthy is True
    assert result.candidate_count == 2
    assert len(result.jobs) == 1
    assert result.jobs[0].url == "https://apply.careers.microsoft.com/careers/job/101"
    assert result.jobs[0].location == "Redmond, WA, US"
    assert result.jobs[0].date_posted == "2026-07-01"


def test_salesforce_public_feed_adapter(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "Report_Entry": [
                    {
                        "Job_Posting_Title": "Associate Software Engineer",
                        "External_Job_Posting_Site": (
                            "https://salesforce.wd12.myworkdayjobs.com/"
                            "External_Career_Site/job/Seattle/JR1"
                        ),
                        "Job_Requisition_Primary_Location": "Washington - Seattle",
                        "External_Job_Posting_Start_Date": "2026-07-01",
                    },
                    {
                        "Job_Posting_Title": "Senior Software Engineer",
                        "External_Job_Posting_Site": "https://example.com/JR2",
                        "Job_Requisition_Primary_Location": "Washington - Seattle",
                    },
                ]
            }

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Salesforce",
        {
            "ats": "salesforce",
            "url": "https://www.salesforce.com/company/careers/jobs/",
        },
    )

    assert result.healthy is True
    assert result.candidate_count == 2
    assert len(result.jobs) == 1
    assert result.jobs[0].title == "Associate Software Engineer"
    assert result.jobs[0].date_posted == "2026-07-01"


def test_phenom_widget_adapter_paginates_and_parses(monkeypatch):
    scraper = cs.CareerScraper()
    offsets = []

    class Response:
        def __init__(self, offset):
            self.offset = offset

        def raise_for_status(self):
            return None

        def json(self):
            jobs = {
                0: [
                    {
                        "jobSeqNo": "ACME1",
                        "title": "Associate Software Engineer",
                        "applyUrl": "https://jobs.example/apply/1",
                        "cityStateCountry": "Bellevue, Washington, United States",
                        "postedDate": "2026-07-01T00:00:00.000+0000",
                    }
                ],
                1: [
                    {
                        "jobSeqNo": "ACME2",
                        "title": "Senior Software Engineer",
                        "applyUrl": "https://jobs.example/apply/2",
                        "location": "Bellevue, WA",
                    }
                ],
            }
            return {
                "refineSearch": {
                    "totalHits": 2,
                    "data": {"jobs": jobs.get(self.offset, [])},
                }
            }

    def fake_post(_url, json, **_kwargs):
        offsets.append(json["from"])
        return Response(json["from"])

    monkeypatch.setattr(scraper.session, "post", fake_post)
    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "phenom",
            "url": "https://careers.example.com",
            "search_queries": ["software"],
        },
    )

    assert offsets == [0, 1]
    assert result.healthy is True
    assert result.candidate_count == 2
    assert len(result.jobs) == 1
    assert result.jobs[0].location == "Bellevue, Washington, United States"


def test_phenom_adapter_enforces_posting_brand_filters(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "refineSearch": {
                    "totalHits": 2,
                    "data": {
                        "jobs": [
                            {
                                "jobSeqNo": "1",
                                "title": "Software Engineer I, Splunk",
                                "applyUrl": "https://careers.example/1",
                                "cityStateCountry": "Austin, Texas, United States",
                                "companyName": "Splunk",
                            },
                            {
                                "jobSeqNo": "2",
                                "title": "Software Engineer I",
                                "applyUrl": "https://careers.example/2",
                                "cityStateCountry": "Austin, Texas, United States",
                                "companyName": "Cisco",
                            },
                        ]
                    },
                }
            }

    monkeypatch.setattr(scraper.session, "post", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Splunk",
        {
            "ats": "phenom",
            "url": "https://careers.example",
            "search_queries": ["splunk software"],
            "required_posting_terms": ["splunk"],
        },
    )

    assert result.candidate_count == 1
    assert [job.url for job in result.jobs] == ["https://careers.example/1"]


def test_phenom_adapter_rejects_incomplete_pagination(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "refineSearch": {
                    "totalHits": 2,
                    "data": {"jobs": []},
                }
            }

    monkeypatch.setattr(scraper.session, "post", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "phenom",
            "url": "https://careers.example",
            "search_queries": ["software"],
        },
    )

    assert result.status == "parse_failure"
    assert "empty page before 2 advertised jobs" in result.error


def test_meta_adapter_discovers_query_and_uses_grad_metadata(monkeypatch):
    scraper = cs.CareerScraper()
    posts = []

    class Response:
        def __init__(self, *, text="", payload=None):
            self.text = text
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_get(url, **_kwargs):
        if "bundle.js" in url:
            return Response(
                text='CareersJobSearchResultsDataQuery",id:"27506805582236862"'
            )
        return Response(
            text=(
                'LSD",[],{"token":"token-123"}'
                '<script src="https://static.xx.fbcdn.net/bundle.js"></script>'
            )
        )

    def fake_post(_url, data, **_kwargs):
        posts.append(data)
        return Response(
            payload={
                "data": {
                    "job_search_with_featured_jobs": {
                        "all_jobs": [
                            {
                                "id": "123",
                                "title": "Software Engineer",
                                "locations": ["Menlo Park, CA"],
                                "teams": [
                                    "University Grad - Engineering, Tech & Design"
                                ],
                            }
                        ]
                    }
                }
            }
        )

    monkeypatch.setattr(scraper.session, "get", fake_get)
    monkeypatch.setattr(scraper.session, "post", fake_post)
    result = scraper._scrape_company(
        "Meta",
        {"ats": "meta", "url": "https://www.metacareers.com/jobsearch/"},
    )

    assert result.healthy is True
    assert result.candidate_count == 1
    assert [job.title for job in result.jobs] == ["Software Engineer"]
    assert posts[0]["doc_id"] == "27506805582236862"
    search_input = __import__("json").loads(posts[0]["variables"])["search_input"]
    assert search_input == {"results_per_page": None}


def test_oracle_candidate_experience_adapter_paginates(monkeypatch):
    scraper = cs.CareerScraper()
    offsets = []

    class Response:
        def __init__(self, offset):
            self.offset = offset

        def raise_for_status(self):
            return None

        def json(self):
            postings = {
                0: {
                    "Id": "1",
                    "Title": "Software Engineer I",
                    "PrimaryLocation": "San Francisco, CA, United States",
                    "PostedDate": "2026-07-21",
                },
                1: {
                    "Id": "2",
                    "Title": "Senior Software Engineer",
                    "PrimaryLocation": "New York, NY, United States",
                },
            }
            return {
                "items": [
                    {
                        "TotalJobsCount": 2,
                        "requisitionList": {"items": [postings[self.offset]]},
                    }
                ]
            }

    def fake_get(_url, params, **_kwargs):
        offset = int(params["finder"].split("offset=")[1])
        offsets.append(offset)
        return Response(offset)

    monkeypatch.setattr(scraper.session, "get", fake_get)
    result = scraper._scrape_company(
        "Uber",
        {
            "ats": "oracle_ce",
            "url": "https://oracle.example/sites/UberCareers",
            "api_url": "https://oracle.example/requisitions",
            "site_number": "CX_1",
        },
    )

    assert offsets == [0, 1]
    assert result.candidate_count == 2
    assert [job.title for job in result.jobs] == ["Software Engineer I"]
    assert result.jobs[0].url == "https://oracle.example/sites/UberCareers/job/1"


def test_oracle_candidate_experience_allows_duplicate_result_rows(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def __init__(self, offset):
            self.offset = offset

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "items": [{
                    "TotalJobsCount": 2,
                    "requisitionList": {
                        "items": [{
                            "Id": "1",
                            "Title": "Software Developer 1",
                            "PrimaryLocation": "Seattle, WA, United States",
                        }]
                    },
                }]
            }

    def fake_get(_url, params, **_kwargs):
        offset = int(params["finder"].split("offset=")[1])
        return Response(offset)

    monkeypatch.setattr(scraper.session, "get", fake_get)
    result = scraper._scrape_company(
        "Oracle",
        {
            "ats": "oracle_ce",
            "url": "https://oracle.example/sites/jobsearch/jobs",
            "api_url": "https://oracle.example/requisitions",
            "site_number": "CX_1",
        },
    )

    assert result.healthy is True
    assert result.candidate_count == 1
    assert [job.title for job in result.jobs] == ["Software Developer 1"]


def test_ibm_hashicorp_adapter_uses_official_experience_level(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultset": {
                    "searchresults": {
                        "totalresults": 1,
                        "searchresultlist": [
                            {
                                "id": "1",
                                "title": "Software Engineer",
                                "description": "Build HashiCorp products.",
                                "url": "https://careers.ibm.com/job/1",
                                "docattributes": [
                                    {"field_keyword_18": "Entry Level"},
                                    {
                                        "field_keyword_19": (
                                            "San Francisco, CA, United States"
                                        )
                                    },
                                    {"effectivedate": "2026-07-01"},
                                ],
                            }
                        ],
                    }
                }
            }

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "HashiCorp",
        {
            "ats": "ibm_search",
            "url": "https://www.ibm.com/careers/search?q=hashicorp",
            "search_query": "hashicorp",
            "required_posting_term": "hashicorp",
        },
    )

    assert result.candidate_count == 1
    assert [job.title for job in result.jobs] == ["Software Engineer"]
    assert result.jobs[0].date_posted == "2026-07-01"


def test_jane_street_adapter_uses_new_grad_availability(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, **_kwargs):
        if url.endswith("position-directories.json"):
            return Response([101, 102])
        return Response(
            [
                {
                    "id": 101,
                    "position": "Software Engineer",
                    "availability": "Full-Time: New Grad",
                    "city": "NYC",
                },
                {
                    "id": 102,
                    "position": "FPGA Engineer",
                    "availability": "Full-Time: New Grad",
                    "city": "NYC",
                },
            ]
        )

    monkeypatch.setattr(scraper.session, "get", fake_get)
    result = scraper._scrape_company(
        "Jane Street",
        {
            "ats": "jane_street",
            "url": "https://www.janestreet.com/join-jane-street/open-roles/",
        },
    )

    assert result.candidate_count == 2
    assert [job.title for job in result.jobs] == ["Software Engineer"]
    assert result.jobs[0].location == "New York, NY, United States"


def test_rippling_algolia_adapter_deduplicates_locations(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "nbHits": 2,
                "nbPages": 1,
                "hits": [
                    {
                        "jobId": "1",
                        "objectID": "1-sf",
                        "name": "Software Engineer I",
                        "url": "https://www.rippling.com/careers/open-roles/1",
                        "locationNames": ["San Francisco, CA, United States"],
                    },
                    {
                        "jobId": "1",
                        "objectID": "1-ny",
                        "name": "Software Engineer I",
                        "url": "https://www.rippling.com/careers/open-roles/1",
                        "locationNames": ["New York, NY, United States"],
                    },
                ],
            }

    monkeypatch.setattr(scraper.session, "post", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Rippling",
        {
            "ats": "rippling",
            "url": "https://www.rippling.com/careers/open-roles",
            "ats_id": "careers_en-US_production",
            "algolia_app_id": "APP",
            "algolia_public_search_key": "public-key",
        },
    )

    assert result.candidate_count == 1
    assert len(result.jobs) == 1
    assert "New York" in result.jobs[0].location
    assert "San Francisco" in result.jobs[0].location


def test_eightfold_apply_v2_adapter(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "count": 1,
                "positions": [
                    {
                        "id": 101,
                        "name": "Software Engineer, New Grad",
                        "canonicalPositionUrl": (
                            "https://explore.jobs.example/careers/job/101"
                        ),
                        "locations": ["Seattle,Washington,United States"],
                        "t_create": 1782864000,
                    }
                ],
            }

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "eightfold_apply",
            "ats_id": "example.com",
            "url": "https://explore.jobs.example",
            "search_queries": ["software engineer"],
        },
    )

    assert result.healthy is True
    assert result.candidate_count == 1
    assert len(result.jobs) == 1
    assert result.jobs[0].location == "Seattle,Washington,United States"
    assert result.jobs[0].date_posted == "2026-07-01"


def test_apple_adapter_uses_csrf_and_parses(monkeypatch):
    scraper = cs.CareerScraper()
    posted_payloads = []

    class TokenResponse:
        headers = {"X-Apple-CSRF-Token": "token-123"}

        def raise_for_status(self):
            return None

    class SearchResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "res": {
                    "totalRecords": 1,
                    "searchResults": [
                        {
                            "positionId": "200000001",
                            "postingTitle": "Early Career Software Engineer",
                            "transformedPostingTitle": (
                                "early-career-software-engineer"
                            ),
                            "postDateInGMT": "2026-07-01T00:00:00Z",
                            "locations": [
                                {
                                    "name": "Seattle",
                                    "countryName": "United States",
                                }
                            ],
                            "team": {"teamCode": "SFTWR"},
                        }
                    ],
                }
            }

    monkeypatch.setattr(
        scraper.session,
        "get",
        lambda *_args, **_kwargs: TokenResponse(),
    )

    def fake_post(_url, json, headers, **_kwargs):
        posted_payloads.append((json, headers))
        return SearchResponse()

    monkeypatch.setattr(scraper.session, "post", fake_post)
    result = scraper._scrape_company(
        "Apple",
        {
            "ats": "apple",
            "url": "https://jobs.apple.com/en-us/search",
            "search_queries": ["early career software engineer"],
        },
    )

    assert result.healthy is True
    assert result.candidate_count == 1
    assert len(result.jobs) == 1
    assert posted_payloads[0][0]["filters"]["keywords"] == [
        "early career software engineer"
    ]
    assert posted_payloads[0][1]["X-Apple-CSRF-Token"] == "token-123"
    assert result.jobs[0].url.endswith(
        "/early-career-software-engineer?team=SFTWR"
    )


def test_workable_public_widget_adapter(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "jobs": [
                    {
                        "title": "Software Engineer, New Grad",
                        "url": "https://apply.workable.com/j/ABC123",
                        "city": "",
                        "state": "",
                        "country": "United States",
                        "telecommuting": True,
                        "published_on": "2026-07-01",
                    },
                    {
                        "title": "Senior Software Engineer",
                        "url": "https://apply.workable.com/j/XYZ789",
                        "country": "United States",
                    },
                ]
            }

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "workable",
            "ats_id": "acme",
            "url": "https://apply.workable.com/acme",
        },
    )

    assert result.healthy is True
    assert result.candidate_count == 2
    assert len(result.jobs) == 1
    assert result.jobs[0].location == "Remote - United States"
    assert result.jobs[0].date_posted == "2026-07-01"


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


def test_career_criteria_rejects_network_operations_engineer():
    scraper = cs.CareerScraper()
    job = Job(
        company="Google",
        title="Network Operations Engineer, University Graduate",
        url="https://www.google.com/about/careers/applications/jobs/results/1",
        location="Austin, TX, USA",
        source="career_page",
    )

    assert scraper._matches_criteria(job) is False


def test_google_adapter_paginates_and_keeps_only_explicit_new_grad(monkeypatch):
    scraper = cs.CareerScraper()
    requested_pages = []

    class Response:
        def __init__(self, page):
            title = (
                "Software Engineer, Early Career, 2027 Start"
                if page == 1
                else "Senior Software Engineer"
            )
            self.text = f"""
              <div>Showing {page} to {page} of 2 rows</div>
              <li class="lLd3Je">
                <h3 class="QJPWVe">{title}</h3>
                <div class="wVoYLb"><span class="pwO9Dc">
                  <span class="r0wTof">Seattle, WA, USA</span>
                  <span class="r0wTof">; Cambridge, MA, USA</span>
                </span></div>
                <a href="jobs/results/{page}-role"></a>
              </li>
            """

        def raise_for_status(self):
            return None

    def fake_get(_url, params, **_kwargs):
        requested_pages.append(params["page"])
        return Response(params["page"])

    monkeypatch.setattr(scraper.session, "get", fake_get)
    result = scraper._scrape_company(
        "Google",
        {
            "ats": "google",
            "url": (
                "https://www.google.com/about/careers/applications/jobs/"
                "results/?target_level=EARLY"
            ),
        },
    )

    assert requested_pages == [1, 2]
    assert result.healthy is True
    assert result.candidate_count == 2
    assert [job.title for job in result.jobs] == [
        "Software Engineer, Early Career, 2027 Start"
    ]
    assert result.jobs[0].location == "Seattle, WA, USA; Cambridge, MA, USA"
    assert result.jobs[0].url.endswith("/jobs/results/1-role")


def test_google_early_career_role_with_multiple_us_locations_matches():
    scraper = cs.CareerScraper()
    job = Job(
        company="Google",
        title="Software Engineer, Early Career, Campus",
        url=(
            "https://www.google.com/about/careers/applications/jobs/results/"
            "78703249065943750-software-engineer-early-career-campus"
        ),
        location="Mountain View, CA, USA; Cambridge, MA, USA",
        source="career_page",
    )

    assert scraper._matches_criteria(job) is True


def test_structured_html_adapter_checks_advertised_total(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        text = """
          <div>2 roles across all locations and departments</div>
          <a href="/careers/software-engineer-new-grad--engineering--seattle-united-states">
            <p>Software Engineer, New Grad</p><p>Seattle, United States</p>
          </a>
        """

        def raise_for_status(self):
            return None

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Retool",
        {
            "ats": "structured_html",
            "site_parser": "retool",
            "url": "https://retool.example/careers",
        },
    )

    assert result.status == "parse_failure"
    assert result.candidate_count == 1
    assert "1/2 advertised jobs" in result.error


def test_miro_embedded_jobs_adapter(monkeypatch):
    scraper = cs.CareerScraper()
    payload = {
        "props": {
            "pageProps": {
                "jobs": [
                    {
                        "id": 123,
                        "title": "Software Engineer, New Grad",
                        "location": "Austin, US; Remote US",
                    },
                    {
                        "id": 456,
                        "title": "Senior Software Engineer",
                        "location": "Austin, US",
                    },
                ]
            }
        }
    }

    class Response:
        text = f'<script id="__NEXT_DATA__">{__import__("json").dumps(payload)}</script>'

        def raise_for_status(self):
            return None

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Miro",
        {"ats": "miro", "url": "https://miro.com/careers/open-positions/"},
    )

    assert result.healthy is True
    assert result.candidate_count == 2
    assert len(result.jobs) == 1
    assert result.jobs[0].url.endswith("/123?gh_jid=123")


def test_spotify_first_party_api_adapter(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "result": [
                    {
                        "id": "backend-engineer-new-grad",
                        "text": "Backend Engineer, New Grad",
                        "locations": [{"location": "New York"}],
                    },
                    {
                        "id": "senior-backend-engineer",
                        "text": "Senior Backend Engineer",
                        "locations": [{"location": "New York"}],
                    },
                ]
            }

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Spotify",
        {"ats": "spotify", "url": "https://www.lifeatspotify.com/jobs"},
    )

    assert result.healthy is True
    assert result.candidate_count == 2
    assert len(result.jobs) == 1
    assert result.jobs[0].location == "New York"


def test_optiver_adapter_uses_from_size_pagination(monkeypatch):
    scraper = cs.CareerScraper()
    offsets = []

    class Response:
        def __init__(self, offset):
            self.offset = offset

        def raise_for_status(self):
            return None

        def json(self):
            postings = {
                0: [{
                    "title": "Graduate Software Engineer 2027",
                    "href": "/join-us/jobs/technology/austin/graduate-software-engineer/",
                    "location": "Austin, United States",
                }],
                1: [{
                    "title": "Senior Software Engineer",
                    "href": "/join-us/jobs/technology/austin/senior-software-engineer/",
                    "location": "Austin, United States",
                }],
            }
            return {"items": postings.get(self.offset, []), "totalCount": 2}

    def fake_get(_url, params, **_kwargs):
        offsets.append(params["from"])
        return Response(params["from"])

    monkeypatch.setattr(scraper.session, "get", fake_get)
    result = scraper._scrape_company(
        "Optiver",
        {"ats": "optiver", "url": "https://www.optiver.com/join-us/jobs/"},
    )

    assert offsets == [0, 1]
    assert result.healthy is True
    assert result.candidate_count == 2
    assert len(result.jobs) == 1


def test_workday_extracts_new_myworkdaysite_url():
    scraper = cs.CareerScraper()

    assert scraper._extract_workday_tenant_site(
        "https://wd1.myworkdaysite.com/recruiting/snapchat/snap"
    ) == ("snapchat", "snap", "https://wd1.myworkdaysite.com")


def test_atom_feed_adapter_accepts_valid_empty_feed(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        content = b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Jobs</title></feed>'

        def raise_for_status(self):
            return None

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Flyio",
        {
            "ats": "atom",
            "url": "https://fly.io/jobs/",
            "feed_url": "https://fly.io/jobs/feed.xml",
        },
    )

    assert result.healthy is True
    assert result.candidate_count == 0


def test_greenhouse_checks_total_and_uses_canonical_url(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "meta": {"total": 1},
                "jobs": [{
                    "id": 1,
                    "title": "Software Engineer I",
                    "absolute_url": "https://acme.example/jobs/1",
                    "location": {"name": "Seattle, WA"},
                }],
            }

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "greenhouse",
            "ats_id": "acme",
            "url": "https://acme.example/careers",
        },
    )

    assert result.healthy is True
    assert result.candidate_count == 1
    assert result.jobs[0].url == "https://acme.example/jobs/1"


def test_jibe_adapter_paginates_to_advertised_total(monkeypatch):
    scraper = cs.CareerScraper()
    requested_pages = []

    class Response:
        def __init__(self, page):
            self.page = page

        def raise_for_status(self):
            return None

        def json(self):
            records = {
                1: {
                    "title": "Software Engineer I",
                    "apply_url": "https://careers.example/jobs/1",
                    "location_name": "Seattle - United States",
                    "posted_date": "2026-08-01",
                },
                2: {
                    "title": "Senior Software Engineer",
                    "apply_url": "https://careers.example/jobs/2",
                    "location_name": "Seattle - United States",
                },
            }
            return {"totalCount": 2, "jobs": [{"data": records[self.page]}]}

    def fake_get(_url, params, **_kwargs):
        requested_pages.append(params["page"])
        return Response(params["page"])

    monkeypatch.setattr(scraper.session, "get", fake_get)
    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "jibe",
            "url": "https://careers.example/jobs",
            "api_url": "https://careers.example/api/jobs",
            "search_category": "Engineering",
        },
    )

    assert requested_pages == [1, 2]
    assert result.candidate_count == 2
    assert [job.title for job in result.jobs] == ["Software Engineer I"]


def test_jibe_adapter_rejects_unparseable_advertised_job(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"totalCount": 1, "jobs": [{"unexpected": "schema"}]}

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "jibe",
            "url": "https://careers.example/jobs",
            "api_url": "https://careers.example/api/jobs",
        },
    )

    assert result.status == "parse_failure"
    assert "malformed Jibe job record" in result.error


def test_two_sigma_adapter_follows_next_page_and_uses_early_career_metadata(
    monkeypatch,
):
    scraper = cs.CareerScraper()
    requested_offsets = []

    class Response:
        def __init__(self, offset):
            title = "Software Engineer" if offset == 0 else "Senior Software Engineer"
            next_link = (
                '<a href="?jobRecordsPerPage=10&amp;jobOffset=10">Next &gt;&gt;</a>'
                if offset == 0
                else ""
            )
            self.text = f"""
              <article class="article article--result">
                <h3 class="article__header__text__title">
                  <a href="/careers/JobDetail/{offset}">{title}</a>
                </h3>
                <div class="article__header__content__text">
                  <span>United States - WA Seattle</span>
                </div>
                <div>Engineering {'Early Careers' if offset == 0 else 'Experienced'}</div>
              </article>
              {next_link}
            """

        def raise_for_status(self):
            return None

    def fake_get(_url, params, **_kwargs):
        requested_offsets.append(params["jobOffset"])
        return Response(params["jobOffset"])

    monkeypatch.setattr(scraper.session, "get", fake_get)
    result = scraper._scrape_company(
        "Two Sigma",
        {
            "ats": "two_sigma",
            "url": "https://careers.twosigma.example/careers/OpenRoles/",
        },
    )

    assert requested_offsets == [0, 10]
    assert result.candidate_count == 2
    assert [job.title for job in result.jobs] == ["Software Engineer"]


def test_de_shaw_adapter_uses_only_public_embedded_jobs(monkeypatch):
    scraper = cs.CareerScraper()
    payload = {
        "props": {
            "pageProps": {
                "jobsFetchingError": False,
                "regularJobs": [{
                    "data": {
                        "id": 1,
                        "displayName": "Software Developer",
                        "jobUrl": "Software-Developer-1",
                        "validFromDate": "2026-08-01",
                        "jobMetadata": {
                            "jobSeekerCategories": ["Student"],
                            "jobLocations": [{"name": "New York"}],
                        },
                    }
                }],
                "internships": [{
                    "data": {
                        "id": 2,
                        "displayName": "Software Developer Intern",
                        "jobUrl": "Software-Developer-Intern-2",
                        "jobMetadata": {
                            "jobSeekerCategories": ["Student"],
                            "jobLocations": [{"name": "New York"}],
                        },
                    }
                }],
                "internalJobs": [{"data": {"id": 3}}],
            }
        }
    }

    class Response:
        text = (
            '<script id="__NEXT_DATA__">'
            + __import__("json").dumps(payload)
            + "</script>"
        )

        def raise_for_status(self):
            return None

    monkeypatch.setattr(scraper.session, "get", lambda *_args, **_kwargs: Response())
    result = scraper._scrape_company(
        "DE Shaw",
        {"ats": "de_shaw", "url": "https://www.deshaw.example/careers"},
    )

    assert result.candidate_count == 2
    assert [job.title for job in result.jobs] == ["Software Developer"]
    assert result.jobs[0].location == "New York"


def test_etsy_adapter_fetches_every_advertised_page(monkeypatch):
    scraper = cs.CareerScraper()
    requested_pages = []

    class Response:
        def __init__(self, page):
            title = "Software Engineer I" if page == 1 else "Senior Software Engineer"
            pagination = '<a href="/jobs/search?page=2">2</a>' if page == 1 else ""
            self.text = f"""
              <article class="job-search-results-card-col">
                <h3 class="job-search-results-card-title">
                  <a href="/jobs/{page}">{title}</a>
                </h3>
                <li class="job-component-workplace-type">Hybrid</li>
                <li class="job-component-location">Brooklyn, New York, United States</li>
              </article>
              {pagination}
            """

        def raise_for_status(self):
            return None

    def fake_get(_url, params, **_kwargs):
        requested_pages.append(params["page"])
        return Response(params["page"])

    monkeypatch.setattr(scraper.session, "get", fake_get)
    result = scraper._scrape_company(
        "Etsy",
        {"ats": "etsy", "url": "https://careers.etsy.example/jobs/search"},
    )

    assert requested_pages == [1, 2]
    assert result.candidate_count == 2
    assert [job.title for job in result.jobs] == ["Software Engineer I"]


def test_workday_rejects_incomplete_pagination(monkeypatch):
    scraper = cs.CareerScraper()
    requested_offsets = []

    class Response:
        status_code = 200

        def __init__(self, offset):
            self.offset = offset

        def raise_for_status(self):
            return None

        def json(self):
            if self.offset == 0:
                return {
                    "total": 2,
                    "jobPostings": [{
                        "title": "Software Engineer I",
                        "externalPath": "/job/1",
                        "locationsText": "Seattle, WA",
                    }],
                }
            return {"total": 2, "jobPostings": []}

    def fake_post(_url, json, **_kwargs):
        requested_offsets.append(json["offset"])
        return Response(json["offset"])

    monkeypatch.setattr(scraper.session, "post", fake_post)
    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "workday",
            "url": "https://acme.wd5.myworkdayjobs.com/External",
        },
    )

    assert requested_offsets == [0, 1]
    assert result.status == "parse_failure"
    assert result.candidate_count == 1
    assert "ended at 1/2 jobs" in result.error


def test_workday_uses_latest_total_when_feed_grows(monkeypatch):
    scraper = cs.CareerScraper()
    requested_offsets = []

    class Response:
        status_code = 200

        def __init__(self, offset):
            self.offset = offset

        def raise_for_status(self):
            return None

        def json(self):
            total = 2 if self.offset == 0 else 3
            return {
                "total": total,
                "jobPostings": [{
                    "title": f"Software Engineer {self.offset + 1}",
                    "externalPath": f"/job/{self.offset + 1}",
                    "locationsText": "Seattle, WA",
                }],
            }

    def fake_post(_url, json, **_kwargs):
        requested_offsets.append(json["offset"])
        return Response(json["offset"])

    monkeypatch.setattr(scraper.session, "post", fake_post)
    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "workday",
            "url": "https://acme.wd5.myworkdayjobs.com/External",
        },
    )

    assert requested_offsets == [0, 1, 2]
    assert result.healthy is True
    assert result.candidate_count == 3


def test_workday_keeps_first_page_total_when_later_pages_report_zero(monkeypatch):
    scraper = cs.CareerScraper()

    class Response:
        status_code = 200

        def __init__(self, offset):
            self.offset = offset

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "total": 2 if self.offset == 0 else 0,
                "jobPostings": [{
                    "title": f"Software Engineer {self.offset + 1}",
                    "externalPath": f"/job/{self.offset + 1}",
                    "locationsText": "Seattle, WA",
                }],
            }

    monkeypatch.setattr(
        scraper.session,
        "post",
        lambda _url, json, **_kwargs: Response(json["offset"]),
    )
    result = scraper._scrape_company(
        "Acme",
        {
            "ats": "workday",
            "url": "https://acme.wd5.myworkdayjobs.com/External",
        },
    )

    assert result.healthy is True
    assert result.candidate_count == 2


def test_workday_allows_a_small_number_of_duplicate_rows(monkeypatch):
    scraper = cs.CareerScraper()
    postings = [
        {
            "title": f"Software Engineer {number}",
            "externalPath": f"/job/{number}",
            "locationsText": "Seattle, WA",
        }
        for number in range(99)
    ]
    postings.append(postings[0].copy())

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"total": 100, "jobPostings": postings}

    monkeypatch.setattr(
        scraper.session,
        "post",
        lambda *_args, **_kwargs: Response(),
    )
    result = scraper._scrape_company(
        "NVIDIA",
        {
            "ats": "workday",
            "url": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        },
    )

    assert result.healthy is True
    assert result.candidate_count == 99


def test_workday_detail_urls_keep_candidate_site_path():
    scraper = cs.CareerScraper()
    posting = {
        "title": "Software Engineer I",
        "externalPath": "/job/Seattle/Software-Engineer/JR1",
        "locationsText": "Seattle, WA",
    }

    legacy = scraper._parse_workday_job(
        "NVIDIA",
        posting,
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/",
    )
    modern = scraper._parse_workday_job(
        "Snap",
        posting,
        "https://wd1.myworkdaysite.com/recruiting/snapchat/snap/",
    )

    assert legacy.url == (
        "https://nvidia.wd5.myworkdayjobs.com/"
        "NVIDIAExternalCareerSite/job/Seattle/Software-Engineer/JR1"
    )
    assert modern.url == (
        "https://wd1.myworkdaysite.com/recruiting/"
        "snapchat/snap/job/Seattle/Software-Engineer/JR1"
    )
