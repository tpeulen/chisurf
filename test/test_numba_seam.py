"""Guard: numba is being retired from the shipped package, and only shrinks.

**The rule: no new numba.** ``test/numba_import_allowlist.txt`` is a shrinking
record of files not yet ported -- never somewhere to add yourself to make this
test pass. When the list empties, numba leaves the six manifests and joins
``RETIRED`` in :mod:`test.test_no_retired_dependency_imports`.

Why it is going, given it is the thing several other retirements were built on:

* **It stalls the GUI thread.** Opening a fit window once cost 229.5 ms
  JIT-compiling a three-line statistic (``okf/log.md``); a ~340 ms
  first-evaluation compile is why ``per``-mode convolution already routes to
  the photon library instead.
* **Its thread pool latches.** ``NUMBA_NUM_THREADS`` cannot be set once a
  ``parallel=True`` kernel has run, which is why ``pytest test/fio`` fails as a
  directory and passes file-by-file, and why ``parallel=True`` is banned
  outright in :mod:`chisurf.core.ml`.
* **``fastmath`` changes answers quietly.** One kernel's ``fastmath=True``
  folded away its own ``isfinite`` guard, so which bin a NaN landed in depended
  on whether numba was installed.
* **It cannot run in the browser**, which blocks shipping any of this to
  Pyodide.

And -- measured, not assumed -- it is no longer buying speed on the fitting hot
path. A 1024-channel 2-component ``LifetimeModel`` fit calls **no numba kernel
at all** (the convolution is 40% of it and is already the photon library's), and
in a FRET fit numba's own dispatcher type-resolution shows up *above* the
kernels it dispatches to. On arrays of ``2 * n_components`` elements, plain
NumPy is the faster answer, not the compromise.

Test files are exempt: keeping numba as an independent oracle for a parity test
is exactly what a parity test is for.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ALLOWLIST = _ROOT / "test" / "numba_import_allowlist.txt"

#: The packages the retirement covers. Sibling checkouts (``modules/quest``,
#: ``modules/imp-tricks``) guard their own and still depend on numba, so numba
#: stays in the solved environment until those are ported too -- the claim this
#: file backs is "chisurf imports numba nowhere", not "the dependency is gone".
#: ChiMOL is excluded, not exempted. Its kernels are being removed by the
#: WebGPU port, which is a separate effort with its own tracking, and it does
#: not go through this list. Listing them here made this guard fail every time
#: that work landed a file -- nine times in one session -- which is noise about
#: someone else's progress rather than a signal about this one.
_EXCLUDED_PREFIXES = ("chisurf/plugins/chimol/",)

_PACKAGES = (
    _ROOT / "chisurf",
    _ROOT / "modules" / "ndxplorer",
)

#: Any spelling of the import, at module scope or inside a function -- a
#: function-local ``import numba`` is still a dependency.
_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+numba|from\s+numba\s+import|import\s+numba\s+as)",
    re.MULTILINE,
)


def _load_allowlist() -> set[str]:
    """Return the allow-listed repository-relative paths.

    Returns
    -------
    set of str
        Paths with blank lines and ``#`` comments (including the per-route
        section headers) stripped.
    """
    lines = _ALLOWLIST.read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def _current_importers() -> set[str]:
    """Return every shipped file that imports numba.

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


def test_no_new_numba_imports():
    """No shipped file imports numba unless it is already on the allow-list."""
    new_offenders = sorted(_current_importers() - _load_allowlist())
    assert not new_offenders, (
        "New numba import(s) detected -- numba is being retired:\n  "
        + "\n  ".join(new_offenders)
        + "\n\nDo NOT add these to test/numba_import_allowlist.txt: that list "
        "only shrinks. Route the kernel instead -- plain NumPy if it is "
        "elementwise or small, tttrlib if a compiled equivalent already ships, "
        "IMP.bff/IMP.cgmol if it is molecular modelling, a new tttrlib kernel "
        "if it is genuinely serial and hot."
    )


def test_allowlist_has_no_stale_entries():
    """Every allow-listed file still imports numba; ported ones must be struck."""
    stale = sorted(_load_allowlist() - _current_importers())
    assert not stale, (
        "Allow-list entries no longer import numba -- strike them from "
        "test/numba_import_allowlist.txt:\n  " + "\n  ".join(stale)
    )
