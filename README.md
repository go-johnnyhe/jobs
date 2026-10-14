# Job Tracker

Automated tracker for new grad software engineering positions. It scans
community job lists and company career pages, screens out roles that exclude
visa sponsorship, and delivers new jobs to Discord and (optionally) to an AI
assistant webhook. Runs on GitHub Actions; source-health alerts fire when a
source fails repeatedly.

## Sources

**Job lists:** [SimplifyJobs/New-Grad-Positions](https://github.com/SimplifyJobs/New-Grad-Positions)
(`dev` branch, HTML tables) and
[speedyapply/2027-SWE-College-Jobs](https://github.com/speedyapply/2027-SWE-College-Jobs)
(`NEW_GRAD_USA.md`, markdown tables). Jobs from lists are kept only for
companies in `COMPANIES` / `COMPANY_ALIASES`.

**Career pages** (111 companies), including:

- **Big Tech:** Google, Meta, Amazon, Apple, Netflix, Microsoft, Stripe, Block
- **Cloud & Infrastructure:** Cloudflare, HashiCorp, Datadog, Confluent, CockroachLabs, PlanetScale, Temporal, Snowflake
- **Developer Tools:** GitHub, GitLab, Vercel, Netlify, Supabase, Linear, Replit
- **Seattle area:** Expedia, Zillow, F5, Redfin, Remitly, T-Mobile, Smartsheet, Tanium, Nintendo, Truveta, Outreach, Qumulo
- **Startups:** Airbnb, Rubrik, Fly.io, Railway, Render

See `config.py` for the full list.

## Setup

### Secrets

Add these under **Settings → Secrets and variables → Actions → Repository secrets**:

| Secret | Required | Purpose |
| --- | --- | --- |
| `DISCORD_WEBHOOK_URL` | yes | Discord channel webhook |
| `ASSISTANT_WEBHOOK_URL` | no | HTTPS endpoint that receives new jobs as JSON. Unset = skipped quietly |
| `ASSISTANT_WEBHOOK_KEY` | no | Shared secret sent as `Authorization: Bearer <key>` and `X-Webhook-Key: <key>` |

The workflow needs `contents: write` (declared in the workflow) to push the
`job-tracker-state` branch. If a branch ruleset covers all branches, exclude
`job-tracker-state` or allow GitHub Actions to push to it.

### Frequent runs (external scheduler)

GitHub's own `schedule` trigger is best-effort: on this repository it has
fired every 3–7 hours rather than hourly. The workflow keeps an hourly cron as
a fallback, but for 15–30 minute checks trigger it from an external scheduler
with `repository_dispatch`:

1. Create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new):
   resource owner `go-johnnyhe`, **Only select repositories → jobs**,
   repository permission **Contents: Read and write** (Metadata: Read is added
   automatically). Pick an expiration and note it.
2. At [cron-job.org](https://cron-job.org) create a job:
   - URL: `https://api.github.com/repos/go-johnnyhe/jobs/dispatches`
   - Schedule: every 15 minutes (or 30)
   - Advanced → Request method: `POST`
   - Headers:
     - `Authorization: Bearer <token>`
     - `Accept: application/vnd.github+json`
     - `X-GitHub-Api-Version: 2022-11-28`
     - `Content-Type: application/json`
   - Request body: `{"event_type": "check-jobs", "client_payload": {"mode": "auto"}}`
3. Test it from cron-job.org ("Test run"): GitHub answers `204 No Content`
   and a run appears under **Actions → Check for New Jobs**.

Equivalent curl:

```bash
curl -X POST https://api.github.com/repos/go-johnnyhe/jobs/dispatches \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -d '{"event_type":"check-jobs","client_payload":{"mode":"auto"}}'
```

`repository_dispatch` runs the workflow from the default branch. Runs share a
concurrency group, so overlapping triggers queue instead of racing. The
repository is public, so Actions minutes are free.

### Scan modes

| Mode | What it scans |
| --- | --- |
| `auto` (scheduled/dispatch default) | Job lists every run; career pages when the last career scan is older than `FULL_SCAN_INTERVAL_MINUTES` (120) |
| `fast` | Job lists only (about 10 seconds) |
| `full` | Job lists and all career pages (a few minutes) |

Pick a mode for a manual run under **Actions → Check for New Jobs → Run
workflow**, or set `client_payload.mode` in the dispatch body.

## Assistant webhook

New jobs are POSTed as JSON, at most `ASSISTANT_BATCH_SIZE` (25) per request:

```json
{
  "schema": "job-tracker.new-jobs.v1",
  "event": "new_jobs",
  "run_timestamp": "2026-10-14T18:30:05Z",
  "batch": {"id": "3f9c…", "index": 0, "count": 1, "size": 1, "total_jobs": 1, "pending_after_run": 0},
  "jobs": [
    {
      "id": "a1b2c3d4e5f6a7b8c9d0",
      "title": "Software Engineer, New Grad",
      "company": "Remitly",
      "location": "Seattle, WA",
      "url": "https://remitly.wd5.myworkdayjobs.com/Remitly_Careers/job/…",
      "source": "career_page",
      "posted_date": "2026-10-13",
      "first_seen": "2026-10-14T18:29:51Z",
      "sponsorship": "unknown",
      "seniority_flag": "none",
      "min_years_experience": null,
      "screening_notes": []
    }
  ]
}
```

- `sponsorship` is `yes` (posting says it sponsors), `no` (only possible when
  the matching drop rule is disabled), or `unknown`.
- `seniority_flag` is `none`, `borderline` (asks for 2–4 years), or `senior`
  (5+ years; kept unless `drop_senior_experience` is enabled).
- `screening_notes` quote the phrases that set the flags.
- `id` is stable per job and `batch.id` (also sent as the `Idempotency-Key`
  header) is stable per batch, so the receiver can drop retried duplicates.
- Any 2xx response marks the batch delivered. 408, 429 and 5xx responses and
  connection errors are retried up to 4 attempts with exponential backoff
  (2 s, 4 s, 8 s), honoring `Retry-After` up to 60 s. Other 4xx responses are
  not retried. Undelivered jobs stay pending and are retried on the next run
  for up to `ASSISTANT_MAX_PENDING_AGE_HOURS` (one week).

Send a test event with `python main.py --test-assistant-webhook`.

Delivery to Discord and to the assistant is tracked separately: one channel
failing does not block or duplicate the other. A run where either channel
fails exits non-zero so it shows up as a failed Action.

## Sponsorship and seniority screening

Signals come from SimplifyJobs markers (🛂 does not offer sponsorship, 🇺🇸
requires U.S. citizenship, 🎓 advanced degree) and from description text for
Lever and Ashby (included in their APIs) and Greenhouse and Workday (fetched
for new jobs only, at most `max_description_fetches_per_run`).

Jobs are dropped when they clearly state they will not sponsor visas, require
U.S. citizenship or permanent residency, require a security clearance, or
exclude F-1/J-1/OPT/CPT candidates. Negated phrases ("no security clearance
required") and statements of sponsorship ("we sponsor visas") are not treated
as exclusions; postings with conflicting statements are kept as `unknown`.
Experience requirements are flagged, not dropped. Every rule, threshold, and
pattern is in `SCREENING` and the `*_PATTERNS` lists in `config.py`.

## State and delivery guarantees

The SQLite database is a per-run working copy. The durable record is
`state.json` on the `job-tracker-state` branch: the workflow restores it
before each run and commits it back afterward (even when the run fails),
using a non-force push so concurrent writers cannot silently overwrite each
other. Jobs are written one per line, so each commit shows exactly which jobs
changed.

- A job is marked delivered on a channel only after that channel accepted it.
- Discord sends at most `MAX_PENDING_JOBS_TO_NOTIFY` (50) jobs per run, oldest
  first; the rest stay pending for the next run and the first message says
  how many are queued.
- The same posting found on several lists or career pages is recognized by
  its ATS job ID (Greenhouse, Lever, Ashby, Workday, Amazon, SmartRecruiters,
  Google) or canonical URL plus title, and is sent once.
- The first scan of a new source with more than `NEW_SOURCE_BASELINE_MAX_JOBS`
  (5) unseen jobs is recorded without notifying, so adding a list does not
  flood Discord. A brand-new install records everything on its first run.
- Jobs no longer listed for `STATE_RETENTION_DAYS` (180) are pruned.

**Migration from the cache-only setup:** on the first run the state branch
does not exist yet, so the workflow restores the last `jobs.db` from the
Actions cache. Existing rows are migrated in place: their Discord status is
kept, they are not replayed to the assistant, and every source that already
had jobs counts as scanned. That run creates the state branch; the cache is
only a fallback afterward. If neither exists, the run is treated as a fresh
install.

## Commands

```bash
pip install -r requirements.txt     # Install dependencies
python main.py                      # Check for jobs (stores them as pending)
python main.py --notify             # Check and deliver to Discord and the assistant webhook
python main.py --notify --dry-run   # Print payloads without sending or marking anything
python main.py --mode fast          # Job lists only (also: auto, full)
python main.py --state-file .state/state.json  # Load/save durable state around the run
python main.py --skip-baseline      # Treat jobs from never-scanned sources as new
python main.py --stats              # View statistics
python main.py --list-recent 20     # List recent jobs with delivery and screening status
python main.py --test-webhook       # Send a Discord test message
python main.py --test-assistant-webhook  # Send an empty test event to the assistant
python main.py --audit-sources      # Live-check every career source (no DB/Discord changes)
```

## Development

```bash
pip install -r requirements-dev.txt  # Install dev dependencies (adds pytest)
python -m pytest tests/ -v           # Run all tests
```

The **Tests** workflow runs the suite on every push and pull request.
`tests/fixtures/` holds trimmed real snapshots of the SimplifyJobs HTML README,
its earlier markdown README, and the speedyapply list; refresh them when a list
changes format.

## Source reliability

Structured Greenhouse, Lever, Ashby, Workday, SmartRecruiters, and Amazon
adapters are preferred. Generic HTML sources are still checked as a fallback,
but are reported as `DEGRADED` because JavaScript rendering and pagination can
make their coverage incomplete.

## Filtering

Senior titles are always excluded, even when they also contain new-grad words.
Internship exclusions use complete words, so Internal Tools roles remain eligible.
List continuation rows (`↳`) use the preceding company name in the same table.
