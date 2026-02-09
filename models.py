"""Data models for job tracker."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Job:
    """Represents a job listing."""
    company: str
    title: str
    url: str
    location: str
    source: str
    date_posted: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "source": self.source,
            "date_posted": self.date_posted,
        }

    @property
    def unique_id(self) -> str:
        """Generate a unique ID for deduplication."""
        return f"{self.company}|{self.title}|{self.url}"
