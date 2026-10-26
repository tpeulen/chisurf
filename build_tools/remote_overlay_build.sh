#!/usr/bin/env bash
# Build a compiled overlay (a ~/dev/<name> checkout, e.g. imp.bff) once per commit on the
# remote test box and print the site directory to put first on PYTHONPATH.
#
#   build_tools/remote_overlay_build.sh <name> <sha>
#
# Called by remote_test.sh's run script, from the mirrored chisurf checkout. The build
# goes into ~/.cache/chisurf-remote/<name>/<sha>/site with the test environment's
# Python (same ABI as the run); a lock keeps concurrent runs on one commit from
# building twice; only the newest three builds per name are kept. The build log is
# ~/.cache/chisurf-remote/<name>/<sha>.build.log.

set -euo pipefail

name="$1"
sha="$2"
root="$HOME/.cache/chisurf-remote/$name"
cache="$root/$sha"
mkdir -p "$root"

exec 9>"$cache.lock"
flock 9
if [[ ! -f "$cache/.done" ]]; then
    rm -rf "$cache"
    mkdir -p "$cache"
    echo "building overlay $name at $sha (log: $cache.build.log)" >&2
    # pip's build backend compiles serially unless told otherwise; use half the box.
    jobs=$(( $(nproc 2>/dev/null || echo 4) / 2 ))
    # Build against the test environment's own libraries, the way build_tools/build_tttrlib.py
    # does (no build isolation: an isolated build links whatever HDF5 pip fetched), and
    # record an absolute RPATH into the environment: the extension lives in this cache, not
    # in the environment, so an $ORIGIN-relative path would point nowhere.
    prefix=$(cd "$HOME/dev/chisurf" && pixi run -e test python -c 'import sys; print(sys.prefix)')
    (cd "$HOME/dev/chisurf" && CMAKE_BUILD_PARALLEL_LEVEL=$jobs MAKEFLAGS=-j$jobs \
        CMAKE_ARGS="-DCMAKE_PREFIX_PATH=$prefix -DHDF5_ROOT=$prefix -DCMAKE_INSTALL_RPATH=$prefix/lib -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON" \
        pixi run -e test python -m pip install --no-deps --no-build-isolation \
        --target "$cache/site" "$HOME/dev/$name") >"$cache.build.log" 2>&1 || {
        echo "overlay build of $name failed; see $cache.build.log" >&2
        tail -n 30 "$cache.build.log" >&2
        exit 1
    }
    # A build that cannot be imported is not a build: check before marking it done.
    mod=$(case "$name" in imp.bff) echo IMP.bff ;; *) echo "$name" ;; esac)
    (cd "$HOME/dev/chisurf" && PYTHONPATH="$cache/site" pixi run -e test python -c "import $mod") \
        >>"$cache.build.log" 2>&1 || {
        echo "overlay $name built but does not import; see $cache.build.log" >&2
        tail -n 15 "$cache.build.log" >&2
        exit 1
    }
    touch "$cache/.done"
fi
exec 9>&-

# Keep the newest three builds.
ls -1dt "$root"/*/ 2>/dev/null | tail -n +4 | while read -r old; do
    rm -rf "$old" "${old%/}.lock" "${old%/}.build.log"
done

echo "$cache/site"
