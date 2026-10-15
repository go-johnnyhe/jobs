"""Screening regression tests on full, real job postings.

Every case screens a whole posting, including its EEO, export-control, and
Employee Polygraph Protection Act footers, because those footers are where
false drops came from. Wordings with no real example found are added to the
requirements section of a real posting with compose().
"""

import pytest

from screening import (
    DROP_CITIZENSHIP,
    DROP_CLEARANCE,
    DROP_NO_SPONSORSHIP,
    DROP_OPT_INELIGIBLE,
    screen_text,
)
from config import SCREENING
from tests.postings import compose, load_posting

CLOUDFLARE = "cloudflare_software_engineer_platforms"
ELASTIC = "elastic_analytics_engineer_us"


def _screen(posting):
    return screen_text(title=posting.title, description=posting.text)


def test_elastic_eppa_poster_and_export_footer_do_not_drop():
    posting = load_posting(ELASTIC)
    assert "Employee Polygraph Protection Act (EPPA) Poster" in posting.text
    assert "an export license may be required" in posting.text
    result = _screen(posting)
    assert result.drop_reason is None, result.notes
    assert result.clearance_required is False
    assert result.sponsorship == "unknown"


def test_cloudflare_export_license_footer_does_not_drop():
    posting = load_posting(CLOUDFLARE)
    assert "without sponsorship for an export license" in posting.text
    result = _screen(posting)
    assert result.drop_reason is None, result.notes
    assert result.sponsorship == "unknown"
    assert result.notes == []


def test_doordash_cpt_eligible_and_j1_statement_is_kept():
    posting = load_posting("doordash_software_engineer_intern")
    assert "DoorDash does not support students on J-1 visas" in posting.text
    result = _screen(posting)
    assert result.drop_reason is None, result.notes
    assert result.opt_ineligible is False
    assert result.sponsorship == "unknown"
    assert any("student work authorization accepted" in note for note in result.notes)


@pytest.mark.parametrize(("name", "reason", "phrase"), [
    ("verkada_engineer_no_sponsorship", DROP_NO_SPONSORSHIP, "unable to sponsor"),
    ("pinterest_software_engineer_intern", DROP_NO_SPONSORSHIP,
     "not eligible for immigration sponsorship"),
    ("mongodb_advisory_solutions_architect_singapore", DROP_NO_SPONSORSHIP,
     "does not include employment sponsor"),
    ("robinhood_android_engineer_government", DROP_CITIZENSHIP,
     "US citizens or lawful permanent residents"),
    ("databricks_fde_public_sector", DROP_CLEARANCE, "secret clearance"),
    ("spacex_ai_security_software_engineer", DROP_CITIZENSHIP, "must be a (i) U.S. citizen"),
])
def test_real_restrictions_still_drop(name, reason, phrase):
    result = _screen(load_posting(name))
    assert result.drop_reason == reason, result.notes
    assert phrase.lower() in " ".join(result.notes).lower()


def test_secret_required_with_top_secret_preferred_in_parentheses():
    posting = load_posting("scaleai_data_engineer_public_sector")
    assert "Have an active Secret security clearance (Top Secret preferred)" in posting.text
    result = _screen(posting)
    assert result.clearance_required is True, result.notes
    assert result.drop_reason == DROP_CLEARANCE


def test_secret_minimum_with_top_secret_preferred():
    posting = load_posting("databricks_deputy_facility_security_officer")
    assert "(Secret minimum, Top Secret preferred)" in posting.text
    result = _screen(posting)
    assert result.clearance_required is True, result.notes


def test_spacex_clearance_perk_sentences_are_not_requirements_but_itar_is():
    posting = load_posting("spacex_ai_security_software_engineer")
    assert "Those with an active clearance will receive a 10% differential" in posting.text
    result = _screen(posting)
    assert result.citizenship_required is True
    assert result.clearance_required is True
    assert "active clearance" not in " ".join(result.notes)


def test_clearance_differential_is_not_a_requirement():
    posting = compose(
        CLOUDFLARE,
        "- Those with an active clearance will receive a 10% differential once briefed.",
    )
    result = _screen(posting)
    assert result.clearance_required is False, result.notes
    assert result.drop_reason is None


@pytest.mark.parametrize("base", [CLOUDFLARE, ELASTIC])
@pytest.mark.parametrize("sentence", [
    "We cannot sponsor H-1B visas for this role, but we can support candidates on OPT and STEM OPT.",
    "We are unable to sponsor visas; F-1 OPT candidates are welcome to apply.",
])
def test_opt_support_without_visa_sponsorship_still_drops(base, sentence):
    # OPT ends; a job that will not sponsor H-1B after it is not viable.
    result = _screen(compose(base, sentence))
    assert result.drop_reason == DROP_NO_SPONSORSHIP, result.notes
    assert result.sponsorship == "no"
    assert result.notes[0].startswith("no sponsorship: ")
    assert result.notes[1].startswith("accepts OPT/CPT without visa sponsorship")


