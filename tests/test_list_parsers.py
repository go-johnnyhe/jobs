"""Tests for job-list table parsing against real README snapshots."""

from pathlib import Path

import pytest

from sources.list_parsers import (
    best_url,
    parse_html_tables,
    parse_listing_tables,
    parse_markdown_tables,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def simplify_rows():
    return parse_listing_tables(load("simplify_readme_html.md"))


@pytest.fixture(scope="module")
def legacy_rows():
    return parse_listing_tables(load("simplify_readme_legacy_markdown.md"))


@pytest.fixture(scope="module")
def speedyapply_rows():
    return parse_listing_tables(load("speedyapply_new_grad_usa.md"))


def by_title(rows, fragment):
    matches = [row for row in rows if fragment in row.title]
    assert matches, f"no row with title containing {fragment!r}"
    return matches


class TestSimplifyHtmlSnapshot:
    @pytest.fixture
    def rows(self, simplify_rows):
        return simplify_rows

    def test_parses_every_row(self, rows):
        assert len(rows) == 9

    def test_basic_row_fields(self, rows):
        row = by_title(rows, "Junior Software Engineer")[0]
        assert row.company == "AeroVironment"
        assert row.location == "Jessup, MD"
        assert row.age == "0d"
        assert row.closed is False
        assert row.markers == ()

    def test_prefers_employer_link_over_simplify_page(self, rows):
        row = by_title(rows, "Junior Software Engineer")[0]
        assert len(row.links) == 2
        assert best_url(row).startswith("https://avav.wd1.myworkdayjobs.com/")

    def test_continuation_row_inherits_company(self, rows):
        nvidia = by_title(rows, "SoC Software Engineer New Grad")
        assert [row.company for row in nvidia] == ["🔥 NVIDIA", "🔥 NVIDIA"]
        assert best_url(nvidia[0]) != best_url(nvidia[1])

    def test_details_multi_location_drops_summary(self, rows):
        row = by_title(rows, "Amazon Dedicated Cloud")[0]
        assert row.location == (
            "Seattle, WA; Jessup, MD; Arlington County, Arlington, VA; "
            "Denver, CO; Herndon, VA"
        )
        assert "locations" not in row.location

    def test_br_separated_locations(self, rows):
        row = by_title(rows, "Software Security Engineer")[0]
        assert row.location == "Beaverton, OR; Solon, OH"

    def test_sponsorship_and_citizenship_markers(self, rows):
        assert by_title(rows, "Full-Stack Engineer")[0].markers == ("🛂",)
        assert by_title(rows, "Software Security Engineer")[0].markers == ("🇺🇸",)
        assert by_title(rows, "Master’s")[0].markers == ("🎓",)

    def test_closed_rows(self, rows):
        closed = {row.title for row in rows if row.closed}
        assert closed == {
            "Associate Cloud Software Engineer 1",
            "Software Security Engineer (Entry-Level) 🇺🇸",
        }
        assert all(best_url(row) is None for row in rows if row.closed)


class TestSimplifyLegacyMarkdownSnapshot:
    @pytest.fixture
    def rows(self, legacy_rows):
        return legacy_rows

    def test_parses_every_row(self, rows):
        assert len(rows) == 19

    def test_bold_link_company_and_apply_link(self, rows):
        row = by_title(rows, "University Graduate - Software Engineer")[0]
        assert row.company == "Adobe"
        assert row.location == "Seattle, WA"
        assert row.age == "Jan 14"
        assert best_url(row).startswith("https://adobe.wd5.myworkdayjobs.com/")

    def test_br_locations_are_split(self, rows):
        row = by_title(rows, "– University Grad")[0]
        assert row.company == "Dagster Labs"
        assert row.location == "SF; NYC; Minneapolis, MN"

    def test_details_locations_in_markdown(self, rows):
        row = by_title(rows, "Open to relocation")[0]
        assert row.location.split("; ")[0] == "Christchurch, UK"
        assert "locations" not in row.location

    def test_markers_and_closed(self, rows):
        sprout = by_title(rows, "Associate Software Engineer")[0]
        assert sprout.markers == ("🛂",)
        assert sprout.closed is False
        visa = [row for row in rows if "🇺🇸" in row.title][0]
        assert visa.markers == ("🇺🇸",)
        assert visa.closed is True


class TestSpeedyApplySnapshot:
    @pytest.fixture
    def rows(self, speedyapply_rows):
        return speedyapply_rows

    def test_parses_tables_with_and_without_salary_column(self, rows):
        assert len(rows) == 7
        five_rings = by_title(rows, "LINK 2027")[0]
        assert five_rings.company == "Five Rings"
        assert five_rings.location == "New York City, NY"
        assert five_rings.age == "56d"
        assert best_url(five_rings) == "https://job-boards.greenhouse.io/fiveringsllc/jobs/5394515008"

        cayuse = by_title(rows, "AI Solutions")[0]
        assert cayuse.company == "Cayuse"
        assert cayuse.location == "Remote - USA"
        assert cayuse.age == "0d"
        assert best_url(cayuse) == "https://job-boards.greenhouse.io/cayuse/jobs/8885769002"

    def test_salary_column_is_not_mistaken_for_link(self, rows):
        row = by_title(rows, "Entry Level 2027")[0]
        assert best_url(row).startswith("https://jobs.lever.co/belvederetrading/")
        assert "$" not in row.location

    def test_no_markers_or_closed_rows(self, rows):
        assert not any(row.closed or row.markers for row in rows)


def test_markdown_escaped_and_unescaped_pipes_in_title():
    content = """
| Company | Role | Location | Application/Link | Date Posted |
| --- | --- | --- | :---: | :---: |
| **Acme** | Software Engineer \\| Platform | Seattle, WA | <a href="https://acme.example/1">Apply</a> | Oct 01 |
| **Beta** | Software Engineer | Backend | Remote | <a href="https://beta.example/2">Apply</a> | Oct 02 |
"""
    rows = parse_markdown_tables(content)
    assert [row.title for row in rows] == [
        "Software Engineer | Platform",
        "Software Engineer | Backend",
    ]
    assert [row.location for row in rows] == ["Seattle, WA", "Remote"]
    assert [best_url(row) for row in rows] == [
        "https://acme.example/1",
        "https://beta.example/2",
    ]


def test_markdown_link_cells_and_continuation_arrows():
    content = """
| Company | Role | Location | Application/Link | Date Posted |
|---|---|---|---|---|
| **[Acme](https://simplify.jobs/c/Acme)** | New Grad SWE | NYC | [Apply](https://acme.example/jobs/1) | 1d |
| ↳ | New Grad SWE II | SF | [Apply](https://acme.example/jobs/2) | 2d |
"""
    rows = parse_markdown_tables(content)
    assert [(row.company, row.title, best_url(row)) for row in rows] == [
        ("Acme", "New Grad SWE", "https://acme.example/jobs/1"),
        ("Acme", "New Grad SWE II", "https://acme.example/jobs/2"),
    ]


def test_html_table_without_headers_uses_positional_columns():
    rows = parse_html_tables("""
    <table><tr>
      <td>Figma</td><td>Software Engineer, New Grad</td><td>New York, NY</td>
      <td><a href="https://figma.example/jobs/1">Apply</a></td><td>1d</td>
    </tr></table>
    """)
    assert len(rows) == 1
    assert rows[0].company == "Figma"
    assert best_url(rows[0]) == "https://figma.example/jobs/1"


def test_headers_in_any_order_are_mapped_by_name():
    rows = parse_markdown_tables("""
| Age | Location | Company | Link | Position |
|---|---|---|---|---|
| 3d | Austin, TX | Acme | [Apply](https://acme.example/9) | Software Engineer I |
""")
    row = rows[0]
    assert (row.company, row.title, row.location, row.age) == (
        "Acme", "Software Engineer I", "Austin, TX", "3d",
    )


def test_only_simplify_links_fall_back_to_simplify():
    rows = parse_markdown_tables("""
| Company | Role | Location | Application/Link | Date Posted |
|---|---|---|---|---|
| Acme | SWE | NYC | <a href="https://simplify.jobs/p/abc">Simplify</a> | 1d |
""")
    assert best_url(rows[0]) == "https://simplify.jobs/p/abc"


def test_non_table_markdown_is_ignored():
    assert parse_listing_tables("# Title\n\nSome text | with a pipe\n") == []
