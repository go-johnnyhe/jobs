"""Tests for filters.py."""

import pytest

from filters import (
    has_blocked_location,
    has_excluded_title,
    has_new_grad_indicator,
    is_senior_level,
    matches_job_criteria,
    matches_location,
)
from models import Job


def _make_job(**kwargs):
    defaults = {
        "company": "TestCo",
        "title": "Software Engineer",
        "url": "https://example.com/job",
        "location": "San Francisco, CA",
        "source": "test",
    }
    defaults.update(kwargs)
    return Job(**defaults)


# --- matches_location ---

class TestMatchesLocation:
    def test_us_matches(self):
        assert matches_location("United States") is True

    def test_us_abbreviation(self):
        assert matches_location("Remote, US") is True

    def test_us_dotted(self):
        assert matches_location("U.S.") is True

    def test_usa(self):
        assert matches_location("USA") is True

    def test_us_not_in_campus(self):
        """'us' should not match 'campus'."""
        assert matches_location("Campus - Austin, TX") is False

    def test_seattle(self):
        assert matches_location("Seattle, WA") is True

    def test_remote(self):
        assert matches_location("Remote") is True

    def test_non_preferred(self):
        assert matches_location("London, UK") is False

    def test_empty_location(self):
        assert matches_location("") is True

    def test_san_francisco(self):
        assert matches_location("San Francisco, CA") is True


# --- is_senior_level ---

class TestIsSeniorLevel:
    def test_senior(self):
        assert is_senior_level("Senior Software Engineer") is True

    def test_staff(self):
        assert is_senior_level("Staff Engineer") is True

    def test_sde_ii(self):
        assert is_senior_level("SDE II") is True

    def test_sde_i_not_senior(self):
        assert is_senior_level("SDE I") is False

    def test_l4(self):
        assert is_senior_level("Software Engineer L4") is True

    def test_l3_not_senior(self):
        assert is_senior_level("Software Engineer L3") is False

    def test_engineer_2(self):
        assert is_senior_level("Software Engineer 2") is True

    def test_years_experience(self):
        assert is_senior_level("Engineer (3+ years)") is True

    def test_graduation_year_not_senior(self):
        """Years like 2024/2025/2026 should NOT trigger seniority."""
        assert is_senior_level("Software Engineer 2025") is False
        assert is_senior_level("New Grad 2026") is False

    def test_plain_entry_level(self):
        assert is_senior_level("Software Engineer") is False

    def test_junior(self):
        assert is_senior_level("Junior Software Engineer") is False


# --- has_excluded_title ---

class TestHasExcludedTitle:
    def test_sales_engineer(self):
        assert has_excluded_title("sales engineer") is True

    def test_android_engineer(self):
        assert has_excluded_title("android engineer") is True

    def test_qa_engineer(self):
        assert has_excluded_title("qa engineer") is True

    def test_swe_allowed(self):
        assert has_excluded_title("software engineer") is False

    def test_backend_allowed(self):
        assert has_excluded_title("backend engineer") is False

    def test_security_engineer(self):
        assert has_excluded_title("security engineer") is True


# --- has_blocked_location ---

class TestHasBlockedLocation:
    def test_empty_not_blocked(self):
        assert has_blocked_location("") is False

    def test_us_not_blocked(self):
        assert has_blocked_location("San Francisco, CA") is False

    def test_london_blocked(self):
        assert has_blocked_location("London, UK") is True

    def test_india_blocked(self):
        assert has_blocked_location("Bangalore, India") is True

    def test_canada_blocked(self):
        assert has_blocked_location("Toronto, Canada") is True

    def test_bare_remote_blocked(self):
        """Bare 'Remote' with no US qualifier should be blocked."""
        assert has_blocked_location("Remote") is True

    def test_remote_us_allowed(self):
        assert has_blocked_location("Remote - US") is False

    def test_remote_united_states_allowed(self):
        assert has_blocked_location("Remote, United States") is False


# --- matches_job_criteria (end-to-end) ---

class TestMatchesJobCriteria:
    def test_basic_swe_passes(self):
        job = _make_job(title="Software Engineer", location="Seattle, WA")
        assert matches_job_criteria(job) is True

    def test_senior_rejected(self):
        job = _make_job(title="Senior Software Engineer", location="Seattle, WA")
        assert matches_job_criteria(job) is False

    def test_blocked_location_rejected(self):
        job = _make_job(title="Software Engineer", location="London, UK")
        assert matches_job_criteria(job) is False

    def test_non_preferred_location_rejected(self):
        job = _make_job(title="Software Engineer", location="Austin, TX")
        assert matches_job_criteria(job) is False

    def test_excluded_title_rejected(self):
        job = _make_job(title="Sales Engineer", location="Seattle, WA")
        assert matches_job_criteria(job) is False

    def test_new_grad_with_empty_location(self):
        job = _make_job(title="Software Engineer New Grad", location="")
        assert matches_job_criteria(job, require_location=True) is True

    def test_empty_location_without_new_grad_rejected(self):
        job = _make_job(title="Software Engineer", location="")
        assert matches_job_criteria(job, require_location=True) is False

    def test_empty_location_no_require(self):
        job = _make_job(title="Software Engineer", location="")
        assert matches_job_criteria(job, require_location=False) is True

    def test_sde_i_new_grad_with_senior_indicator(self):
        """SDE I - New Grad should pass even if it has a senior-like pattern."""
        job = _make_job(title="SDE I - New Grad", location="Seattle, WA")
        assert matches_job_criteria(job) is True
