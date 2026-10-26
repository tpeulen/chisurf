#!/usr/bin/env bash
# Build a compiled overlay (a <slot>/<name> checkout, e.g. ~/dev/imp.bff) once per commit
# and environment on the remote test box and print the site directory to put first on
# PYTHONPATH.
#
#   build_tools/remote_overlay_build.sh <name> <sha> [<slot base, default dev>]
#
# Called by remote_test.sh's run script (prepare.sh). The slot (~/dev, ~/dev-slot1, ...)
# has its own pixi environment, and a build links that environment's libraries, so the
# cache is keyed by both: ~/.cache/chisurf-remote/<name>/<sha>-<env hash>/site. A lock
# keeps concurrent runs from building one key twice; the newest six builds per name are
# kept. The build log is beside it, <key>.build.log.

set -euo pipefail

name="$1"
sha="$2"
base="${3:-dev}"
chisurf="$HOME/$base/chisurf"
source_dir="$HOME/$base/$name"
root="$HOME/.cache/chisurf-remote/$name"
mkdir -p "$root"
# The slot's test environment: the build links its libraries and records its lib as RPATH.
prefix=$(cd "$chisurf" && pixi run -e test python -c 'import sys; print(sys.prefix)' | tail -n 1)
env_key=$(printf '%s' "$prefix" | sha256sum | cut -c1-10)
cache="$root/$sha-$env_key"

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
    (cd "$chisurf" && CMAKE_BUILD_PARALLEL_LEVEL=$jobs MAKEFLAGS=-j$jobs \
        CMAKE_ARGS="-DCMAKE_PREFIX_PATH=$prefix -DHDF5_ROOT=$prefix -DCMAKE_INSTALL_RPATH=$prefix/lib -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON" \
        pixi run -e test python -m pip install --no-deps --no-build-isolation \
        --target "$cache/site" "$source_dir") >"$cache.build.log" 2>&1 || {
        echo "overlay build of $name failed; see $cache.build.log" >&2
        tail -n 30 "$cache.build.log" >&2
        exit 1
    }
    # A build that cannot be imported is not a build: check before marking it done.
    mod=$(case "$name" in imp.bff) echo IMP.bff ;; *) echo "$name" ;; esac)
    (cd "$chisurf" && PYTHONPATH="$cache/site" pixi run -e test python -c "import $mod") \
        >>"$cache.build.log" 2>&1 || {
        echo "overlay $name built but does not import; see $cache.build.log" >&2
        tail -n 15 "$cache.build.log" >&2
        exit 1
    }
    touch "$cache/.done"
fi
exec 9>&-

# Keep the newest six builds (several slots, several commits).
ls -1dt "$root"/*/ 2>/dev/null | tail -n +7 | while read -r old; do
    rm -rf "$old" "${old%/}.lock" "${old%/}.build.log"
done

echo "$cache/site"
