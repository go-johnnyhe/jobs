#!/usr/bin/env python3
"""Job Tracker - Main entry point."""

import argparse
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
import re
import sys
import traceback
from typing import Callable, Optional

from sources import GitHubTracker, CareerScraper
from storage import JobStorage, PENDING, SUPPRESSED
from notifier import DiscordNotifier, MAX_EMBEDS_PER_MESSAGE
from assistant_notifier import AssistantNotifier
from enrichment import enrich_descriptions
from http_client import describe_request_error
from job_keys import dedupe_key
from models import Job
from posted_dates import normalize_posted_date
from screening import SCREENING_VERSION, screen_job
from state_store import load_state_file, save_state_file
from config import (
    ASSISTANT_MAX_JOBS_PER_RUN,
    ASSISTANT_MAX_PENDING_AGE_HOURS,
    ASSISTANT_MAX_REJECTIONS,
    BASELINE_DELIVER_POSTED_WITHIN_HOURS,
    COMPANY_FAILURE_ALERT_THRESHOLDS,
    DISCORD_MAX_PENDING_AGE_HOURS,
    ENABLE_COMPANY_HEALTH_ALERTS,
    FULL_SCAN_INTERVAL_MINUTES,
    MAX_PENDING_JOBS_TO_NOTIFY,
    NEW_SOURCE_BASELINE_MAX_JOBS,
    PRIORITY_COMPANIES,
    SCREENING,
    SOURCE_FAILURE_ALERT_THRESHOLDS,
    STATE_RETENTION_DAYS,
)

META_LAST_FULL_SCAN = "last_full_scan_at"
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
META_FRESH_INSTALL = "fresh_install"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _deduplicate_scan_jobs(jobs: list) -> list:
    """Keep one record per posting and prefer direct career sources."""
    selected = {}
    order = []
    for job in jobs:
        key = dedupe_key(job.url, job.title) or job.unique_id
        existing = selected.get(key)
        if existing is None:
            selected[key] = job
            order.append(key)
        elif existing.source != "career_page" and job.source == "career_page":
            selected[key] = job
    return [selected[key] for key in order]


def _format_age_hours(age_hours: int | None) -> str:
    """Format an hour count for stats output."""
    if age_hours is None:
        return "N/A"

    days, hours = divmod(max(age_hours, 0), 24)
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h"


def _update_source_health(storage: JobStorage, notifier: DiscordNotifier, source_statuses: list, *, notify: bool, dry_run: bool):
    """Update aggregate source health and emit alerts if configured."""
    for source_name, healthy, error in source_statuses:
        if healthy:
            recovered_after = storage.record_source_success(
                source_name,
                alert_thresholds=SOURCE_FAILURE_ALERT_THRESHOLDS,
            )
            if recovered_after and notify:
                print(f"Source recovered: {source_name} (after {recovered_after} failed runs)")
                sent = notifier.notify_source_recovery(
                    source_name,
                    recovered_after,
                    dry_run=dry_run,
                )
                if sent and not dry_run:
                    storage.confirm_source_recovery_alert(source_name)
        else:
            failures, alert_threshold = storage.record_source_failure(
                source_name,
                error or "unknown source failure",
                alert_thresholds=SOURCE_FAILURE_ALERT_THRESHOLDS,
            )
            print(f"Source failure recorded: {source_name} ({failures} consecutive)")
            if alert_threshold and notify:
                sent = notifier.notify_source_failure(
                    source_name,
                    failures,
                    error or "unknown source failure",
                    dry_run=dry_run,
                )
                if sent and not dry_run:
                    storage.confirm_source_failure_alert(source_name, alert_threshold)


def _update_company_health(
    storage: JobStorage,
    notifier: DiscordNotifier,
    company_results: dict,
    *,
    notify: bool,
    dry_run: bool,
):
    """Update company-level health tracking for career-page scrapes."""
    for company_name, result in company_results.items():
        if result.healthy:
            recovered_after = storage.record_company_success(
                company_name,
                alert_thresholds=COMPANY_FAILURE_ALERT_THRESHOLDS,
            )
            # Company health is diagnostic data. Do not send recovery messages
            # for individual companies because they create Discord noise.
            if recovered_after:
                storage.confirm_company_recovery_alert(company_name)
        else:
            failures, alert_threshold = storage.record_company_failure(
                company_name,
                result.error or "unknown company scrape failure",
                alert_thresholds=COMPANY_FAILURE_ALERT_THRESHOLDS,
            )
            print(f"Company failure recorded: {company_name} ({failures} consecutive)")
            if (
                alert_threshold
                and notify
                and ENABLE_COMPANY_HEALTH_ALERTS
                and company_name in PRIORITY_COMPANIES
            ):
                sent = notifier.notify_company_failure(
                    company_name,
                    failures,
                    result.error or "unknown company scrape failure",
                    dry_run=dry_run,
                )
                if sent and not dry_run:
                    storage.confirm_company_failure_alert(
                        company_name,
                        alert_threshold,
                    )


