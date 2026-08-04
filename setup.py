import os
import pathlib
from distutils.command.build import build as _build
from setuptools import setup

HERE = pathlib.Path(__file__).parent.resolve()

# ---------------------------------------------------------------------------
# Build-time static version
# ---------------------------------------------------------------------------
# Resolve the version once at build time and freeze it into
# ``chisurf/core/_version.py`` so the *installed* app reads a static string
# instead of spawning git on every ``import chisurf`` (see chisurf/core/info.py).
# Editable/develop installs deliberately skip this, keeping the dev version
# git-derived and live.
#
# This file used to also compile the Burbulator C++ library into the acquisition
# plugin, which is why it overrode ``develop`` as well. That simulator is retired
# — the photon simulator in the TTTR library covers its model and more — so
# ChiSurf itself no longer builds any C++ here. See
# ``okf/references/burbulator-simulator.md`` for what it did.


def _resolve_version() -> str:
    env = os.environ.get("CHISURF_VERSION")
    if env:
        return env.strip()
    # Remove any stale generated file so info.py falls through to the git path
    # rather than reading a previous build's frozen version.
    version_file = HERE / "chisurf" / "core" / "_version.py"
    try:
        version_file.unlink()
    except FileNotFoundError:
        pass
    info_path = HERE / "chisurf" / "core" / "info.py"
    ns: dict = {"__file__": str(info_path)}
    exec(compile(info_path.read_text(), str(info_path), "exec"), ns)
    return ns.get("__version__", "26.dev0")


def _write_version_file(version: str) -> None:
    target = HERE / "chisurf" / "core" / "_version.py"
    target.write_text(
        "# Generated at build time -- do not edit or commit.\n"
        f'__version__ = "{version}"\n'
    )
    print(f"Wrote static version {version!r} -> {target}")


class build(_build):
    """Freeze the version, then build normally."""

    def run(self):
        _write_version_file(_resolve_version())
        super().run()


# ---------------------------------------------------------------------------
setup(
    name="chisurf",
    version=os.environ.get("CHISURF_VERSION", "26.dev0"),
    # Package discovery (incl. the vendored ``chinet`` package) is configured in
    # pyproject.toml's [tool.setuptools.packages.find].
    include_package_data=True,
    zip_safe=False,
    cmdclass={"build": build},
)
