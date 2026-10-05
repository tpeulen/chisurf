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

After a successful build every extra developer environment (by default a conda
env named ``arm64``) gets **its own build**, against its own native libraries,
installed as real files. It used to get symlinks into this environment instead,
which broke twice over: pixi environments are detached into
``~/Library/Caches/rattler``, which macOS purges under disk pressure -- taking
every linked environment's tttrlib with it mid-run -- and one build is only
loadable where the native libraries (HDF5) agree. Set
``CHISURF_TTTRLIB_LINK_ENVS`` to override the targets, or to an empty string to
switch it off. A target environment that then cannot import tttrlib fails the task.

The build itself needs nothing beyond the environment prefix. It used to inject
macOS-specific ``libomp`` linker flags, because tttrlib's Python extension
compiled with OpenMP but never linked it and then failed at import with
``symbol not found in flat namespace '___kmpc_barrier'``; that is fixed in
tttrlib, so a plain build is enough.
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

# Extra environments that should import this source as well: a developer usually
# *also* has a conda env they run scripts and editors from (here `arm64`). Each one
# gets its own build (see the module docstring for why never a symlink).
#
# Override with CHISURF_TTTRLIB_LINK_ENVS (os.pathsep-separated env prefixes); set it to
# an empty string to disable. Missing envs are skipped silently.
_LINK_ENVS_VAR = "CHISURF_TTTRLIB_LINK_ENVS"
_DEFAULT_LINK_ENV_NAMES = ("arm64",)

#: The post-split package directory (extension + one library per module).
_PACKAGE_DIR = "tttrlib"
#: Every name a tttrlib install -- either layout, either scheme -- leaves in
#: site-packages: the package, the pre-split flat wrapper and extension, and the
#: distribution metadata.
_INSTALL_GLOBS = (_PACKAGE_DIR, "tttrlib.py", "_tttrlib*.so", "tttrlib-*.dist-info")


def _clear_tttrlib(site_packages: Path) -> None:
    """Remove every tttrlib install from *site_packages*, dangling links included.

    A symlink whose target was purged still *names* an install, so it reads as
    one and shadows nothing useful; ``Path.exists`` is False for it, which is
    why this tests ``is_symlink`` first.
    """
    for pattern in _INSTALL_GLOBS:
        for path in sorted(site_packages.glob(pattern)):
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)


def _conda_env_prefixes() -> list[Path]:
    """Return candidate conda env prefixes for the default link targets."""
    roots: list[Path] = []
    for var in ("MAMBA_ROOT_PREFIX", "CONDA_ROOT"):
        if os.environ.get(var):
            roots.append(Path(os.environ[var]))
    # CONDA_PREFIX points at the *active* env; its parent's parent is the root when the
    # env is not the base one.
    active = os.environ.get("CONDA_PREFIX")
    if active:
        p = Path(active)
        roots += [p, p.parent.parent]
    roots += [
        Path.home() / "mambaforge",
        Path.home() / "miniforge3",
        Path.home() / "miniconda3",
        Path.home() / "anaconda3",
    ]
    out: list[Path] = []
    for root in roots:
        for name in _DEFAULT_LINK_ENV_NAMES:
            cand = root / "envs" / name
            if cand.is_dir() and cand not in out:
                out.append(cand)
    return out


def _link_targets() -> list[Path]:
    raw = os.environ.get(_LINK_ENVS_VAR)
    if raw is not None:
        return [Path(p) for p in raw.split(os.pathsep) if p.strip()]
    return _conda_env_prefixes()


def _site_packages(prefix: Path) -> Path | None:
    """Return the site-packages directory of an environment prefix, if it has one."""
    matches = sorted(prefix.glob("lib/python3.*/site-packages"))
    return matches[-1] if matches else None


