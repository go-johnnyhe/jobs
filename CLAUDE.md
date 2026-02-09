# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
python main.py                # Check for new jobs (no notifications)
python main.py --notify       # Check and send Discord alerts
python main.py --notify --dry-run  # Print Discord payload without sending
python main.py --stats        # View job database statistics
python main.py --list-recent 20  # List 20 most recent jobs
python main.py --skip-github  # Skip GitHub repo source
python main.py --skip-careers # Skip career page scraping
pip install -r requirements.txt      # Install dependencies (requests, beautifulsoup4)
pip install -r requirements-dev.txt  # Install dev dependencies (adds pytest)
python -m pytest tests/ -v           # Run all tests
```

## Architecture

This is an automated new-grad SWE job tracker that scrapes jobs from two source types and sends Discord alerts. It runs hourly via GitHub Actions (`.github/workflows/check-jobs.yml`) with the SQLite database persisted via Actions cache.

### Data Flow

`main.py` orchestrates: **Sources** (fetch jobs) → **Filters** (apply criteria) → **Storage** (deduplicate via SQLite) → **Notifier** (Discord webhook)

### Key Components

- **`models.py`** — Defines the `Job` dataclass used throughout the codebase.
- **`http_client.py`** — `create_session()` factory providing retry-enabled `requests.Session` with exponential backoff on transient HTTP errors (429/5xx). Used by all HTTP consumers.
- **`sources/github_tracker.py`** — Scrapes the SimplifyJobs/New-Grad-Positions GitHub repo. Parses HTML tables from the README. Filters by `TARGET_COMPANIES` list (with length-aware matching for short names), then applies `matches_job_criteria()`.
- **`sources/career_scraper.py`** — Scrapes company career pages directly. Has specialized parsers for ATS platforms (Greenhouse JSON API, Lever JSON API, Workday CXS API) with a generic HTML fallback. Checks `ROLE_KEYWORDS` first, then delegates to shared `matches_job_criteria()`.
- **`filters.py`** — Centralized filtering: seniority exclusion (senior/staff/L4+), title exclusion (non-SWE roles), location blocking (non-US), and preferred location matching. Word-boundary regex matching throughout. `matches_job_criteria()` is the unified filter entry point.
- **`config.py`** — All configuration: `COMPANIES` dict with ATS types, `COMPANY_ALIASES` for GitHub-repo matching, auto-derived `TARGET_COMPANIES`, GitHub repos, keyword lists, location preferences/blocklists, seniority exclusion patterns. This is the primary file to edit when adding companies or adjusting filters.
- **`storage.py`** — SQLite wrapper (`jobs.db`). Deduplication via `unique_id` (company|title|url). Tracks notification status. Indexed on company, first_seen, and notified+first_seen. Also stores source health state for repeated-failure/recovery alerts.
- **`notifier.py`** — Discord webhook integration with embed formatting. Batches in groups of 10 (Discord's embed limit). Status-code retries disabled to avoid duplicate messages. Also sends source failure/recovery alerts.

### Filtering Pipeline

Both sources delegate to shared `matches_job_criteria()` in `filters.py`:
- **GitHubTracker**: Checks company against `TARGET_COMPANIES` first, then calls `matches_job_criteria()`
- **CareerScraper**: Checks `ROLE_KEYWORDS` first, then calls `matches_job_criteria(require_location=True)`

### Environment

- `DISCORD_WEBHOOK_URL` env var (set via GitHub Secrets in CI)
- Python 3.11, dependencies: `requests`, `beautifulsoup4`
- `jobs.db` is gitignored; persisted via GitHub Actions cache in CI
- Source health alerts trigger at configured consecutive-failure thresholds in `SOURCE_FAILURE_ALERT_THRESHOLDS`
- Career source health requires a minimum success rate and count (`CAREERS_MIN_HEALTHY_SUCCESS_RATE`, `CAREERS_MIN_HEALTHY_SUCCESSES`)
- Recovery alerts are pending until successfully sent; a new failure clears pending recovery (treats one-run success blips as non-recovery)
