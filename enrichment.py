"""Fetch posting descriptions for newly found jobs whose list API omits them."""

import concurrent.futures
from typing import Optional

import requests

from http_client import create_session
from models import Job
from screening import html_to_text


def extract_description(payload: dict) -> str:
    """Pull description text from a Greenhouse or Workday job-detail response."""
    if not isinstance(payload, dict):
        return ""
    if payload.get("content"):
        return html_to_text(payload["content"])
    info = payload.get("jobPostingInfo")
    if isinstance(info, dict):
        return html_to_text(info.get("jobDescription", ""))
    for key in ("descriptionPlain", "description", "jobDescription"):
        if payload.get(key):
            return html_to_text(payload[key])
    return ""


def _fetch(session: requests.Session, job: Job) -> tuple[Job, Optional[str], str]:
    try:
        response = session.get(
            job.description_url,
            headers={"Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        return job, extract_description(response.json()), ""
    except (requests.RequestException, ValueError) as exc:
        return job, None, str(exc)


def enrich_descriptions(
    jobs: list[Job],
    *,
    max_fetches: int,
    session: Optional[requests.Session] = None,
    workers: int = 6,
) -> dict[str, int]:
    """Fill job.description for jobs with a description_url and no description.

    Jobs whose fetch fails keep an empty description and get a screening note;
    they are still delivered. Returns counts for logging.
    """
    candidates = [job for job in jobs if job.description_url and not job.description]
    selected = candidates[:max(0, max_fetches)]
    counts = {"candidates": len(candidates), "fetched": 0, "failed": 0, "skipped": 0}
    counts["skipped"] = len(candidates) - len(selected)
    if not selected:
        return counts
    session = session or create_session(retries=1)
    session.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        for job, description, error in executor.map(lambda j: _fetch(session, j), selected):
            if description:
                job.description = description
                counts["fetched"] += 1
            else:
                counts["failed"] += 1
                job.screening_notes = [
                    *job.screening_notes,
                    f"description unavailable: {error[:80] if error else 'empty'}",
                ]
    return counts
