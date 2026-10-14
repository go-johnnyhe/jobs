"""Data models for job tracker."""

from dataclasses import dataclass, field
from typing import Optional


SPONSORSHIP_NO = "no"
SPONSORSHIP_UNKNOWN = "unknown"
SPONSORSHIP_YES = "yes"

SENIORITY_NONE = "none"
SENIORITY_BORDERLINE = "borderline"
SENIORITY_SENIOR = "senior"


@dataclass
class Job:
    """Represents a job listing."""
    company: str
    title: str
    url: str
    location: str
    source: str
    date_posted: Optional[str] = None
    sponsorship: str = SPONSORSHIP_UNKNOWN
    seniority_flag: str = SENIORITY_NONE
    min_years_experience: Optional[int] = None
    screening_notes: list[str] = field(default_factory=list)
    # Scan-time inputs for screening. They are not persisted, and they are not
    # part of job identity.
    description: str = field(default="", repr=False, compare=False)
    description_url: str = field(default="", repr=False, compare=False)
    list_markers: tuple[str, ...] = field(default=(), repr=False, compare=False)

    @property
    def unique_id(self) -> str:
        """Generate a unique ID for deduplication."""
        return f"{self.company}|{self.title}|{self.url}"

    @property
    def unit_key(self) -> str:
        """Name of the scan unit (list repository or career company) that produced the job."""
        if self.source == "career_page":
            return f"careers:{self.company}"
        return self.source


@dataclass
class ScrapeResult:
    """Represents the outcome of scraping a single source unit."""

    jobs: list["Job"] = field(default_factory=list)
    candidate_count: int = 0
    status: str = "empty"
    error: str = ""

    @property
    def healthy(self) -> bool:
        """Whether the scrape result should count as healthy."""
        return self.status in {"success", "empty"}

    @property
    def scanned(self) -> bool:
        """Whether the unit returned a usable listing, even if coverage is degraded."""
        return self.healthy or bool(self.jobs) or self.status.startswith("degraded_")
