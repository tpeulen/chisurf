#!/usr/bin/env bash
# Run heavy test suites on a remote machine so the workstation stays free.
#
# The remote mirrors the local layout: this checkout lives at the same path
# relative to $HOME there (~/dev/chisurf, its submodule in place), cloned once
# from the same origin. The commit under test is pushed straight into that
# clone over ssh as refs/remote-test/<id> (no branch is touched, no GitHub
# round trip) and checked out detached. Pixi environments are detached into
# the pixi cache, so the checkout stays clean. Each run is a systemd user
# unit (survives a dropped ssh connection).
#
# Slots: the remote keeps CHISURF_REMOTE_SLOTS (default 3) full mirrors -- slot 0 is ~/dev
# (~/dev/chisurf, ~/dev/tttrlib, ...), slot N is ~/dev-slot<N> with the same layout, each
# with its own pixi environment (pixi keys detached environments by project path). Runs
# in one slot share its checkout, so they must be on the same commit; `start` takes the
# slot already on the commit, else a free one, else refuses (--slot N forces one). So
# runs on different commits go at once. Run output lands in
# <slot>/chisurf/build/remote-test/<id> on the remote (meta.txt names the slot) and,
# after `fetch`, in build/remote-test/<id> here. Sibling checkouts the
# tree links in (modules/<name> -> ~/dev/<name>: tttrlib, mmfdb, chimol, ...)
# are mirrored the same way: their committed HEAD is pushed to the same path
# on the remote and checked out detached (their uncommitted edits are not
# sent; meta.txt records each sibling's sha and whether it was dirty).
#
#   build_tools/remote_test.sh start [--dirty | --sha REV] [--slot N] [--id ID] [-- CMD...]
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
# CHISURF_REMOTE_OVERLAYS= to test the locked env alone. Compiled overlays
# (CHISURF_REMOTE_BUILT_OVERLAYS, default "imp.bff") are mirrored too, built once per
# commit and environment into ~/.cache/chisurf-remote/<name>/<sha>-<env> on the remote
# (build_tools/remote_overlay_build.sh) and put first on PYTHONPATH.
# Every run gets its own CHISURF_SETTINGS_DIR / MMFDB_SETTINGS_DIR under $RUN/settings.
#
# Environment: CHISURF_REMOTE_HOST (default: home), CHISURF_REMOTE_OVERLAYS,
# CHISURF_REMOTE_BUILT_OVERLAYS, CHISURF_REMOTE_SLOTS (default 3).

set -euo pipefail

