"""Tests for config.py — TARGET_COMPANIES auto-derivation."""

import pytest

from config import COMPANIES, COMPANY_ALIASES, TARGET_COMPANIES


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

    def test_sorted(self):
        assert TARGET_COMPANIES == sorted(TARGET_COMPANIES)


class TestShortNameMatching:
    """Test that the length-aware matching in github_tracker works correctly."""

    def test_exact_match_for_short_names(self):
        """Short targets (len <= 2) should only match exact company names."""
        # Simulate the matching logic from github_tracker._matches_criteria
        def matches(company_name):
            company_lower = company_name.lower()
            return any(
                (company_lower == target if len(target) <= 2 else target in company_lower)
                for target in TARGET_COMPANIES
            )

        # "f5" is in TARGET_COMPANIES and should match "F5" exactly
        assert matches("F5") is True
        # "f5" should NOT match "Flexport" (substring match blocked for short targets)
        assert matches("Flexport") is False

    def test_substring_match_for_long_names(self):
        """Longer targets should still use substring matching."""
        def matches(company_name):
            company_lower = company_name.lower()
            return any(
                (company_lower == target if len(target) <= 2 else target in company_lower)
                for target in TARGET_COMPANIES
            )

        # "cockroach" alias should match "CockroachLabs"
        assert matches("CockroachLabs") is True
        # "epic games" should match "Epic Games"
        assert matches("Epic Games") is True
