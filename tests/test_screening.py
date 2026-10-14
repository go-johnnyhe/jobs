"""Tests for sponsorship, citizenship, clearance, OPT, and experience screening."""

import pytest

import screening
from models import Job
from screening import (
    DROP_CITIZENSHIP,
    DROP_CLEARANCE,
    DROP_NO_SPONSORSHIP,
    DROP_OPT_INELIGIBLE,
    DROP_SENIOR_EXPERIENCE,
    extract_markers,
    html_to_text,
    screen_job,
    screen_text,
)


@pytest.mark.parametrize("text", [
    "We are unable to sponsor visas for this role.",
    "The company will not sponsor applicants for work visa status.",
    "We do not offer visa sponsorship.",
    "This position does not provide H-1B sponsorship.",
    "Visa sponsorship: No",
    "Sponsorship is not available for this position.",
    "No visa sponsorship is available.",
    "Candidates must be authorized to work in the US without sponsorship.",
    "Must be able to work in the U.S. without the need for current or future visa sponsorship.",
    "Applicants must not require sponsorship now or in the future.",
    "Applicants who now or in the future require sponsorship will not be considered.",
    "This role is not eligible for visa sponsorship.",
    "We can't sponsor at this time.",
    "Immigration sponsorship unavailable.",
])
def test_detects_no_sponsorship(text):
    result = screen_text(description=text)
    assert result.sponsorship == "no", result.notes
    assert result.drop_reason == DROP_NO_SPONSORSHIP


@pytest.mark.parametrize("text", [
    "We sponsor visas for qualified candidates.",
    "Visa sponsorship is available for this role.",
    "We offer H-1B sponsorship and relocation.",
    "The company will sponsor work visas for new grads.",
    "We are open to sponsoring candidates.",
])
def test_detects_sponsorship_offered(text):
    result = screen_text(description=text)
    assert result.sponsorship == "yes", result.notes
    assert result.drop_reason is None


@pytest.mark.parametrize("text", [
    "We do not sponsor visas? Not true: we sponsor visas for every new grad.",
    "We are unable to sponsor visas for contractors; for employees, visa sponsorship is available.",
])
def test_conflicting_statements_are_unknown_and_kept(text):
    result = screen_text(description=text)
    assert result.sponsorship == "unknown"
    assert result.drop_reason is None
    assert result.notes[0].startswith("conflicting sponsorship statements")


@pytest.mark.parametrize("text", [
    "",
    "Join our team building distributed systems in Seattle.",
    "We welcome applicants with or without sponsorship needs.",
    "Sponsorship of tech meetups and open source projects is part of our culture.",
    "No sponsorship required for the conference talk budget.",
    "Our sponsors include major universities.",
])
def test_neutral_text_is_unknown(text):
    result = screen_text(description=text)
    assert result.sponsorship == "unknown", result.notes
    assert result.drop_reason is None


@pytest.mark.parametrize("text", [
    "Must be a U.S. citizen.",
    "US citizenship is required for this position.",
    "Requires U.S. citizenship due to government contract requirements.",
    "Open to U.S. citizens only.",
    "Only open to US citizens.",
    "Applicants must be U.S. citizens or permanent residents.",
    "Green card holders only.",
    "Due to export control laws, candidates must be a U.S. person.",
])
def test_detects_citizenship_requirement(text):
    result = screen_text(description=text)
    assert result.citizenship_required is True, result.notes
    assert result.drop_reason == DROP_CITIZENSHIP


@pytest.mark.parametrize("text", [
    "U.S. citizenship is not required.",
    "Citizen Developer platform team building low-code tools.",
    "We value good corporate citizenship and community work.",
    "Help us build tools that serve citizens across the country.",
])
def test_citizenship_false_positives(text):
    assert screen_text(description=text).citizenship_required is False


def test_title_mention_of_citizenship_is_a_requirement():
    result = screen_text(title="Software Engineer (U.S. Citizen)")
    assert result.citizenship_required is True
    assert screen_text(title="Citizen Developer Engineer").citizenship_required is False


@pytest.mark.parametrize("text", [
    "Active TS/SCI clearance with polygraph required.",
    "Must hold a Secret clearance.",
    "Top Secret eligibility is required.",
    "Applicants must be able to obtain a DoD clearance.",
    "Security clearance required.",
])
def test_detects_clearance(text):
    result = screen_text(description=text)
    assert result.clearance_required is True, result.notes
    assert result.drop_reason == DROP_CLEARANCE