HOST="${CHISURF_REMOTE_HOST:-home}"
SUBMODULE="modules/ndxplorer"
OVERLAYS="${CHISURF_REMOTE_OVERLAYS-emtk}"
BUILT_OVERLAYS="${CHISURF_REMOTE_BUILT_OVERLAYS-imp.bff}"
SLOTS="${CHISURF_REMOTE_SLOTS:-3}"
KEEP_REFS=20
REPO="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
case "$REPO" in
    "$HOME"/dev/*) DIR="${REPO#"$HOME"/}" ;;
    *) echo "the checkout must live under \$HOME/dev to be mirrored: $REPO" >&2; exit 2 ;;
esac
#: The local runs folder (fetch target); on the remote it sits in the run's slot.
RUNS="$DIR/build/remote-test"
#: Slot 0 is the workstation's own layout; the slot a run uses is chosen in cmd_start.
BASE="dev"
#: Every slot's runs folder on the remote, for finding a run by id.
ALL_RUNS="\$HOME/dev/${DIR#dev/}/build/remote-test \$HOME/dev-slot*/${DIR#dev/}/build/remote-test"

# Run every remote command in bash (the remote login shell may be zsh, which aborts on an
# unmatched glob).
remote() { ssh -o BatchMode=yes "$HOST" "bash -c $(printf '%q' "$*")"; }

#: A path under the local ~/dev mapped into the slot's tree (dev/x -> <base>/x).
in_slot() { local rel="$1"; case "$rel" in dev/*) echo "$BASE/${rel#dev/}" ;; *) echo "$rel" ;; esac; }

slot_base() { if [[ "$1" == 0 ]]; then echo dev; else echo "dev-slot$1"; fi; }

#: The remote run directory of *id* (searched across slots).
run_dir() {
    local d
    d="$(remote "shopt -s nullglob; for r in $ALL_RUNS; do [ -d \$r/$1 ] && { echo \$r/$1; break; }; done")"
    [[ -n "$d" ]] || { echo "no run $1 on $HOST" >&2; exit 2; }
    echo "$d"
}

resolve_id() {
    local id="${1:-}"
    [[ -n "$id" ]] || id="$(remote "shopt -s nullglob; ls -1dt $(printf '%s/*/ ' $ALL_RUNS) 2>/dev/null | head -1 | xargs -r basename")"
    [[ -n "$id" ]] || { echo "no runs on $HOST" >&2; exit 2; }
    echo "$id"
}

ensure_remote() {
    local origin dir
    origin="$(git -C "$REPO" remote get-url origin)"
    dir="$(in_slot "$DIR")"
    # A new slot is seeded from slot 0's clone on the remote (no second download), then
    # pointed at the same origin.
    remote "set -e
        [ -x ~/.pixi/bin/pixi ] || { curl -fsSL https://pixi.sh/install.sh | PIXI_NO_PATH_UPDATE=1 bash >/dev/null; }
        ~/.pixi/bin/pixi config set --global detached-environments true >/dev/null 2>&1
        if [ ! -d $dir/.git ]; then
            mkdir -p \$(dirname $dir)
            if [ -d $DIR/.git ] && [ $dir != $DIR ]; then
                git -c advice.detachedHead=false clone -q $DIR $dir && git -C $dir remote set-url origin $origin
            else
                git -c advice.detachedHead=false clone -q $origin $dir
            fi
        fi
        cd $dir
        git -c protocol.file.allow=always submodule update -q --init $SUBMODULE 2>/dev/null || true"
}

#: Make the remote repository *rel* (under the slot) exist, seeded from slot 0's copy.
ensure_repo() {
    local rel="$1" slot0="$2" origin="$3"
    remote "set -e
        if [ ! -d $rel/.git ]; then
            mkdir -p \$(dirname $rel)
            if [ -d $slot0/.git ] && [ $rel != $slot0 ]; then
                git -c advice.detachedHead=false clone -q $slot0 $rel && git -C $rel remote set-url origin $origin
            else
                mkdir -p $rel && git -C $rel init -q && git -C $rel remote add origin $origin
            fi
        fi"
}

#: Run a bash script given on stdin on the remote, with positional arguments.
remote_script() { ssh -o BatchMode=yes "$HOST" "bash -s -- $(printf '%q ' "$@")"; }

#: Pick and claim the slot for *sha* on the remote, atomically (a lock around the choice,
#: a claim file so a run still being set up counts as busy): the slot already on the
#: commit, else a free one; refuse otherwise. Prints the slot's base (dev, dev-slot1, ...).
choose_slot() {
    remote_script "$1" "${2:-}" "$SLOTS" "${DIR#dev/}" <<'SLOT_EOF'
set -euo pipefail
sha="$1"; forced="$2"; slots="$3"; repo="$4"
state="$HOME/.cache/chisurf-remote"; mkdir -p "$state/claims"
exec 8>"$state/slots.lock"; flock 8
base_of() { if [ "$1" = 0 ]; then echo dev; else echo "dev-slot$1"; fi; }
# "<base> <sha>" for every active run and every fresh claim (< 15 min)
busy=$(
  for u in $(systemctl --user list-units --state=active,activating --no-legend --plain 'chisurf-test-*' | awk '{print $1}'); do
    id=${u#chisurf-test-}; id=${id%.service}
    for r in "$HOME"/dev/"$repo"/build/remote-test "$HOME"/dev-slot*/"$repo"/build/remote-test; do
      m="$r/$id/meta.txt"; [ -f "$m" ] || continue
      b=$(sed -n 's/^slot: //p' "$m"); s=$(sed -n 's/^sha: //p' "$m"); echo "${b:-dev} $s"; break
    done
  done
  now=$(date +%s)
  for c in "$state"/claims/*; do
    [ -f "$c" ] || continue
    read -r csha ctime < "$c" || continue
    # An if, not `test && echo`: under set -e an expired claim made the loop -- and with it
    # this whole script -- fail silently, so every later start was refused without a word.
    if [ $((now - ctime)) -lt 900 ]; then echo "$(basename "$c") $csha"; fi
  done
)
shas_of() { awk -v b="$1" '$1==b{print $2}' <<<"$busy" | sort -u; }
pick=""
if [ -n "$forced" ]; then
  b=$(base_of "$forced"); s=$(shas_of "$b")
  if [ -n "$s" ] && [ "$s" != "$sha" ]; then echo "slot $forced ($b) is busy on another commit ($s)" >&2; exit 3; fi
  pick=$b
else
  for ((n = 0; n < slots; n++)); do b=$(base_of $n); [ "$(shas_of "$b")" = "$sha" ] && { pick=$b; break; }; done
  if [ -z "$pick" ]; then
    for ((n = 0; n < slots; n++)); do b=$(base_of $n); [ -z "$(shas_of "$b")" ] && { pick=$b; break; }; done
  fi
fi
if [ -z "$pick" ]; then echo "all $slots slots are busy:" >&2; echo "$busy" >&2; exit 3; fi
echo "$sha $(date +%s)" > "$state/claims/$pick"
echo "$pick"
SLOT_EOF
}

cmd_start() {
    local dirty=0 id="" cmd=() rev="" slot=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dirty) dirty=1; shift ;;
            --sha) rev="$2"; shift 2 ;;
            --slot) slot="$2"; shift 2 ;;
            --id) id="$2"; shift 2 ;;
            --) shift; cmd=("$@"); break ;;
            *) echo "unknown option: $1" >&2; exit 2 ;;
        esac
    done
    [[ ${#cmd[@]} -gt 0 ]] || cmd=(pixi run -e test test)

    cd "$REPO"
    local sha="" label="HEAD"
    if [[ $dirty -eq 1 ]]; then sha="$(git stash create "remote_test snapshot")"; fi
    if [[ -n "$sha" ]]; then
        label="dirty"
    elif [[ -n "$rev" ]]; then
        sha="$(git rev-parse --verify "$rev^{commit}")"; label="$rev"
    else
        sha="$(git rev-parse HEAD)"
    fi

    # Runs in one slot share its checkout, so they must be on the same commit; a run on
    # another commit takes another slot (choose_slot).
    BASE="$(choose_slot "$sha" "$slot")"
    local rdir rruns
    rdir="$(in_slot "$DIR")"
    rruns="$rdir/build/remote-test"
    [[ -n "$id" ]] || id="$(date +%Y%m%d-%H%M%S)-$(git rev-parse --short "$sha")"

    ensure_remote
    git push -q "$HOST:$rdir" "+$sha:refs/remote-test/$id"

    # Siblings: modules/<link> -> a git checkout elsewhere under $HOME.
    local link target top rel ssha sdirty siblings="" sibmeta=""
    for link in "$REPO"/modules/*; do
        [[ -L "$link" ]] || continue
        target="$(cd "$link" 2>/dev/null && pwd -P)" || continue
        top="$(git -C "$target" rev-parse --show-toplevel 2>/dev/null)" || continue
        case "$top" in "$HOME"/*) rel="${top#"$HOME"/}" ;; *) continue ;; esac
        ssha="$(git -C "$top" rev-parse HEAD)"
        sdirty="clean"; [[ -z "$(git -C "$top" status --porcelain --untracked-files=no)" ]] || sdirty="dirty (not sent)"
        ensure_repo "$(in_slot "$rel")" "$rel" "$(git -C "$top" remote get-url origin 2>/dev/null || echo none)"
        rel="$(in_slot "$rel")"
        git -C "$top" push -q "$HOST:$rel" "+$ssha:refs/remote-test/$id"
        # an untracked link (local convenience) is recreated as it is here
        remote "[ -e $rdir/modules/${link##*/} ] || ln -sn $(readlink "$link") $rdir/modules/${link##*/}"
        siblings="$siblings $rel:$ssha"
        sibmeta="${sibmeta}sibling: $rel $ssha $sdirty"$'\n'
    done
    # Overlays: mirrored the same way, then imported from source ahead of the locked env.
    local name pypath=""
    for name in $OVERLAYS; do
        top="$HOME/dev/$name"
        [[ -d "$top/.git" ]] || continue
        ssha="$(git -C "$top" rev-parse HEAD)"
        sdirty="clean"; [[ -z "$(git -C "$top" status --porcelain --untracked-files=no)" ]] || sdirty="dirty (not sent)"
        ensure_repo "$(in_slot "dev/$name")" "dev/$name" "$(git -C "$top" remote get-url origin 2>/dev/null || echo none)"
        rel="$(in_slot "dev/$name")"
        git -C "$top" push -q "$HOST:$rel" "+$ssha:refs/remote-test/$id"
        siblings="$siblings $rel:$ssha"
        sibmeta="${sibmeta}overlay: $rel $ssha $sdirty (first on PYTHONPATH)"$'\n'
        pypath="${pypath:+$pypath:}\$HOME/$rel"
    done
    # Compiled overlays: mirrored the same way, built once per commit on the remote
    # (build_tools/remote_overlay_build.sh) and put first on PYTHONPATH.
    local prepare=""
    for name in $BUILT_OVERLAYS; do
        top="$HOME/dev/$name"
        [[ -d "$top/.git" ]] || continue
        ssha="$(git -C "$top" rev-parse HEAD)"
        sdirty="clean"; [[ -z "$(git -C "$top" status --porcelain --untracked-files=no)" ]] || sdirty="dirty (not sent)"
        ensure_repo "$(in_slot "dev/$name")" "dev/$name" "$(git -C "$top" remote get-url origin 2>/dev/null || echo none)"
        rel="$(in_slot "dev/$name")"
        git -C "$top" push -q "$HOST:$rel" "+$ssha:refs/remote-test/$id"
        siblings="$siblings $rel:$ssha"
        sibmeta="${sibmeta}built overlay: $rel $ssha $sdirty (built, first on PYTHONPATH)"$'\n'
        # The build prints its site directory (cache keyed by commit and the slot's
        # environment); prepare.sh puts it first on PYTHONPATH.
        prepare="${prepare}site=\$(bash \$HOME/$rdir/build_tools/remote_overlay_build.sh $name $ssha $BASE) || return 1"$'\n'
        prepare="${prepare}export PYTHONPATH=\"\$site\${PYTHONPATH:+:\$PYTHONPATH}\""$'\n'
    done
    local subsha=""
    if subsha="$(git rev-parse "$sha:$SUBMODULE" 2>/dev/null)"; then
        git -C "$SUBMODULE" push -q "$HOST:$rdir/$SUBMODULE" "+$subsha:refs/remote-test/$id"
    fi

    # A JUnit report for the pytest tasks (pixi run [-e ENV] test*), at an absolute
    # path: the command runs from the checkout, not from $HOME.
    local quoted extra="" task="${cmd[2]:-}"
    [[ "$task" == "-e" ]] && task="${cmd[4]:-}"
    if [[ "${cmd[0]}" == "pixi" && "${cmd[1]:-}" == "run" && "$task" == test* ]]; then
        extra=" --junitxml=\$HOME/$rruns/$id/junit.xml"
    fi
    printf -v quoted '%q ' "${cmd[@]}"

    remote "set -e
        cd $rdir
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
        RUN=\$HOME/$rruns/$id; mkdir -p \$RUN
        cat > \$RUN/meta.txt <<EOF
id: $id
slot: $BASE
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
        # the compiled overlays' builds, sourced by run.sh (their site dirs go on PYTHONPATH)
        cat > \$RUN/prepare.sh <<'PREP_EOF'
$prepare
PREP_EOF
        cat > \$RUN/run.sh <<EOF
#!/bin/bash
export PATH=\$HOME/.pixi/bin:/usr/local/bin:/usr/bin:/bin
export RUN=\$RUN
export PYTHONPATH=$pypath
# per-run user state: nothing a run does lands in the remote's real ~/.chisurf
export CHISURF_SETTINGS_DIR=\$RUN/settings MMFDB_SETTINGS_DIR=\$RUN/settings
cd \$HOME/$rdir
. \$RUN/prepare.sh > \$RUN/log.txt 2>&1 || { echo 1 > \$RUN/exit_code; date -Is > \$RUN/finished; exit 1; }
bash \$RUN/cmd.sh >> \$RUN/log.txt 2>&1
rc=\\\$?
echo \\\$rc > \$RUN/exit_code
date -Is > \$RUN/finished
exit \\\$rc
EOF
        chmod +x \$RUN/run.sh
        systemd-run --user --quiet --collect --unit=chisurf-test-$id --nice=10 \$RUN/run.sh
        # the unit now marks the slot busy; the setup claim is no longer needed
        rm -f \$HOME/.cache/chisurf-remote/claims/$BASE"
    echo "$id"
    echo "started on $HOST in $BASE: $label $sha (${cmd[*]})" >&2
}

cmd_status() {
    local id run; id="$(resolve_id "${1:-}")"; run="$(run_dir "$id")"
    remote "RUN=$run
        cat \$RUN/meta.txt
        if [ -f \$RUN/exit_code ]; then echo \"state: finished, exit \$(cat \$RUN/exit_code) at \$(cat \$RUN/finished)\";
        elif systemctl --user is-active -q chisurf-test-$id; then echo 'state: running';
        else echo 'state: dead (unit gone without an exit code)'; fi
        tail -n 5 \$RUN/log.txt 2>/dev/null"
}

cmd_wait() {
    local id run; id="$(resolve_id "${1:-}")"; run="$(run_dir "$id")"
    while ! remote "test -f $run/exit_code"; do
        remote "systemctl --user is-active -q chisurf-test-$id" || { cmd_status "$id"; exit 4; }
        sleep 60
    done
    cmd_status "$id"
    exit "$(remote "cat $run/exit_code")"
}

cmd_log() {
    local id run; id="$(resolve_id "${1:-}")"; run="$(run_dir "$id")"
    if [[ "${2:-}" == "-f" ]]; then remote "tail -n 50 -f $run/log.txt"
    else remote "cat $run/log.txt"; fi
}

cmd_fetch() {
    local id run; id="$(resolve_id "${1:-}")"; run="$(run_dir "$id")"
    mkdir -p "$HOME/$RUNS"
    rsync -a "$HOST:$run" "$HOME/$RUNS/"
    echo "$HOME/$RUNS/$id"
}

cmd_stop() {
    local id; id="$(resolve_id "${1:-}")"
    remote "systemctl --user stop chisurf-test-$id"
}

cmd_list() {
    remote "shopt -s nullglob; for r in \$(ls -1dt $(printf '%s/*/ ' $ALL_RUNS) 2>/dev/null); do
        r=\${r%/}; id=\$(basename \$r)
        if [ -f \$r/exit_code ]; then st=\"exit \$(cat \$r/exit_code)\"
        elif systemctl --user is-active -q chisurf-test-\$id; then st=running
        else st=dead; fi
        printf '%-36s %-11s %s\n' \$id \$(sed -n 's/^slot: //p' \$r/meta.txt 2>/dev/null | grep . || echo dev) \"\$st\"; done"
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
    *) sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
