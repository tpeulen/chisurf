"""Guard: pyqtgraph is imported only through the chiplot backend seam.

PRD-64 confines every ``pyqtgraph`` import to one sanctioned module
(``chisurf/gui/chiplot/backends/pyqtgraph_backend.py``). Every other file that
still imports pyqtgraph directly is listed in
``test/pyqtgraph_import_allowlist.txt`` — the migration tracker.

This test fails if a **new** file imports pyqtgraph directly (regression) or if
a listed file has already been migrated (stale allow-list entry). The end state
is an empty allow-list (bar the ChiMOL OpenGL module owned by PRD-57).
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"
_ALLOWLIST = _ROOT / "test" / "pyqtgraph_import_allowlist.txt"
_SANCTIONED = "chisurf/gui/chiplot/backends/pyqtgraph_backend.py"
_IMPORT_RE = re.compile(r"^\s*(?:import\s+pyqtgraph|from\s+pyqtgraph)", re.MULTILINE)
_DOCKAREA_RE = re.compile(
    r"^\s*(?:import\s+pyqtgraph\.dockarea|from\s+pyqtgraph\.dockarea\s+import|"
    r"from\s+pyqtgraph\s+import\s+dockarea)",
    re.MULTILINE,
)


def _load_allowlist() -> set[str]:
    lines = _ALLOWLIST.read_text().splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def _current_importers() -> set[str]:
    found = set()
    for path in _PKG.rglob("*.py"):
        rel = path.relative_to(_ROOT).as_posix()
        if rel == _SANCTIONED:
            continue
        if _IMPORT_RE.search(path.read_text(encoding="utf-8", errors="ignore")):
            found.add(rel)
    return found


def test_no_new_direct_pyqtgraph_imports():
    """No file outside the sanctioned backend imports pyqtgraph unless allow-listed."""
    allow = _load_allowlist()
    current = _current_importers()

    new_offenders = sorted(current - allow)
    assert not new_offenders, (
        "New direct pyqtgraph import(s) detected — route plotting through "
        "chisurf.gui.chiplot instead (PRD-64):\n  " + "\n  ".join(new_offenders)
    )


def test_allowlist_has_no_stale_entries():
    """Every allow-listed file still imports pyqtgraph; migrated ones must be removed."""
    allow = _load_allowlist()
    current = _current_importers()

    stale = sorted(allow - current)
    assert not stale, (
        "Allow-list entries no longer import pyqtgraph — remove them from "
        "test/pyqtgraph_import_allowlist.txt:\n  " + "\n  ".join(stale)
    )


def test_no_pyqtgraph_dockarea():
    """``pyqtgraph.dockarea`` is deprecated repo-wide — use the chisurf DockArea.

    Replaced by ``chisurf.gui.widgets.dock_area.dock_area`` (DockArea /
    DockSplitter). This guard forbids reintroducing the pyqtgraph dock system
    anywhere, including the sanctioned chiplot backend.
    """
    offenders = sorted(
        path.relative_to(_ROOT).as_posix()
        for path in _PKG.rglob("*.py")
        if _DOCKAREA_RE.search(path.read_text(encoding="utf-8", errors="ignore"))
    )
    assert not offenders, (
        "pyqtgraph.dockarea is deprecated — use chisurf.gui.widgets.dock_area "
        "(DockArea / DockSplitter) instead:\n  " + "\n  ".join(offenders)
    )
