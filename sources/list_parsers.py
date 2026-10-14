"""Parsers for community-maintained new-grad job lists.

Supports HTML tables (current SimplifyJobs README) and Markdown tables
(older SimplifyJobs README, speedyapply). Columns are located by header name,
so lists with extra columns such as Salary parse the same way. Tables without
a header row fall back to Company | Role | Location | Application | Age.
"""

from dataclasses import dataclass
import re
from typing import Optional

from bs4 import BeautifulSoup

from screening import extract_markers

CONTINUATION_MARKERS = {"", "↳", "↪", "^", "〃"}
CLOSED_MARKER = "🔒"

_HEADER_ALIASES = {
    "company": ("company", "employer", "organization"),
    "title": ("role", "position", "job title", "title", "job"),
    "location": ("location", "locations"),
    "link": ("application", "application/link", "apply", "link", "posting", "links"),
    "age": ("age", "date posted", "posted", "date"),
}
_DEFAULT_COLUMNS = {"company": 0, "title": 1, "location": 2, "link": 3, "age": 4}
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
_MARKDOWN_SEPARATOR_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_PIPE_SPLIT_RE = re.compile(r"(?<!\\)\|")
_LOCATION_SPLIT_RE = re.compile(r"\s*(?:<br\s*/?>|</br>|\n)\s*", re.IGNORECASE)


@dataclass
class ListingRow:
    """One table row from a job list."""

    company: str
    title: str
    location: str
    links: list[str]
    age: str
    closed: bool
    markers: tuple[str, ...]


def _column_map(headers: list[str]) -> Optional[dict[str, int]]:
    """Map logical columns to indexes when the header names are recognizable."""
    normalized = [re.sub(r"[^a-z/ ]", "", h.lower()).strip() for h in headers]
    columns = {}
    for name, aliases in _HEADER_ALIASES.items():
        for index, header in enumerate(normalized):
            if header in aliases and index not in columns.values():
                columns[name] = index
                break
    if {"company", "title", "link"} <= columns.keys():
        return columns
    return None


def _pick_url(links: list[str]) -> Optional[str]:
    """Prefer the employer apply link over the list's own tracking page."""
    links = [link for link in links if link.startswith(("https://", "http://"))]
    if not links:
        return None
    return next((link for link in links if "simplify.jobs" not in link), links[0])


def best_url(row: ListingRow) -> Optional[str]:
    return _pick_url(row.links)


def _row_from_cells(
    cells: list[dict],
    columns: dict[str, int],
    previous_company: str,
) -> Optional[ListingRow]:
    def cell(name: str) -> dict:
        index = columns.get(name)
        if index is None or index >= len(cells):
            return {"text": "", "links": [], "lines": []}
        return cells[index]

    company_text = cell("company")["text"]
    company = previous_company if company_text in CONTINUATION_MARKERS else company_text
    title_cell = cell("title")
    link_cell = cell("link")
    location_lines = [line for line in cell("location")["lines"] if line]
    return ListingRow(
        company=company,
        title=title_cell["text"],
        location="; ".join(location_lines),
        links=link_cell["links"],
        age=cell("age")["text"],
        closed=CLOSED_MARKER in link_cell["text"] or CLOSED_MARKER in title_cell["text"],
        markers=extract_markers(title_cell["text"] + " " + company_text),
    )


def _html_cell(td) -> dict:
    for summary in td.find_all("summary"):
        summary.decompose()
    for br in td.find_all("br"):
        br.replace_with("\n")
    lines = [
        line.strip()
        for line in td.get_text("\n", strip=True).split("\n")
    ]
    return {
        "text": td.get_text(" ", strip=True),
        "links": [a["href"].strip() for a in td.find_all("a", href=True)],
        "lines": lines,
    }


def parse_html_tables(content: str) -> list[ListingRow]:
    soup = BeautifulSoup(content, "html.parser")
    rows = []
    for table in soup.find_all("table"):
        headers = [th.get_text(" ", strip=True) for th in table.find_all("th")]
        columns = _column_map(headers) if headers else None
        if columns is None:
            columns = _DEFAULT_COLUMNS
        company = ""
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 4:
                continue
            row = _row_from_cells([_html_cell(td) for td in tds], columns, company)
            company = row.company
            rows.append(row)
    return rows


def _markdown_cell(raw: str) -> dict:
    raw = raw.strip().replace("\\|", "|")
    links = [m.group(2) for m in _MARKDOWN_LINK_RE.finditer(raw)]
    if "<" in raw:
        # html.parser drops "</br>" (used by the lists), so split lines first.
        soup = BeautifulSoup(_LOCATION_SPLIT_RE.sub("\n", raw), "html.parser")
        links += [a["href"].strip() for a in soup.find_all("a", href=True)]
        for summary in soup.find_all("summary"):
            summary.decompose()
        lines = [
            " ".join(line.split())
            for line in soup.get_text("", strip=False).split("\n")
        ]
        text = " ".join(soup.get_text(" ", strip=True).split())
    else:
        text = raw
        lines = [raw]
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = re.sub(r"\*\*|__", "", text).strip()
    lines = [re.sub(r"\*\*|__", "", _MARKDOWN_LINK_RE.sub(r"\1", line)).strip() for line in lines]
    return {"text": text, "links": links, "lines": lines}


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith("\\|"):
        stripped = stripped[:-1]
    return _PIPE_SPLIT_RE.split(stripped)


def parse_markdown_tables(content: str) -> list[ListingRow]:
    rows = []
    lines = content.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if not (line.lstrip().startswith("|") and _MARKDOWN_SEPARATOR_RE.match(next_line.strip())):
            index += 1
            continue
        headers = [h.strip() for h in _split_markdown_row(line)]
        columns = _column_map(headers) or _DEFAULT_COLUMNS
        width = len(headers)
        title_index = columns.get("title", 1)
        company = ""
        index += 2
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            raw_cells = _split_markdown_row(lines[index])
            index += 1
            if len(raw_cells) < 4:
                continue
            if len(raw_cells) > width >= 4:
                # An unescaped pipe inside the title splits it; rejoin it.
                extra = len(raw_cells) - width
                merged = "|".join(raw_cells[title_index:title_index + extra + 1])
                raw_cells = (
                    raw_cells[:title_index] + [merged]
                    + raw_cells[title_index + extra + 1:]
                )
            row = _row_from_cells([_markdown_cell(c) for c in raw_cells], columns, company)
            company = row.company
            rows.append(row)
    return rows


def parse_listing_tables(content: str) -> list[ListingRow]:
    """Parse every HTML and Markdown job table in a list document."""
    rows = parse_html_tables(content)
    if "|" in content:
        rows += parse_markdown_tables(content)
    return rows