def _send_pending_notifications(
    storage: JobStorage,
    notifier: DiscordNotifier,
    *,
    dry_run: bool,
    checkpoint: Callable[[], None] = lambda: None,
):
    """Send pending Discord notifications oldest-first and mark only sent batches.

    At most MAX_PENDING_JOBS_TO_NOTIFY jobs go out per run. The rest stay
    pending for later runs; nothing is marked notified unless it was sent.
    """
    if DISCORD_MAX_PENDING_AGE_HOURS is not None and not dry_run:
        retired = storage.retire_stale_pending("discord", DISCORD_MAX_PENDING_AGE_HOURS)
        if retired:
            print(f"Retired {retired} Discord job(s) pending longer than {DISCORD_MAX_PENDING_AGE_HOURS}h")
    pending_jobs = storage.get_unnotified()
    if not pending_jobs:
        print("No new or pending jobs to notify about")
        return True

    jobs_to_send = pending_jobs[:MAX_PENDING_JOBS_TO_NOTIFY]
    queued_after = len(pending_jobs) - len(jobs_to_send)
    if queued_after:
        print(
            f"Pending backlog has {len(pending_jobs)} job(s); sending the oldest "
            f"{len(jobs_to_send)} now and keeping {queued_after} pending for later runs"
        )

    print(f"Sending Discord notifications for {len(jobs_to_send)} pending job(s)...")
    sent_jobs = 0

    for batch_index, start in enumerate(range(0, len(jobs_to_send), MAX_EMBEDS_PER_MESSAGE)):
        batch = jobs_to_send[start:start + MAX_EMBEDS_PER_MESSAGE]
        sent = notifier.send_job_batch(
            batch,
            total_jobs=len(jobs_to_send),
            batch_index=batch_index,
            dry_run=dry_run,
            queued_after=queued_after,
        )
        if not sent:
            remaining = len(pending_jobs) - sent_jobs
            print(
                f"Stopped after failed batch {batch_index + 1}; "
                f"{remaining} job(s) remain pending"
            )
            return False

        if not dry_run:
            storage.mark_notified(batch)
            checkpoint()
        sent_jobs += len(batch)

    if dry_run:
        print("Dry run complete; pending jobs were not marked as notified")
    else:
        print(f"Marked {sent_jobs} job(s) as notified")
        if queued_after:
            print(f"{queued_after} job(s) remain pending for the next run")
    return True


