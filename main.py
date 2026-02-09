#!/usr/bin/env python3
"""Job Tracker - Main entry point."""

import argparse
import sys

from sources import GitHubTracker, CareerScraper
from storage import JobStorage
from notifier import DiscordNotifier
from config import SOURCE_FAILURE_ALERT_THRESHOLDS


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

    args = parser.parse_args()

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

    # Update source health state and emit alerts at configured thresholds
    for source_name, healthy, error in source_statuses:
        if healthy:
            recovered_after = storage.record_source_success(
                source_name,
                alert_thresholds=SOURCE_FAILURE_ALERT_THRESHOLDS,
            )
            if recovered_after and args.notify:
                print(f"Source recovered: {source_name} (after {recovered_after} failed runs)")
                sent = notifier.notify_source_recovery(
                    source_name,
                    recovered_after,
                    dry_run=args.dry_run,
                )
                if sent and not args.dry_run:
                    storage.confirm_source_recovery_alert(source_name)
        else:
            failures, alert_threshold = storage.record_source_failure(
                source_name,
                error or "unknown source failure",
                alert_thresholds=SOURCE_FAILURE_ALERT_THRESHOLDS,
            )
            print(f"Source failure recorded: {source_name} ({failures} consecutive)")
            if alert_threshold and args.notify:
                sent = notifier.notify_source_failure(
                    source_name,
                    failures,
                    error or "unknown source failure",
                    dry_run=args.dry_run,
                )
                if sent and not args.dry_run:
                    storage.confirm_source_failure_alert(source_name, alert_threshold)

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
    if args.notify and new_jobs:
        print("Sending Discord notifications...")
        success = notifier.notify(new_jobs, dry_run=args.dry_run)

        if success and not args.dry_run:
            for job in new_jobs:
                storage.mark_notified(job)
            print("All jobs marked as notified")
    elif args.notify and not new_jobs:
        print("No new jobs to notify about")


if __name__ == "__main__":
    main()
