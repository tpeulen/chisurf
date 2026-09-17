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

After a successful build the artifacts are **symlinked** into any extra developer
environment (by default a conda env named ``arm64``), so that env imports this build
directly and never needs its own ``pip install``. A rebuild is then visible everywhere
at once. Set ``CHISURF_TTTRLIB_LINK_ENVS`` to override the targets, or to an empty
string to switch it off. Linking is a convenience: a missing or ABI-incompatible env is
reported and skipped, never a build failure.

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

# Extra environments that should see this build without a second install. The pixi
# environment is where the wheel lands; a developer usually *also* has a conda env they
# run scripts and editors from (here `arm64`), and re-installing tttrlib into it after
# every C++ change is both slow and the source of the stale-copy litter this replaces.
# Symlinking instead means one build serves both, and a rebuild is visible immediately.
#
# Override with CHISURF_TTTRLIB_LINK_ENVS (os.pathsep-separated env prefixes); set it to
# an empty string to disable. Missing envs are skipped silently — this is a convenience,
# never a build failure.
_LINK_ENVS_VAR = "CHISURF_TTTRLIB_LINK_ENVS"
_DEFAULT_LINK_ENV_NAMES = ("arm64",)

#: The files a tttrlib install consists of. Only these names are ever replaced.
#:
#: tttrlib ships in one of two shapes and this has to handle both, because which
#: one you get depends on the checkout under ``modules/tttrlib`` rather than on
#: anything here. Before the module split it was a flat wrapper plus one
#: extension; after it, a **package directory** holding the extension and one
#: shared library per module. Linking only the flat names against a split build
#: finds no extension and skips silently -- which is what left the sibling env
#: with three dangling symlinks and no tttrlib at all.
_ARTIFACTS = ("tttrlib.py",)
_ARTIFACT_GLOBS = ("_tttrlib*.so", "tttrlib-*.dist-info")
#: The post-split package directory, linked whole when it is what was built.
_PACKAGE_DIR = "tttrlib"


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
    roots += [Path.home() / "mambaforge", Path.home() / "miniforge3",
              Path.home() / "miniconda3", Path.home() / "anaconda3"]
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

    This is not hypothetical. ``tttrlib.py`` is shared with the linked
    environments by symlink while each keeps its own ``_tttrlib*.so``, so any
    build that copies a wrapper into a *linked* environment writes through the
    symlink and replaces the shared one, leaving every other environment with an
    older extension. Verifying the environment we installed into turns that into
    a failed build task instead of a broken launch.
    """
    python = prefix / "bin" / "python"
    if not python.is_file():
        return True
    check = subprocess.run(
        [str(python), "-c",
         "import tttrlib;print(tttrlib.__version__, tttrlib.__file__)"],
        capture_output=True, text=True,
    )
    if check.returncode != 0:
        print("build-tttrlib: the build installed but does not import:\n"
              f"{check.stderr.strip()}\n"
              "build-tttrlib: the wrapper and the compiled extension disagree; "
              "rebuild rather than copying one of them into place.", flush=True)
        return False
    print(f"build-tttrlib: {prefix.name} -> {check.stdout.strip()}", flush=True)
    return True


def _link_into(prefix: Path, source_sp: Path) -> bool:
    """Symlink the freshly built tttrlib from *source_sp* into the env at *prefix*.

    Returns True when the environment ends up importing this build.
    """
    target_sp = _site_packages(prefix)
    if target_sp is None:
        print(f"build-tttrlib: {prefix} has no site-packages; skipped", flush=True)
        return False

    # A compiled extension is tied to an exact CPython ABI. Linking a cp312 module into a
    # cp311 env produces an ImportError at first use, far from the cause, so refuse here.
    package = source_sp / _PACKAGE_DIR
    ext_globs = (
        [package.glob("_tttrlib*.so")] if package.is_dir() else []
    ) + [source_sp.glob("_tttrlib*.so")]
    src_ext = next(
        (e for glob in ext_globs for e in sorted(glob)), None
    )
    if src_ext is None:
        print("build-tttrlib: no built extension to link from; skipped", flush=True)
        return False
    tag = src_ext.name.split(".")[1]                     # e.g. cpython-312-darwin
    target_py = target_sp.parent.name                    # e.g. python3.12
    want = "cpython-" + target_py.replace("python", "").replace(".", "")
    if not tag.startswith(want):
        print(f"build-tttrlib: {prefix.name} is {target_py} but the extension is '{tag}'; "
              "skipped (a compiled extension cannot cross CPython versions)", flush=True)
        return False

    linked = []
    if package.is_dir():
        # The split build: one link for the package, which carries the extension
        # and every module library with it.
        linked.append((package, target_sp / _PACKAGE_DIR))
    else:
        for name in _ARTIFACTS:
            src = source_sp / name
            if src.is_file():
                linked.append((src, target_sp / name))
        for pattern in ("_tttrlib*.so",):
            for src in sorted(source_sp.glob(pattern)):
                linked.append((src, target_sp / src.name))
    for src in sorted(source_sp.glob("tttrlib-*.dist-info")):
        linked.append((src, target_sp / src.name))

    # Whichever shape was *not* built leaves its own names behind, and a stale
    # symlink to a file that no longer exists is worse than an absent one: it
    # reads as an install. Clear the other layout's artefacts before linking.
    stale = [target_sp / _PACKAGE_DIR] if not package.is_dir() else [
        target_sp / name for name in _ARTIFACTS
    ] + sorted(target_sp.glob("_tttrlib*.so"))
    for path in stale:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    for src, dst in linked:
        # Replace whatever is there — a previous real install, or an older symlink.
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        elif dst.is_dir():
            shutil.rmtree(dst)
        dst.symlink_to(src)

    # Prove it: a link that does not import is worse than no link, because the failure
    # surfaces later in someone else's script.
    python = prefix / "bin" / "python"
    if not python.is_file():
        print(f"build-tttrlib: linked into {prefix} (no interpreter found to verify)",
              flush=True)
        return True
    check = subprocess.run(
        [str(python), "-c",
         "import tttrlib,sys;print(tttrlib.__version__, tttrlib.__file__)"],
        capture_output=True, text=True,
    )
    if check.returncode != 0:
        print(f"build-tttrlib: linked into {prefix} but it does not import:\n"
              f"{check.stderr.strip()}", flush=True)
        return False
    print(f"build-tttrlib: linked into {prefix.name} -> {check.stdout.strip()}", flush=True)
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
        # traditional (module-mode) find_package(HDF5) the way tttrlib's
        # cmake/FindHDF5.cmake uses it -- confirmed on real CI: "Could NOT
        # find HDF5" even with HDF5_ROOT/CMAKE_PREFIX_PATH pointed at this
        # env's prefix. CI provisions a vcpkg-built HDF5 instead (see
        # .github/workflows/*.yml, "Install HDF5 via vcpkg (Windows)", which
        # matches tttrlib's own CI setup); use it here when present, since
        # HDF5_NO_FIND_PACKAGE_CONFIG_FILE below forces module mode and so
        # cannot fall back to vcpkg's config package on its own.
        vcpkg_root = os.environ.get("VCPKG_INSTALLATION_ROOT")
        if vcpkg_root:
            vcpkg_hdf5 = Path(vcpkg_root) / "installed" / "x64-windows"
            if (vcpkg_hdf5 / "include" / "H5public.h").is_file():
                hdf5_root = vcpkg_hdf5
                cmake_prefix_path = f"{prefix};{vcpkg_hdf5}"
    return " ".join(
        (
            f"-DCMAKE_PREFIX_PATH={cmake_prefix_path}",
            f"-DHDF5_ROOT={hdf5_root}",
            "-DHDF5_NO_FIND_PACKAGE_CONFIG_FILE=TRUE",
        )
    )


def _build_into(prefix: Path) -> bool:
    """Build tttrlib against *prefix* and install it there as a real directory.

    The fallback when a symlink to the shared build cannot be loaded. One build
    can serve two environments only while they agree on the native libraries it
    links; they do not have to. HDF5 is the one that bites — an environment
    solving HDF5 2.1 produces an extension wanting ``libhdf5.320``, which an
    environment carrying 1.14 cannot load at all:

        ImportError: dlopen(...): Library not loaded: @rpath/libhdf5.320.dylib

    So this environment gets an extension linked against *its own* libraries,
    installed as real files rather than symlinks so the next shared build does
    not silently point it back at something it cannot load.

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
    env["CMAKE_ARGS"] = _cmake_args(prefix)
    print(f"build-tttrlib: {prefix.name} cannot load the shared build; "
          "building against its own libraries (this takes a few minutes)", flush=True)
    rc = subprocess.call(
        [str(python), "-m", "pip", "install", str(_SRC),
         "--no-build-isolation", "--no-deps", "--no-cache-dir",
         "--target", str(staging),
         f"--config-settings=build-dir={build_dir / 'tree'}"],
        env=env,
    )
    if rc != 0:
        print(f"build-tttrlib: dedicated build for {prefix.name} failed", flush=True)
        return False

    installed = []
    for src in [staging / _PACKAGE_DIR, *sorted(staging.glob("tttrlib-*.dist-info"))]:
        if not src.exists():
            continue
        dst = target_sp / src.name
        # Symlinks from an earlier shared build: unlink drops the link, never
        # the environment it points into.
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        elif dst.is_dir():
            shutil.rmtree(dst)
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
    """Make every configured extra environment import this build.

    Symlinks the freshly built tttrlib into each one, and where that link cannot
    be *loaded* — different CPython ABI, or native libraries that disagree —
    builds a dedicated copy for that environment instead. A link that does not
    import is worse than no link: the failure surfaces later, in someone else's
    script, as an environment with no tttrlib.

    Returns
    -------
    bool
        ``True`` when every target environment imports tttrlib afterwards.
    """
    source_sp = Path(
        subprocess.run([sys.executable, "-c",
                        "import site;print(site.getsitepackages()[0])"],
                       capture_output=True, text=True).stdout.strip()
    )
    if not source_sp.is_dir():
        return True
    ok = True
    for prefix in _link_targets():
        try:
            if _link_into(prefix, source_sp):
                continue
        except OSError as exc:
            print(f"build-tttrlib: could not link into {prefix}: {exc}", flush=True)
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
        environment -- the one built into and each linked one -- imports it.
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
    # A linked environment that cannot import what was built is a failed build,
    # not a cosmetic warning: it is discovered later, as a suite that cannot
    # collect, by someone with no reason to suspect this task.
    return 0 if link_build() else 1


if __name__ == "__main__":
    raise SystemExit(main())