def _send_assistant_notifications(
    storage: JobStorage,
    assistant: AssistantNotifier,
    *,
    dry_run: bool,
    run_timestamp: str,
    checkpoint: Callable[[], None] = lambda: None,
) -> bool:
    """Deliver pending jobs to the assistant webhook, independently of Discord.

    checkpoint runs after every batch whose outcome was recorded, so a run
    killed midway still persists what it delivered.
    """
    if not dry_run:
        retired = storage.retire_stale_pending("assistant", ASSISTANT_MAX_PENDING_AGE_HOURS)
        if retired:
            print(
                f"Retired {retired} assistant job(s) pending longer than "
                f"{ASSISTANT_MAX_PENDING_AGE_HOURS}h"
            )
    if not assistant.configured and not dry_run:
        print("Assistant webhook not configured (ASSISTANT_WEBHOOK_URL); skipping")
        return True

    pending_jobs = storage.get_pending("assistant")
    if not pending_jobs:
        print("No pending jobs for the assistant webhook")
        return True

    jobs_to_send = pending_jobs[:ASSISTANT_MAX_JOBS_PER_RUN]
    queued_after = len(pending_jobs) - len(jobs_to_send)
    batches = assistant.batches(jobs_to_send)
    print(
        f"Sending {len(jobs_to_send)} job(s) to the assistant webhook "
        f"in {len(batches)} batch(es)..."
    )
    sent_jobs = 0
    rejected = 0
    queue = deque(enumerate(batches))
    while queue:
        batch_index, batch = queue.popleft()
        payload = assistant.build_payload(
            batch,
            run_timestamp=run_timestamp,
            batch_index=batch_index,
            batch_count=len(batches),
            total_jobs=len(jobs_to_send),
            pending_after_run=queued_after,
        )
        result = assistant.deliver(payload, dry_run=dry_run)
        if result.ok:
            if not dry_run:
                storage.mark_delivered("assistant", batch)
                checkpoint()
            sent_jobs += len(batch)
            continue
        if result.content_rejected and len(batch) > 1:
            middle = len(batch) // 2
            print(
                f"Assistant batch {batch_index + 1} was rejected (HTTP {result.status}); "
                f"retrying its {len(batch)} job(s) in two smaller batches"
            )
            queue.extendleft([(batch_index, batch[middle:]), (batch_index, batch[:middle])])
            continue
        if result.content_rejected:
            rejected += 1
            job = batch[0]
            retired = storage.record_assistant_rejection(
                job, result.status, ASSISTANT_MAX_REJECTIONS,
            )
            checkpoint()
            outcome = (
                f"retired after {ASSISTANT_MAX_REJECTIONS} rejections" if retired
                else "kept pending for the next run"
            )
            print(
                f"Assistant webhook rejected {job['company']} - {job['title']} "
                f"(HTTP {result.status}); {outcome}"
            )
            continue
        print(
            f"Assistant batch {batch_index + 1} failed; "
            f"{len(pending_jobs) - sent_jobs} job(s) remain pending for the assistant"
        )
        return False

    if dry_run:
        print("Dry run complete; assistant jobs were not marked as delivered")
    else:
        print(f"Delivered {sent_jobs} job(s) to the assistant webhook")
    if rejected:
        print(f"{rejected} job(s) were rejected by the assistant webhook")
    return not rejected


def _resolve_scan_plan(args, storage: JobStorage, now: datetime) -> tuple[bool, bool, str]:
    """Return (scan_lists, scan_careers, description) for this run."""
    scan_lists = not args.skip_github
    if args.mode == "fast":
        return scan_lists, False, "fast (job lists only)"
    if args.mode == "auto" and not args.skip_careers:
        last_full = storage.get_meta(META_LAST_FULL_SCAN)
        due = True
        if last_full:
            try:
                last = datetime.fromisoformat(last_full.replace("Z", "+00:00"))
                due = now - last >= timedelta(minutes=FULL_SCAN_INTERVAL_MINUTES)
            except ValueError:
                due = True
        if not due:
            return scan_lists, False, (
                f"auto: fast (last career scan {last_full}; "
                f"full scan every {FULL_SCAN_INTERVAL_MINUTES} min)"
            )
        return scan_lists, True, "auto: full (career scan due)"
    scan_careers = not args.skip_careers
    return scan_lists, scan_careers, "full" if scan_careers else "lists only"


def _classify_new_jobs(
    new_jobs: list[Job],
    *,
    baselined_units: set[str],
    fresh_install: bool,
    threshold: int,
    skip_baseline: bool,
    now: Optional[datetime] = None,
) -> tuple[list[Job], list[Job], dict[str, int]]:
    """Split new jobs into (to deliver, to record silently as baseline).

    A unit that was never scanned before is baselined when this is a fresh
    install, or when it suddenly yields more than threshold unseen jobs (a
    newly added list). Smaller first batches, such as a new company with two
    open new-grad roles, are delivered normally. Jobs in a baselined batch
    that were posted within BASELINE_DELIVER_POSTED_WITHIN_HOURS are still
    delivered, since they are new postings rather than backlog.
    """
    recent_since = (
        (now or _utc_now()) - timedelta(hours=BASELINE_DELIVER_POSTED_WITHIN_HOURS)
    ).date().isoformat()
    by_unit: dict[str, list[Job]] = defaultdict(list)
    for job in new_jobs:
        by_unit[job.unit_key].append(job)
    deliver, baseline = [], []
    baselined_counts = {}
    for unit, jobs in by_unit.items():
        if (
            not skip_baseline
            and unit not in baselined_units
            and (fresh_install or len(jobs) > threshold)
        ):
            for job in jobs:
                posted = normalize_posted_date(job.date_posted, now=now)
                if posted and _ISO_DATE_RE.match(posted) and posted >= recent_since:
                    deliver.append(job)
                else:
                    baseline.append(job)
                    baselined_counts[unit] = baselined_counts.get(unit, 0) + 1
        else:
            deliver.extend(jobs)
    return deliver, baseline, baselined_counts