@pytest.mark.parametrize("text", [
    "No security clearance required.",
    "A security clearance is not required for this role.",
    "We keep secrets safe with end-to-end encryption.",
])
def test_clearance_false_positives(text):
    assert screen_text(description=text).clearance_required is False


@pytest.mark.parametrize("text", [
    "Candidates on F-1 OPT or CPT are not eligible for this role.",
    "We are unable to accept OPT or STEM OPT candidates.",
    "Students on F-1 visas will not be considered.",
    "Not eligible: J-1 visa holders.",
])
def test_detects_student_visa_ineligibility(text):
    result = screen_text(description=text)
    assert result.opt_ineligible is True, result.notes
    assert result.drop_reason in {DROP_OPT_INELIGIBLE, DROP_NO_SPONSORSHIP}


@pytest.mark.parametrize("text", [
    "You can opt out of marketing emails at any time.",
    "We optimize compilers. Not eligible for remote work.",
    "Our F1 racing analytics team builds telemetry tools.",
    "F-1 OPT and STEM OPT candidates are welcome to apply.",
])
def test_student_visa_false_positives(text):
    assert screen_text(description=text).opt_ineligible is False


@pytest.mark.parametrize(("text", "required", "flag"), [
    ("New grads welcome. 0-1 years of experience.", 0, "none"),
    ("1+ years of professional software experience.", 1, "none"),
    ("2+ years of experience building backend services.", 2, "borderline"),
    ("At least two years of industry experience required.", 2, "borderline"),
    ("Minimum of 3 years of relevant work experience.", 3, "borderline"),
    ("3-5 years of software engineering experience.", 3, "borderline"),
    ("5+ years of experience with distributed systems.", 5, "senior"),
    ("You have 7 yrs experience leading teams.", 7, "senior"),
])
def test_experience_years(text, required, flag):
    result = screen_text(description=text)
    assert result.min_years_experience == required
    assert result.seniority_flag == flag


@pytest.mark.parametrize("text", [
    "0-2 years of experience. 5+ years of experience preferred.",
    "BS in CS, or 4 years of equivalent experience in lieu of a degree.",
    "Over 20 years of experience in our industry, our company leads the market.",
    "Join a company with 30 years of experience serving customers.",
])
def test_experience_ignores_preferred_degree_alternatives_and_company_history(text):
    result = screen_text(description=text)
    assert result.seniority_flag != "senior"
    assert result.drop_reason is None


def test_preferred_years_are_noted_but_not_flagged():
    result = screen_text(description="2+ years of experience preferred.")
    assert result.min_years_experience is None
    assert result.seniority_flag == "none"
    assert result.notes == ["prefers 2+ years of experience"]


def test_senior_experience_flag_only_drops_when_enabled(monkeypatch):
    result = screen_text(description="6+ years of experience required.")
    assert result.seniority_flag == "senior"
    assert result.drop_reason is None
    monkeypatch.setitem(screening.SCREENING, "drop_senior_experience", True)
    assert result.drop_reason == DROP_SENIOR_EXPERIENCE


def test_experience_thresholds_are_configurable(monkeypatch):
    monkeypatch.setitem(screening.SCREENING, "experience_flag_min_years", 3)
    assert screen_text(description="2+ years of experience.").seniority_flag == "none"
    assert screen_text(description="3+ years of experience.").seniority_flag == "borderline"


@pytest.mark.parametrize(("rule", "text"), [
    ("drop_no_sponsorship", "We do not sponsor visas."),
    ("drop_citizenship_required", "Must be a U.S. citizen."),
    ("drop_clearance_required", "TS/SCI clearance required."),
    ("drop_opt_ineligible", "OPT candidates are not eligible."),
])
def test_each_drop_rule_can_be_disabled(monkeypatch, rule, text):
    assert screen_text(description=text).drop_reason is not None
    monkeypatch.setitem(screening.SCREENING, rule, False)
    assert screen_text(description=text).drop_reason is None


def test_list_markers_override_description():
    result = screen_text(
        title="Software Engineer 🛂",
        description="Visa sponsorship is available.",
        markers=("🛂",),
    )
    assert result.sponsorship == "no"
    assert result.notes[0] == "list marker: does not offer sponsorship"


