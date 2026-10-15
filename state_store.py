"""Durable JSON state file for the job tracker.

The SQLite database is a per-run working copy. The state file is the durable
record: CI restores it from a dedicated git branch before a run and commits
it back afterward. Jobs are written one per line in a stable order, so each
commit's diff contains only the jobs that changed.
"""

import argparse
import json
import os
import sys
import tempfile

from storage import (
    CHANNEL_COLUMNS,
    DELIVERED,
    PENDING,
    STATE_FORMAT,
    SUPPRESSED,
    JobStorage,
)

# When two runs disagree about a channel, a job either side delivered stays
# delivered and one either side suppressed stays suppressed, so a merge never
# makes a job pending again (which would send it twice). screening_version
# travels with the suppressed mark: a re-queued pending copy (new version)
# merged with an older suppress must not keep the new version, or
# stale_screened_out would skip the job and the drop would stick.
_CHANNEL_PRECEDENCE = {PENDING: 0, SUPPRESSED: 1, DELIVERED: 2}
_LATEST_META_KEYS = {"last_full_scan_at"}


def load_state_file(path: str, storage: JobStorage) -> bool:
    """Replace storage contents with the state file. Returns False if it does not exist."""
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as handle:
        state = json.load(handle)
    storage.import_state(state)
    return True


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def format_state(state: dict) -> str:
    lines = ["{"]
    keys = [key for key in state if key != "jobs"]
    for key in keys:
        value = state[key]
        if isinstance(value, list):
            items = ",\n".join(f"    {_dumps(item)}" for item in value)
            body = f"[\n{items}\n  ]" if value else "[]"
        else:
            body = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=4).replace("\n", "\n  ")
        lines.append(f"  {json.dumps(key)}: {body},")
    jobs = state.get("jobs", [])
    items = ",\n".join(f"    {_dumps(job)}" for job in jobs)
    lines.append(f'  "jobs": [\n{items}\n  ]' if jobs else '  "jobs": []')
    lines.append("}")
    return "\n".join(lines) + "\n"


def _merge_job(ours: dict, theirs: dict) -> dict:
    merged = dict(ours)
    for column in CHANNEL_COLUMNS.values():
        mine, other = ours.get(column, PENDING), theirs.get(column, PENDING)
        if _CHANNEL_PRECEDENCE.get(other, 0) > _CHANNEL_PRECEDENCE.get(mine, 0):
            merged[column] = other
            if other == SUPPRESSED:
                merged["suppressed_reason"] = theirs.get("suppressed_reason")
                merged["screening_version"] = theirs.get("screening_version")
    for column, pick in (("first_seen", min), ("last_seen", max), ("assistant_attempts", max)):
        values = [v for v in (ours.get(column), theirs.get(column)) if v is not None]
        if values:
            merged[column] = pick(values)
    return merged


def merge_states(ours: dict, theirs: dict) -> dict:
    """Combine this run's state with one another run pushed in the meantime."""
    for state in (ours, theirs):
        if state.get("format") != STATE_FORMAT:
            raise ValueError("Not a job tracker state file")
    if ours.get("version") != theirs.get("version"):
        raise ValueError("Cannot merge state files with different versions")

    jobs = {job["unique_id"]: job for job in theirs.get("jobs", [])}
    for job in ours.get("jobs", []):
        other = jobs.get(job["unique_id"])
        jobs[job["unique_id"]] = _merge_job(job, other) if other else job

    meta = {**theirs.get("meta", {}), **ours.get("meta", {})}
    for key in _LATEST_META_KEYS:
        values = [v for v in (ours.get("meta", {}).get(key), theirs.get("meta", {}).get(key)) if v]
        if values:
            meta[key] = max(values)
    if "fresh_install" not in ours.get("meta", {}) or "fresh_install" not in theirs.get("meta", {}):
        meta.pop("fresh_install", None)

    baselines = dict(theirs.get("baselines", {}))
    for unit, when in ours.get("baselines", {}).items():
        baselines[unit] = min(filter(None, (when, baselines.get(unit))), default=when)

    merged = {
        "format": STATE_FORMAT,
        "version": ours.get("version"),
        "meta": dict(sorted(meta.items())),
        "baselines": dict(sorted(baselines.items())),
    }
    for table, key_column in (("source_health", "source"), ("company_health", "company")):
        records = {record[key_column]: record for record in theirs.get(table, [])}
        records.update({record[key_column]: record for record in ours.get(table, [])})
        merged[table] = [records[key] for key in sorted(records)]
    merged["jobs"] = sorted(jobs.values(), key=lambda job: job.get("first_seen") or "")
    return merged


def _write_atomically(path: str, text: str):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    json.loads(text)
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".state-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temp_path, 0o644)
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def save_state_file(path: str, storage: JobStorage):
    """Atomically write the storage contents to path."""
    _write_atomically(path, format_state(storage.export_state()))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Job tracker state file tools")
    commands = parser.add_subparsers(dest="command", required=True)
    merge = commands.add_parser("merge", help="merge two state files into OUTPUT")
    merge.add_argument("ours")
    merge.add_argument("theirs")
    merge.add_argument("output")
    args = parser.parse_args(argv)
    with open(args.ours, encoding="utf-8") as handle:
        ours = json.load(handle)
    with open(args.theirs, encoding="utf-8") as handle:
        theirs = json.load(handle)
    try:
        merged = merge_states(ours, theirs)
    except ValueError as exc:
        print(f"Cannot merge state files: {exc}", file=sys.stderr)
        return 1
    _write_atomically(args.output, format_state(merged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