def _scanned_units(github_tracker, career_scraper) -> set[str]:
    units = set()
    if github_tracker is not None:
        units.update(
            repo for repo, result in github_tracker.last_repo_results.items()
            if result.scanned
        )
    if career_scraper is not None:
        units.update(
            f"careers:{company}"
            for company, result in career_scraper.last_company_results.items()
            if result.scanned
        )
    return units


def _process_scan(
    storage: JobStorage,
    all_jobs: list[Job],
    *,
    scanned_units: set[str],
    skip_baseline: bool,
    summary: dict,
) -> list[Job]:
    """Deduplicate, baseline, enrich, screen, and store a scan. Returns jobs queued for delivery."""
    deduplicated_jobs = _deduplicate_scan_jobs(all_jobs)
    summary["duplicates_in_scan"] = len(all_jobs) - len(deduplicated_jobs)
    if summary["duplicates_in_scan"]:
        print(f"  Removed {summary['duplicates_in_scan']} duplicate listing(s) from this scan")
    new_jobs, known_jobs = storage.partition_new(deduplicated_jobs)
    summary["unique"] = len(deduplicated_jobs)
    summary["already_known"] = len(known_jobs)
    summary["new"] = len(new_jobs)

    deliver, baseline, baselined_counts = _classify_new_jobs(
        new_jobs,
        baselined_units=storage.baselined_units(),
        fresh_install=storage.get_meta(META_FRESH_INSTALL) == "1",
        threshold=NEW_SOURCE_BASELINE_MAX_JOBS,
        skip_baseline=skip_baseline,
    )
    summary["baselined"] = baselined_counts
    rescreen = storage.stale_screened_out(known_jobs, SCREENING_VERSION)

    if SCREENING["fetch_descriptions"] and (deliver or rescreen):
        # New jobs come first, so they get the per-run fetch budget before re-screens.
        counts = enrich_descriptions(
            deliver + rescreen,
            max_fetches=SCREENING["max_description_fetches_per_run"],
        )
        summary["descriptions"] = counts
        if counts["candidates"]:
            print(
                f"  Fetched {counts['fetched']}/{counts['candidates']} job description(s)"
                f" ({counts['failed']} failed, {counts['skipped']} over the per-run limit)"
            )

    screened_out: dict[str, list[Job]] = defaultdict(list)
    queued = []
    for job in deliver:
        if job.description_url and job.description:
            reason = screen_job(job)
            if reason:
                screened_out[reason].append(job)
                print(
                    f"  Screened out after description fetch: {job.company} - {job.title}"
                    f" ({job.screening_notes[0] if job.screening_notes else reason})"
                )
                continue
        queued.append(job)
    summary["screened_after_fetch"] = {reason: len(jobs) for reason, jobs in screened_out.items()}
    dropped = {id(job) for jobs in screened_out.values() for job in jobs}
    summary["flags"] = _flag_counts([job for job in deduplicated_jobs if id(job) not in dropped])

    storage.add_jobs(
        baseline,
        discord_state=SUPPRESSED,
        assistant_state=SUPPRESSED,
        suppressed_reason="baseline",
    )
    for reason, jobs in screened_out.items():
        storage.add_jobs(
            jobs,
            discord_state=SUPPRESSED,
            assistant_state=SUPPRESSED,
            suppressed_reason=f"screened_out:{reason}",
            screening_version=SCREENING_VERSION,
        )
    stored = storage.add_jobs(queued, discord_state=PENDING, assistant_state=PENDING)
    storage.add_jobs(known_jobs)
    storage.mark_baselined(scanned_units)
    requeued = _rescreen_known(storage, rescreen)
    summary["requeued"] = len(requeued)
    summary["queued"] = len(stored) + len(requeued)
    return stored + requeued


