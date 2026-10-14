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
python main.py --mode fast # Job lists only (auto: careers every FULL_SCAN_INTERVAL_MINUTES)
python main.py --state-file .state/state.json # Load/save durable JSON state around the run
python main.py --test-assistant-webhook # Send an empty test event to ASSISTANT_WEBHOOK_URL
pip install -r requirements.txt      # Install dependencies (requests, beautifulsoup4)
pip install -r requirements-dev.txt  # Install dev dependencies (adds pytest)
python -m pytest tests/ -v           # Run all tests
```

## Architecture

This is an automated new-grad SWE job tracker that scrapes jobs from two source types and sends Discord alerts plus an optional JSON assistant webhook. It runs via GitHub Actions (`.github/workflows/check-jobs.yml`), triggered by an external scheduler through `repository_dispatch` with an hourly cron fallback. Durable state is `state.json` on the `job-tracker-state` branch (`scripts/state_branch.sh`); the SQLite database is a per-run working copy.

### Data Flow

`main.py` orchestrates: **Sources** (fetch jobs) → **Filters + screening** → **Storage** (deduplicate, baseline new sources) → **Enrichment** (fetch descriptions for new jobs, re-screen) → **Assistant webhook** and **Discord**, each tracked separately

### Key Components

- **`models.py`** — Defines the `Job` dataclass (including screening flags and transient description fields) and `ScrapeResult`.
- **`screening.py`** — Sponsorship/citizenship/clearance/OPT/experience detection from list markers, titles, and descriptions. `screen_job()` sets flags and returns a drop reason. Patterns and switches live in `config.py` (`SCREENING`, `*_PATTERNS`).
- **`sources/list_parsers.py`** — Header-driven HTML and markdown table parsing for job lists (SimplifyJobs, speedyapply). Snapshots in `tests/fixtures/`.
- **`job_keys.py`** — Canonical URLs and cross-source `dedupe_key()` (ATS job IDs, else canonical URL + title).
- **`enrichment.py`** — Fetches Greenhouse/Workday descriptions for newly found jobs.
- **`assistant_notifier.py`** — Batched JSON webhook (`job-tracker.new-jobs.v1`) with bearer auth, idempotency keys, and retries.
- **`state_store.py`** — Atomic load/save of the durable JSON state file.
- **`http_client.py`** — `create_session()` factory providing retry-enabled `requests.Session` with exponential backoff on transient HTTP errors (429/5xx). Used by all HTTP consumers.
- **`sources/github_tracker.py`** — Scrapes the job-list repos in `GITHUB_REPOS` (SimplifyJobs, speedyapply) via `list_parsers`. Filters by `TARGET_COMPANIES` list (with length-aware matching for short names), then applies `matches_job_criteria()`.
- **`sources/career_scraper.py`** — Scrapes company career pages directly. Has specialized parsers for ATS platforms (Greenhouse JSON API, Lever JSON API, Workday CXS API) with a generic HTML fallback. Checks `ROLE_KEYWORDS` first, then delegates to shared `matches_job_criteria()`.
- **`filters.py`** — Centralized filtering: seniority exclusion (senior/staff/L4+), title exclusion (non-SWE roles), location blocking (non-US), and preferred location matching. Word-boundary regex matching throughout. `matches_job_criteria()` is the unified filter entry point.
- **`config.py`** — All configuration: `COMPANIES` dict with ATS types, `COMPANY_ALIASES` for GitHub-repo matching, auto-derived `TARGET_COMPANIES`, GitHub repos, keyword lists, location preferences/blocklists, seniority exclusion patterns. This is the primary file to edit when adding companies or adjusting filters.
- **`storage.py`** — SQLite wrapper (`jobs.db`). Deduplication via `unique_id` (company|title|url) or `dedupe_key`. Per-channel delivery state in `notified` (Discord) and `assistant_notified`: 0 pending, 1 delivered, 2 suppressed (`suppressed_reason`). Source baselines, metadata, export/import of durable state, and pruning. Migrates older databases in place. Indexed on company, first_seen, and notified+first_seen. Also stores source health state for repeated-failure/recovery alerts.
- **`notifier.py`** — Discord webhook integration with embed formatting. Batches in groups of 10 (Discord's embed limit); at most `MAX_PENDING_JOBS_TO_NOTIFY` per run, the rest stay pending. Status-code retries disabled to avoid duplicate messages. Also sends source failure/recovery alerts.

### Filtering Pipeline

Both sources delegate to shared `matches_job_criteria()` in `filters.py`:
- **GitHubTracker**: Checks company against `TARGET_COMPANIES` first, then calls `matches_job_criteria()`, then `screen_job()`
- **CareerScraper**: Checks `ROLE_KEYWORDS` first, then calls `matches_job_criteria(require_location=True)`, then `screen_job()`
- New jobs with a `description_url` are re-screened in `main._process_scan()` after enrichment

### Environment

- `DISCORD_WEBHOOK_URL` env var (set via GitHub Secrets in CI); optional `ASSISTANT_WEBHOOK_URL` / `ASSISTANT_WEBHOOK_KEY`
- Python 3.11, dependencies: `requests`, `beautifulsoup4`
- `jobs.db` and `.state/` are gitignored; CI restores `state.json` from the `job-tracker-state` branch (the Actions cache copy of `jobs.db` is only a migration fallback)
- Source health alerts trigger at configured consecutive-failure thresholds in `SOURCE_FAILURE_ALERT_THRESHOLDS`
- Career source health requires a minimum success rate and count (`CAREERS_MIN_HEALTHY_SUCCESS_RATE`, `CAREERS_MIN_HEALTHY_SUCCESSES`)
- Recovery alerts are pending until successfully sent; a new failure clears pending recovery (treats one-run success blips as non-recovery)

### Maintenance: Career Source URLs

Company career page URLs break regularly as companies redesign their sites. Common failure modes:
- **404s**: URL path changed (most common). Fix by finding the new careers page and updating `config.py`.
- **403s**: Site blocking the scraper. Prefer switching to a direct ATS API (e.g. `boards.greenhouse.io/{board}`) over the company's own careers page.
- **Greenhouse board ID extraction fails**: If the regex can't find the board ID from the page, add the company to the `known_boards` dict in `career_scraper.py` and point the URL directly at `boards.greenhouse.io/{board}`.
- **Workday 400 errors**: Some tenants reject large page sizes. The CXS API limit is set to 20 to avoid this.

To diagnose, write a quick script that loops over `COMPANIES` and calls `scraper._scrape_company()` for each, logging OK/FAIL with error details. Last full audit (Feb 2026) fixed 17/95 broken sources.
