"""Centralized filtering logic for job listings."""

import re
from typing import TYPE_CHECKING

from config import (
    PREFERRED_LOCATIONS,
    SENIORITY_EXCLUSIONS,
    SENIORITY_EXCLUSION_PATTERNS,
    TITLE_KEYWORDS,
)

if TYPE_CHECKING:
    from sources.github_tracker import Job


def matches_location(location: str) -> bool:
    """
    Check if a location matches preferred locations using word boundaries.

    Uses regex word boundaries to prevent partial matches like "campus" matching "us".
    Handles "us" specially to match "U.S.", "US", "U.S.A.", etc.

    Returns True if:
    - No preferred locations configured (empty list)
    - Location is empty/not specified
    - Location matches any preferred location
    """
    if not PREFERRED_LOCATIONS:
        return True

    if not location:
        return True

    location_lower = location.lower()

    for loc in PREFERRED_LOCATIONS:
        loc_lower = loc.lower()

        # Special handling for "us" to match word boundaries and variants like "U.S."
        if loc_lower == "us":
            # Match "us", "u.s.", "u.s.a.", etc. with word boundaries
            pattern = r'\bu\.?s\.?(?:a\.?)?\b'
        else:
            # Standard word boundary matching
            pattern = r'\b' + re.escape(loc_lower) + r'\b'

        if re.search(pattern, location_lower):
            return True

    return False


def is_senior_level(title: str) -> bool:
    """
    Check if a job title indicates a senior/non-entry-level position.

    Returns True if the title contains:
    - Senior keywords (senior, staff, principal, etc.)
    - Roman numerals II, III, IV, V (but NOT I)
    - Numeric levels (SDE 2, Engineer 3, L4, L5, etc.)
    - Experience requirements (2+ years, 3 years, etc.)

    Does NOT exclude:
    - I or 1 (entry-level indicators)
    - Years like 2024, 2025, 2026 (graduation years)
    - L3 (entry-level at Google)
    """
    title_lower = title.lower()

    # Check for senior keywords
    for keyword in SENIORITY_EXCLUSIONS:
        if keyword in title_lower:
            return True

    # Check regex patterns for seniority indicators
    for pattern in SENIORITY_EXCLUSION_PATTERNS:
        if re.search(pattern, title_lower, re.IGNORECASE):
            return True

    return False


def has_new_grad_indicator(title: str) -> bool:
    """
    Check if a job title contains explicit new grad/entry-level keywords.

    This helps identify jobs that are explicitly targeted at new grads,
    which may have looser location requirements.
    """
    title_lower = title.lower()
    return any(kw in title_lower for kw in TITLE_KEYWORDS)


def matches_job_criteria(job: "Job", check_title_keywords: bool = False) -> bool:
    """
    Unified job filtering that combines seniority and location checks.

    Args:
        job: The job to check
        check_title_keywords: If True, require title to have new grad keywords
                            (used by career_scraper which scrapes all jobs)

    Returns:
        True if the job passes all filters

    Filtering rules:
    1. If check_title_keywords is True, title must contain new grad keywords
       OR must not be a senior-level position
    2. Title must NOT indicate senior level (unless explicitly new grad)
    3. Location must match preferred locations (with word boundaries)
       - Empty locations are accepted if title has new grad indicator
    """
    title_lower = job.title.lower()

    # Check for explicit new grad indicator
    is_new_grad = has_new_grad_indicator(title_lower)

    # Check seniority - always exclude senior roles unless explicitly new grad
    if not is_new_grad and is_senior_level(title_lower):
        return False

    # If new grad but also has senior indicators, still exclude
    # (e.g., "Senior Engineer - New Grad Program" should be excluded)
    if is_senior_level(title_lower):
        # Exception: if it has new grad keywords AND roman numeral I or level 1, allow it
        # This handles cases like "SDE I - New Grad"
        has_level_one = bool(re.search(r'\b(?:sde|swe|engineer|developer)\s*[i1]\b', title_lower, re.IGNORECASE))
        if not has_level_one:
            return False

    # Location check with word boundaries
    if not matches_location(job.location):
        # Allow empty location only if title has new grad indicator
        if job.location and not is_new_grad:
            return False
        elif job.location:
            return False

    return True
