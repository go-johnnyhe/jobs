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


def test_fetch_uses_configured_raw_branch_without_github_api(monkeypatch):
    tracker = GitHubTracker()
    requested_urls = []

    class Response:
        text = """
        <table><tr>
          <td>Figma</td>
          <td>Software Engineer, New Grad</td>
          <td>New York, NY</td>
          <td><a href="https://figma.example/jobs/1">Apply</a></td>
          <td>1d</td>
        </tr></table>
        """

        def raise_for_status(self):
            return None

    def fake_get(url, **_kwargs):
        requested_urls.append(url)
        return Response()

    monkeypatch.setattr(tracker.session, "get", fake_get)
    result = tracker._fetch_from_repo({
        "owner": "SimplifyJobs",
        "repo": "New-Grad-Positions",
        "branch": "dev",
        "file": "README.md",
    })

    assert requested_urls == [
        "https://raw.githubusercontent.com/"
        "SimplifyJobs/New-Grad-Positions/dev/README.md"
    ]
    assert result.healthy is True
    assert [job.company for job in result.jobs] == ["Figma"]


def test_continuation_rows_keep_company_and_separate_locations():
    tracker = GitHubTracker()
    result = tracker._parse_simplify_readme('''
      <table>
        <tr><td>Figma</td><td>Senior Software Engineer</td><td>Seattle, WA</td>
            <td>🔒</td></tr>
        <tr><td>↳</td><td>Software Engineer I</td><td>London, UK<br>Seattle, WA</td>
            <td><a href="https://example.com/1">Apply</a></td></tr>
        <tr><td>Untracked Company</td><td>Software Engineer</td><td>Seattle, WA</td>
            <td><a href="https://example.com/2">Apply</a></td></tr>
        <tr><td>↳</td><td>Software Engineer</td><td>Seattle, WA</td>
            <td><a href="https://example.com/3">Apply</a></td></tr>
      </table>
      <table><tr><td>↳</td><td>Software Engineer</td><td>Seattle, WA</td>
            <td><a href="https://example.com/4">Apply</a></td></tr></table>
    ''', repo_name="test/repository")
    assert [(job.company, job.url, job.source) for job in result.jobs] == [
        ("Figma", "https://example.com/1", "test/repository")
    ]
    assert result.jobs[0].location == "London, UK; Seattle, WA"


def test_company_matching_uses_real_filter(monkeypatch):
    from sources import github_tracker
    monkeypatch.setattr(github_tracker, "TARGET_COMPANIES", ["f5", "cockroach"])
    tracker = GitHubTracker()
    for company, expected in [("F5", True), ("F5 Labs", False), ("CockroachLabs", True)]:
        job = Job(company, "Software Engineer", "https://example.com/1", "Seattle, WA", "test")
        assert tracker._matches_criteria(job) is expected
