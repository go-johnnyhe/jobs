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
through the `workflow_dispatch` API:

1. Create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new):
   resource owner `go-johnnyhe`, **Only select repositories → jobs**,
   repository permission **Actions: Read and write** and nothing else
   (Metadata: Read is added automatically). The token can start workflows but
   cannot read or change code. Pick an expiration and note it.
2. At [cron-job.org](https://cron-job.org) create a job:
   - URL: `https://api.github.com/repos/go-johnnyhe/jobs/actions/workflows/check-jobs.yml/dispatches`
   - Schedule: every 15 minutes (or 30)
   - Advanced → Request method: `POST`
   - Headers:
     - `Authorization: Bearer <token>`
     - `Accept: application/vnd.github+json`
     - `X-GitHub-Api-Version: 2022-11-28`
     - `Content-Type: application/json`
   - Request body: `{"ref":"main","inputs":{"mode":"auto"}}`
3. Test it from cron-job.org ("Test run"): GitHub answers `204 No Content`
   and a run appears under **Actions → Check for New Jobs**. A `422` that
   mentions `mode` means the `main` branch does not have this workflow's
   `mode` input yet; a `403` or `404` means the token lacks Actions: write on
   this repository.

Equivalent curl:

```bash
curl -X POST https://api.github.com/repos/go-johnnyhe/jobs/actions/workflows/check-jobs.yml/dispatches \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -d '{"ref":"main","inputs":{"mode":"auto"}}'
```

Runs share a concurrency group, so overlapping triggers queue instead of
racing. The repository is public, so Actions minutes are free.

### Scan modes

| Mode | What it scans |
| --- | --- |
| `auto` (scheduled/dispatch default) | Job lists every run; career pages when the last career scan is older than `FULL_SCAN_INTERVAL_MINUTES` (120) |
| `fast` | Job lists only (about 10 seconds) |
| `full` | Job lists and all career pages (a few minutes) |

Pick a mode for a manual run under **Actions → Check for New Jobs → Run
workflow**, or set `inputs.mode` in the dispatch body.

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
  (2 s, 4 s, 8 s), honoring `Retry-After` up to 60 s. Undelivered jobs stay
  pending and are retried on the next run for up to
  `ASSISTANT_MAX_PENDING_AGE_HOURS` (one week).
- A 400, 413, or 422 response is treated as a rejection of the batch's
  content: the batch is split in half and each half is resent, down to single
  jobs, so one bad job does not hold back the others. A job rejected on its
  own on `ASSISTANT_MAX_REJECTIONS` (3) runs is retired with the reason
  `assistant_rejected:HTTP <status>` (shown by `--list-recent`). If the
  webhook rejects every job in a run and accepts none, the receiver is
  treated as broken rather than the jobs: nothing is counted and every job
  stays pending. Other failures (401, 403, 404, retries exhausted) stop
  assistant delivery for that run and leave everything pending.
- Discord is sent first. The assistant starts no new batch after
  `ASSISTANT_MAX_SECONDS_PER_RUN` (300 s), so long `Retry-After` waits
  cannot reach the step timeout; the rest stays pending.
- Webhook errors are logged as the exception type and HTTP status only, so
  webhook URLs, keys, and response bodies never appear in Action logs.
- Assistant failures (including a crash of the assistant step) do not fail
  the run. They are tracked like a failing source named `assistant_webhook`:
  a Discord alert after 3, 6, and 12 failed runs, and a recovery message
  when it works again.

Send a test event with `python main.py --test-assistant-webhook`.

Delivery to Discord and to the assistant is tracked separately: one channel
failing does not block or duplicate the other. A run where Discord fails
exits non-zero so it shows up as a failed Action.

## Sponsorship and seniority screening

Signals come from SimplifyJobs markers (🛂 does not offer sponsorship, 🇺🇸
requires U.S. citizenship, 🎓 advanced degree) and from description text for
Lever and Ashby (included in their APIs) and Greenhouse and Workday (fetched
for new jobs only, at most `max_description_fetches_per_run`).

Jobs are dropped when they clearly state they will not sponsor work visas,
require U.S. citizenship or permanent residency (including ITAR "U.S. person"
requirements), require a security clearance, or exclude F-1 OPT/CPT
candidates. To avoid false drops from boilerplate:

- "Sponsor" only counts when the same sentence has an immigration word (visa,
  H-1B, work authorization, immigration, citizenship, OPT/CPT, or
  "sponsorship" itself), so "unable to sponsor relocation costs" is ignored.
  Export-control footers ("may require sponsorship of an export license")
  are ignored even though they say "sponsorship".
- The EPPA footer ("Employee Polygraph Protection Act") and EEO statements
  ("citizens and permanent residents are encouraged to apply") are ignored;
  "citizens, permanent residents, or anyone authorized to work (including
  F-1 OPT)" is not a citizenship requirement.
