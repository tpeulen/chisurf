#!/usr/bin/env bash
# Run heavy test suites on a remote machine so the workstation stays free.
#
# The remote mirrors the local layout: this checkout lives at the same path
# relative to $HOME there (~/dev/chisurf, its submodule in place), cloned once
# from the same origin. The commit under test is pushed straight into that
# clone over ssh as refs/remote-test/<id> (no branch is touched, no GitHub
# round trip) and checked out detached. Pixi environments are detached into
# the pixi cache, so the checkout stays clean. Each run is a systemd user
# unit (survives a dropped ssh connection); only one runs at a time, never
# two pytest suites at once. Run output lands in build/remote-test/<id> on
# the remote and, after `fetch`, at the same path here.
#
#   build_tools/remote_test.sh start [--dirty] [--id ID] [-- CMD...]
#   build_tools/remote_test.sh status [ID]      # state + log tail
#   build_tools/remote_test.sh wait [ID]        # block until done, exit with its code
#   build_tools/remote_test.sh log [ID] [-f]    # whole log (or follow)
#   build_tools/remote_test.sh fetch [ID]       # copy the run dir back
#   build_tools/remote_test.sh stop [ID]
#   build_tools/remote_test.sh list
#
# CMD defaults to `pixi run -e test test`; a JUnit report is requested when
# CMD is a `pixi run` task. --dirty tests the working tree's tracked changes
# (a `git stash create` commit, which leaves the tree and the stash list
# alone; untracked files and uncommitted submodule edits are not included).
# Without it, HEAD is tested.
#
# Environment: CHISURF_REMOTE_HOST (default: home).

set -euo pipefail

