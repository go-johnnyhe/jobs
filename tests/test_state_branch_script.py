"""Exercise scripts/state_branch.sh against a throwaway bare repository."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from models import Job
from state_store import format_state, load_state_file
from storage import DELIVERED, PENDING, JobStorage

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "state_branch.sh"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def script(command, state_file, cwd, output_file):
    env = {**os.environ, "GITHUB_OUTPUT": str(output_file)}
    return subprocess.run(
        ["bash", str(SCRIPT), command, str(state_file)],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=60,
    )


@pytest.fixture
def repos(tmp_path):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git("init", "--quiet", "--bare", str(remote), cwd=tmp_path)
    git("init", "--quiet", str(work), cwd=tmp_path)
    git("remote", "add", "origin", str(remote), cwd=work)
    return remote, work


def test_restore_save_cycle(repos, tmp_path):
    remote, work = repos
    output = tmp_path / "output"
    state = tmp_path / "state" / "state.json"

    result = script("restore", state, work, output)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == "found=false\n"

    state.write_text('{"jobs": [1]}\n')
    result = script("save", state, work, output)
    assert result.returncode == 0, result.stderr
    assert git("ls-tree", "--name-only", "job-tracker-state", cwd=remote).split() == [
        "README.md", "state.json",
    ]

    result = script("save", state, work, output)
    assert "State unchanged" in result.stdout
    assert git("rev-list", "--count", "job-tracker-state", cwd=remote) == "1"

    state.write_text('{"jobs": [1, 2]}\n')
    assert script("save", state, work, output).returncode == 0
    assert git("rev-list", "--count", "job-tracker-state", cwd=remote) == "2"

    # A later run in a fresh clone restores the latest state and builds on it.
    clone = tmp_path / "clone"
    git("init", "--quiet", str(clone), cwd=tmp_path)
    git("remote", "add", "origin", str(remote), cwd=clone)
    restored = tmp_path / "restored" / "state.json"
    output.write_text("")
    result = script("restore", restored, clone, output)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == "found=true\n"
    assert restored.read_text() == '{"jobs": [1, 2]}\n'

    restored.write_text('{"jobs": [1, 2, 3]}\n')
    assert script("save", restored, clone, output).returncode == 0
    assert git("rev-list", "--count", "job-tracker-state", cwd=remote) == "3"
    assert git("show", "job-tracker-state:state.json", cwd=remote) == '{"jobs": [1, 2, 3]}'
    # The checked-out branch is never touched.
    assert git("status", "--porcelain", cwd=clone) == ""


def test_save_rejects_invalid_json(repos, tmp_path):
    _remote, work = repos
    state = tmp_path / "state.json"
    state.write_text("{not json")
    result = script("save", state, work, tmp_path / "output")
    assert result.returncode != 0


def test_save_without_state_file_is_a_no_op(repos, tmp_path):
    _remote, work = repos
    result = script("save", tmp_path / "missing.json", work, tmp_path / "output")
    assert result.returncode == 0
    assert "nothing to save" in result.stdout


def clone_of(remote, tmp_path, name):
    path = tmp_path / name
    git("init", "--quiet", str(path), cwd=tmp_path)
    git("remote", "add", "origin", str(remote), cwd=path)
    return path


def write_state(path, storage):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_state(storage.export_state()), encoding="utf-8")


def remote_state(remote):
    return json.loads(git("show", "job-tracker-state:state.json", cwd=remote))


def job(n):
    return Job("Acme", f"Software Engineer {n}", f"https://acme.example/{n}", "Seattle, WA", "list")


def test_save_refuses_to_overwrite_a_state_it_cannot_merge(repos, tmp_path):
    remote, work = repos
    other = clone_of(remote, tmp_path, "other")
    output = tmp_path / "output"
    state = tmp_path / "state.json"

    # This run restores before the branch exists...
    assert script("restore", tmp_path / "unused.json", work, output).returncode == 0
    # ...another writer creates it meanwhile with something that is not a state file...
    state.write_text('{"from": "other"}')
    assert script("save", state, other, output).returncode == 0
    # ...so this run must not replace it.
    state.write_text('{"from": "work"}')
    result = script("save", state, work, output)
    assert result.returncode != 0
    assert "Refusing to overwrite" in result.stderr
    assert git("show", "job-tracker-state:state.json", cwd=remote) == '{"from": "other"}'


def test_rejected_push_merges_the_other_runs_deliveries(repos, tmp_path):
    remote, work = repos
    output = tmp_path / "output"
    base = JobStorage(str(tmp_path / "base.db"))
    base.add_jobs([job(1), job(2)])
    seed = tmp_path / "seed" / "state.json"
    write_state(seed, base)
    assert script("save", seed, work, output).returncode == 0

    # Two runs restore the same state.
    run_a, run_b = clone_of(remote, tmp_path, "a"), clone_of(remote, tmp_path, "b")
    state_a, state_b = tmp_path / "a" / ".state.json", tmp_path / "b" / ".state.json"
    assert script("restore", state_a, run_a, output).returncode == 0
    assert script("restore", state_b, run_b, output).returncode == 0

    # Run B delivers job 1 to Discord and saves first.
    storage_b = JobStorage(str(tmp_path / "b.db"))
    load_state_file(str(state_b), storage_b)
    storage_b.mark_delivered("discord", [job(1)])
    write_state(state_b, storage_b)
    assert script("save", state_b, run_b, output).returncode == 0

    # Run A delivered job 2 to the assistant and found job 3. Its push is
    # rejected, so it merges with B's state instead of dropping B's delivery.
    storage_a = JobStorage(str(tmp_path / "a.db"))
    load_state_file(str(state_a), storage_a)
    storage_a.mark_delivered("assistant", [job(2)])
    storage_a.add_jobs([job(3)])
    write_state(state_a, storage_a)
    started = time.monotonic()
    result = script("save", state_a, run_a, output)
    assert result.returncode == 0, result.stderr
    assert time.monotonic() - started < 10
    assert "merging with the current job-tracker-state" in result.stderr

    jobs = {j["title"]: j for j in remote_state(remote)["jobs"]}
    assert jobs["Software Engineer 1"]["notified"] == DELIVERED
    assert jobs["Software Engineer 2"]["assistant_notified"] == DELIVERED
    assert jobs["Software Engineer 2"]["notified"] == PENDING
    assert set(jobs) == {"Software Engineer 1", "Software Engineer 2", "Software Engineer 3"}
    assert git("rev-list", "--count", "job-tracker-state", cwd=remote) == "3"


def test_branch_created_mid_run_is_merged_not_replaced(repos, tmp_path):
    remote, work = repos
    other = clone_of(remote, tmp_path, "other")
    output = tmp_path / "output"
    assert script("restore", tmp_path / "unused.json", work, output).returncode == 0

    first = JobStorage(str(tmp_path / "first.db"))
    first.add_jobs([job(1)], notified=True)
    write_state(tmp_path / "other.json", first)
    assert script("save", tmp_path / "other.json", other, output).returncode == 0

    second = JobStorage(str(tmp_path / "second.db"))
    second.add_jobs([job(2)])
    write_state(tmp_path / "work.json", second)
    result = script("save", tmp_path / "work.json", work, output)
    assert result.returncode == 0, result.stderr
    titles = {j["title"]: j["notified"] for j in remote_state(remote)["jobs"]}
    assert titles == {"Software Engineer 1": DELIVERED, "Software Engineer 2": PENDING}
