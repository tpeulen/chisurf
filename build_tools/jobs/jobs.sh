#!/usr/bin/env bash
#
# Control the scheduled ChiSurf maintenance jobs (macOS LaunchAgents).
#
# Usage:
#   jobs.sh status              # what is installed / loaded / disabled / running
#   jobs.sh start [job ...]     # enable + load (default: all jobs)
#   jobs.sh stop  [job ...]     # unload + persistently disable (default: all jobs)
#   jobs.sh install [job ...]   # copy plists into ~/Library/LaunchAgents, then start
#   jobs.sh uninstall [job ...] # stop, then remove the plists
#   jobs.sh run <job>           # fire one run right now (ignores the schedule)
#   jobs.sh logs <job>          # tail today's log
#
# Why both unload AND disable: plists in ~/Library/LaunchAgents are loaded again
# automatically at the next login, so `unload` alone is a stop that quietly undoes
# itself after a reboot. `disable` writes a persistent per-user override that
# survives login — which is also why `start` must `enable` before it loads, or the
# load is silently a no-op.

set -uo pipefail

REPO="/Users/tpeulen/dev/chisurf"
JOBS_DIR="$REPO/build_tools/jobs"
AGENTS_SRC="$JOBS_DIR/launchagents"
AGENTS_DST="$HOME/Library/LaunchAgents"

ALL_JOBS=(translate-ui build-docs improve-prds review-code fix-issues gui-tester)

plist() { echo "$AGENTS_DST/com.chisurf.$1.plist"; }
label() { echo "com.chisurf.$1"; }

# Jobs named on the command line, or every job when none were given.
jobs_from_args() {
    if [ "$#" -eq 0 ]; then
        printf '%s\n' "${ALL_JOBS[@]}"
    else
        printf '%s\n' "$@"
    fi
}

cmd_status() {
    printf '%-14s %-10s %-8s %-9s %s\n' JOB INSTALLED LOADED DISABLED RUNNING
    local disabled
    disabled="$(launchctl print-disabled "gui/$UID" 2>/dev/null)"
    for j in "${ALL_JOBS[@]}"; do
        local inst=no loaded=no dis=no running=no
        [ -f "$(plist "$j")" ] && inst=yes
        launchctl list 2>/dev/null | grep -q "$(label "$j")$" && loaded=yes
        grep -q "\"$(label "$j")\" => \(disabled\|true\)" <<<"$disabled" && dis=yes
        [ -d "$JOBS_DIR/logs/$j.lock" ] && running=yes
        printf '%-14s %-10s %-8s %-9s %s\n' "$j" "$inst" "$loaded" "$dis" "$running"
    done
}

cmd_start() {
    for j in $(jobs_from_args "$@"); do
        local p; p="$(plist "$j")"
        [ -f "$p" ] || { echo "not installed: $j (run '$0 install $j')" >&2; continue; }
        launchctl enable "gui/$UID/$(label "$j")"
        launchctl load "$p" 2>/dev/null && echo "started $j" || echo "already loaded: $j"
    done
}

cmd_stop() {
    for j in $(jobs_from_args "$@"); do
        local p; p="$(plist "$j")"
        [ -f "$p" ] && launchctl unload "$p" 2>/dev/null
        launchctl disable "gui/$UID/$(label "$j")" 2>/dev/null
        echo "stopped $j"
    done
    echo "note: a run already in flight keeps going; check '$0 status' for RUNNING."
}

cmd_install() {
    mkdir -p "$AGENTS_DST"
    for j in $(jobs_from_args "$@"); do
        cp "$AGENTS_SRC/com.chisurf.$j.plist" "$AGENTS_DST/" && echo "installed $j"
    done
    cmd_start "$@"
}

cmd_uninstall() {
    cmd_stop "$@"
    for j in $(jobs_from_args "$@"); do
        rm -f "$(plist "$j")" && echo "removed $j"
    done
}

cmd_run() {
    local j="${1:?usage: jobs.sh run <job>}"
    launchctl start "$(label "$j")" && echo "kicked off $j — watch: $0 logs $j"
}

cmd_logs() {
    local j="${1:?usage: jobs.sh logs <job>}"
    tail -f "$JOBS_DIR/logs/$j-$(date +%Y%m%d).log"
}

case "${1:-status}" in
    status)    shift || true; cmd_status ;;
    start)     shift; cmd_start "$@" ;;
    stop)      shift; cmd_stop "$@" ;;
    install)   shift; cmd_install "$@" ;;
    uninstall) shift; cmd_uninstall "$@" ;;
    run)       shift; cmd_run "$@" ;;
    logs)      shift; cmd_logs "$@" ;;
    *) sed -n '3,20p' "$0"; exit 2 ;;
esac
