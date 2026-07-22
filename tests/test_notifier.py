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


def test_notify_returns_false_on_later_batch_failure(monkeypatch):
    notifier = DiscordNotifier("https://discord.example/webhook")
    calls = {"count": 0}

    def fake_send_payload(_payload):
        calls["count"] += 1
        if calls["count"] == 2:
            raise requests.RequestException("discord down")

    monkeypatch.setattr(notifier, "_send_payload", fake_send_payload)

    jobs = [_make_job(index) for index in range(15)]
    success = notifier.notify(jobs)

    assert success is False
    assert calls["count"] == 2


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


def test_backlog_summary_payload(monkeypatch):
    notifier = DiscordNotifier("https://discord.example/webhook")
    payloads = []

    def fake_send_payload(payload):
        payloads.append(payload)

    monkeypatch.setattr(notifier, "_send_payload", fake_send_payload)

    success = notifier.notify_backlog_skipped(173, 20)

    assert success is True
    assert payloads == [
        {
            "content": (
                "Job Tracker recovered from a notification backlog. "
                "Skipped 173 older pending job(s) and will send the newest "
                "20 pending job(s)."
            )
        }
    ]


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
