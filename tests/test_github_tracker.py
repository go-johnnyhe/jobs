"""Tests for GitHub tracker parse-failure handling."""

from pathlib import Path

from models import Job, ScrapeResult
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
    monkeypatch.setattr(
        github_tracker, "TARGET_COMPANIES",
        ["f5", "cockroach", "cisco", "cohere", "snap", "intel", "xai", "openai", "citadel", "block"],
    )
    tracker = GitHubTracker()
    for company, expected in [
        ("F5", True), ("Flexport", False), ("F5 Labs", True), ("CockroachLabs", True),
        ("City of San Francisco", False), ("Cisco", True), ("Cisco Systems", True),
        ("Coherent Solutions", False), ("Cohere", True),
        ("Snap Finance", False), ("Snap", True), ("Snap Inc.", True),
        ("Mintel", False), ("Modern Intelligence", False), ("Intel Corporation", True),
        ("FlexAI", False), ("xAI", True), ("OpenAI", True), ("🔥 OpenAI", True),
        ("Citadel Securities", True), ("H&R Block", False), ("The Block", True),
    ]:
        job = Job(company, "Software Engineer", "https://example.com/1", "Seattle, WA", "test")
        assert tracker._matches_criteria(job) is expected, company


FIXTURES = Path(__file__).parent / "fixtures"


def _parse_fixture(monkeypatch, name, targets):
    from sources import github_tracker
    monkeypatch.setattr(github_tracker, "TARGET_COMPANIES", targets)
    tracker = GitHubTracker()
    content = (FIXTURES / name).read_text(encoding="utf-8")
    return tracker, tracker._parse_simplify_readme(content, repo_name="owner/list")


def test_simplify_snapshot_drops_no_sponsorship_marker(monkeypatch):
    tracker, result = _parse_fixture(
        monkeypatch,
        "simplify_readme_html.md",
        ["amazon", "people culture talent", "tektronix", "northrop grumman"],
    )
    assert result.status == "success"
    assert result.candidate_count == 9
    assert [job.company for job in result.jobs] == ["🔥 Amazon"]
    amazon = result.jobs[0]
    assert amazon.url.startswith("https://amazon.jobs/en/jobs/10529546/")
    assert amazon.date_posted and len(amazon.date_posted) == 10
    assert amazon.sponsorship == "unknown"
    # People Culture Talent is marked 🛂; Tektronix (🇺🇸) and Northrop are closed.
    assert dict(tracker.screen_counts) == {"no_sponsorship": 1}


def test_legacy_markdown_snapshot_still_parses(monkeypatch):
    tracker, result = _parse_fixture(
        monkeypatch,
        "simplify_readme_legacy_markdown.md",
        ["adobe", "dagster labs", "visa"],
    )
    assert [(job.company, job.location) for job in result.jobs] == [
        ("Adobe", "Seattle, WA"),
        ("Dagster Labs", "SF; NYC; Minneapolis, MN"),
    ]
    assert tracker.screen_counts == {}


def test_speedyapply_snapshot_parses(monkeypatch):
    _tracker, result = _parse_fixture(
        monkeypatch,
        "speedyapply_new_grad_usa.md",
        ["five rings", "cayuse", "dxc"],
    )
    assert [(job.company, job.location) for job in result.jobs] == [
        ("Five Rings", "New York City, NY"),
        ("Cayuse", "Remote - USA"),
    ]


def test_citizenship_marker_on_open_row_is_dropped(monkeypatch):
    from sources import github_tracker
    monkeypatch.setattr(github_tracker, "TARGET_COMPANIES", ["acme"])
    tracker = GitHubTracker()
    result = tracker._parse_simplify_readme("""
| Company | Role | Location | Application/Link | Date Posted |
|---|---|---|---|---|
| **Acme** | Software Engineer I 🇺🇸 | Seattle, WA | <a href="https://acme.example/1">Apply</a> | 2d |
| **Acme** | Software Engineer 🛂 | Seattle, WA | <a href="https://acme.example/2">Apply</a> | 2d |
| **Acme** | Software Engineer, New Grad | Seattle, WA | <a href="https://acme.example/3">Apply</a> | 2d |
""", repo_name="owner/list")
    assert [job.url for job in result.jobs] == ["https://acme.example/3"]
    assert dict(tracker.screen_counts) == {"citizenship_required": 1, "no_sponsorship": 1}


def test_marker_drop_can_be_disabled(monkeypatch):
    from sources import github_tracker
    import screening
    monkeypatch.setattr(github_tracker, "TARGET_COMPANIES", ["acme"])
    monkeypatch.setitem(screening.SCREENING, "drop_no_sponsorship", False)
    tracker = GitHubTracker()
    result = tracker._parse_simplify_readme("""
| Company | Role | Location | Application/Link | Date Posted |
|---|---|---|---|---|
| **Acme** | Software Engineer 🛂 | Seattle, WA | <a href="https://acme.example/2">Apply</a> | 2d |
""", repo_name="owner/list")
    assert len(result.jobs) == 1
    assert result.jobs[0].sponsorship == "no"
    assert result.jobs[0].screening_notes == ["list marker: does not offer sponsorship"]


def test_one_failing_repo_does_not_mark_the_whole_source_unhealthy(monkeypatch):
    from sources import github_tracker
    monkeypatch.setattr(github_tracker, "GITHUB_REPOS", [
        {"owner": "a", "repo": "one", "branch": "main", "file": "README.md"},
        {"owner": "b", "repo": "two", "branch": "main", "file": "README.md"},
    ])
    tracker = GitHubTracker()
    job = Job("Figma", "Software Engineer", "https://figma.example/1", "New York, NY", "a/one")

    def fake_fetch(repo_config):
        if repo_config["repo"] == "one":
            return ScrapeResult(jobs=[job], candidate_count=1, status="success")
        return ScrapeResult(status="request_failure", error="b/two: 404")

    monkeypatch.setattr(tracker, "_fetch_from_repo", fake_fetch)
    jobs, healthy, error = tracker.fetch_jobs_with_status()
    assert jobs == [job]
    assert healthy is True
    assert error == "b/two: 404"
    assert set(tracker.last_repo_results) == {"a/one", "b/two"}
    assert tracker.last_repo_results["a/one"].healthy is True
    assert tracker.last_repo_results["b/two"].healthy is False
    assert tracker.last_repo_results["a/one"].scanned is True
    assert tracker.last_repo_results["b/two"].scanned is False