HOST="${CHISURF_REMOTE_HOST:-home}"
SUBMODULE="modules/ndxplorer"
KEEP_REFS=20
REPO="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
case "$REPO" in
    "$HOME"/*) DIR="${REPO#"$HOME"/}" ;;
    *) echo "the checkout must live under \$HOME to be mirrored: $REPO" >&2; exit 2 ;;
esac
RUNS="$DIR/build/remote-test"

remote() { ssh -o BatchMode=yes "$HOST" "$@"; }

resolve_id() {
    local id="${1:-}"
    [[ -n "$id" ]] || id="$(remote "ls -1t $RUNS 2>/dev/null | head -1")"
    [[ -n "$id" ]] || { echo "no runs on $HOST" >&2; exit 2; }
    echo "$id"
}

ensure_remote() {
    local origin
    origin="$(git -C "$REPO" remote get-url origin)"
    remote "set -e
        [ -x ~/.pixi/bin/pixi ] || { curl -fsSL https://pixi.sh/install.sh | PIXI_NO_PATH_UPDATE=1 bash >/dev/null; }
        ~/.pixi/bin/pixi config set --global detached-environments true >/dev/null 2>&1
        if [ ! -d $DIR/.git ]; then
            mkdir -p \$(dirname $DIR)
            git clone -q $origin $DIR
        fi
        cd $DIR
        git -c protocol.file.allow=always submodule update -q --init $SUBMODULE 2>/dev/null || true"
}

cmd_start() {
    local dirty=0 id="" cmd=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dirty) dirty=1; shift ;;
            --id) id="$2"; shift 2 ;;
            --) shift; cmd=("$@"); break ;;
            *) echo "unknown option: $1" >&2; exit 2 ;;
        esac
    done
    [[ ${#cmd[@]} -gt 0 ]] || cmd=(pixi run -e test test)

    if remote "systemctl --user list-units --state=active,activating --no-legend 'chisurf-test-*' | grep -q ."; then
        echo "a run is already active on $HOST:" >&2
        remote "systemctl --user list-units --state=active,activating --no-legend 'chisurf-test-*'" >&2
        exit 3
    fi

    cd "$REPO"
    local sha="" label="HEAD"
    if [[ $dirty -eq 1 ]]; then sha="$(git stash create "remote_test snapshot")"; fi
    if [[ -n "$sha" ]]; then label="dirty"; else sha="$(git rev-parse HEAD)"; fi
    [[ -n "$id" ]] || id="$(date +%Y%m%d-%H%M%S)-$(git rev-parse --short "$sha")"

    ensure_remote
    git push -q "$HOST:$DIR" "+$sha:refs/remote-test/$id"
    local subsha=""
    if subsha="$(git rev-parse "$sha:$SUBMODULE" 2>/dev/null)"; then
        git -C "$SUBMODULE" push -q "$HOST:$DIR/$SUBMODULE" "+$subsha:refs/remote-test/$id"
    fi

    local quoted extra=""
    if [[ "${cmd[0]}" == "pixi" && "${cmd[1]:-}" == "run" ]]; then
        extra=" --junitxml=$RUNS/$id/junit.xml"
    fi
    printf -v quoted '%q ' "${cmd[@]}"

    remote "set -e
        cd $DIR
        git checkout -q -f --detach $sha
        if [ -n '$subsha' ]; then git -C $SUBMODULE checkout -q -f --detach $subsha; fi
        # keep the newest $KEEP_REFS pushed refs, drop the rest
        for repo in . $SUBMODULE; do
            git -C \$repo for-each-ref --sort=-refname --format='%(refname)' refs/remote-test/ \
                | tail -n +$((KEEP_REFS + 1)) | xargs -r -n1 git -C \$repo update-ref -d
        done
        RUN=\$HOME/$RUNS/$id; mkdir -p \$RUN
        cat > \$RUN/meta.txt <<EOF
id: $id
sha: $sha
tree: $label
submodule: $subsha
cmd: $quoted
started: \$(date -Is)
EOF
        cat > \$RUN/run.sh <<EOF
#!/bin/bash
export PATH=\$HOME/.pixi/bin:/usr/local/bin:/usr/bin:/bin
cd \$HOME/$DIR
$quoted$extra > \$RUN/log.txt 2>&1
rc=\\\$?
echo \\\$rc > \$RUN/exit_code
date -Is > \$RUN/finished
exit \\\$rc
EOF
        chmod +x \$RUN/run.sh
        systemd-run --user --quiet --collect --unit=chisurf-test-$id --nice=10 \$RUN/run.sh"
    echo "$id"
    echo "started on $HOST: $label $sha (${cmd[*]})" >&2
}

cmd_status() {
    local id; id="$(resolve_id "${1:-}")"
    remote "RUN=$RUNS/$id
        cat \$RUN/meta.txt
        if [ -f \$RUN/exit_code ]; then echo \"state: finished, exit \$(cat \$RUN/exit_code) at \$(cat \$RUN/finished)\";
        elif systemctl --user is-active -q chisurf-test-$id; then echo 'state: running';
        else echo 'state: dead (unit gone without an exit code)'; fi
        tail -n 5 \$RUN/log.txt 2>/dev/null"
}

cmd_wait() {
    local id; id="$(resolve_id "${1:-}")"
    while ! remote "test -f $RUNS/$id/exit_code"; do
        remote "systemctl --user is-active -q chisurf-test-$id" || { cmd_status "$id"; exit 4; }
        sleep 60
    done
    cmd_status "$id"
    exit "$(remote "cat $RUNS/$id/exit_code")"
}

cmd_log() {
    local id; id="$(resolve_id "${1:-}")"
    if [[ "${2:-}" == "-f" ]]; then remote "tail -n 50 -f $RUNS/$id/log.txt"
    else remote "cat $RUNS/$id/log.txt"; fi
}

cmd_fetch() {
    local id; id="$(resolve_id "${1:-}")"
    mkdir -p "$HOME/$RUNS"
    rsync -a "$HOST:$RUNS/$id" "$HOME/$RUNS/"
    echo "$HOME/$RUNS/$id"
}

cmd_stop() {
    local id; id="$(resolve_id "${1:-}")"
    remote "systemctl --user stop chisurf-test-$id"
}

cmd_list() {
    remote "cd $RUNS 2>/dev/null && for r in \$(ls -1t); do printf '%s  %s\n' \$r \"\$(cat \$r/exit_code 2>/dev/null || echo running/dead)\"; done"
}

sub="${1:-}"; shift || true
case "$sub" in
    start) cmd_start "$@" ;;
    status) cmd_status "$@" ;;
    wait) cmd_wait "$@" ;;
    log) cmd_log "$@" ;;
    fetch) cmd_fetch "$@" ;;
    stop) cmd_stop "$@" ;;
    list) cmd_list ;;
    *) sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
