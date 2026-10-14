"""Tests for Discord notifier batching behavior."""

import requests

from models import Job
from notifier import (
    DiscordNotifier,
    MAX_EMBED_TITLE_CHARS,
    MAX_JOB_FIELD_VALUE_CHARS,
    MAX_SOURCE_FIELD_VALUE_CHARS,
)


def _make_job(index: int) -> Job:
    return Job(
        company=f"Company {index}",
        title=f"Software Engineer {index}",
        url=f"https://example.com/{index}",
        location="Seattle, WA",
        source="test",
    )


def test_job_embeds_are_capped_to_discord_limits():
    notifier = DiscordNotifier("https://discord.example/webhook")
    job = Job(
        company="Company",
        title="Software Engineer " + ("x" * 500),
        url="https://example.com/job",
        location="Seattle, WA " + ("x" * 500),
        source="source-" + ("x" * 200),
    )

    embed = notifier._build_embed(job)

    assert len(embed["title"]) == MAX_EMBED_TITLE_CHARS
    assert embed["title"].endswith("...")
    assert len(embed["fields"][0]["value"]) == MAX_JOB_FIELD_VALUE_CHARS
    assert embed["fields"][0]["value"].endswith("...")
    assert len(embed["fields"][1]["value"]) == MAX_SOURCE_FIELD_VALUE_CHARS
    assert embed["fields"][1]["value"].endswith("...")


def test_invalid_embed_url_is_omitted():
    notifier = DiscordNotifier("https://discord.example/webhook")
    job = Job(
        company="Company",
        title="Software Engineer",
        url="not a url",
        location="Seattle, WA",
        source="test",
    )

    embed = notifier._build_embed(job)

    assert "url" not in embed


def test_career_source_label_is_user_friendly():
    notifier = DiscordNotifier("https://discord.example/webhook")
    job = Job(
        company="Jane Street",
        title="Software Engineer",
        url="https://example.com/job",
        location="New York, NY",
        source="career_page",
    )

    embed = notifier._build_embed(job)

    assert embed["fields"][1]["value"] == "Company career page"


def test_first_batch_mentions_jobs_queued_for_later_runs():
    notifier = DiscordNotifier("https://discord.example/webhook")
    jobs = [_make_job(index) for index in range(3)]

    first = notifier._build_job_batch_payload(
        jobs, total_jobs=50, batch_index=0, queued_after=173,
    )
    later = notifier._build_job_batch_payload(
        jobs, total_jobs=50, batch_index=1, queued_after=173,
    )
    plain = notifier._build_job_batch_payload(jobs, total_jobs=3, batch_index=0)

    assert first["content"] == (
        "**New Job Alert!** Sending 3 of 50 position(s) "
        "(173 more queued; they will be sent in the next run(s))"
    )
    assert "queued" not in later["content"]
    assert plain["content"] == "**New Job Alert!** Sending 3 of 3 position(s)"


def test_plain_job_embed_is_unchanged_without_screening_flags():
    notifier = DiscordNotifier("https://discord.example/webhook")
    embed = notifier._build_embed(_make_job(1))

    assert [field["name"] for field in embed["fields"]] == ["Location", "Source"]


def test_screening_flags_are_shown_for_stored_rows():
    notifier = DiscordNotifier("https://discord.example/webhook")
    row = {
        "company": "Acme",
        "title": "Software Engineer",
        "url": "https://example.com/1",
        "location": "Seattle, WA",
        "source": "career_page",
        "sponsorship": "yes",
        "seniority_flag": "borderline",
        "min_years_experience": 2,
    }

    embed = notifier._build_embed(row)

    assert embed["fields"][-1] == {
        "name": "Screening",
        "value": "Visa sponsorship mentioned | Asks for 2+ years (borderline)",
        "inline": False,
    }


def test_full_batch_stays_under_discord_embed_character_limit():
    notifier = DiscordNotifier("https://discord.example/webhook")
    jobs = [
        Job(
            company="Company " + ("x" * 200),
            title=f"Software Engineer {index} " + ("x" * 500),
            url=f"https://example.com/{index}",
            location="Seattle, WA " + ("x" * 500),
            source="source-" + ("x" * 200),
        )
        for index in range(10)
    ]

    payload = notifier._build_job_batch_payload(jobs, total_jobs=10, batch_index=0)
    total_embed_chars = 0
    for embed in payload["embeds"]:
        total_embed_chars += len(embed["title"])
        for field in embed["fields"]:
            total_embed_chars += len(field["name"])
            total_embed_chars += len(field["value"])

    assert total_embed_chars <= 6000


def test_discord_error_body_is_included(monkeypatch):
    notifier = DiscordNotifier("https://discord.example/webhook")
    response = requests.Response()
    response.status_code = 400
    response.url = "https://discord.example/webhook"
    response._content = b'{"embeds": ["Must be 6000 or fewer in length."]}'

    class FakeSession:
        def post(self, *_args, **_kwargs):
            return response

    notifier.session = FakeSession()

    try:
        notifier._send_payload({"content": "hello"})
    except requests.HTTPError as exc:
        assert "response body" in str(exc)
        assert "Must be 6000" in str(exc)
    else:
        raise AssertionError("expected HTTPError")


def test_dry_run_without_webhook_never_sends(monkeypatch):
    notifier = DiscordNotifier()
    notifier.webhook_url = ""
    def unexpected_send(*args, **kwargs):
        raise AssertionError("dry run must not send")
    monkeypatch.setattr(notifier.session, "post", unexpected_send)
    assert notifier.send_job_batch([_make_job(1)], dry_run=True)
    assert notifier.send_test(dry_run=True)
    assert notifier.notify_source_failure("github", 3, "timeout", dry_run=True)
    assert notifier.notify_source_recovery("github", 3, dry_run=True)
    assert notifier.notify_company_failure("Acme", 3, "timeout", dry_run=True)


def test_long_url_is_omitted_instead_of_changed():
    notifier = DiscordNotifier()
    job = _make_job(1)
    job.url = "https://example.com/" + "a" * 2100
    assert "url" not in notifier._build_embed(job)
