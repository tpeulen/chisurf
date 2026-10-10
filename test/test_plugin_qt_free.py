"""Guard: plugins do not import Qt (the plugin half of the Qt retirement).

Every plugin is an emtk app declared by an AutoForm ``view.json``; Qt may only
*host* an emtk surface. So a ``qtpy`` / ``PyQt`` / ``PySide`` import under
``chisurf/plugins/`` is a defect unless the file is in the **shrinking**
``test/plugin_qt_allowlist.txt`` (files written before the rule, each waiting for
its emtk port). The allow-list is never somewhere to add yourself: the end state
is an empty list and the deletion of this paragraph.

The test fails in both directions: a new importer is rejected, and an entry whose
file is gone or no longer imports Qt must be struck, so the list can only shrink.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PLUGINS = _ROOT / "chisurf" / "plugins"
_ALLOWLIST = _ROOT / "test" / "plugin_qt_allowlist.txt"

#: ``import qtpy...`` / ``from PyQt5...`` at any indentation (lazy imports count).
_QT_RE = re.compile(r"^[ \t]*(?:from|import)[ \t]+(?:qtpy|PyQt\d*|PySide\d*)\b", re.MULTILINE)


def _imports_qt(path: pathlib.Path) -> bool:
    """Return whether *path* contains a Qt import statement.

    Parameters
    ----------
    path : pathlib.Path
        A Python source file.

    Returns
    -------
    bool
    """
    try:
        return _QT_RE.search(path.read_text(encoding="utf-8", errors="replace")) is not None
    except OSError:
        return False


def _importers() -> set[str]:
    """Return the repo-relative paths of every plugin file that imports Qt.

    Returns
    -------
    set of str
    """
    return {
        p.relative_to(_ROOT).as_posix()
        for p in _PLUGINS.rglob("*.py")
        if "__pycache__" not in p.parts and _imports_qt(p)
    }


def _allowlist() -> set[str]:
    """Return the allow-listed repo-relative paths.

    Returns
    -------
    set of str
    """
    if not _ALLOWLIST.exists():
        return set()
    lines = _ALLOWLIST.read_text(encoding="utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def test_no_new_plugin_imports_qt():
    """A plugin file that imports Qt must already be on the shrinking allow-list."""
    new = sorted(_importers() - _allowlist())
    assert not new, (
        "plugins import Qt (declare the UI as an AutoForm view.json drawn by emtk; "
        "see test/test_plugin_qt_free.py):\n  " + "\n  ".join(new)
    )


def test_the_allowlist_only_shrinks():
    """An allow-list entry that no longer imports Qt (or is gone) must be struck."""
    stale = sorted(a for a in _allowlist() if not (_ROOT / a).is_file() or not _imports_qt(_ROOT / a))
    assert not stale, "strike from test/plugin_qt_allowlist.txt (no longer imports Qt):\n  " + "\n  ".join(stale)
