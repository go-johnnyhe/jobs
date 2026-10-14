"""Visa-sponsorship and seniority screening for job postings.

Signals come from three places: list markers (the SimplifyJobs README legend),
the job title, and description text when a source provides it. A job is
dropped only when an enabled SCREENING rule clearly matches. Ambiguous or
conflicting text leaves sponsorship as "unknown" and the job is kept.
"""

from dataclasses import dataclass, field
import html
import re
from typing import Optional

from bs4 import BeautifulSoup

from config import (
    CITIZENSHIP_REQUIRED_PATTERNS,
    CLEARANCE_REQUIRED_PATTERNS,
    LIST_MARKERS,
    NO_SPONSORSHIP_PATTERNS,
    OPT_INELIGIBLE_PATTERNS,
    SCREENING,
    SPONSORSHIP_OFFERED_PATTERNS,
    TITLE_CITIZENSHIP_PATTERNS,
)
from models import (
    SENIORITY_BORDERLINE,
    SENIORITY_NONE,
    SENIORITY_SENIOR,
    SPONSORSHIP_NO,
    SPONSORSHIP_UNKNOWN,
    SPONSORSHIP_YES,
    Job,
)

DROP_NO_SPONSORSHIP = "no_sponsorship"
DROP_CITIZENSHIP = "citizenship_required"
DROP_CLEARANCE = "clearance_required"
DROP_OPT_INELIGIBLE = "opt_ineligible"
DROP_SENIOR_EXPERIENCE = "senior_experience"


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(pattern, re.IGNORECASE) for pattern in patterns]


_NO_SPONSORSHIP_RE = _compile(NO_SPONSORSHIP_PATTERNS)
_SPONSORSHIP_OFFERED_RE = _compile(SPONSORSHIP_OFFERED_PATTERNS)
_CITIZENSHIP_RE = _compile(CITIZENSHIP_REQUIRED_PATTERNS)
_TITLE_CITIZENSHIP_RE = _compile(TITLE_CITIZENSHIP_PATTERNS)
_CLEARANCE_RE = _compile(CLEARANCE_REQUIRED_PATTERNS)
_OPT_RE = _compile(OPT_INELIGIBLE_PATTERNS)