def test_citizenship_and_degree_markers():
    result = screen_text(title="SWE", markers=("🇺🇸", "🎓"))
    assert result.citizenship_required is True
    assert result.advanced_degree is True
    assert result.drop_reason == DROP_CITIZENSHIP


def test_extract_markers_in_config_order():
    assert extract_markers("Engineer 🎓 🛂") == ("🛂", "🎓")
    assert extract_markers("Engineer") == ()
    assert extract_markers(None) == ()


def test_html_to_text_handles_escaped_greenhouse_content():
    escaped = "&lt;p&gt;We &lt;strong&gt;do not&lt;/strong&gt; sponsor visas.&lt;/p&gt;"
    assert html_to_text(escaped) == "We do not sponsor visas."
    assert html_to_text("") == ""
    assert html_to_text("plain\u00a0text") == "plain text"


def test_screen_job_sets_fields_and_returns_reason():
    job = Job(
        company="Acme",
        title="Software Engineer",
        url="https://acme.example/1",
        location="Seattle, WA",
        source="career_page",
        description="2+ years of experience. We are unable to sponsor visas.",
    )
    assert screen_job(job) == DROP_NO_SPONSORSHIP
    assert job.sponsorship == "no"
    assert job.seniority_flag == "borderline"
    assert job.min_years_experience == 2
    assert job.screening_notes == [
        "no sponsorship: 'unable to sponsor'",
        "requires 2+ years of experience",
    ]


def test_screen_job_without_signals_keeps_defaults():
    job = Job("Acme", "Software Engineer", "https://acme.example/2", "Seattle, WA", "list")
    assert screen_job(job) is None
    assert (job.sponsorship, job.seniority_flag, job.screening_notes) == ("unknown", "none", [])


PALANTIR_STYLE_VALUE = (
    "A World-Changing Company\nWe build software.\n"
    "What We Value\n"
    "Willingness to learn and make decisions independently.\n"
    "Active US Security clearance, or eligibility and willingness to obtain a US Security clearance.\n"
    "What We Require\n"
    "Engineering background in fields such as Computer Science.\n"
)
PALANTIR_STYLE_REQUIRE = (
    "What We Require\n"
    "Strong coder with shown proficiency in Java or Go\n"
    "Active US Security clearance, or eligibility and willingness to obtain a US Security clearance\n"
    "Salary\nThe estimated salary range is $135,000 - $145,000/year.\n"
)


def test_clearance_under_a_preference_heading_is_not_required():
    result = screen_text(description=PALANTIR_STYLE_VALUE)
    assert result.clearance_required is False
    assert result.drop_reason is None
    assert result.notes == [
        "security clearance preferred: 'Security clearance'",
    ]


def test_clearance_under_requirements_is_required():
    result = screen_text(description=PALANTIR_STYLE_REQUIRE)
    assert result.clearance_required is True
    assert result.drop_reason == DROP_CLEARANCE


def test_clearance_marked_preferred_in_the_sentence():
    result = screen_text(description="Secret clearance preferred.")
    assert result.clearance_required is False
    assert result.drop_reason is None


def test_experience_under_preferred_qualifications_heading():
    html = (
        "<h3>Minimum Qualifications</h3><ul><li>BS in Computer Science</li>"
        "<li>1+ years of experience</li></ul>"
        "<h3>Preferred Qualifications</h3><ul><li>3+ years of industry experience</li></ul>"
    )
    result = screen_text(description=html_to_text(html))
    assert result.min_years_experience == 1
    assert result.seniority_flag == "none"
    assert "prefers 3+ years of experience" in result.notes


def test_short_requirement_bullets_are_not_mistaken_for_headings():
    text = "Nice to have\nRust\nRequirements\n3+ years of experience\nBonus: Kubernetes\n2+ years of Go experience"
    result = screen_text(description=text)
    assert result.min_years_experience == 3
    assert result.seniority_flag == "borderline"


def test_html_to_text_keeps_block_structure():
    html = "<p>About us</p><p>We <b>build</b> things.</p><ul><li>One</li><li>Two</li></ul>Tail<br>End"
    assert html_to_text(html) == "About us\nWe build things.\nOne\nTwo\nTail\nEnd"
