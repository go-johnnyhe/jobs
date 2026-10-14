"""Tests for the assistant webhook against a real local HTTP server."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import pytest

import assistant_notifier
from assistant_notifier import PAYLOAD_SCHEMA, AssistantNotifier, job_id, job_payload
from models import Job


class WebhookServer:
    """Records requests and replies with scripted (status, headers, body) tuples."""

    def __init__(self):
        self.requests = []
        self.responses = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                server.requests.append({
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": json.loads(body),
                })
                status, headers, text = (
                    server.responses.pop(0) if server.responses else (200, {}, "ok")
                )
                server.requests[-1]["status"] = status
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(text)))
                self.end_headers()
                self.wfile.write(text.encode())

            def log_message(self, *_args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/hooks/jobs"
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True,
        )

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    with WebhookServer() as webhook:
        yield webhook


def make_notifier(url, key="", sleeps=None, **kwargs):
    recorded = sleeps if sleeps is not None else []
    return AssistantNotifier(
        url,
        key,
        backoff_seconds=kwargs.pop("backoff_seconds", 2.0),
        sleep=recorded.append,
        timeout=5,
        **kwargs,
    )


def stored_row(n=1, **overrides):
    row = {
        "unique_id": f"Acme|Software Engineer {n}|https://acme.example/{n}",
        "company": "🔥 Acme",
        "title": f"Software Engineer {n} 🛂",
        "location": "Seattle, WA",
        "url": f"https://acme.example/{n}",
        "source": "SimplifyJobs/New-Grad-Positions",
        "date_posted": "2026-10-13",
        "first_seen": "2026-10-14 12:30:00",
        "sponsorship": "no",
        "seniority_flag": "borderline",
        "min_years_experience": 2,
        "screening_notes": json.dumps(["requires 2+ years of experience"]),
    }
    row.update(overrides)
    return row


def build(notifier, jobs, **kwargs):
    return notifier.build_payload(
        jobs,
        run_timestamp="2026-10-14T12:31:00Z",
        batch_index=kwargs.get("batch_index", 0),
        batch_count=kwargs.get("batch_count", 1),
        total_jobs=kwargs.get("total_jobs", len(jobs)),
        pending_after_run=kwargs.get("pending_after_run", 0),
    )


def test_job_payload_from_stored_row():
    payload = job_payload(stored_row())
    assert payload == {
        "id": job_id("Acme|Software Engineer 1|https://acme.example/1"),
        "title": "Software Engineer 1",
        "company": "Acme",
        "location": "Seattle, WA",
        "url": "https://acme.example/1",
        "source": "SimplifyJobs/New-Grad-Positions",
        "posted_date": "2026-10-13",
        "first_seen": "2026-10-14T12:30:00Z",
        "sponsorship": "no",
        "seniority_flag": "borderline",
        "min_years_experience": 2,
        "screening_notes": ["requires 2+ years of experience"],
    }
    assert len(payload["id"]) == 20


def test_job_payload_resolves_relative_age_against_first_seen():
    payload = job_payload(stored_row(date_posted="3d", first_seen="2026-10-14 01:00:00"))
    assert payload["posted_date"] == "2026-10-11"


def test_job_payload_from_job_object():
    job = Job("Acme", "SWE", "https://acme.example/1", "NYC", "career_page", date_posted="Posted Today")
    payload = job_payload(job)
    assert payload["id"] == job_id(job.unique_id)
    assert payload["first_seen"] is None
    assert payload["sponsorship"] == "unknown"
    assert payload["screening_notes"] == []


def test_payload_envelope_and_stable_batch_id():
    notifier = make_notifier("https://example.invalid")
    rows = [stored_row(1), stored_row(2)]
    payload = build(notifier, rows, batch_index=1, batch_count=3, total_jobs=60, pending_after_run=5)
    assert payload["schema"] == PAYLOAD_SCHEMA
    assert payload["event"] == "new_jobs"
    assert payload["run_timestamp"] == "2026-10-14T12:31:00Z"
    assert payload["batch"] == {
        "id": payload["batch"]["id"],
        "index": 1,
        "count": 3,
        "size": 2,
        "total_jobs": 60,
        "pending_after_run": 5,
    }
    assert [job["title"] for job in payload["jobs"]] == ["Software Engineer 1", "Software Engineer 2"]
    assert build(notifier, rows)["batch"]["id"] == payload["batch"]["id"]
    assert build(notifier, rows[:1])["batch"]["id"] != payload["batch"]["id"]


def test_batches_respect_batch_size():
    notifier = make_notifier("https://example.invalid", batch_size=25)
    assert [len(batch) for batch in notifier.batches(list(range(60)))] == [25, 25, 10]
    assert notifier.batches([]) == []


def test_posts_json_with_auth_headers(server):
    notifier = make_notifier(server.url, key="s3cret")
    payload = build(notifier, [stored_row()])
    assert notifier.send_payload(payload) is True

    assert len(server.requests) == 1
    request = server.requests[0]
    assert request["path"] == "/hooks/jobs"
    assert request["body"] == payload
    headers = {name.lower(): value for name, value in request["headers"].items()}
    assert headers["content-type"] == "application/json"
    assert headers["authorization"] == "Bearer s3cret"
    assert headers["x-webhook-key"] == "s3cret"
    assert headers["idempotency-key"] == payload["batch"]["id"]


def test_no_auth_headers_without_key(server):
    notifier = make_notifier(server.url)
    assert notifier.send_payload(build(notifier, [stored_row()])) is True
    headers = {name.lower() for name in server.requests[0]["headers"]}
    assert "authorization" not in headers
    assert "x-webhook-key" not in headers


def test_unicode_survives_the_wire(server):
    notifier = make_notifier(server.url)
    notifier.send_payload(build(notifier, [stored_row(title="Ingénieur logiciel – New Grad")]))
    assert server.requests[0]["body"]["jobs"][0]["title"] == "Ingénieur logiciel – New Grad"


def test_retries_transient_errors_with_exponential_backoff(server):
    server.responses = [(503, {}, "busy"), (500, {}, "oops"), (200, {}, "ok")]
    sleeps = []
    notifier = make_notifier(server.url, sleeps=sleeps, max_attempts=4)
    payload = build(notifier, [stored_row()])
    assert notifier.send_payload(payload) is True
    assert len(server.requests) == 3
    assert sleeps == [2.0, 4.0]
    keys = {request["headers"]["Idempotency-Key"] for request in server.requests}
    assert keys == {payload["batch"]["id"]}


def test_honors_retry_after_with_a_cap(server):
    server.responses = [(429, {"Retry-After": "7"}, "slow down"), (429, {"Retry-After": "9999"}, ""), (200, {}, "")]
    sleeps = []
    notifier = make_notifier(server.url, sleeps=sleeps, max_retry_after_seconds=60)
    assert notifier.send_payload(build(notifier, [stored_row()])) is True
    assert sleeps == [7.0, 60.0]


def test_gives_up_after_max_attempts(server):
    server.responses = [(502, {}, "")] * 5
    sleeps = []
    notifier = make_notifier(server.url, sleeps=sleeps, max_attempts=3)
    assert notifier.send_payload(build(notifier, [stored_row()])) is False
    assert len(server.requests) == 3
    assert sleeps == [2.0, 4.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_does_not_retry_client_errors(server, status):
    server.responses = [(status, {}, "nope")]
    sleeps = []
    notifier = make_notifier(server.url, sleeps=sleeps)
    assert notifier.send_payload(build(notifier, [stored_row()])) is False
    assert len(server.requests) == 1
    assert sleeps == []


def test_retries_connection_errors():
    with WebhookServer() as webhook:
        url = webhook.url
    sleeps = []
    notifier = make_notifier(url, sleeps=sleeps, max_attempts=2, backoff_seconds=0.5)
    assert notifier.send_payload(build(notifier, [stored_row()])) is False
    assert sleeps == [0.5]


def test_unconfigured_notifier_sends_nothing(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("must not POST")

    notifier = make_notifier("")
    monkeypatch.setattr(notifier.session, "post", fail)
    assert notifier.configured is False
    assert notifier.send_payload(build(notifier, [stored_row()])) is False
    assert notifier.send_test() is False


def test_dry_run_prints_payload_without_posting(monkeypatch, capsys):
    def fail(*_args, **_kwargs):
        raise AssertionError("must not POST")

    notifier = make_notifier("https://example.invalid")
    monkeypatch.setattr(notifier.session, "post", fail)
    assert notifier.send_payload(build(notifier, [stored_row()]), dry_run=True) is True
    printed = capsys.readouterr().out
    assert '"schema": "job-tracker.new-jobs.v1"' in printed


def test_send_test_posts_empty_test_event(server):
    notifier = make_notifier(server.url, key="k")
    assert notifier.send_test() is True
    body = server.requests[0]["body"]
    assert body["event"] == "test"
    assert body["jobs"] == []


def test_reads_url_and_key_from_config(monkeypatch):
    monkeypatch.setattr(assistant_notifier, "ASSISTANT_WEBHOOK_URL", " https://hook.example/x ")
    monkeypatch.setattr(assistant_notifier, "ASSISTANT_WEBHOOK_KEY", "abc")
    notifier = AssistantNotifier()
    assert notifier.webhook_url == "https://hook.example/x"
    assert notifier.headers("id")["Authorization"] == "Bearer abc"


def test_session_does_not_retry_on_its_own():
    notifier = make_notifier("https://example.invalid")
    adapter = notifier.session.get_adapter("https://example.invalid")
    assert adapter.max_retries.total == 0
