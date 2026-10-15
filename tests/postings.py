"""Load real job postings saved under tests/fixtures/postings.

Each file starts with "# key: value" header lines (company, title, location,
source), then a blank line, then the posting text as html_to_text produced it
from the Greenhouse API, including the EEO, export-control, and EPPA footers.
"""

from dataclasses import dataclass
from pathlib import Path
import re

POSTINGS_DIR = Path(__file__).parent / "fixtures" / "postings"

# Where compose() inserts a sentence: the end of each posting's requirements.
_INSERT_BEFORE = {
    "cloudflare_software_engineer_platforms": r"^Bonus Points$",
    "elastic_analytics_engineer_us": r"^What You Bring$",
}


@dataclass(frozen=True)
class Posting:
    name: str
    company: str
    title: str
    location: str
    text: str


def load_posting(name: str) -> Posting:
    raw = (POSTINGS_DIR / f"{name}.txt").read_text(encoding="utf-8")
    header, text = raw.split("\n\n", 1)
    fields = dict(
        line[2:].split(": ", 1) for line in header.splitlines() if line.startswith("# ")
    )
    return Posting(name, fields["company"], fields["title"], fields["location"], text.strip())


def compose(name: str, sentence: str) -> Posting:
    """A real posting with sentence added to its requirements section."""
    posting = load_posting(name)
    lines = posting.text.split("\n")
    anchor = re.compile(_INSERT_BEFORE[name])
    index = next(i for i, line in enumerate(lines) if anchor.match(line))
    lines.insert(index, sentence)
    return Posting(posting.name, posting.company, posting.title, posting.location, "\n".join(lines))
