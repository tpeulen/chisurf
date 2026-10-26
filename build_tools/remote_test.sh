#!/usr/bin/env bash
# Run heavy test suites on a remote machine so the workstation stays free.
#
# The remote mirrors the local layout: this checkout lives at the same path
# relative to $HOME there (~/dev/chisurf, its submodule in place), cloned once
# from the same origin. The commit under test is pushed straight into that
# clone over ssh as refs/remote-test/<id> (no branch is touched, no GitHub
# round trip) and checked out detached. Pixi environments are detached into
# the pixi cache, so the checkout stays clean. Each run is a systemd user
# unit (survives a dropped ssh connection). Several runs may go at once, but
# only on the same commit (they share the checkout); `start` refuses otherwise.
# Run output lands in build/remote-test/<id> on the remote and, after `fetch`,
# at the same path here. Sibling checkouts the
# tree links in (modules/<name> -> ~/dev/<name>: tttrlib, mmfdb, chimol, ...)
# are mirrored the same way: their committed HEAD is pushed to the same path
# on the remote and checked out detached (their uncommitted edits are not
# sent; meta.txt records each sibling's sha and whether it was dirty).
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
# CMD is a pixi `test*` task. --dirty tests the working tree's tracked changes
# (a `git stash create` commit, which leaves the tree and the stash list
# alone; untracked files and uncommitted submodule edits are not included).
# Without it, HEAD is tested.
#
# The command sees \$RUN, its run directory (for extra output, e.g. --out \$RUN/chunks).
#
# Overlays: the ~/dev/<name> checkouts in CHISURF_REMOTE_OVERLAYS (default "emtk") are
# mirrored like the siblings and put first on PYTHONPATH -- the workstation has them
# installed editable, newer than pixi.lock (the lock moves at the release cut). Set
# CHISURF_REMOTE_OVERLAYS= to test the locked env alone.
#
# Environment: CHISURF_REMOTE_HOST (default: home), CHISURF_REMOTE_OVERLAYS.

set -euo pipefail