def _rescreen_known(storage: JobStorage, jobs: list[Job]) -> list[Job]:
    """Re-screen jobs dropped by an older screening version; queue the ones now kept.

    A job whose description could not be fetched this run keeps its old
    version and is tried again on a later run.
    """
    requeued = []
    for job in jobs:
        if job.description_url and not job.description:
            continue
        reason = screen_job(job)
        if storage.apply_rescreen(job, version=SCREENING_VERSION, drop_reason=reason):
            print(f"  Re-screened and queued: {job.company} - {job.title}")
            requeued.append(job)
    return requeued


def _print_summary(summary: dict):
    print("\n=== Run summary ===")
    print(f"Mode: {summary['mode']}")
    for name, details in summary.get("lists", {}).items():
        print(
            f"  List {name}: {details['candidates']} row(s), {details['matched']} matched"
            f" ({details['status']})"
        )
    if "careers" in summary:
        careers = summary["careers"]
        print(
            f"  Career pages: {careers['healthy']}/{careers['attempted']} companies healthy, "
            f"{careers['matched']} matched"
        )
    screened = summary.get("screened_at_source", {})
    if screened:
        details = ", ".join(f"{reason}={count}" for reason, count in sorted(screened.items()))
        print(f"  Dropped by sponsorship/seniority screening at source: {details}")
    after_fetch = summary.get("screened_after_fetch", {})
    if after_fetch:
        details = ", ".join(f"{reason}={count}" for reason, count in sorted(after_fetch.items()))
        print(f"  Dropped after description fetch: {details}")
    print(
        f"  Unique postings this scan: {summary.get('unique', 0)} "
        f"(already known {summary.get('already_known', 0)}, new {summary.get('new', 0)})"
    )
    if summary.get("baselined"):
        details = ", ".join(f"{unit}={count}" for unit, count in sorted(summary["baselined"].items()))
        print(f"  Recorded without notifying (first scan of a source): {details}")
    if summary.get("requeued"):
        print(f"  Queued again after re-screening with new rules: {summary['requeued']}")
    print(f"  Queued for delivery: {summary.get('queued', 0)}")
    flags = summary.get("flags")
    if flags:
        details = ", ".join(f"{name}={count}" for name, count in sorted(flags.items()))
        print(f"  Flags on kept jobs (after description fetch): {details}")


def _flag_counts(jobs: list[Job]) -> dict[str, int]:
    counts = Counter()
    for job in jobs:
        counts[f"sponsorship_{job.sponsorship}"] += 1
        if job.seniority_flag != "none":
            counts[f"seniority_{job.seniority_flag}"] += 1
    return dict(counts)


