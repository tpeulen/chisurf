#!/bin/bash
# Runs one tranche of the ChiSurf docs-mining loop under Claude Code, headless.
#
# Scheduled by ~/Library/LaunchAgents/dev.chisurf.docs-mining.plist (weekdays,
# hourly during working hours). Replaced the goose/GLM scheduled recipe, whose
# provider quota ran out; the mandate and safety rails live in
# wikipedia-docs-mining.prompt.md and are unchanged.

set -uo pipefail

REPO=/Users/tpeulen/dev/chisurf
PROMPT="$REPO/okf/recipes/wikipedia-docs-mining.prompt.md"
DUMP=/Volumes/SD1TB/wikipedia
LOGDIR="$HOME/Library/Logs/chisurf-docs-mining"
LOCK=/tmp/chisurf-docs-mining.lock

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$LOGDIR"
LOG="$LOGDIR/$(date +%Y%m%d-%H%M%S).log"
exec >>"$LOG" 2>&1

echo "=== mining tranche $(date -Iseconds) ==="

# One tranche at a time: a run that overruns its hour must not be joined by the
# next one, or two agents commit into the same shared tree concurrently.
# macOS ships no flock(1), so this is a pid file.
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "SKIP: previous tranche (pid $(cat "$LOCK")) still running"
  exit 0
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

cd "$REPO" || { echo "FAIL: repo missing"; exit 1; }

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "development" ]; then
  echo "SKIP: branch is $BRANCH, not development"
  exit 0
fi

if [ ! -d "$DUMP" ]; then
  echo "NOTE: SD card not mounted at $DUMP; the run will fall back to live articles"
fi

# GIT_INDEX_FILE must not leak in from the environment: the prompt tells the
# agent to set its own, and a stale one here would corrupt its commits.
unset GIT_INDEX_FILE

ARGS=(-p --permission-mode bypassPermissions --add-dir "$REPO")
[ -d "$DUMP" ] && ARGS+=(--add-dir "$DUMP")

echo "--- claude start $(date -Iseconds) ---"
claude "${ARGS[@]}" < "$PROMPT"
STATUS=$?
echo "--- claude exit $STATUS at $(date -Iseconds) ---"

echo "=== head after run: $(git rev-parse --short HEAD) $(git log -1 --format=%s) ==="
exit $STATUS
