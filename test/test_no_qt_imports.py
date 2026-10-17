"""Guard: nothing shipped imports Qt (the end of the Qt retirement).

The ChiSurf window is the emtk shell (:mod:`chisurf.emtk.main_app`) and every plugin is an
emtk app; ``qtpy`` / ``PyQt`` / ``PySide`` are not dependencies any more. So an import of a
Qt binding anywhere under ``chisurf/`` -- or of emtk's and rendercanvas's Qt hosts, or of
pytest-qt -- is a defect. There is no allow-list: the plugin allow-list that tracked the
retirement (505 entries at its start) reached zero and was deleted with the Qt shell.

Lazy imports count (any indentation): a function that imports Qt fails on the user's machine
when it runs, which is later and harder to find than at import.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PACKAGE = _ROOT / "chisurf"

#: ``import qtpy...`` / ``from PyQt5...`` / ``from emtk.qt_host import ...`` at any indentation.
_QT_RE = re.compile(
    r"^[ \t]*(?:from|import)[ \t]+(?:qtpy|PyQt\d*|PySide\d*|pytestqt|sip\b|emtk\.qt_host|"
    r"rendercanvas\.qt|pyqtgraph)\b",
    re.MULTILINE,
)
#: ``from emtk import qt_host`` names the Qt host without the dotted module.
_QT_FROM_RE = re.compile(r"^[ \t]*from[ \t]+(?:emtk|rendercanvas)[ \t]+import[ \t]+[^\n]*\bqt", re.MULTILINE)


def _imports_qt(path: pathlib.Path) -> list[int]:
    """Return the line numbers of Qt import statements in *path*.

    Parameters
    ----------
    path : pathlib.Path
        A Python source file.

    Returns
    -------
    list of int
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    hits = [m.start() for m in _QT_RE.finditer(text)] + [m.start() for m in _QT_FROM_RE.finditer(text)]
    return sorted(text.count("\n", 0, at) + 1 for at in hits)


def test_nothing_under_chisurf_imports_qt():
    """No module under ``chisurf/`` (tests and the plugin template included) imports Qt."""
    offenders = [
        f"{path.relative_to(_ROOT).as_posix()}:{line}"
        for path in sorted(_PACKAGE.rglob("*.py"))
        if "__pycache__" not in path.parts
        for line in _imports_qt(path)
    ]
    assert not offenders, (
        "Qt is retired: draw with emtk (an AutoForm view.json, or emtk draw code for what a spec "
        "cannot express), see test/test_no_qt_imports.py:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_sees_a_lazy_qt_import(tmp_path):
    """The pattern catches an indented import and the ``from emtk import qt_host`` spelling."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "def f():\n    from qtpy import QtWidgets\n\nfrom emtk import qt_host\nimport numpy\n",
        encoding="utf-8",
    )
    assert _imports_qt(sample) == [2, 4]
