"""Tests for Discord notifier batching behavior."""

import requests

from models import Job
from notifier import DiscordNotifier


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
