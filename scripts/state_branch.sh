#!/usr/bin/env bash
# Keep the job tracker's durable state file on a dedicated git branch.
#
#   scripts/state_branch.sh restore <state-file>   # fetch the branch's state.json
#   scripts/state_branch.sh save <state-file>      # commit and push it if changed
#
# The branch holds only state.json and a README. Commits are built with git
# plumbing, so the checked-out working tree is never touched. A missing branch
# (first run) is reported as found=false; any other git failure is fatal so a
# network error is never mistaken for an empty state.
set -euo pipefail

command="${1:?usage: state_branch.sh restore|save <state-file>}"
state_file="${2:?usage: state_branch.sh restore|save <state-file>}"
branch="${STATE_BRANCH:-job-tracker-state}"
remote="${STATE_REMOTE:-origin}"
tracking_ref="refs/remotes/${remote}/${branch}"

export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-github-actions[bot]}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"
export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-$GIT_AUTHOR_NAME}"
export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-$GIT_AUTHOR_EMAIL}"

output() {
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "$1" >> "$GITHUB_OUTPUT"
  fi
}

with_retries() {
  local attempt=1 delay=4
  until "$@"; do
    if (( attempt >= 4 )); then
      return 1
    fi
    echo "Retrying in ${delay}s: $*" >&2
    sleep "$delay"
    attempt=$((attempt + 1))
    delay=$((delay * 2))
  done
}

branch_exists() {
  local status=0
  git ls-remote --exit-code --heads "$remote" "refs/heads/${branch}" >/dev/null || status=$?
  case "$status" in
    0) return 0 ;;
    2) return 1 ;;
    *) echo "git ls-remote failed with status ${status}" >&2; exit "$status" ;;
  esac
}

restore() {
  mkdir -p "$(dirname "$state_file")"
  if ! with_retries git ls-remote "$remote" >/dev/null; then
    echo "Cannot reach ${remote}; refusing to continue without durable state" >&2
    exit 1
  fi
  if ! branch_exists; then
    echo "State branch ${branch} does not exist yet"
    output "found=false"
    return
  fi
  with_retries git fetch --quiet --no-tags --depth=1 "$remote" \
    "+refs/heads/${branch}:${tracking_ref}"
  if git cat-file -e "${tracking_ref}:state.json" 2>/dev/null; then
    git show "${tracking_ref}:state.json" > "$state_file"
    echo "Restored ${state_file} from ${branch} ($(git rev-parse --short "$tracking_ref"))"
    output "found=true"
  else
    echo "State branch ${branch} has no state.json"
    output "found=false"
  fi
}

save() {
  if [[ ! -f "$state_file" ]]; then
    echo "No state file at ${state_file}; nothing to save"
    return
  fi
  python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$state_file"

  local readme_blob state_blob tree parent=""
  state_blob="$(git hash-object -w "$state_file")"
  readme_blob="$(printf '%s\n' \
    "# Job tracker state" \
    "" \
    "Written by the Check for New Jobs workflow after every run." \
    "state.json records every job seen and whether it was delivered to Discord" \
    "and to the assistant webhook. Do not edit while the workflow is running." \
    | git hash-object -w --stdin)"
  tree="$(printf '100644 blob %s\tREADME.md\n100644 blob %s\tstate.json\n' \
    "$readme_blob" "$state_blob" | git mktree)"

  if git rev-parse -q --verify "${tracking_ref}^{commit}" >/dev/null; then
    parent="$(git rev-parse "${tracking_ref}^{commit}")"
    if [[ "$(git rev-parse "${parent}^{tree}")" == "$tree" ]]; then
      echo "State unchanged; nothing to commit"
      return
    fi
  elif branch_exists; then
    echo "State branch ${branch} appeared during this run; refusing to overwrite it" >&2
    exit 1
  fi

  local commit
  commit="$(git commit-tree "$tree" ${parent:+-p "$parent"} \
    -m "Update job tracker state ($(date -u +%Y-%m-%dT%H:%M:%SZ))")"
  # A plain push (no force) fails if another run moved the branch, rather
  # than discarding that run's deliveries.
  with_retries git push --quiet "$remote" "${commit}:refs/heads/${branch}"
  git update-ref "$tracking_ref" "$commit"
  echo "Saved state to ${branch} ($(git rev-parse --short "$commit"))"
}

case "$command" in
  restore) restore ;;
  save) save ;;
  *) echo "unknown command: ${command}" >&2; exit 2 ;;
esac
