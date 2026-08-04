"""Guard: pyqtgraph is imported only through the chiplot backend seam.

**The rule: plot through chiplot, never pyqtgraph.** ``chisurf.gui.chiplot`` is
*the* plotting API; pyqtgraph is an implementation detail behind it that the repo
is migrating away from (PRD-64). Concretely:

* new code must not ``import pyqtgraph``;
* ``test/pyqtgraph_import_allowlist.txt`` is a **shrinking** record of files not
  yet ported — never somewhere to add yourself to make this test pass;
* use the chiplot spelling: ``Plot.line`` not ``plot``, ``to_pen`` not
  ``mkPen``, ``set_labels`` not ``setLabel``. Anything chiplot lacks *falls
  through* to pyqtgraph with a ``ChiplotPassthroughWarning`` rather than
  failing, so a wrong spelling does not announce itself at import time — it
  breaks later, when a chiplot ``Pen`` reaches a pyqtgraph function;
* **if chiplot cannot do it, add the API to chiplot**, then use it. Reaching
  past the seam "just this once" is what stops a migration ever finishing.

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
        "New direct pyqtgraph import(s) detected — plot through "
        "chisurf.gui.chiplot instead (PRD-64):\n  "
        + "\n  ".join(new_offenders)
        + "\n\nDo NOT add these to test/pyqtgraph_import_allowlist.txt: that list "
        "only shrinks. Port the call site — Plot.line(x, y, pen=…, width=…, "
        "style=…, name=…) rather than plot(...)/mkPen(...) — and if chiplot "
        "cannot express it, add the API to chiplot first."
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


# ── the other way past the seam: ``.native`` ──────────────────────────────────
#
# ``Plot.native`` is the *documented* escape hatch to the backing pyqtgraph
# object, which makes it the invisible one: it reaches pyqtgraph without
# importing it, so every check above passes while the call site is as coupled to
# the renderer as a direct import. Worse, most of these are not gaps at all —
# they predate the chiplot API that now covers them (``set_si_prefix``,
# ``set_axis_visible``, ``set_tick_spacing``, ``legend``), so they are simply
# legacy that nobody had a reason to notice.
#
# Same contract as the import list: shrinking, never somewhere to add yourself.

_NATIVE_ALLOWLIST = _ROOT / "test" / "chiplot_native_allowlist.txt"
#: ``.native`` on a chiplot handle or canvas. Deliberately loose — it also
#: catches ``handle.native``, which is the same reach one level down.
_NATIVE_RE = re.compile(r"\.native\b(?!_)")
#: Attribute names that merely *start* with ``native`` and have nothing to do
#: with plotting (``self.native_tools``, ``native_cutoff_on``).
_NATIVE_FALSE_POSITIVES = re.compile(r"\.native_[a-z]")
#: A ``#`` comment. Naming the escape hatch in prose — which the comment
#: *explaining a port away from it* necessarily does — is not reaching through
#: it, and a guard that cannot tell the difference punishes documenting the fix.
_COMMENT_RE = re.compile(r"#.*$", re.MULTILINE)


def _load_native_allowlist() -> set[str]:
    if not _NATIVE_ALLOWLIST.is_file():
        return set()
    lines = _NATIVE_ALLOWLIST.read_text().splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def _current_native_users() -> set[str]:
    found = set()
    for path in _PKG.rglob("*.py"):
        rel = path.relative_to(_ROOT).as_posix()
        if rel.startswith("chisurf/gui/chiplot/"):
            continue  # chiplot *is* the seam; ``.native`` is its own property
        text = path.read_text(encoding="utf-8", errors="ignore")
        text = _COMMENT_RE.sub("", text)
        text = _NATIVE_FALSE_POSITIVES.sub(".", text)
        if _NATIVE_RE.search(text):
            found.add(rel)
    return found


def test_no_new_reaches_past_the_chiplot_seam():
    """A file outside chiplot must not reach the renderer through ``.native``."""
    offenders = sorted(_current_native_users() - _load_native_allowlist())
    assert not offenders, (
        "these files reach pyqtgraph through the chiplot escape hatch:\n  "
        + "\n  ".join(offenders)
        + "\n\nCheck whether chiplot already has the API — most of these predate "
        "one that exists (set_si_prefix, set_axis_visible, set_tick_spacing, "
        "legend). If it genuinely does not, add it to chiplot and use that. Do "
        "NOT add the file to test/chiplot_native_allowlist.txt; that list only "
        "shrinks."
    )


def test_native_allowlist_has_no_stale_entries():
    """A file that no longer reaches past the seam must be struck from the list."""
    stale = sorted(_load_native_allowlist() - _current_native_users())
    assert not stale, (
        "these files no longer use .native — remove them from "
        "test/chiplot_native_allowlist.txt:\n  " + "\n  ".join(stale)
    )