HOST="${CHISURF_REMOTE_HOST:-home}"
SUBMODULE="modules/ndxplorer"
OVERLAYS="${CHISURF_REMOTE_OVERLAYS-emtk}"
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

    cd "$REPO"
    local sha="" label="HEAD"
    if [[ $dirty -eq 1 ]]; then sha="$(git stash create "remote_test snapshot")"; fi
    if [[ -n "$sha" ]]; then label="dirty"; else sha="$(git rev-parse HEAD)"; fi

    # Runs share the one checkout: several may run at once (the box has the cores), but
    # only on the same commit -- checking out another would change the tree under them.
    local busy
    busy="$(remote "for u in \$(systemctl --user list-units --state=active,activating --no-legend --plain 'chisurf-test-*' | awk '{print \$1}'); do
        id=\${u#chisurf-test-}; id=\${id%.service}; sed -n 's/^sha: //p' $RUNS/\$id/meta.txt 2>/dev/null; done | sort -u")"
    if [[ -n "$busy" && "$busy" != "$sha" ]]; then
        echo "runs on another commit are active on $HOST ($busy); wait or stop them" >&2
        exit 3
    fi
    [[ -n "$id" ]] || id="$(date +%Y%m%d-%H%M%S)-$(git rev-parse --short "$sha")"

    ensure_remote
    git push -q "$HOST:$DIR" "+$sha:refs/remote-test/$id"

    # Siblings: modules/<link> -> a git checkout elsewhere under $HOME.
    local link target top rel ssha sdirty siblings="" sibmeta=""
    for link in "$REPO"/modules/*; do
        [[ -L "$link" ]] || continue
        target="$(cd "$link" 2>/dev/null && pwd -P)" || continue
        top="$(git -C "$target" rev-parse --show-toplevel 2>/dev/null)" || continue
        case "$top" in "$HOME"/*) rel="${top#"$HOME"/}" ;; *) continue ;; esac
        ssha="$(git -C "$top" rev-parse HEAD)"
        sdirty="clean"; [[ -z "$(git -C "$top" status --porcelain --untracked-files=no)" ]] || sdirty="dirty (not sent)"
        remote "set -e
            if [ ! -d $rel/.git ]; then
                mkdir -p $rel && git -C $rel init -q
                git -C $rel remote add origin $(git -C "$top" remote get-url origin 2>/dev/null || echo none)
            fi"
        git -C "$top" push -q "$HOST:$rel" "+$ssha:refs/remote-test/$id"
        # an untracked link (local convenience) is recreated as it is here
        remote "[ -e $DIR/modules/${link##*/} ] || ln -sn $(readlink "$link") $DIR/modules/${link##*/}"
        siblings="$siblings $rel:$ssha"
        sibmeta="${sibmeta}sibling: $rel $ssha $sdirty"$'\n'
    done
    # Overlays: mirrored the same way, then imported from source ahead of the locked env.
    local name pypath=""
    for name in $OVERLAYS; do
        top="$HOME/dev/$name"
        [[ -d "$top/.git" ]] || continue
        rel="dev/$name"
        ssha="$(git -C "$top" rev-parse HEAD)"
        sdirty="clean"; [[ -z "$(git -C "$top" status --porcelain --untracked-files=no)" ]] || sdirty="dirty (not sent)"
        remote "[ -d $rel/.git ] || { mkdir -p $rel && git -C $rel init -q; }"
        git -C "$top" push -q "$HOST:$rel" "+$ssha:refs/remote-test/$id"
        siblings="$siblings $rel:$ssha"
        sibmeta="${sibmeta}overlay: $rel $ssha $sdirty (first on PYTHONPATH)"$'\n'
        pypath="${pypath:+$pypath:}\$HOME/$rel"
    done
    local subsha=""
    if subsha="$(git rev-parse "$sha:$SUBMODULE" 2>/dev/null)"; then
        git -C "$SUBMODULE" push -q "$HOST:$DIR/$SUBMODULE" "+$subsha:refs/remote-test/$id"
    fi

    # A JUnit report for the pytest tasks (pixi run [-e ENV] test*), at an absolute
    # path: the command runs from the checkout, not from $HOME.
    local quoted extra="" task="${cmd[2]:-}"
    [[ "$task" == "-e" ]] && task="${cmd[4]:-}"
    if [[ "${cmd[0]}" == "pixi" && "${cmd[1]:-}" == "run" && "$task" == test* ]]; then
        extra=" --junitxml=\$HOME/$RUNS/$id/junit.xml"
    fi
    printf -v quoted '%q ' "${cmd[@]}"

    remote "set -e
        cd $DIR
        git checkout -q -f --detach $sha
        if [ -n '$subsha' ]; then git -C $SUBMODULE checkout -q -f --detach $subsha; fi
        for pair in $siblings; do
            git -C \$HOME/\${pair%%:*} checkout -q -f --detach \${pair#*:}
        done
        # keep the newest $KEEP_REFS pushed refs, drop the rest
        for repo in . $SUBMODULE \$(for pair in $siblings; do echo \$HOME/\${pair%%:*}; done); do
            git -C \$repo for-each-ref --sort=-refname --format='%(refname)' refs/remote-test/ \
                | tail -n +$((KEEP_REFS + 1)) | xargs -r -n1 git -C \$repo update-ref -d
        done
        RUN=\$HOME/$RUNS/$id; mkdir -p \$RUN
        cat > \$RUN/meta.txt <<EOF
id: $id
sha: $sha
tree: $label
submodule: $subsha
${sibmeta}cmd: $quoted
started: \$(date -Is)
EOF
        # the command verbatim: a quoted heredoc expands nothing
        cat > \$RUN/cmd.sh <<'CMD_EOF'
$quoted$extra
CMD_EOF
        cat > \$RUN/run.sh <<EOF
#!/bin/bash
export PATH=\$HOME/.pixi/bin:/usr/local/bin:/usr/bin:/bin
export RUN=\$RUN
export PYTHONPATH=$pypath
cd \$HOME/$DIR
bash \$RUN/cmd.sh > \$RUN/log.txt 2>&1
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
