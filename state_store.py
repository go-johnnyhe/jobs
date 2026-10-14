"""Durable JSON state file for the job tracker.

The SQLite database is a per-run working copy. The state file is the durable
record: CI restores it from a dedicated git branch before a run and commits
it back afterward. Jobs are written one per line in a stable order, so each
commit's diff contains only the jobs that changed.
"""

import json
import os
import tempfile

from storage import JobStorage


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


def save_state_file(path: str, storage: JobStorage):
    """Atomically write the storage contents to path."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    text = format_state(storage.export_state())
    json.loads(text)
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".state-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