- A posting that refuses visa sponsorship but accepts OPT/STEM OPT or CPT
  is still dropped, because the job would need H-1B sponsorship once OPT
  ends. Set `drop_no_sponsorship_with_opt` to `False` to keep those as
  `unknown` with a note. J-1-only statements are ignored.
- "Preferred" downgrades only the requirement it is attached to, so "TS/SCI
  required; Python preferred" still drops.
- Negated phrases ("no security clearance required") and statements of
  sponsorship ("we sponsor visas") are not treated as exclusions; postings
  with conflicting statements are kept as `unknown`.

Experience requirements are flagged, not dropped. Every rule, threshold, and
pattern is in `SCREENING` and the `*_PATTERNS` lists in `config.py`.

Screened-out jobs record a `screening_version` (a hash of those rules). When
the rules change, previously dropped jobs that are still listed are screened
again on the next run, and jobs that now pass are queued for both channels.

List companies match `COMPANIES` / `COMPANY_ALIASES` by whole leading words
plus corporate suffixes (Inc, LLC, Labs, AI, Technologies, ...), so "Snap Inc"
matches Snap but "Snap Finance", "Coherent", and "City of San Francisco" do
not match Snap, Cohere, or Cisco.

## State and delivery guarantees

The SQLite database is a per-run working copy. The durable record is
`state.json` on the `job-tracker-state` branch: the workflow restores it
before each run and commits it back afterward (even when the run fails),
using a non-force push so concurrent writers cannot silently overwrite each
other. Jobs are written one per line, so each commit shows exactly which jobs
changed, and a run that changes nothing writes an identical file and makes no
commit.

- If the push is rejected because another run pushed first, the script
  fetches the branch, merges the two state files (a delivered mark on either
  side wins), and pushes again. It never force-pushes and stops with an error
  if the remote file cannot be merged.
- The state file is rewritten after every delivered Discord or assistant
  batch, so a run that times out or is cancelled still saves what it sent.
  The tracker step has a 15-minute timeout inside the 20-minute job so the
  save step always gets to run.
- A job is marked delivered on a channel only after that channel accepted it.
- Discord sends at most `MAX_PENDING_JOBS_TO_NOTIFY` (50) jobs per run, oldest
  first; the rest stay pending for the next run and the first message says
  how many are queued.
- A batch Discord refuses (HTTP 400 or 413, such as an embed it will not
  accept) is split in half and resent down to single jobs. A job refused on
  its own on `DISCORD_MAX_REJECTIONS` (3) runs is retired with the reason
  `discord_rejected:HTTP <status>`, so one bad job cannot stop every later
  job. Rate limits, outages, and auth errors stop that run's delivery and
  leave everything pending.
- The same posting found on several lists or career pages is recognized by
  its ATS job ID (Greenhouse, Lever, Ashby, Workday, Amazon, SmartRecruiters,
  Google) or canonical URL plus title, and is sent once.
- The first scan of a new source with more than `NEW_SOURCE_BASELINE_MAX_JOBS`
  (5) unseen jobs is recorded without notifying, so adding a list does not
  flood Discord. A brand-new install records everything on its first run the
  same way. In both cases, jobs posted within
  `BASELINE_DELIVER_POSTED_WITHIN_HOURS` (48) are still delivered.
- Each job list has its own health record, so one broken list does not mark
  the others unhealthy. The career-page scan time is recorded only when the
  career scan was healthy; otherwise the next `auto` run retries it.
- Jobs no longer listed for `STATE_RETENTION_DAYS` (180) are pruned.

**Migration from the cache-only setup:** on the first run the state branch
does not exist yet, so the workflow restores the last `jobs.db` from the
Actions cache. Existing rows are migrated in place: their Discord status is
kept, they are not replayed to the assistant, and every source that already
had jobs counts as scanned. Their last-listed date starts at the migration,
so the 180-day pruning cannot delete (and later resend) old jobs whose
source failed on that first run. That run creates the state branch. The workflow
no longer saves to the cache; the old cache entry is only read when the
state branch is missing. If neither exists, the run is treated as a fresh
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

The **Tests** workflow runs the suite on pull requests and pushes to `main`.
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
