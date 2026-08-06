import os
import pathlib
import sys
from distutils.command.build import build as _build

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

HERE = pathlib.Path(__file__).parent.resolve()

# A PEP 517 build runs this file with ``exec`` and the project root *not* on
# ``sys.path``, so a plain import of the sibling module fails there and only
# there -- which is every real ``pip install``.
sys.path.insert(0, str(HERE))
from _shipped_docs import iter_shipped_docs  # noqa: E402

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
        """Write the static version file, then run the normal build."""
        _write_version_file(_resolve_version())
        super().run()


class build_py(_build_py):
    """Build normally, then carry the documentation inside the package.

    The help browser reads ``docs/`` at runtime, and ``docs/`` is not part of
    any package, so an installed ChiSurf had no documentation to open. The
    selection ships into ``chisurf/docs`` in the *build* directory -- never
    into the checkout, where it would shadow the originals with a stale copy.
    """

    def run(self):
        """Build the packages, then copy the shipped documentation beside them."""
        super().run()
        if self.build_lib is None:
            return
        docs = HERE / "docs"
        target = pathlib.Path(self.build_lib) / "chisurf" / "docs"
        count = 0
        for relative in iter_shipped_docs(docs):
            destination = target / relative
            self.mkpath(str(destination.parent))
            self.copy_file(str(docs / relative), str(destination), preserve_mode=False)
            count += 1
        print(f"Copied {count} documentation files -> {target}")

    def get_outputs(self, include_bytecode=1):
        """Report the copied documentation, so installers place it too."""
        outputs = super().get_outputs(include_bytecode)
        target = pathlib.Path(self.build_lib) / "chisurf" / "docs"
        outputs.extend(str(target / relative) for relative in iter_shipped_docs(HERE / "docs"))
        return outputs


# ---------------------------------------------------------------------------
setup(
    name="chisurf",
    version=os.environ.get("CHISURF_VERSION", "26.dev0"),
    # Package discovery (incl. the vendored ``chinet`` package) is configured in
    # pyproject.toml's [tool.setuptools.packages.find].
    include_package_data=True,
    zip_safe=False,
    cmdclass={"build": build, "build_py": build_py},
)
