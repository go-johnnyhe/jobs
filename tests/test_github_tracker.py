"""Tests for GitHub tracker parse-failure handling."""

from models import Job
from sources.github_tracker import GitHubTracker


def test_zero_candidate_rows_is_parse_failure():
    tracker = GitHubTracker()

    result = tracker._parse_simplify_readme(
        "<html><body><p>No table rows here</p></body></html>",
        repo_name="SimplifyJobs/New-Grad-Positions",
    )

    assert result.healthy is False
    assert result.status == "parse_failure"
    assert "no candidate job rows found" in result.error


def test_non_engineering_role_is_rejected():
    tracker = GitHubTracker()
    job = Job(
        company="Figma",
        title="Data Scientist, Core Data",
        url="https://example.com/job/1",
        location="New York, NY",
        source="SimplifyJobs/New-Grad-Positions",
    )

    assert tracker._matches_criteria(job) is False
