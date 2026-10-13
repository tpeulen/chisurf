"""Opening a fit window in the emtk shell must not import Qt.

Each check runs in a fresh interpreter, because any earlier test in the process may
have imported Qt. A local TCSPC lifetime fit is opened as the shell opens one
(:class:`chisurf.emtk.fit_window.FitWindow`), every page is built and drawn, and the
Code face is turned over.

Today the surface, the page registry and the Code face are Qt-free
(:mod:`chisurf.emtk.fit_pages`), so the only way to Qt left is a page class: they draw
through ``chisurf.gui.chiplot``, which imports Qt at package import (its ``Plot`` is a
``QWidget``), and they live under ``chisurf.gui``, whose ``__init__`` imports Qt. The
full guard is a strict xfail until that move lands (``okf/subsystems/qt-retirement.md``);
the narrower guard holds what has landed.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

OPEN_WINDOW = """
import sys, traceback, builtins
first = []
real_import = builtins.__import__
def spy(name, *args, **kwargs):
    if not first and name.split(".")[0] in ("qtpy", "PyQt5"):
        first.append([f"{f.filename}:{f.lineno}" for f in traceback.extract_stack()[:-1]
                      if "/chisurf/" in f.filename and "/site-packages/" not in f.filename])
    return real_import(name, *args, **kwargs)
builtins.__import__ = spy

import numpy as np
import chisurf.core.fitting.fit as fit_mod
from chisurf.core.data import DataCurve
from chisurf.core.models.description import tcspc_lifetime

x = np.linspace(0.05, 25, 256)
fit = fit_mod.Fit(model_class=tcspc_lifetime, data=DataCurve(x=x, y=np.exp(-x / 4.0) + 1.0))
from chisurf.emtk.fit_window import FitWindow
from emtk.testing import Driver
window = FitWindow("guard", fit, "guard")
driver = Driver(window.app, size=(900, 600))
driver.frame(2)
for index in range(len(window.specs)):
    window.page(index)
    driver.frame()
assert window.names, "the fit window has no pages"
window.show_code(True)
driver.frame(2)
loaded = sorted(m for m in ("qtpy", "PyQt5") if m in sys.modules)
print("LOADED", loaded)
print("FIRST", first[0] if first else [])
"""


def _run(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    return result.stdout


def test_the_fit_window_surface_registry_and_code_face_import_no_qt():
    out = _run(
        """
        import sys
        import chisurf.emtk.fit_pages.surface, chisurf.emtk.fit_pages.plots
        import chisurf.emtk.fit_pages.code_face, chisurf.emtk.fit_window
        print(sorted(m for m in ("qtpy", "PyQt5") if m in sys.modules))
        """
    )
    assert out.strip().splitlines()[-1] == "[]", out


def test_opening_a_fit_window_reaches_qt_only_through_a_page_class():
    """What landed: the surface, ``model_plot_specs`` and the Code face no longer pull Qt in."""
    out = _run(OPEN_WINDOW)
    first = next(line for line in out.splitlines() if line.startswith("FIRST"))
    chain = [frame for frame in eval(first[len("FIRST ") :]) if "/chisurf/chisurf/" in frame]
    via = [frame for frame in chain if "/chisurf/gui/" in frame]
    assert via, out
    for module in ("fit_plots_area.py", "model_editor.py", "autoform/", "fit_code_face.py"):
        assert not any(module in frame for frame in chain), (module, chain)


@pytest.mark.xfail(
    strict=True,
    reason="page classes draw through chisurf.gui.chiplot, which imports Qt "
    "(qt-retirement ledger: move the fit page classes and a Qt-free chiplot core)",
)
def test_opening_a_fit_window_imports_no_qt():
    out = _run(OPEN_WINDOW)
    assert "LOADED []" in out, out