@pytest.mark.parametrize("base", [CLOUDFLARE, ELASTIC])
@pytest.mark.parametrize("sentence", [
    "We cannot sponsor H-1B visas for this role, but we can support candidates on OPT and STEM OPT.",
    "We are unable to sponsor visas; F-1 OPT candidates are welcome to apply.",
])
def test_opt_support_vetoes_no_sponsorship_when_enabled(monkeypatch, base, sentence):
    monkeypatch.setitem(SCREENING, "drop_no_sponsorship_with_opt", False)
    result = _screen(compose(base, sentence))
    assert result.drop_reason is None, result.notes
    assert result.sponsorship == "unknown"
    assert result.notes[0].startswith("no sponsorship (")
    assert "student work authorization accepted" in result.notes[0]


@pytest.mark.parametrize("base", [CLOUDFLARE, ELASTIC])
@pytest.mark.parametrize("sentence", [
    "Applicants must be U.S. citizens, permanent residents, or have valid work "
    "authorization (including F-1 OPT).",
    "Must be a U.S. citizen or permanent resident, or otherwise authorized to work in the U.S.",
    "U.S. citizens and permanent residents are encouraged to apply.",
])
def test_citizenship_alternatives_and_invitations_are_kept(base, sentence):
    result = _screen(compose(base, sentence))
    assert result.citizenship_required is False, result.notes
    assert result.drop_reason is None


@pytest.mark.parametrize("base", [CLOUDFLARE, ELASTIC])
@pytest.mark.parametrize("sentence", [
    "We are unable to sponsor relocation costs for this role.",
    "Relocation sponsorship is not available.",
    "Relocation sponsorship is not available for this position.",
])
def test_relocation_sponsorship_is_not_visa_sponsorship(base, sentence):
    result = _screen(compose(base, sentence))
    assert result.sponsorship == "unknown", result.notes
    assert result.drop_reason is None


@pytest.mark.parametrize("base", [CLOUDFLARE, ELASTIC])
@pytest.mark.parametrize("sentence", [
    "Applicants requiring visa sponsorship now or in the future are not eligible for this position.",
    "We cannot accept candidates who require visa sponsorship.",
    "We are unable to sponsor or take over sponsorship of an employment visa for this role.",
])
def test_no_sponsorship_wordings_drop(base, sentence):
    result = _screen(compose(base, sentence))
    assert result.drop_reason == DROP_NO_SPONSORSHIP, result.notes


@pytest.mark.parametrize("base", [CLOUDFLARE, ELASTIC])
@pytest.mark.parametrize("sentence", [
    "This position is restricted to US citizens or lawful permanent residents.",
    "Applicants must be U.S. citizens or permanent residents.",
])
def test_citizenship_restrictions_drop(base, sentence):
    result = _screen(compose(base, sentence))
    assert result.drop_reason == DROP_CITIZENSHIP, result.notes


@pytest.mark.parametrize(("sentence", "required"), [
    ("- Must hold an active Secret clearance, and a TS/SCI is a plus.", True),
    ("- Secret clearance required, TS/SCI preferred.", True),
    ("- Active TS/SCI clearance with polygraph required.", True),
    ("- Must have the opportunity to obtain a TS/SCI clearance.", True),
    ("- Active Secret clearance is strongly preferred; TS/SCI is a plus.", False),
    ("- Candidates with an active Secret or higher clearance are strongly encouraged to apply.", False),
])
def test_clearance_preference_is_clause_level(sentence, required):
    result = _screen(compose(CLOUDFLARE, sentence))
    assert result.clearance_required is required, result.notes


@pytest.mark.parametrize(("sentence", "required", "preferred_note"), [
    ("- 5+ years of experience required, and experience with Go preferred.", 5, None),
    ("- 1+ years of experience required; 4+ years of experience preferred.", 1,
     "prefers 4+ years of experience"),
    ("- 3+ years of experience in Python, Java, or Go preferred.", None,
     "prefers 3+ years of experience"),
])
def test_experience_preference_is_clause_level(sentence, required, preferred_note):
    posting = compose(CLOUDFLARE, sentence)
    result = _screen(posting)
    assert result.min_years_experience == required, result.notes
    if preferred_note:
        assert preferred_note in result.notes


@pytest.mark.parametrize("sentence", [
    "Candidates on F-1 OPT or CPT are not eligible for this role.",
    "We are unable to accept OPT or STEM OPT candidates.",
])
def test_student_visa_ineligibility_drops_in_full_posting(sentence):
    result = _screen(compose(ELASTIC, sentence))
    assert result.opt_ineligible is True, result.notes
    assert result.drop_reason in {DROP_OPT_INELIGIBLE, DROP_NO_SPONSORSHIP}
