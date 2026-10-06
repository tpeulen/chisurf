"""Guard: scipy is being retired from the shipped package's runtime deps.

**The rule: no new scipy.** ``test/scipy_import_allowlist.txt`` is a shrinking
record of files not yet routed -- never somewhere to add yourself to make this
test pass. When the list empties, scipy leaves the runtime manifests
(``pyproject.toml``, ``pixi.toml``, ``rattler-recipe/recipe.yaml``) into the
``test`` and ``legacy-io`` extras, and joins ``RETIRED`` in
:mod:`test.test_no_retired_dependency_imports`.

Why it is going:

* **WASM.** chisurf is moving to the browser (Pyodide, PRD-041's route). scipy
  is a ~30 MB wheel where chisurf uses ~2% of its surface; every scipy call in
  the runtime tree is a thing a browser page must download and JIT-load.
  tttrlib and IMP.bff compile to wasm32 and take their kernels with them.
* **Import cost.** ``scipy.stats`` costs ~0.9 s at import -- measured, and the
  reason ``irf_estimation`` is already lazy-served from
  ``chisurf.core.fluorescence.tcspc``.
* **Ownership.** The remaining calls split cleanly along seams that already
  exist: performance-relevant numerics belong in IMP.bff's C++ core (the
  optimizers around ``FitMinimizer``), image/spatial/clustering kernels in
  tttrlib (next to the already-shipping ``hdbscan``, ``kmeans``, ``KDTree``,
  ``richardson_lucy_2d/3d`` and the tested C++ ``rank_filters``/fast-gaussian),
  cold scalar math in a small local ``chisurf/core/math/special.py``, and the
  MAT-file readers behind an optional ``legacy-io`` extra.

Test files are exempt: scipy stays a test dependency and is the independent
oracle for every parity test this retirement writes.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ALLOWLIST = _ROOT / "test" / "scipy_import_allowlist.txt"

#: The packages the retirement covers. Same scope as the numba seam: the claim
#: is "the shipped chisurf tree imports scipy nowhere at runtime", not "the
#: solved environment has no scipy" -- it stays for tests and for sibling
#: checkouts (modules/quest, modules/imp-tricks) that guard their own.
#: ChiMOL is excluded like under numba: its kernels are being removed by the
#: WebGPU port, a separate effort with its own tracking.
_EXCLUDED_PREFIXES = ("chisurf/plugins/chimol/",)

_PACKAGES = (
    _ROOT / "chisurf",
    _ROOT / "modules" / "ndxplorer",
)

#: Any spelling of the import, at module scope or inside a function -- a
#: function-local ``import scipy`` is still a dependency.
_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+scipy[\w.]*|from\s+scipy[\w.]*\s+import)",
    re.MULTILINE,
)


def _load_allowlist() -> set[str]:
    """Return the allow-listed repository-relative paths.

    Returns
    -------
    set of str
        Paths with blank lines and ``#`` comments (including the per-route
        section headers and per-file route notes) stripped.
    """
    lines = _ALLOWLIST.read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def _current_importers() -> set[str]:
    """Return every shipped file that imports scipy.

    Returns
    -------
    set of str
        Repository-relative POSIX paths, tests excluded.
    """
    found: set[str] = set()
    for package in _PACKAGES:
        if not package.exists():
            continue
        for path in package.rglob("*.py"):
            if any(part in ("test", "tests") for part in path.parts):
                continue
            relative = path.relative_to(_ROOT).as_posix()
            if relative.startswith(_EXCLUDED_PREFIXES):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if _IMPORT_RE.search(text):
                found.add(relative)
    return found


def test_no_new_scipy_imports():
    """No shipped file imports scipy unless it is already on the allow-list."""
    new_offenders = sorted(_current_importers() - _load_allowlist())
    assert not new_offenders, (
        "New scipy import(s) detected -- scipy is being retired:\n  "
        + "\n  ".join(new_offenders)
        + "\n\nDo NOT add these to test/scipy_import_allowlist.txt: that list "
        "only shrinks. Route the call instead -- numpy if numpy 2.x already "
        "has it, IMP.bff C++ for performance-relevant numerics (optimizers, "
        "hot special functions), tttrlib for image/spatial/clustering "
        "kernels, a small local module for cold scalar math, the legacy-io "
        "extra for scipy.io MAT files."
    )


def test_allowlist_has_no_stale_entries():
    """Every allow-listed file still imports scipy; routed ones must be struck."""
    stale = sorted(_load_allowlist() - _current_importers())
    assert not stale, (
        "Allow-list entries no longer import scipy -- strike them from "
        "test/scipy_import_allowlist.txt:\n  " + "\n  ".join(stale)
    )
