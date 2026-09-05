"""Shared title and location filters for job listings."""

import re

from config import (
    BLOCKED_LOCATIONS,
    PREFERRED_LOCATIONS,
    ROLE_KEYWORDS,
    SENIORITY_EXCLUSIONS,
    SENIORITY_EXCLUSION_PATTERNS,
    TITLE_EXCLUSIONS,
    TITLE_KEYWORDS,
)
from models import Job

# Compile configuration once, rather than rebuilding patterns for every job.
_US_RE = re.compile(
    r"\b(?:u\.?s\.?(?:a\.?)?|united states|america)\b", re.IGNORECASE,
)
_PREFERRED_RE = re.compile(
    r"\b(?:" + "|".join(
        r"u\.?s\.?(?:a\.?)?" if loc.lower() == "us" else re.escape(loc)
        for loc in PREFERRED_LOCATIONS
    ) + r")\b", re.IGNORECASE,
)
_BLOCKED_RE = re.compile(
    r"\b(?:" + "|".join(map(re.escape, BLOCKED_LOCATIONS)) + r")\b",
    re.IGNORECASE,
)
_ROLE_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(map(re.escape, ROLE_KEYWORDS)) + r")(?!\w)",
    re.IGNORECASE,
)
_SENIOR_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(kw.strip()) for kw in SENIORITY_EXCLUSIONS)
    + r")(?!\w)|" + "|".join(SENIORITY_EXCLUSION_PATTERNS), re.IGNORECASE,
)
_EXCLUDED_TITLE_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(
        r"intern(?:ship|ships|s)?" if kw == "intern" else re.escape(kw)
        for kw in TITLE_EXCLUSIONS
    ) + r"|android|ios|mobile|embedded|firmware|hardware|solutions?\s+engineer)(?!\w)",
    re.IGNORECASE,
)
_NEW_GRAD_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(map(re.escape, TITLE_KEYWORDS)) + r")(?!\w)",
    re.IGNORECASE,
)


def matches_location(location: str) -> bool:
    """Accept unspecified locations or a configured preferred location."""
    return not PREFERRED_LOCATIONS or not location or bool(_PREFERRED_RE.search(location))


def has_role_keyword(title: str) -> bool:
    """Require a complete role keyword, not a substring of another word."""
    return bool(_ROLE_RE.search(title))


def is_senior_level(title: str) -> bool:
    """Reject senior keywords, higher job levels, and experience requirements."""
    return bool(_SENIOR_RE.search(title))


def has_excluded_title(title: str) -> bool:
    """Reject internships and excluded engineering disciplines."""
    return bool(_EXCLUDED_TITLE_RE.search(title))


def has_blocked_location(location: str) -> bool:
    """Reject blocked places and bare Remote; explicit US markers take priority."""
    if not location or _US_RE.search(location):
        return False
    if BLOCKED_LOCATIONS and _BLOCKED_RE.search(location):
        return True
    return "remote" in location.lower() and not location.lower().replace(
        "remote", ""
    ).strip(" -,/")


def has_new_grad_indicator(title: str) -> bool:
    """Check for an explicit new-graduate or entry-level title keyword."""
    return bool(_NEW_GRAD_RE.search(title))


def matches_job_criteria(
    job: Job,
    check_title_keywords: bool = False,
    require_location: bool = False,
) -> bool:
    """Apply title exclusions, seniority, optional entry level, and location rules.

    A multi-location posting is eligible if any semicolon-separated location
    passes. Missing locations require a new-grad title when require_location
    is set. Entry-level wording never overrides an explicit senior title.
    """
    if has_excluded_title(job.title) or is_senior_level(job.title):
        return False
    is_new_grad = has_new_grad_indicator(job.title)
    if check_title_keywords and not is_new_grad:
        return False
    location = job.location.strip()
    if not location:
        return not require_location or is_new_grad
    return any(
        not has_blocked_location(option) and matches_location(option)
        for part in location.split(";")
        if (option := part.strip())
    )
