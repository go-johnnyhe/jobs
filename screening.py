"""Visa-sponsorship and seniority screening for job postings.

Signals come from three places: list markers (the SimplifyJobs README legend),
the job title, and description text when a source provides it. A job is
dropped only when an enabled SCREENING rule clearly matches. Ambiguous or
conflicting text leaves sponsorship as "unknown" and the job is kept.
"""

from dataclasses import dataclass, field
import hashlib
import html
import json
import re
from typing import Optional

from bs4 import BeautifulSoup

from config import (
    CITIZENSHIP_MENTION_PATTERNS,
    CITIZENSHIP_REQUIRED_PATTERNS,
    CLEARANCE_REQUIRED_PATTERNS,
    EXPORT_LICENSE_SPONSORSHIP_PATTERN,
    IMMIGRATION_CONTEXT_PATTERN,
    LIST_MARKERS,
    NO_SPONSORSHIP_PATTERNS,
    OPT_ELIGIBLE_PATTERNS,
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
_CITIZENSHIP_MENTION_RE = _compile(CITIZENSHIP_MENTION_PATTERNS)
_TITLE_CITIZENSHIP_RE = _compile(TITLE_CITIZENSHIP_PATTERNS)
_CLEARANCE_RE = _compile(CLEARANCE_REQUIRED_PATTERNS)
_OPT_RE = _compile(OPT_INELIGIBLE_PATTERNS)
_OPT_ELIGIBLE_RE = _compile(OPT_ELIGIBLE_PATTERNS)
_IMMIGRATION_CONTEXT_RE = re.compile(IMMIGRATION_CONTEXT_PATTERN, re.IGNORECASE)
_EXPORT_LICENSE_RE = re.compile(EXPORT_LICENSE_SPONSORSHIP_PATTERN, re.IGNORECASE)

# Bump when screening logic in this module changes. Together with the
# configured rules it forms SCREENING_VERSION, which is stored on jobs
# screened out after a description fetch so a rules change re-screens them.
SCREENING_LOGIC_REVISION = 2
SCREENING_VERSION = hashlib.sha256(json.dumps({
    "revision": SCREENING_LOGIC_REVISION,
    "rules": {
        key: value for key, value in SCREENING.items()
        if key.startswith(("drop_", "experience_"))
    },
    "patterns": [
        NO_SPONSORSHIP_PATTERNS, SPONSORSHIP_OFFERED_PATTERNS,
        CITIZENSHIP_REQUIRED_PATTERNS, CITIZENSHIP_MENTION_PATTERNS,
        TITLE_CITIZENSHIP_PATTERNS, CLEARANCE_REQUIRED_PATTERNS,
        OPT_INELIGIBLE_PATTERNS, OPT_ELIGIBLE_PATTERNS,
        IMMIGRATION_CONTEXT_PATTERN, EXPORT_LICENSE_SPONSORSHIP_PATTERN,
    ],
    "markers": LIST_MARKERS,
}, sort_keys=True).encode()).hexdigest()[:12]

# A requirement phrase is ignored when it is negated nearby, for example
# "no security clearance required" or "U.S. citizenship is not required".
_NEGATED_BEFORE_RE = re.compile(
    r"(?:\b(?:no|not|without|never|nor)\b|n't)[^.;:!?]{0,25}$", re.IGNORECASE,
)
_NEGATED_AFTER_RE = re.compile(
    r"^[^.;:!?]{0,15}?\b(?:is|are)?\s*not\s+(?:required|needed|necessary|a\s+requirement)",
    re.IGNORECASE,
)
# "We can't sponsor, but can support OPT": negation does not cross a contrast.
_CONTRAST_RE = re.compile(r"\b(?:but|however|although|though)\b", re.IGNORECASE)
_PREFERRED_RE = re.compile(
    r"\b(?:preferred|nice[\s-]to[\s-]have|a\s+plus|bonus|ideally|desired|encouraged)\b",
    re.IGNORECASE,
)
# Clearance mentions that describe a perk or an option rather than a
# requirement: "Those with an active clearance will receive a 10% differential".
_CLEARANCE_SOFT_RE = re.compile(
    _PREFERRED_RE.pattern + r"|\b(?:differential|will\s+receive|may\s+provide|opportunity)\b",
    re.IGNORECASE,
)
_REQUIRED_CUE_RE = re.compile(
    r"\b(?:required|requires?|requirement|must|minimum|mandatory|necessary)\b",
    re.IGNORECASE,
)
_CLAUSE_BOUNDARY = ";()[]"
_CITIZENSHIP_CUE_RE = re.compile(
    r"\b(?:must|required|requires?|requirement|only|restricted|limited\s+to|eligib\w*"
    r"|open\s+to|need\s+to\s+be|have\s+to\s+be)\b",
    re.IGNORECASE,
)
_CITIZENSHIP_INVITATION_RE = re.compile(
    r"\b(?:encouraged|welcomed?|preferred|a\s+plus)\b", re.IGNORECASE,
)
# "must be U.S. citizens, permanent residents, or have valid work authorization"
_WORK_AUTH_ALTERNATIVE_RE = re.compile(
    r"\bor\b[^.;]{0,80}?\b(?:work\s+authori[sz]ation|authori[sz]ed\s+to\s+work"
    r"|eligible\s+to\s+work|work\s+permit|employment\s+authori[sz]ation|visas?)\b",
    re.IGNORECASE,
)
# Periods inside "U.S." or "e.g." do not end a sentence.
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<!\b[A-Za-z])\.(?=\s|$)|[;!?\n]")
_J1_RE = re.compile(r"\bJ-?1\b", re.IGNORECASE)
_NON_J1_VISA_RE = re.compile(r"\b(?:F-?1|H-?1B|(?-i:OPT|CPT))\b", re.IGNORECASE)
_HEADING_LINE_MAX = 60
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
# Section headings such as Lever's "What We Value" / "What We Require". Text
# under a preference heading states nice-to-haves, not requirements.
_PREFERENCE_HEADING_RE = re.compile(
    r"\b(?:what\s+we\s+value|nice[\s-]to[\s-]haves?|preferred|bonus|pluses|a\s+plus"
    r"|desired|ideally|extra\s+credit|good\s+to\s+have|we'?d\s+love)\b",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(
    r"^(?:what\s+(?:we|you)|who\s+(?:we|you)|requirements?|required|minimum|basic|preferred"
    r"|nice|bonus|desired|ideal|extra|pluses|qualifications?|responsibilities|about"
    r"|the\s+(?:role|team|opportunity)|your|you(?:'ll|\s+will|\s+have|\s+bring|\s+are)"
    r"|skills|benefits|compensation|salary|pay|key|job|position|overview|summary"
    r"|additional|day[\s-]to[\s-]day|why|how|in\s+this\s+role)\b",
    re.IGNORECASE,
)
_BLOCK_TAGS = ("p", "li", "ul", "ol", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section")


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
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup.find_all(_BLOCK_TAGS):
            tag.insert_before("\n")
            tag.insert_after("\n")
        text = soup.get_text("")
    lines = (re.sub(r"[ \t\r\f\v\u00a0]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def _split_sections(text: str) -> tuple[str, str]:
    """Return (text outside preference sections, text inside them)."""
    regular, preferred = [], []
    in_preferred = False
    for line in text.split("\n"):
        stripped = line.strip()
        is_heading = (
            0 < len(stripped) <= 60
            and not stripped.endswith((".", "!", "?", ";", ","))
            and ":" not in stripped[:-1]
            and (stripped.endswith(":") or _HEADING_RE.search(stripped))
        )
        if is_heading:
            in_preferred = bool(_PREFERENCE_HEADING_RE.search(stripped))
        (preferred if in_preferred else regular).append(line)
    return "\n".join(regular), "\n".join(preferred)


def _affirmed(patterns: list[re.Pattern], text: str) -> list[re.Match]:
    """Return matches that are not negated by nearby words."""
    found = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            before = text[max(0, match.start() - 40):match.start()]
            before = _CONTRAST_RE.split(before)[-1]
            after = text[match.end():match.end() + 40]
            if _NEGATED_BEFORE_RE.search(before) or _NEGATED_AFTER_RE.search(after):
                continue
            found.append(match)
    return found


def _affirmed_matches(patterns: list[re.Pattern], text: str) -> list[str]:
    return [match.group(0) for match in _affirmed(patterns, text)]


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = 0
    for boundary in _SENTENCE_BOUNDARY_RE.finditer(text, 0, start):
        left = boundary.end()
    following = _SENTENCE_BOUNDARY_RE.search(text, end)
    return left, following.start() if following else len(text)


def _sentence_at(text: str, start: int, end: int) -> str:
    """The sentence around text[start:end], plus a heading line right above it."""
    left, right = _sentence_bounds(text, start, end)
    sentence = text[left:right]
    if left > 0 and text[left - 1] == "\n":
        previous_start = text.rfind("\n", 0, left - 1) + 1
        previous = text[previous_start:left - 1].strip()
        if 0 < len(previous) <= _HEADING_LINE_MAX and not previous.endswith((".", "!", "?", ";")):
            sentence = f"{previous}\n{sentence}"
    return sentence


def _is_preferred(
    sentence: str, start: int, end: int, preferred_re: re.Pattern = _PREFERRED_RE,
) -> bool:
    """Whether the cue nearest to sentence[start:end] in its clause marks a preference.

    "Active Secret clearance (Top Secret preferred)" and "Secret clearance
    required, TS/SCI preferred" prefer only TS; a clause with no cue states a
    requirement.
    """
    left = max(sentence.rfind(mark, 0, start) for mark in _CLAUSE_BOUNDARY) + 1
    right_candidates = [
        i for i in (sentence.find(mark, end) for mark in _CLAUSE_BOUNDARY) if i != -1
    ]
    right = min(right_candidates) if right_candidates else len(sentence)
    clause = sentence[left:right]
    start, end = start - left, end - left
    nearest: Optional[tuple[int, bool]] = None
    for cue_re, preferred in ((_REQUIRED_CUE_RE, False), (preferred_re, True)):
        for cue in cue_re.finditer(clause):
            if cue.end() <= start:
                distance = start - cue.end()
            elif cue.start() >= end:
                distance = cue.start() - end
            else:
                distance = 0
            if nearest is None or distance < nearest[0]:
                nearest = (distance, preferred)
    return bool(nearest and nearest[1])


def _is_immigration_sponsorship(text: str, match: re.Match) -> bool:
    """Whether a no-sponsorship match refers to work visas."""
    phrase = match.group(0)
    if _J1_RE.search(phrase) and not _NON_J1_VISA_RE.search(phrase):
        return False
    tail = text[match.start():match.end() + 60]
    export = _EXPORT_LICENSE_RE.search(tail)
    if export and export.start() <= match.end() - match.start():
        return False
    sentence = _EXPORT_LICENSE_RE.sub(" ", _sentence_at(text, match.start(), match.end()))
    return bool(_IMMIGRATION_CONTEXT_RE.search(sentence))


def _citizenship_requirements(text: str) -> list[str]:
    """Citizenship requirements that do not also admit other work authorization."""
    found = []
    for patterns, needs_cue in ((_CITIZENSHIP_RE, False), (_CITIZENSHIP_MENTION_RE, True)):
        for match in _affirmed(patterns, text):
            sentence = _sentence_at(text, match.start(), match.end())
            if needs_cue and (
                not _CITIZENSHIP_CUE_RE.search(sentence)
                or _CITIZENSHIP_INVITATION_RE.search(sentence)
            ):
                continue
            _, sentence_end = _sentence_bounds(text, match.start(), match.end())
            if _WORK_AUTH_ALTERNATIVE_RE.search(text, match.end(), sentence_end):
                continue
            found.append(match.group(0))
    return found


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
            if _is_preferred(sentence, match.start(), match.end()):
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

    opt_eligible = _affirmed_matches(_OPT_ELIGIBLE_RE, text)
    no_sponsorship = [
        match.group(0)
        for pattern in _NO_SPONSORSHIP_RE
        for match in pattern.finditer(text)
        if _is_immigration_sponsorship(text, match)
    ]
    offered = _affirmed_matches(_SPONSORSHIP_OFFERED_RE, text)
    if "no_sponsorship" in marker_names:
        result.sponsorship = SPONSORSHIP_NO
        result.notes.append("list marker: does not offer sponsorship")
    elif no_sponsorship and offered:
        result.notes.append(
            "conflicting sponsorship statements: "
            f"'{_short(no_sponsorship[0])}' / '{_short(offered[0])}'"
        )
    elif no_sponsorship and opt_eligible:
        result.notes.append(
            f"no sponsorship ('{_short(no_sponsorship[0])}'), but student work "
            f"authorization accepted: '{_short(opt_eligible[0])}'"
        )
    elif no_sponsorship:
        result.sponsorship = SPONSORSHIP_NO
        result.notes.append(f"no sponsorship: '{_short(no_sponsorship[0])}'")
    elif offered:
        result.sponsorship = SPONSORSHIP_YES
        result.notes.append(f"sponsorship offered: '{_short(offered[0])}'")

    citizenship = _citizenship_requirements(text)
    citizenship += _affirmed_matches(_TITLE_CITIZENSHIP_RE, title)
    if "citizenship_required" in marker_names:
        result.citizenship_required = True
        result.notes.append("list marker: requires U.S. citizenship")
    elif citizenship and opt_eligible:
        result.notes.append(
            f"citizenship mentioned ('{_short(citizenship[0])}'), but student work "
            f"authorization accepted: '{_short(opt_eligible[0])}'"
        )
    elif citizenship:
        result.citizenship_required = True
        result.notes.append(f"citizenship required: '{_short(citizenship[0])}'")

    regular_text, preferred_text = _split_sections(description)
    clearance, clearance_preferred = [], []
    for sentence in _SENTENCE_SPLIT_RE.split(f"{title}.\n{regular_text}"):
        for match in _affirmed(_CLEARANCE_RE, sentence):
            soft = _is_preferred(sentence, match.start(), match.end(), _CLEARANCE_SOFT_RE)
            (clearance_preferred if soft else clearance).append(match.group(0))
    clearance_preferred += _affirmed_matches(_CLEARANCE_RE, preferred_text)
    if clearance:
        result.clearance_required = True
        result.notes.append(f"security clearance: '{_short(clearance[0])}'")
    elif clearance_preferred:
        result.notes.append(f"security clearance preferred: '{_short(clearance_preferred[0])}'")

    opt = [
        match.group(0)
        for pattern in _OPT_RE
        for match in pattern.finditer(text)
    ]
    if opt and opt_eligible:
        result.notes.append(
            f"conflicting student visa statements: '{_short(opt[0])}' / "
            f"'{_short(opt_eligible[0])}'"
        )
    elif opt:
        result.opt_ineligible = True
        result.notes.append(f"student visa ineligible: '{_short(opt[0])}'")
    elif opt_eligible:
        result.notes.append(f"student work authorization accepted: '{_short(opt_eligible[0])}'")

    if "advanced_degree" in marker_names:
        result.advanced_degree = True
        result.notes.append("list marker: advanced degree required")

    required, preferred = _experience_years(regular_text)
    section_required, section_preferred = _experience_years(preferred_text)
    preferred_values = [v for v in (preferred, section_required, section_preferred) if v is not None]
    preferred = max(preferred_values) if preferred_values else None
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
