"""Exercise scripts/state_branch.sh against a throwaway bare repository."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

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


def test_save_refuses_to_overwrite_a_branch_created_mid_run(repos, tmp_path):
    remote, work = repos
    other = tmp_path / "other"
    git("init", "--quiet", str(other), cwd=tmp_path)
    git("remote", "add", "origin", str(remote), cwd=other)
    output = tmp_path / "output"
    state = tmp_path / "state.json"

    # This run restores before the branch exists...
    assert script("restore", tmp_path / "unused.json", work, output).returncode == 0
    # ...another run creates it meanwhile...
    state.write_text('{"from": "other"}')
    assert script("save", state, other, output).returncode == 0
    # ...so this run must not replace it.
    state.write_text('{"from": "work"}')
    result = script("save", state, work, output)
    assert result.returncode != 0
    assert "refusing to overwrite" in result.stderr
    assert git("show", "job-tracker-state:state.json", cwd=remote) == '{"from": "other"}'