def _verify(prefix: Path) -> bool:
    """Check that the environment at *prefix* can actually import what was built.

    The wrapper and the compiled extension are one unit: ``tttrlib.py`` reads
    every attribute off ``_tttrlib`` at class-definition time, so a wrapper that
    is newer than its extension raises ``AttributeError`` on a getter that does
    not exist yet -- at ``import tttrlib``, i.e. at application start, far from
    whatever produced the mismatch.

    It happened while environments shared the wrapper by symlink and kept their
    own extensions; a copy into one wrote through the link into all of them.
    Verifying the environment we installed into turns any such mismatch into a
    failed build task instead of a broken launch.
    """
    python = prefix / "bin" / "python"
    if not python.is_file():
        return True
    check = subprocess.run(
        [str(python), "-c", "import tttrlib;print(tttrlib.__version__, tttrlib.__file__)"],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        print(
            "build-tttrlib: the build installed but does not import:\n"
            f"{check.stderr.strip()}\n"
            "build-tttrlib: the wrapper and the compiled extension disagree; "
            "rebuild rather than copying one of them into place.",
            flush=True,
        )
        return False
    print(f"build-tttrlib: {prefix.name} -> {check.stdout.strip()}", flush=True)
    return True


def _cmake_args(prefix: Path) -> str:
    """Return the ``CMAKE_ARGS`` that pin the build to one environment's libraries.

    Parameters
    ----------
    prefix : pathlib.Path
        Environment prefix to build against.

    Returns
    -------
    str
    """
    hdf5_root = prefix
    cmake_prefix_path = str(prefix)
    if sys.platform == "win32":
        # conda-forge's Windows hdf5 package is not discoverable by CMake's
        # find_package(HDF5) the way tttrlib's cmake/FindHDF5.cmake uses it --
        # confirmed on real CI: "Could NOT find HDF5" even with HDF5_ROOT/
        # CMAKE_PREFIX_PATH pointed at this env's prefix. CI provisions a
        # vcpkg-built HDF5 instead (see .github/workflows/*.yml, "Install
        # HDF5 via vcpkg (Windows)", which matches tttrlib's own CI setup);
        # use it here when present.
        # VCPKG_INSTALLATION_ROOT is set in the CI step that runs `vcpkg
        # install`, but this script may run several `pixi run` task-chain
        # levels deeper (test -> build-extensions -> build-tttrlib), and
        # nothing here confirms that env var actually survives that chain --
        # so also try C:\vcpkg, the fixed, documented location every
        # windows-2022/-latest GitHub-hosted runner installs vcpkg to.
        vcpkg_roots = [r for r in (os.environ.get("VCPKG_INSTALLATION_ROOT"), r"C:\vcpkg") if r]
        for vcpkg_root in vcpkg_roots:
            vcpkg_hdf5 = Path(vcpkg_root) / "installed" / "x64-windows"
            if (vcpkg_hdf5 / "include" / "H5public.h").is_file():
                hdf5_root = vcpkg_hdf5
                # vcpkg_hdf5 FIRST: a standalone find_package(HDF5 REQUIRED
                # COMPONENTS C) against vcpkg's tree alone succeeds (real CI,
                # --debug-find-pkg probe), but the real build still failed
                # with prefix listed first. hdf5 is still a conda dependency
                # (other consumers may want it), so CMAKE_PREFIX_PATH search
                # order matters: CONFIG mode uses the first match, and conda's
                # own hdf5-config.cmake in `prefix` -- the one confirmed
                # broken here -- would otherwise be found before vcpkg's.
                cmake_prefix_path = f"{vcpkg_hdf5};{prefix}"
                print(f"build-tttrlib: using vcpkg HDF5 at {vcpkg_hdf5}", flush=True)
                break
        else:
            print(
                f"build-tttrlib: no vcpkg HDF5 found in {vcpkg_roots or '(none checked)'}; "
                f"falling back to {prefix}",
                flush=True,
            )
    args = [
        f"-DCMAKE_PREFIX_PATH={cmake_prefix_path}",
        f"-DHDF5_ROOT={hdf5_root}",
    ]
    if sys.platform != "win32":
        # Forces CMake's module-mode search and skips its own internal
        # CONFIG-mode delegation: on macOS, find_package(HDF5) without this
        # finds Homebrew's config package (/opt/homebrew/lib/cmake/hdf5) and
        # wins over this environment's, which is what the docstring above
        # describes. Confirmed the opposite is true on Windows: this flag is
        # exactly what keeps CMake from finding vcpkg's own hdf5-config.cmake
        # (real CI, "Could NOT find HDF5" even with vcpkg's build correctly
        # selected above) -- vcpkg has no Homebrew-style competing system
        # install to guard against, so leave CONFIG mode available there.
        args.append("-DHDF5_NO_FIND_PACKAGE_CONFIG_FILE=TRUE")
    else:
        # Confirmed via a standalone --debug-find-pkg=HDF5 probe on real CI
        # (run 35255607034): the exact same find_package(HDF5 REQUIRED
        # COMPONENTS C) call, same CMAKE_PREFIX_PATH/HDF5_ROOT, succeeds
        # under the runner's system CMake but still fails under pixi's own
        # cmake package ("Could NOT find HDF5") -- different FindHDF5.cmake
        # internals (different line numbers for the same failure), not an
        # arguments problem. CMAKE_FIND_PACKAGE_PREFER_CONFIG makes
        # find_package() try CONFIG mode first regardless of what a given
        # CMake's bundled FindHDF5.cmake does internally, sidestepping
        # whatever pixi's version lacks rather than depending on it.
        args.append("-DCMAKE_FIND_PACKAGE_PREFER_CONFIG=TRUE")
    return " ".join(args)


def _build_into(prefix: Path) -> bool:
    """Build tttrlib against *prefix* and install it there as a real directory.

    One build can serve two environments only while they agree on the native
    libraries it links; they do not have to. HDF5 is the one that bites — an environment
    solving HDF5 2.1 produces an extension wanting ``libhdf5.320``, which an
    environment carrying 1.14 cannot load at all:

        ImportError: dlopen(...): Library not loaded: @rpath/libhdf5.320.dylib

    So this environment gets an extension linked against *its own* libraries,
    installed as real files, so nothing it imports lives in another
    environment (or in a cache that can be purged under it).

    Parameters
    ----------
    prefix : pathlib.Path
        Environment prefix to build for and install into.

    Returns
    -------
    bool
        ``True`` when the environment imports the build afterwards.
    """
    python = prefix / "bin" / "python"
    target_sp = _site_packages(prefix)
    if not python.is_file() or target_sp is None:
        return False

    build_dir = _BUILD_DIR.parent / f"tttrlib-{prefix.name}"
    staging = build_dir / "pkg"
    shutil.rmtree(build_dir, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    if "CMAKE_BUILD_PARALLEL_LEVEL" not in env:
        env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(os.cpu_count() or 2)
    env["CMAKE_ARGS"] = _cmake_args(prefix)
    print(
        f"build-tttrlib: building for {prefix.name} against its own libraries "
        "(this takes a few minutes)",
        flush=True,
    )
    rc = subprocess.call(
        [
            str(python),
            "-m",
            "pip",
            "install",
            str(_SRC),
            "--no-build-isolation",
            "--no-deps",
            "--no-cache-dir",
            "--target",
            str(staging),
            f"--config-settings=build-dir={build_dir / 'tree'}",
        ],
        env=env,
    )
    if rc != 0:
        print(f"build-tttrlib: dedicated build for {prefix.name} failed", flush=True)
        return False

    # Unlinking drops a link from the old scheme, never the environment it
    # pointed into.
    _clear_tttrlib(target_sp)
    installed = []
    for pattern in _INSTALL_GLOBS:
        for src in sorted(staging.glob(pattern)):
            dst = target_sp / src.name
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
            installed.append(dst)

    # macOS refuses a copied extension whose signature the copy invalidated, and
    # kills the interpreter (exit 137) with no message rather than raising.
    if sys.platform == "darwin":
        for root in installed:
            for pattern in ("*.so", "*.dylib"):
                for binary in root.rglob(pattern):
                    subprocess.run(
                        ["/usr/bin/codesign", "--force", "--sign", "-", str(binary)],
                        capture_output=True,
                    )

    return _verify(prefix)


def link_build() -> bool:
    """Give every configured extra environment its own build of this source.

    Returns
    -------
    bool
        ``True`` when every target environment imports tttrlib afterwards.
    """
    ok = True
    for prefix in _link_targets():
        if (prefix / "bin" / "python").is_file() and not _build_into(prefix):
            print(f"build-tttrlib: {prefix.name} still cannot import tttrlib", flush=True)
            ok = False
    return ok


def main() -> int:
    """Build tttrlib from source and make every configured environment import it.

    Returns
    -------
    int
        Process exit status: ``0`` when the build installed and every
        environment -- this one and each extra one -- imports it.
    """
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

    # The environment prefix is where CMake looks for OpenMP and the rest.
    # This used to also inject `-L… -lomp -Wl,-rpath,…` on macOS,
    # because tttrlib's Python extension compiled with OpenMP but never linked
    # it — and the module's flat-namespace flag let the missing symbols through
    # to fail at import time. That is fixed in tttrlib itself (the extension now
    # links `OpenMP::OpenMP_CXX` like the R and Java modules always did), so a
    # plain build produces an importable module.
    # HDF5 must come from this environment, and pointing CMake at the prefix is
    # not enough to guarantee it: ``find_package(HDF5)`` also searches for an
    # installed HDF5 *CMake config package*, which on macOS finds Homebrew's
    # (``/opt/homebrew/lib/cmake/hdf5``) and wins. The extension then links a
    # second HDF5 into a process that already has this environment's — and
    # whichever initialises first wins, so writing a Photon-HDF5 file aborted
    # the whole process ("Bye...") unless something imported h5py/PyTables
    # first. Forcing module mode with an explicit root keeps both out of the
    # same process.
    env = dict(os.environ)
    if "CMAKE_BUILD_PARALLEL_LEVEL" not in env:
        env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(os.cpu_count() or 2)
    env["CMAKE_ARGS"] = _cmake_args(Path(prefix))

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
    rc = subprocess.call(cmd, env=env)
    if rc != 0:
        return rc
    if not _verify(Path(sys.prefix)):
        return 1
    # An extra environment that cannot import its build is a failed build,
    # not a cosmetic warning: it is discovered later, as a suite that cannot
    # collect, by someone with no reason to suspect this task.
    return 0 if link_build() else 1


if __name__ == "__main__":
    raise SystemExit(main())
