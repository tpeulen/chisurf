"""Guardrail: retired third-party packages stay out of the tree.

Each package listed in :data:`RETIRED` was a runtime dependency that either had
an in-tree replacement written for it -- because the whole package was a few
lines of code -- was superseded by something an existing dependency already
does, or was declared without anything ever importing it. This test fails if an
import or a packaging declaration brings one back.

Notes
-----
These packages may still be *installed* in a development environment, pulled in
transitively by other scientific packages. That is exactly why the guardrail is
needed: an accidental import would work on a developer machine and fail in a
packaged install, usually inside a ``try``/``except`` that turns it into a
silently degraded path rather than a crash.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: ``import name -> (packaging name, what to use instead)``.
RETIRED = {
    "deprecation": (
        "deprecation",
        "use chisurf.core.decorators.deprecated",
    ),
    "click_didyoumean": (
        "click-didyoumean",
        "use chisurf.core.cli_support.DidYouMeanGroup",
    ),
    "tqdm": (
        "tqdm",
        "use chisurf.core.progress.progress / trange",
    ),
    "msgpack_numpy": (
        "msgpack-numpy",
        "encode arrays through the MMFDB payload codec",
    ),
    "pytools": ("pytools", "it was never imported"),
    "jsonschema": ("jsonschema", "it was never imported"),
    "tifffile": (
        "tifffile",
        "use chisurf.core.fio.image (tttrlib's bundled libtiff)",
    ),
    "imageio": (
        "imageio",
        "use chisurf.core.fio.image; note skimage.io routes through imageio too",
    ),
    "imagecodecs": (
        "imagecodecs",
        "it only ever existed to let tifffile decode compressed TIFFs",
    ),
    "numexpr": (
        "numexpr",
        "write a numba kernel; NUMBA_NUM_THREADS already comes from settings",
    ),
    "tables": (
        "pytables",
        "posterior samples are .npz; nothing else needed HDF5 through it",
    ),
    "mdtraj": (
        "mdtraj",
        "use chisurf.core.fio.trajectory + chisurf.core.structure.trajectory_data",
    ),
    "boost_histogram": (
        "boost-histogram",
        "histograms are filled in tttrlib, which is faster on matched features",
    ),
    "pyarrow": (
        "pyarrow",
        "it backed ndxplorer's Arrow tables; nothing in chisurf ever imported it",
    ),
    "requests": (
        "requests",
        "use chisurf.core.http",
    ),
    "emcee": (
        "emcee",
        "use chisurf.core.fitting.ensemble",
    ),
    "qtconsole": (
        "qtconsole",
        "use chisurf.gui.chinsole",
    ),
    "sklearn": (
        "scikit-learn",
        "use chisurf.core.ml (GaussianMixture, KMeans, PCA, IncrementalPCA, "
        "StandardScaler, MLPRegressor, HDBSCAN)",
    ),
    "hdbscan": (
        "hdbscan",
        "use chisurf.core.ml.cluster.HDBSCAN",
    ),
}

#: Further distribution names that install the same retired module, checked by
#: the packaging test alongside the primary name. A conda recipe says
#: ``pyarrow-core`` where a wheel says ``pyarrow``, and matching only the latter
#: would let the dependency back in under a spelling the guardrail cannot see.
_ALSO_PACKAGED_AS = {
    "pyarrow": ("pyarrow-core",),
    "tables": ("pytables",),
}

#: Retired from the *application* but still declared as an optional extra, so
#: only the import check applies: ``requests`` backs the spectra scrapers under
#: the ``scrape`` extra, which the application never imports.
_IMPORT_ONLY = {"requests"}

#: Files whose only mention of the names is this test itself.
_ALLOWED = {"test/test_no_retired_dependency_imports.py"}

#: Paths exempt from one module's import check, with the reason.
_ALLOWED_PREFIXES = {
    "requests": ("chisurf/plugins/spectra_downloader/download/",),
    # The parity suite compares chisurf.core.ml against scikit-learn *where it
    # happens to be installed* (`pytest.importorskip`), and the benchmark times
    # the replacement against both packages it replaced. That is the only way to
    # keep proving the port is a drop-in and still worth its speed now that
    # neither library is in any manifest. Nothing shipped may import them — that
    # is what this guardrail is for — but the tests that prove the replacement
    # must be allowed to.
    "sklearn": ("test/ml/", "test/benchmarks/"),
    "hdbscan": ("test/benchmarks/",),
}

#: Packaging manifests that describe the chisurf runtime. Deliberately only
#: chisurf's own: the manifests under ``modules/`` belong to sibling checkouts
#: that are not pinned by this repository, so asserting on them would make this
#: test's result depend on which revision of a neighbour happens to be present.
#: Each of those projects guards its own dependencies.
#:
#: ``build_tools/setup_runtime.sh`` is a manifest too, even though it is a shell
#: script: it is the dependency list the AppImage runtime is solved from. It was
#: missing here until 2026-08-05, and in that blind spot it had accumulated six
#: packages retired long before -- ``pytools``, ``click-didyoumean``,
#: ``deprecation``, ``emcee``, ``pyarrow`` and ``boost-histogram``. A guardrail
#: that covers only the manifests someone remembered to list is how a retired
#: dependency comes back.
_MANIFESTS = (
    "pixi.toml",
    "pyproject.toml",
    "setup.py",
    "rattler-recipe/recipe.yaml",
    "test/settings/test_py314.toml",
    "build_tools/setup_runtime.sh",
)


def _python_sources():
    """Yield every Python source file under the folders chisurf ships.

    Yields
    ------
    pathlib.Path
    """
    for folder in ("chisurf", "modules/chinet", "modules/ndxplorer", "test"):
        folder_path = REPO_ROOT / folder
        if folder_path.exists():
            yield from folder_path.rglob("*.py")


def _declared_dependencies(text: str) -> set[str]:
    """Return the requirement names declared in a manifest.

    Comments are stripped first, so an explanatory note naming a retired
    package does not read as a declaration. The TOML (``name = "*"``), recipe
    YAML (``- name >=1.0``) and shell-array (``"name<2.0"``) spellings are all
    recognised.

    The shell form makes this deliberately over-eager -- every bare word in
    ``setup_runtime.sh`` reads as a name. That is harmless, because the result
    is only ever intersected with the retired set, and being over-eager is the
    safe direction: a missed declaration lets a dependency back in, while a
    spurious one would have to collide with a retired package name to matter.

    Parameters
    ----------
    text : str
        Full manifest text.

    Returns
    -------
    set of str
        Lower-cased requirement names.
    """
    names = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        match = re.match(r"^\s*(?:-\s*)?[\"']?([A-Za-z0-9_.\-]+)", line)
        if match:
            names.add(match.group(1).lower())
    return names


@pytest.mark.parametrize("module", sorted(RETIRED))
def test_no_module_imports_retired_package(module):
    """No shipped source imports the retired package."""
    packaging_name, hint = RETIRED[module]
    pattern = re.compile(rf"^\s*(?:import\s+{module}\b|from\s+{module}[\s.])", re.MULTILINE)
    exempt = _ALLOWED_PREFIXES.get(module, ())
    offenders = []
    for path in _python_sources():
        rel = str(path.relative_to(REPO_ROOT))
        if rel in _ALLOWED or rel.startswith(exempt):
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(rel)
    assert not offenders, (
        f"{packaging_name} is no longer a dependency ({hint}). Importing modules: {offenders}"
    )


def test_no_module_imports_skimage_io():
    """``skimage.io`` is imageio wearing a different name.

    scikit-image stays a dependency, but its ``io`` subpackage reads and writes
    through an imageio plugin, so importing it undoes the removal without ever
    naming the package -- and it is the reader people reach for out of habit.
    Everything it was used for goes through :mod:`chisurf.core.fio.image`.
    """
    pattern = re.compile(
        r"^\s*(?:import\s+skimage\.io\b|from\s+skimage\.io\s|from\s+skimage\s+import\s+io\b)",
        re.MULTILINE,
    )
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _python_sources()
        if str(path.relative_to(REPO_ROOT)) not in _ALLOWED
        and pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not offenders, (
        "skimage.io reads through imageio, a retired dependency; "
        f"use chisurf.core.fio.image instead. Importing modules: {offenders}"
    )


@pytest.mark.parametrize("module", sorted(RETIRED))
def test_packaging_does_not_declare_retired_package(module):
    """No packaging manifest declares the retired package."""
    if module in _IMPORT_ONLY:
        pytest.skip(f"{module} stays declared as an optional extra")
    packaging_name, hint = RETIRED[module]
    names = {packaging_name.lower(), *(n.lower() for n in _ALSO_PACKAGED_AS.get(module, ()))}
    offenders = []
    for rel in _MANIFESTS:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        declared = _declared_dependencies(path.read_text(encoding="utf-8", errors="ignore"))
        found = names & declared
        if found:
            offenders.append(f"{rel} ({', '.join(sorted(found))})")
    assert not offenders, f"{packaging_name} reintroduced as a dependency ({hint}) in: {offenders}"
