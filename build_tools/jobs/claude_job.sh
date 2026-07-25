#!/usr/bin/env bash
#
# Generic runner for scheduled ChiSurf maintenance jobs that drive Claude Code
# headlessly. launchd/cron start this with a job name + a prompt file; it sets up
# a sane environment (launchd hands the process an almost-empty PATH), moves into
# the repo, and runs `claude -p <prompt>` non-interactively, teeing everything to
# a dated log.
#
# Usage:  claude_job.sh <job-name> <prompt-file>
# Example (from launchd):  claude_job.sh translate-ui build_tools/jobs/prompts/translate_ui.md
#
# Notes
# -----
# * --dangerously-skip-permissions is required for an unattended run (there is no
#   TTY to approve tool calls). The prompt is the safety boundary: it scopes the
#   job to a narrow set of files and forbids pushing / history rewrites.
# * Uses the credentials already stored under ~/.claude; if the login has
#   expired the run fails and is logged — re-authenticate with `claude` once.
# * One instance at a time per job (flock) so a long run never overlaps the next
#   scheduled tick.

set -uo pipefail

JOB_NAME="${1:?usage: claude_job.sh <job-name> <prompt-file>}"
PROMPT_FILE="${2:?usage: claude_job.sh <job-name> <prompt-file>}"

REPO="/Users/tpeulen/dev/chisurf"

# launchd/cron start with a minimal PATH; make the tools this job needs findable:
# claude (local bin), pixi + Qt tools (homebrew / conda arm64 env), git.
export PATH="/Users/tpeulen/.local/bin:/opt/homebrew/bin:/usr/local/bin:/Users/tpeulen/mambaforge/envs/arm64/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

cd "$REPO" || { echo "repo not found: $REPO" >&2; exit 1; }

# Resolve the prompt file relative to the repo when a bare path is given.
[ -f "$PROMPT_FILE" ] || PROMPT_FILE="$REPO/$PROMPT_FILE"
[ -f "$PROMPT_FILE" ] || { echo "prompt not found: $PROMPT_FILE" >&2; exit 1; }

LOG_DIR="$REPO/build_tools/jobs/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${JOB_NAME}-$(date +%Y%m%d).log"

# Serialize runs of the same job without flock (absent on stock macOS): an atomic
# mkdir is the lock. Clear a lock older than 6h so a killed run can't wedge the
# schedule forever.
LOCKDIR="$LOG_DIR/${JOB_NAME}.lock"
if [ -d "$LOCKDIR" ] && [ -z "$(find "$LOCKDIR" -maxdepth 0 -mmin -360 2>/dev/null)" ]; then
    rmdir "$LOCKDIR" 2>/dev/null || true
fi

CLAUDE_BIN="$(command -v claude || true)"

{
  echo "======== ${JOB_NAME} @ $(date '+%Y-%m-%d %H:%M:%S %z') ========"
  if [ -z "$CLAUDE_BIN" ]; then
    echo "ERROR: claude not on PATH; aborting." >&2
    exit 127
  fi
  if ! mkdir "$LOCKDIR" 2>/dev/null; then
    echo "another ${JOB_NAME} run is in progress; skipping this tick."
    exit 0
  fi
  trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT
  "$CLAUDE_BIN" -p "$(cat "$PROMPT_FILE")" --dangerously-skip-permissions
  echo "-------- ${JOB_NAME} done @ $(date '+%H:%M:%S') --------"
} >>"$LOG" 2>&1