def _save_state(storage: JobStorage, path: Optional[str]):
    if not path:
        return
    pruned = storage.prune(STATE_RETENTION_DAYS)
    if pruned:
        print(f"Pruned {pruned} job(s) not listed for {STATE_RETENTION_DAYS} days")
    save_state_file(path, storage)
    print(f"Saved durable state to {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Track new grad software engineering jobs"
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Discord (and assistant webhook, if configured) notifications",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent without actually sending",
    )
    parser.add_argument(
        "--test-webhook",
        action="store_true",
        help="Send a test notification to verify webhook setup",
    )
    parser.add_argument(
        "--test-assistant-webhook",
        action="store_true",
        help="Send an empty test payload to ASSISTANT_WEBHOOK_URL",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics about tracked jobs",
    )
    parser.add_argument(
        "--list-recent",
        type=int,
        metavar="N",
        help="List N most recently seen jobs",
    )
    parser.add_argument(
        "--skip-github",
        action="store_true",
        help="Skip GitHub repository tracking",
    )
    parser.add_argument(
        "--skip-careers",
        action="store_true",
        help="Skip career page scraping",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "fast", "auto"],
        default="full",
        help=(
            "full: lists and career pages; fast: lists only; auto: lists every "
            f"run, career pages when the last full scan is over "
            f"{FULL_SCAN_INTERVAL_MINUTES} minutes old"
        ),
    )
    parser.add_argument(
        "--state-file",
        metavar="PATH",
        help="Durable JSON state: loaded before the run (if present) and saved after",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help="SQLite working database (default: jobs.db or $JOB_TRACKER_DB)",
    )
    parser.add_argument(
        "--skip-baseline",
        action="store_true",
        help="Treat jobs from never-scanned sources as new instead of recording them silently",
    )
    parser.add_argument(
        "--audit-sources",
        action="store_true",
        help="Check every career source without touching job or notification state",
    )

    args = parser.parse_args()
    if args.list_recent is not None and args.list_recent < 0:
        parser.error("--list-recent must be zero or greater")

    if args.audit_sources:
        scraper = CareerScraper()
        jobs, healthy, error = scraper.fetch_jobs_with_status()
        healthy_count = 0
        degraded_count = 0
        failed_count = 0
        print("\n=== Career Source Audit ===")
        for company, result in scraper.last_company_results.items():
            if result.healthy:
                label = "OK"
                healthy_count += 1
            elif result.status.startswith("degraded_"):
                label = "DEGRADED"
                degraded_count += 1
            else:
                label = "FAILED"
                failed_count += 1
            print(
                f"[{label}] {company}: {result.candidate_count} candidate(s), "
                f"{len(result.jobs)} match(es) ({result.status})"
            )
            if result.error:
                print(f"         {result.error}")
        print(
            f"\nSummary: {healthy_count} reliable, {degraded_count} degraded, "
            f"{failed_count} failed; {len(jobs)} matching job(s)"
        )
        print(f"Aggregate careers health: {'healthy' if healthy else 'unhealthy'}")
        if error:
            print(f"Errors: {error}")
        return

    notifier = DiscordNotifier()
    assistant = AssistantNotifier()

    # Handle special commands
    if args.test_webhook:
        success = notifier.send_test(dry_run=args.dry_run)
        sys.exit(0 if success else 1)

    if args.test_assistant_webhook:
        success = assistant.send_test(dry_run=args.dry_run)
        sys.exit(0 if success else 1)

    storage = JobStorage(args.db) if args.db else JobStorage()
    if args.state_file:
        if load_state_file(args.state_file, storage):
            print(f"Loaded durable state from {args.state_file}")
        else:
            print(
                f"No state file at {args.state_file}; continuing from the local "
                "database (it will be created after this run)"
            )

    if args.stats:
        stats = storage.get_stats()
        print("\n=== Job Tracker Statistics ===")
        print(f"Total jobs tracked: {stats['total_jobs']}")
        print(f"Jobs notified: {stats['notified_jobs']}")
        print(f"Pending notification: {stats['pending_notification']}")
        print(f"Recorded without notifying: {stats['suppressed_jobs']}")
        print(
            f"Assistant webhook: {stats['assistant_delivered']} delivered, "
            f"{stats['assistant_pending']} pending, {stats['assistant_suppressed']} not sent"
        )
        print(
            "Oldest pending age: "
            f"{_format_age_hours(stats['oldest_unnotified_age_hours'])}"
        )
        if stats["oldest_unnotified_first_seen"]:
            print(
                "Oldest pending first seen: "
                f"{stats['oldest_unnotified_first_seen']}"
            )
        print("\nFailing priority companies:")
        if stats["failing_priority_companies"]:
            for company in stats["failing_priority_companies"]:
                print(
                    f"  {company['company']}: "
                    f"{company['consecutive_failures']} consecutive "
                    f"({company['last_error'] or 'unknown error'})"
                )
        else:
            print("  None")
        print("\nJobs by company:")
        for company, count in stats["by_company"].items():
            print(f"  {company}: {count}")
        return

    if args.list_recent is not None:
        jobs = storage.get_recent(args.list_recent)
        labels = {0: "Pending", 1: "Notified", 2: "Not sent"}
        print(f"\n=== {len(jobs)} Most Recent Jobs ===\n")
        for job in jobs:
            status = labels.get(job["notified"], "Unknown")
            print(f"[{status}] {job['company']} - {job['title']}")
            print(f"         Location: {job['location'] or 'N/A'}")
            print(f"         URL: {job['url']}")
            print(f"         Seen: {job['first_seen']}")
            print(
                f"         Sponsorship: {job['sponsorship']}; "
                f"seniority: {job['seniority_flag']}"
            )
            if job["suppressed_reason"]:
                print(f"         Note: {job['suppressed_reason']}")
            print()
        return

    delivered_ok = True
    try:
        delivered_ok = _run_tracker(args, storage, notifier, assistant)
    finally:
        _save_state(storage, args.state_file)
    if not delivered_ok:
        sys.exit(1)


