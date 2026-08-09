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
