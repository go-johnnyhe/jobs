# Job Tracker

Automated job tracker for new grad software engineering positions. Sends Discord alerts hourly via GitHub Actions.
Includes source-health alerts when a job source fails repeatedly.

## Monitored Companies

**Big Tech:** Google, Meta, Amazon, Apple, Netflix, Microsoft, Stripe, Block

**Cloud & Infrastructure:** Cloudflare, HashiCorp, Datadog, Confluent, CockroachLabs, PlanetScale, Temporal, Snowflake

**Developer Tools:** GitHub, GitLab, Vercel, Netlify, Supabase, Linear, Replit

**Seattle:** Expedia, Zillow, F5

**Startups:** Airbnb, Rubrik, Fly.io, Railway, Render

## Setup

1. Add `DISCORD_WEBHOOK_URL` to GitHub repository secrets
2. Edit `config.py` to customize companies
3. Runs hourly automatically, or trigger manually from Actions tab

## Commands

```bash
pip install -r requirements.txt  # Install dependencies
python main.py                   # Check for jobs
python main.py --notify              # Check and send Discord alerts
python main.py --notify --dry-run    # Print Discord payload without sending
python main.py --stats               # View statistics
python main.py --audit-sources       # Live-check every career source (no DB/Discord changes)
```

## Development

```bash
pip install -r requirements-dev.txt  # Install dev dependencies (adds pytest)
python -m pytest tests/ -v           # Run all tests
```

## Source reliability

Structured Greenhouse, Lever, Ashby, Workday, SmartRecruiters, and Amazon
adapters are preferred. Generic HTML sources are still checked as a fallback,
but are reported as `DEGRADED` because JavaScript rendering and pagination can
make their coverage incomplete.

## Filtering and storage

Senior titles are always excluded, even when they also contain new-grad words.
Internship exclusions use complete words, so Internal Tools roles remain eligible.
GitHub continuation rows use the preceding company name in the same table.

Each scan stores new jobs in one database transaction. Each successful Discord
batch is then marked as notified in one transaction. Failed batches remain pending.
Dry runs can print notification payloads without a webhook URL. They still store
scan results and source health; they do not mark jobs as notified.

The storage API is `add_jobs(jobs)`, which returns newly stored jobs, and
`mark_notified(jobs)`, which accepts a batch. Source callers use
`fetch_jobs_with_status()`. These replace the former single-job storage calls
and the unused `fetch_jobs()` wrappers. Notification callers use
`send_job_batch()` in place of the removed `notify()` batching method.
