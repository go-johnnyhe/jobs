"""Tests for config.py — TARGET_COMPANIES auto-derivation."""

from config import (
    COMPANIES,
    COMPANY_ALIASES,
    COMPANY_FAILURE_ALERT_THRESHOLDS,
    PRIORITY_COMPANIES,
    TARGET_COMPANIES,
)


class TestTargetCompaniesDerivation:
    def test_all_company_keys_present(self):
        for name in COMPANIES:
            assert name.lower() in TARGET_COMPANIES, f"{name} missing from TARGET_COMPANIES"

    def test_all_aliases_present(self):
        for aliases in COMPANY_ALIASES.values():
            for alias in aliases:
                assert alias in TARGET_COMPANIES, f"alias '{alias}' missing from TARGET_COMPANIES"

    def test_alias_keys_are_valid_companies(self):
        for key in COMPANY_ALIASES:
            assert key in COMPANIES, f"COMPANY_ALIASES key '{key}' not in COMPANIES"

    def test_critical_aliases(self):
        for alias in ["facebook", "square", "fly.io", "tripactions"]:
            assert alias in TARGET_COMPANIES, f"critical alias '{alias}' missing"

    def test_no_duplicates(self):
        assert len(TARGET_COMPANIES) == len(set(TARGET_COMPANIES))

    def test_priority_companies_are_configured_companies(self):
        for company in PRIORITY_COMPANIES:
            assert company in COMPANIES, f"priority company '{company}' not in COMPANIES"

    def test_company_alert_thresholds_are_single_shot(self):
        assert COMPANY_FAILURE_ALERT_THRESHOLDS == [3]


def test_structured_ats_configs_have_required_identifiers():
    needs_id = {"ashby", "smartrecruiters"}
    for company, config in COMPANIES.items():
        if config.get("ats") in needs_id:
            assert config.get("ats_id"), f"{company} needs an explicit ATS identifier"


def test_corrected_career_sources_use_current_adapters():
    assert COMPANIES["Temporal"]["ats"] == "ashby"
    assert COMPANIES["Temporal"]["ats_id"] == "temporal"
    assert COMPANIES["Twitter"]["ats"] == "smartrecruiters"
    assert COMPANIES["Twitter"]["ats_id"] == "X"
    assert COMPANIES["HRT"]["ats"] == "greenhouse"
    assert COMPANIES["HRT"]["ats_id"] == "wehrtyou"