# A requirement phrase is ignored when it is negated nearby, for example
# "no security clearance required" or "U.S. citizenship is not required".
_NEGATED_BEFORE_RE = re.compile(
    r"(?:\b(?:no|not|without|never|nor)\b|n't)[^.;:!?]{0,25}$", re.IGNORECASE,
)
_NEGATED_AFTER_RE = re.compile(
    r"^[^.;:!?]{0,15}?\b(?:is|are)?\s*not\s+(?:required|needed|necessary|a\s+requirement)",
    re.IGNORECASE,
)
_PREFERRED_RE = re.compile(
    r"\b(?:preferred|nice[\s-]to[\s-]have|a\s+plus|bonus|ideally|desired)\b",
    re.IGNORECASE,
)
_DEGREE_ALTERNATIVE_RE = re.compile(
    r"\b(?:in\s+lieu|equivalent|instead\s+of\s+a\s+degree)\b", re.IGNORECASE,
)
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_YEARS_NUMBER = r"(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")"
_EXPERIENCE_RE = re.compile(
    r"(?:\bat\s+least\s+|\bminimum\s+(?:of\s+)?|\bmin\.?\s+)?\b" + _YEARS_NUMBER
    + r"\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b['’]?"
    r"\s+(?:of\s+)?(?:[\w/&+#.,-]+\s+){0,6}?(?:experience|exp\b)",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+|\n+|\s+[•·]\s+")


@dataclass
class ScreeningResult:
    """Signals detected in one posting."""

    sponsorship: str = SPONSORSHIP_UNKNOWN
    citizenship_required: bool = False
    clearance_required: bool = False
    opt_ineligible: bool = False
    advanced_degree: bool = False
    min_years_experience: Optional[int] = None
    notes: list[str] = field(default_factory=list)

    @property
    def seniority_flag(self) -> str:
        years = self.min_years_experience
        if years is None or years < SCREENING["experience_flag_min_years"]:
            return SENIORITY_NONE
        if years >= SCREENING["experience_senior_min_years"]:
            return SENIORITY_SENIOR
        return SENIORITY_BORDERLINE

    @property
    def drop_reason(self) -> Optional[str]:
        """The first enabled rule that excludes this posting, if any."""
        if self.sponsorship == SPONSORSHIP_NO and SCREENING["drop_no_sponsorship"]:
            return DROP_NO_SPONSORSHIP
        if self.citizenship_required and SCREENING["drop_citizenship_required"]:
            return DROP_CITIZENSHIP
        if self.clearance_required and SCREENING["drop_clearance_required"]:
            return DROP_CLEARANCE
        if self.opt_ineligible and SCREENING["drop_opt_ineligible"]:
            return DROP_OPT_INELIGIBLE
        if (
            self.seniority_flag == SENIORITY_SENIOR
            and SCREENING["drop_senior_experience"]
        ):
            return DROP_SENIOR_EXPERIENCE
        return None


def html_to_text(value: str) -> str:
    """Convert HTML (optionally entity-escaped, as Greenhouse returns it) to text."""
    if not value:
        return ""
    text = html.unescape(str(value))
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    return re.sub(r"[ \t\r\f\v\u00a0]+", " ", text).strip()


def _affirmed_matches(patterns: list[re.Pattern], text: str) -> list[str]:
    """Return matched phrases that are not negated by nearby words."""
    found = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            before = text[max(0, match.start() - 40):match.start()]
            after = text[match.end():match.end() + 40]
            if _NEGATED_BEFORE_RE.search(before) or _NEGATED_AFTER_RE.search(after):
                continue
            found.append(match.group(0))
    return found


def _any_match(patterns: list[re.Pattern], text: str) -> list[str]:
    return [m.group(0) for p in patterns for m in p.finditer(text)]


def _experience_years(text: str) -> tuple[Optional[int], Optional[int]]:
    """Return (required, preferred) minimum years of experience in text."""
    required = None
    preferred = None
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        for match in _EXPERIENCE_RE.finditer(sentence):
            raw = match.group(1).lower()
            years = _NUMBER_WORDS.get(raw) or int(raw)
            if years > 15:
                continue
            context = sentence[max(0, match.start() - 60):match.end() + 60]
            if _DEGREE_ALTERNATIVE_RE.search(context):
                continue
            if _PREFERRED_RE.search(sentence):
                preferred = max(preferred or 0, years)
            else:
                required = max(required or 0, years)
    return required, preferred


def _short(phrase: str) -> str:
    phrase = re.sub(r"\s+", " ", phrase).strip()
    return phrase if len(phrase) <= 80 else phrase[:77] + "..."


def screen_text(
    *,
    title: str = "",
    description: str = "",
    markers: tuple[str, ...] = (),
) -> ScreeningResult:
    """Detect sponsorship, citizenship, clearance, OPT, and experience signals."""
    result = ScreeningResult()
    marker_names = {LIST_MARKERS.get(marker, marker) for marker in markers}
    title = title or ""
    description = description or ""
    text = f"{title}. {description}" if description else title

    no_sponsorship = _any_match(_NO_SPONSORSHIP_RE, text)
    offered = _affirmed_matches(_SPONSORSHIP_OFFERED_RE, text)
    if "no_sponsorship" in marker_names:
        result.sponsorship = SPONSORSHIP_NO
        result.notes.append("list marker: does not offer sponsorship")
    elif no_sponsorship and offered:
        result.notes.append(
            "conflicting sponsorship statements: "
            f"'{_short(no_sponsorship[0])}' / '{_short(offered[0])}'"
        )
    elif no_sponsorship:
        result.sponsorship = SPONSORSHIP_NO
        result.notes.append(f"no sponsorship: '{_short(no_sponsorship[0])}'")
    elif offered:
        result.sponsorship = SPONSORSHIP_YES
        result.notes.append(f"sponsorship offered: '{_short(offered[0])}'")

    citizenship = _affirmed_matches(_CITIZENSHIP_RE, text)
    citizenship += _affirmed_matches(_TITLE_CITIZENSHIP_RE, title)
    if "citizenship_required" in marker_names:
        result.citizenship_required = True
        result.notes.append("list marker: requires U.S. citizenship")
    elif citizenship:
        result.citizenship_required = True
        result.notes.append(f"citizenship required: '{_short(citizenship[0])}'")

    clearance = _affirmed_matches(_CLEARANCE_RE, text)
    if clearance:
        result.clearance_required = True
        result.notes.append(f"security clearance: '{_short(clearance[0])}'")

    opt = _any_match(_OPT_RE, text)
    if opt:
        result.opt_ineligible = True
        result.notes.append(f"student visa ineligible: '{_short(opt[0])}'")

    if "advanced_degree" in marker_names:
        result.advanced_degree = True
        result.notes.append("list marker: advanced degree required")

    required, preferred = _experience_years(description)
    result.min_years_experience = required
    if required is not None and required >= SCREENING["experience_flag_min_years"]:
        result.notes.append(f"requires {required}+ years of experience")
    if preferred is not None and preferred >= SCREENING["experience_flag_min_years"]:
        result.notes.append(f"prefers {preferred}+ years of experience")
    return result


def screen_job(job: Job) -> Optional[str]:
    """Attach screening flags to job and return a drop reason, or None to keep it."""
    result = screen_text(
        title=job.title,
        description=job.description,
        markers=job.list_markers,
    )
    job.sponsorship = result.sponsorship
    job.seniority_flag = result.seniority_flag
    job.min_years_experience = result.min_years_experience
    job.screening_notes = result.notes
    return result.drop_reason


def extract_markers(text: str) -> tuple[str, ...]:
    """Return the configured list markers present in text, in config order."""
    return tuple(marker for marker in LIST_MARKERS if marker in (text or ""))
