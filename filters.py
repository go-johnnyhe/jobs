"""Centralized filtering logic for job listings."""

import re

from config import (
    BLOCKED_LOCATIONS,
    PREFERRED_LOCATIONS,
    SENIORITY_EXCLUSIONS,
    SENIORITY_EXCLUSION_PATTERNS,
    TITLE_EXCLUSIONS,
    TITLE_KEYWORDS,
)
from models import Job


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


def has_excluded_title(title: str) -> bool:
    """
    Check if a job title contains exclusion keywords indicating non-SWE roles.

    Returns True for roles like:
    - Sales/Solutions/Customer Engineer
    - Android/iOS/Mobile Engineer
    - QA/Test/SDET roles
    - Hardware/Embedded/Firmware

    Returns False for (intentionally allowed):
    - Data/ML/AI Engineer
    - DevOps/SRE/Platform Engineer
    """
    title_lower = title.lower()

    for exclusion in TITLE_EXCLUSIONS:
        if exclusion in title_lower:
            return True

    return False


def has_blocked_location(location: str) -> bool:
    """
    Check if a location is in the blocklist (non-US locations).

    Uses word boundary matching to prevent partial matches.

    Returns True for:
    - UK locations (London, Cambridge, etc.)
    - Europe (Germany, France, Ireland, etc.)
    - India (Bangalore, Hyderabad, etc.)
    - APAC (Singapore, Japan, Australia)
    - Canada (Toronto, Vancouver, Montreal)

    Special handling for "Remote":
    - "Remote" alone without US qualifier → blocked
    - "Remote - US", "Remote, United States" → allowed
    """
    if not location:
        return False

    location_lower = location.lower()

    # Special handling for Remote
    if "remote" in location_lower:
        # Check if it explicitly mentions US
        us_patterns = [
            r'\bus\b',
            r'\bu\.s\.',
            r'\bunited states\b',
            r'\busa\b',
            r'\bu\.s\.a\.',
            r'\bamerica\b',
        ]
        has_us_qualifier = any(re.search(pattern, location_lower) for pattern in us_patterns)

        # If it's just "Remote" without US qualifier, block it
        # But allow if it has US qualifier
        if not has_us_qualifier:
            # Check if location is just "Remote" or "Remote" with non-US location
            # If it contains a blocked location, block it
            for blocked in BLOCKED_LOCATIONS:
                pattern = r'\b' + re.escape(blocked.lower()) + r'\b'
                if re.search(pattern, location_lower):
                    return True
            # Pure "Remote" without any country qualifier should be blocked
            # Check if there's any country/city indicator beyond just "remote"
            stripped = location_lower.replace("remote", "").strip(" -,/")
            if not stripped:
                # Just "Remote" with no qualifier - block it
                return True
        else:
            # Has US qualifier, so allow it
            return False

    # Check against blocked locations with word boundaries
    for blocked in BLOCKED_LOCATIONS:
        pattern = r'\b' + re.escape(blocked.lower()) + r'\b'
        if re.search(pattern, location_lower):
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


def matches_job_criteria(
    job: Job,
    check_title_keywords: bool = False,
    require_location: bool = False,
) -> bool:
    """
    Unified job filtering that combines seniority, title exclusions, and location checks.

    Args:
        job: The job to check
        check_title_keywords: If True, require title to have new grad keywords
                            (used by career_scraper which scrapes all jobs)
        require_location: If True, reject empty locations unless job has new grad keywords
                         (used for generic-scraped jobs where location might be missing)

    Returns:
        True if the job passes all filters

    Filtering rules:
    1. Title must NOT contain excluded role keywords (fast fail)
    2. Title must NOT indicate senior level (unless explicitly new grad + level 1)
    3. Location must NOT be in blocked locations list
    4. Location must match preferred locations (with word boundaries)
       - Empty locations are only accepted if title has new grad indicator
         OR if require_location is False
    """
    title_lower = job.title.lower()

    # 1. Check title exclusions first (fast fail for non-SWE roles)
    if has_excluded_title(title_lower):
        return False

    # Check for explicit new grad indicator
    is_new_grad = has_new_grad_indicator(title_lower)

    # 2. Check seniority - always exclude senior roles unless explicitly new grad
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

    # 3. Check blocked locations (must happen before preferred locations check)
    if has_blocked_location(job.location):
        return False

    # 4. Location check with word boundaries
    if job.location:
        if not matches_location(job.location):
            return False
    else:
        # Empty location handling
        if require_location and not is_new_grad:
            # For generic scraped jobs, require location unless it's a new grad role
            return False

    return True
