"""Canonical URLs and cross-source deduplication keys for job postings."""

import re
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_QUERY_KEYS = {"gh_src", "ref", "source"}
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def canonical_job_url(url: str) -> str:
    """Remove tracking-only URL differences used by job aggregators."""
    parts = urlsplit((url or "").strip())
    query = urlencode([
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in _TRACKING_QUERY_KEYS
    ])
    path = parts.path.rstrip("/")
    if parts.netloc.lower() == "jobs.lever.co" and path.endswith("/apply"):
        path = path[:-len("/apply")]
    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        path,
        query,
        "",
    ))


def normalize_title(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (title or "").lower()))


def dedupe_key(url: str, title: str = "") -> str:
    """Identify the underlying posting, independent of which list linked to it.

    Known ATS URLs reduce to their job ID, so the same posting linked by
    SimplifyJobs, speedyapply, and the company career page collapses to one key.
    Other URLs can be shared by several roles (a generic careers page), so
    their key is the canonical URL plus the normalized title.
    """
    key = _ats_key(url)
    if key.startswith("ats:"):
        return key[len("ats:"):]
    return f"{key}#{normalize_title(title)}" if title else key


def _ats_key(url: str) -> str:
    canonical = canonical_job_url(url)
    parts = urlsplit(canonical)
    host = parts.netloc
    path = parts.path
    query = parse_qs(parts.query)

    gh_jid = query.get("gh_jid")
    if gh_jid and gh_jid[0].isdigit():
        return f"ats:greenhouse:{gh_jid[0]}"
    if host.endswith("greenhouse.io"):
        match = re.search(r"/jobs/(\d+)", path)
        if match:
            return f"ats:greenhouse:{match.group(1)}"
    if host == "jobs.lever.co":
        match = re.search(rf"/({_UUID})", path, re.IGNORECASE)
        if match:
            return f"ats:lever:{match.group(1).lower()}"
    if host == "jobs.ashbyhq.com":
        match = re.search(rf"/({_UUID})", path, re.IGNORECASE)
        if match:
            return f"ats:ashby:{match.group(1).lower()}"
    if host.endswith((".myworkdayjobs.com", ".myworkdaysite.com")) and "/job/" in path:
        tenant = host.split(".")[0]
        if host.endswith(".myworkdaysite.com"):
            segments = [s for s in path.split("/") if s]
            if len(segments) > 1 and segments[0] == "recruiting":
                tenant = segments[1]
        slug = path.rstrip("/").rsplit("/", 1)[-1]
        if slug.lower() == "apply":
            slug = path.rstrip("/").rsplit("/", 2)[-2]
        return f"ats:workday:{tenant.lower()}:{slug.lower()}"
    if host.endswith("amazon.jobs"):
        match = re.search(r"/jobs/(\d+)", path)
        if match:
            return f"ats:amazon:{match.group(1)}"
    if host == "jobs.smartrecruiters.com":
        match = re.search(r"^/[^/]+/(\d+)", path)
        if match:
            return f"ats:smartrecruiters:{match.group(1)}"
    if host.endswith("google.com") and "/jobs/results/" in path:
        match = re.search(r"/jobs/results/(\d+)", path)
        if match:
            return f"ats:google:{match.group(1)}"
    return canonical
