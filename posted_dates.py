"""Normalize the many posted-date formats used by job lists and ATS feeds."""

from datetime import date, datetime, timedelta, timezone
import re
from typing import Optional

_RELATIVE_RE = re.compile(
    r"^\s*(\d+)\s*(h|hr|hrs|hours?|d|days?|w|wk|weeks?|mo|mos|months?|y|yr|years?)\s*(?:ago)?\s*$",
    re.IGNORECASE,
)
_UNIT_DAYS = {"h": 0, "d": 1, "w": 7, "m": 30, "y": 365}
_MONTH_DAY_FORMATS = ("%b %d", "%B %d")
_FULL_DATE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d %b %Y", "%d %B %Y")


def _now(now: Optional[datetime]) -> datetime:
    return now or datetime.now(timezone.utc)


def normalize_posted_date(raw, now: Optional[datetime] = None) -> Optional[str]:
    """Return an ISO date (YYYY-MM-DD) when raw can be interpreted, else raw text.

    Relative ages ("0d", "4mo") are resolved against now. Unrecognized text is
    returned unchanged so no information is lost.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return _from_epoch(raw)
    text = str(raw).strip()
    if not text:
        return None
    if text.isdigit() and len(text) >= 9:
        return _from_epoch(int(text))

    current = _now(now)
    relative = _RELATIVE_RE.match(text)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).lower()
        key = "m" if unit.startswith("mo") else unit[0]
        if key == "h":
            return (current - timedelta(hours=amount)).date().isoformat()
        return (current - timedelta(days=amount * _UNIT_DAYS[key])).date().isoformat()
    if text.lower() in {"today", "posted today", "just posted"}:
        return current.date().isoformat()
    if text.lower() in {"yesterday", "posted yesterday"}:
        return (current - timedelta(days=1)).date().isoformat()

    iso = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[T ].*)?$", text)
    if iso:
        return iso.group(1)
    for fmt in _FULL_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    for fmt in _MONTH_DAY_FORMATS:
        try:
            parsed = datetime.strptime(f"{text} {current.year}", f"{fmt} %Y").date()
        except ValueError:
            continue
        if parsed > current.date() + timedelta(days=1):
            parsed = date(parsed.year - 1, parsed.month, parsed.day)
        return parsed.isoformat()
    return text


def _from_epoch(value) -> Optional[str]:
    seconds = float(value)
    if seconds > 1e11:
        seconds /= 1000
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return str(value)
