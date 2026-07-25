"""Build & install the ``tttrlib`` source into the active pixi env.

This is tttrlib's *only* provider: ChiSurf deliberately does not depend on the
published conda/PyPI package. Both are capped at ``0.26.2``, which lags the
source by enough to be wrong rather than merely old — it predates the
photon-simulation subsystem (``SimEngine``) and still carries a ``compute_ics``
defect that segfaults any image correlation using frame lags. Depending on it
meant a fresh environment silently got a broken correlator.

The source is reached through the tracked ``modules/tttrlib`` symlink, which
points at a sibling checkout (the same arrangement as ``modules/mmfdb``). When
it does not resolve this script fails loudly: with no conda package behind it,
silently continuing would leave the environment with no tttrlib at all.

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
            f"build-tttrlib: no tttrlib source at {_SRC}.\n"
            "\n"
            "  ChiSurf builds tttrlib from source and has no conda/PyPI package\n"
            "  to fall back on, so this is fatal rather than skippable.\n"
            "\n"
            "  modules/tttrlib is a symlink to a sibling checkout. Clone it next\n"
            "  to the ChiSurf repository:\n"
            "\n"
            "      git clone https://github.com/Fluorescence-Tools/tttrlib.git \\\n"
            f"          {_REPO.parent / 'tttrlib'}\n",
            file=sys.stderr,
            flush=True,
        )
        return 1

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
