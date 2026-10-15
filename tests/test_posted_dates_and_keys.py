"""Tests for posted-date normalization and cross-source dedupe keys."""

from datetime import datetime, timezone

import pytest

from job_keys import canonical_job_url, dedupe_key, normalize_title
from posted_dates import normalize_posted_date

NOW = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(("raw", "expected"), [
    ("0d", "2026-10-14"),
    ("1d", "2026-10-13"),
    ("12d", "2026-10-02"),
    ("2w", "2026-09-30"),
    ("4mo", "2026-06-16"),
    ("1y", "2025-10-14"),
    ("3h", "2026-10-14"),
    ("20h", "2026-10-13"),
    ("5 days ago", "2026-10-09"),
    ("Posted Today", "2026-10-14"),
    ("Posted Yesterday", "2026-10-13"),
    ("Posted 3 Days Ago", "2026-10-11"),
    ("Posted 30+ Days Ago", "2026-09-14"),
    ("Oct 14", "2026-10-14"),
    ("Sep 16", "2026-09-16"),
    ("Dec 20", "2025-12-20"),
    ("Jan 14, 2025", "2025-01-14"),
    ("2026-10-01", "2026-10-01"),
    ("2026-10-01T12:30:00Z", "2026-10-01"),
    ("10/02/2026", "2026-10-02"),
    (1760400000000, "2025-10-14"),
    (1760400000, "2025-10-14"),
    ("1760400000000", "2025-10-14"),
])
def test_normalize_posted_date(raw, expected):
    assert normalize_posted_date(raw, now=NOW) == expected


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_empty_posted_date_is_none(raw):
    assert normalize_posted_date(raw, now=NOW) is None


def test_unknown_posted_text_is_kept():
    assert normalize_posted_date("Rolling basis", now=NOW) == "Rolling basis"


def test_canonical_url_strips_tracking_and_lever_apply():
    assert canonical_job_url(
        "https://Jobs.Lever.co/acme/1234/apply/?utm_source=Simplify&ref=Simplify&lever-source=x"
    ) == "https://jobs.lever.co/acme/1234?lever-source=x"


SAME_POSTING_URLS = {
    "greenhouse": [
        "https://boards.greenhouse.io/accenturefederalservices/jobs/4721696006?gh_jid=4721696006",
        "https://job-boards.greenhouse.io/accenturefederalservices/jobs/4721696006?utm_source=Simplify",
        "https://www.accenture.com/careers/job?gh_jid=4721696006",
    ],
    "lever": [
        "https://jobs.lever.co/palantir/fbca0358-083a-4222-bdbb-3bd729b48382/apply?utm_source=Simplify",
        "https://jobs.lever.co/palantir/FBCA0358-083A-4222-BDBB-3BD729B48382",
    ],
    "ashby": [
        "https://jobs.ashbyhq.com/harvey/4d8dc9ba-eb86-4d88-af7d-65d2fdaf3fdc/application?embed=true",
        "https://jobs.ashbyhq.com/harvey/4d8dc9ba-eb86-4d88-af7d-65d2fdaf3fdc",
    ],
    "workday": [
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/US-CA-Santa-Clara/"
        "SoC-Software-Engineer---New-College-Grad-2027_JR2026744?utm_source=Simplify&ref=Simplify",
        "https://nvidia.wd5.myworkdayjobs.com/en-US/nvidiaexternalcareersite/job/US-CA-Santa-Clara/"
        "SoC-Software-Engineer---New-College-Grad-2027_JR2026744",
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/US-CA-Santa-Clara/"
        "SoC-Software-Engineer---New-College-Grad-2027_JR2026744/apply",
    ],
    "amazon": [
        "https://amazon.jobs/en/jobs/10529546/software-development-engineer?utm_source=Simplify",
        "https://www.amazon.jobs/jobs/10529546",
    ],
}


@pytest.mark.parametrize("ats", sorted(SAME_POSTING_URLS))
def test_same_posting_from_different_lists_shares_a_key(ats):
    urls = SAME_POSTING_URLS[ats]
    titles = ["Software Engineer, New Grad", "SWE New Grad 2027", "Software Engineer"]
    keys = {dedupe_key(url, title) for url, title in zip(urls, titles)}
    assert len(keys) == 1
    assert next(iter(keys)).startswith(f"{ats}:")


def test_different_ats_postings_have_different_keys():
    assert dedupe_key("https://boards.greenhouse.io/a/jobs/1") != dedupe_key(
        "https://boards.greenhouse.io/a/jobs/2"
    )
    assert dedupe_key(
        "https://acme.wd5.myworkdayjobs.com/External/job/Seattle/SWE_R1"
    ) != dedupe_key("https://other.wd5.myworkdayjobs.com/External/job/Seattle/SWE_R1")


def test_generic_urls_include_the_title():
    careers = "https://acme.example/careers?utm_source=Simplify"
    assert dedupe_key(careers, "Software Engineer I") == (
        "https://acme.example/careers#software engineer i"
    )
    assert dedupe_key(careers, "Software Engineer I") != dedupe_key(careers, "Data Engineer")
    assert dedupe_key(careers, "Software Engineer I") == dedupe_key(
        "https://acme.example/careers/", "software engineer  I!"
    )


def test_normalize_title():
    assert normalize_title("Software Engineer – New Grad (2027) 🛂") == (
        "software engineer new grad 2027"
    )
