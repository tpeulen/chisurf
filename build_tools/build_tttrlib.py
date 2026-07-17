"""Build & install the local ``tttrlib`` source into the active pixi env.

ChiSurf pins ``tttrlib`` as a conda dependency (bioconda) so CI and fresh
installs get a working baseline. That published package can lag the local
development tree, though — e.g. the photon-simulation subsystem (``SimEngine``)
lands in the unreleased ``0.27.0`` source before it reaches bioconda. This task
overrides the conda package with a fresh build of the local source so
``pixi run chisurf`` always uses the most recent tttrlib.

It is a no-op when the local source is not present (the ``modules/tttrlib``
symlink is a gitignored, developer-local pointer to the tttrlib checkout), so on
CI / other machines the conda ``tttrlib`` package is used unchanged.

macOS note: the SWIG module must link ``libomp`` explicitly, otherwise it builds
but fails to load with ``symbol not found in flat namespace '___kmpc_barrier'``.
We pass the env's ``libomp`` on the shared/module linker flags on Darwin.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# build_tools/ lives at the repo root; the local tttrlib source is the
# (gitignored) modules/tttrlib symlink.
_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "modules" / "tttrlib"
# Dedicated build tree (gitignored) so we never disturb the developer's own
# tttrlib checkout build dir and always start from a reproducible clean state —
# reusing tttrlib's in-source build dir across flag changes regenerates a stale
# SWIG wrapper that fails to compile.
_BUILD_DIR = _REPO / "build" / "tttrlib"


def main() -> int:
    if not (_SRC / "pyproject.toml").is_file():
        print(
            f"build-tttrlib: {_SRC} not present — keeping the conda tttrlib package.",
            flush=True,
        )
        return 0

    prefix = os.environ.get("CONDA_PREFIX") or sys.prefix
    lib = Path(prefix) / "lib"

    env = dict(os.environ)
    cmake_args = [f"-DCMAKE_PREFIX_PATH={prefix}"]
    if sys.platform == "darwin":
        # Link the env's libomp into the SWIG module (flat-namespace fix). The
        # quotes keep each -D<flag>=<value with spaces> a single scikit-build arg.
        omp = f"-L{lib} -lomp -Wl,-rpath,{lib}"
        cmake_args += [
            f'"-DCMAKE_SHARED_LINKER_FLAGS={omp}"',
            f'"-DCMAKE_MODULE_LINKER_FLAGS={omp}"',
        ]
    env["CMAKE_ARGS"] = " ".join(cmake_args)

    shutil.rmtree(_BUILD_DIR, ignore_errors=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        str(_SRC),
        "--no-build-isolation",
        "--no-deps",
        "--force-reinstall",
        "--no-cache-dir",
        f"--config-settings=build-dir={_BUILD_DIR}",
    ]
    print(f"build-tttrlib: {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