def _run_tracker(args, storage: JobStorage, notifier: DiscordNotifier, assistant: AssistantNotifier) -> bool:
    """Scan, store, and deliver. Returns False if any delivery channel failed."""
    print("=== Job Tracker ===\n")
    now = _utc_now()
    run_timestamp = _iso(now)
    scan_lists, scan_careers, mode_description = _resolve_scan_plan(args, storage, now)
    print(f"Mode: {mode_description}\n")
    summary: dict = {"mode": mode_description, "lists": {}, "screened_at_source": Counter()}

    all_jobs = []
    source_statuses = []
    company_results = {}
    github_tracker = None
    career_scraper = None

    if scan_lists:
        print("Fetching from GitHub repositories...")
        github_tracker = GitHubTracker()
        github_jobs, _github_healthy, _github_error = github_tracker.fetch_jobs_with_status()
        print(f"  Found {len(github_jobs)} matching jobs from GitHub\n")
        all_jobs.extend(github_jobs)
        summary["screened_at_source"].update(github_tracker.screen_counts)
        for repo, result in github_tracker.last_repo_results.items():
            # Each list has its own health record and alerts, so one broken
            # list does not report the others as failing.
            source_statuses.append((f"github:{repo}", result.healthy, result.error))
            summary["lists"][repo] = {
                "candidates": result.candidate_count,
                "matched": len(result.jobs),
                "status": result.status,
            }

    if scan_careers:
        print("Scraping career pages...")
        career_scraper = CareerScraper()
        career_jobs, careers_healthy, careers_error = career_scraper.fetch_jobs_with_status()
        print(f"\n  Found {len(career_jobs)} matching jobs from career pages\n")
        all_jobs.extend(career_jobs)
        source_statuses.append(("careers", careers_healthy, careers_error))
        company_results = career_scraper.last_company_results
        summary["screened_at_source"].update(career_scraper.screen_counts)
        summary["careers"] = {
            "attempted": career_scraper.last_attempted_companies,
            "healthy": career_scraper.last_successful_companies,
            "matched": len(career_jobs),
        }
        if careers_healthy:
            storage.set_meta(META_LAST_FULL_SCAN, run_timestamp)
        else:
            print("Career scan was unhealthy; auto mode will scan career pages again next run")

    _update_source_health(
        storage,
        notifier,
        source_statuses,
        notify=args.notify,
        dry_run=args.dry_run,
    )
    if company_results:
        _update_company_health(
            storage,
            notifier,
            company_results,
            notify=args.notify,
            dry_run=args.dry_run,
        )

    print("Checking for new jobs...")
    new_jobs = _process_scan(
        storage,
        all_jobs,
        scanned_units=_scanned_units(github_tracker, career_scraper),
        skip_baseline=args.skip_baseline,
        summary=summary,
    )
    if scan_lists and scan_careers:
        storage.set_meta(META_FRESH_INSTALL, None)

    print(
        f"\nFound {len(new_jobs)} new job(s) to deliver out of "
        f"{summary.get('unique', 0)} unique total\n"
    )

    if new_jobs:
        print("=== New Jobs ===\n")
        for job in new_jobs:
            print(f"{job.company} - {job.title}")
            print(f"  Location: {job.location or 'Not specified'}")
            print(f"  Apply: {job.url}")
            print(f"  Source: {job.source}")
            print(f"  Sponsorship: {job.sponsorship}; seniority: {job.seniority_flag}")
            print()

    _print_summary(summary)

    if not args.notify:
        return True

    def checkpoint():
        if args.state_file:
            save_state_file(args.state_file, storage)

    print()
    try:
        assistant_ok = _send_assistant_notifications(
            storage,
            assistant,
            dry_run=args.dry_run,
            run_timestamp=run_timestamp,
            checkpoint=checkpoint,
        )
    except Exception as exc:
        # Discord delivery must not depend on the assistant channel.
        # The traceback frames are printed without the exception message,
        # which can contain the webhook URL.
        print(f"Assistant delivery crashed ({describe_request_error(exc)}); continuing with Discord")
        print("".join(traceback.format_tb(exc.__traceback__)), end="")
        assistant_ok = False
    print()
    discord_ok = _send_pending_notifications(
        storage,
        notifier,
        dry_run=args.dry_run,
        checkpoint=checkpoint,
    )
    return assistant_ok and discord_ok


if __name__ == "__main__":
    main()
