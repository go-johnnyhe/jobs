#!/usr/bin/env python3
"""Job Tracker - Main entry point."""

import argparse
import sys

from sources import GitHubTracker, CareerScraper
from storage import JobStorage
from notifier import DiscordNotifier, MAX_EMBEDS_PER_MESSAGE
from config import (
    COMPANY_FAILURE_ALERT_THRESHOLDS,
    ENABLE_COMPANY_HEALTH_ALERTS,
    PRIORITY_COMPANIES,
    SOURCE_FAILURE_ALERT_THRESHOLDS,
)

MAX_PENDING_JOBS_TO_NOTIFY = 50


def _iter_batches(items: list, batch_size: int):
    """Yield fixed-size batches from a list."""
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


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


def _send_pending_notifications(storage: JobStorage, notifier: DiscordNotifier, *, dry_run: bool):
    """Send pending notifications oldest-first and mark only sent batches."""
    pending_jobs = storage.get_unnotified()
    if not pending_jobs:
        print("No new or pending jobs to notify about")
        return True

    skipped_jobs = []
    jobs_to_send = pending_jobs
    if len(pending_jobs) > MAX_PENDING_JOBS_TO_NOTIFY:
        skipped_jobs = pending_jobs[:-MAX_PENDING_JOBS_TO_NOTIFY]
        jobs_to_send = pending_jobs[-MAX_PENDING_JOBS_TO_NOTIFY:]
        print(
            f"Pending backlog has {len(pending_jobs)} job(s); "
            f"skipping {len(skipped_jobs)} older job(s) and sending the newest "
            f"{len(jobs_to_send)}"
        )
        summary_sent = notifier.notify_backlog_skipped(
            len(skipped_jobs),
            len(jobs_to_send),
            dry_run=dry_run,
        )
        if not summary_sent:
            print("Stopped before sending job batches; backlog summary failed")
            return False

    print(f"Sending Discord notifications for {len(jobs_to_send)} pending job(s)...")
    sent_jobs = 0

    for batch_index, batch in enumerate(_iter_batches(jobs_to_send, MAX_EMBEDS_PER_MESSAGE)):
        sent = notifier.send_job_batch(
            batch,
            total_jobs=len(jobs_to_send),
            batch_index=batch_index,
            dry_run=dry_run,
        )
        if not sent:
            remaining = len(jobs_to_send) - sent_jobs
            print(
                f"Stopped after failed batch {batch_index + 1}; "
                f"{remaining} job(s) remain pending"
            )
            return False

        if not dry_run:
            for job in batch:
                storage.mark_notified(job)
        sent_jobs += len(batch)

    if dry_run:
        print("Dry run complete; pending jobs were not marked as notified")
    else:
        for job in skipped_jobs:
            storage.mark_notified(job)
        print(f"Marked {sent_jobs} job(s) as notified")
        if skipped_jobs:
            print(f"Marked {len(skipped_jobs)} skipped older job(s) as handled")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Track new grad software engineering jobs"
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Discord notifications for new jobs",
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
        "--audit-sources",
        action="store_true",
        help="Check every career source without touching job or notification state",
    )

    args = parser.parse_args()

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

    storage = JobStorage()
    notifier = DiscordNotifier()

    # Handle special commands
    if args.test_webhook:
        success = notifier.send_test()
        sys.exit(0 if success else 1)

    if args.stats:
        stats = storage.get_stats()
        print("\n=== Job Tracker Statistics ===")
        print(f"Total jobs tracked: {stats['total_jobs']}")
        print(f"Jobs notified: {stats['notified_jobs']}")
        print(f"Pending notification: {stats['pending_notification']}")
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

    if args.list_recent:
        jobs = storage.get_recent(args.list_recent)
        print(f"\n=== {len(jobs)} Most Recent Jobs ===\n")
        for job in jobs:
            status = "Notified" if job["notified"] else "Pending"
            print(f"[{status}] {job['company']} - {job['title']}")
            print(f"         Location: {job['location'] or 'N/A'}")
            print(f"         URL: {job['url']}")
            print(f"         Seen: {job['first_seen']}")
            print()
        return

    # Main job tracking flow
    print("=== Job Tracker ===\n")

    all_jobs = []
    new_jobs = []
    source_statuses = []
    company_results = {}

    # Fetch from GitHub repos
    if not args.skip_github:
        print("Fetching from GitHub repositories...")
        github_tracker = GitHubTracker()
        github_jobs, github_healthy, github_error = github_tracker.fetch_jobs_with_status()
        print(f"  Found {len(github_jobs)} matching jobs from GitHub\n")
        all_jobs.extend(github_jobs)
        source_statuses.append(("github", github_healthy, github_error))

    # Fetch from career pages
    if not args.skip_careers:
        print("Scraping career pages...")
        career_scraper = CareerScraper()
        career_jobs, careers_healthy, careers_error = career_scraper.fetch_jobs_with_status()
        print(f"\n  Found {len(career_jobs)} matching jobs from career pages\n")
        all_jobs.extend(career_jobs)
        source_statuses.append(("careers", careers_healthy, careers_error))
        company_results = career_scraper.last_company_results

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

    # Check for new jobs
    print("Checking for new jobs...")
    for job in all_jobs:
        if storage.is_new(job):
            new_jobs.append(job)
            storage.mark_seen(job, notified=False)
            print(f"  NEW: {job.company} - {job.title}")

    print(f"\nFound {len(new_jobs)} new job(s) out of {len(all_jobs)} total\n")

    # Print all new jobs
    if new_jobs:
        print("=== New Jobs ===\n")
        for job in new_jobs:
            print(f"{job.company} - {job.title}")
            print(f"  Location: {job.location or 'Not specified'}")
            print(f"  Apply: {job.url}")
            print(f"  Source: {job.source}")
            print()

    # Send notifications if requested
    if args.notify:
        notifications_sent = _send_pending_notifications(
            storage,
            notifier,
            dry_run=args.dry_run,
        )
        if not notifications_sent:
            sys.exit(1)


if __name__ == "__main__":
    main()
