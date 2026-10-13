"""Opening a fit window in the emtk shell must not import Qt.

Each check runs in a fresh interpreter, because any earlier test in the process may
have imported Qt. A local TCSPC lifetime fit is opened as the shell opens one
(:class:`chisurf.emtk.fit_window.FitWindow`), every page is built and drawn, and the
Code face is turned over.

The surface, the page registry, the Code face and the page classes are Qt-free
(:mod:`chisurf.emtk.fit_pages`, pages in :mod:`chisurf.emtk.fit_pages.pages`), and the
pages draw through the toolkit-free chiplot core (:mod:`chisurf.chiplot`); the Qt
widgets of chiplot are the host layer :mod:`chisurf.gui.chiplot`, which only a Qt host
imports (``okf/subsystems/qt-retirement.md``, item 6).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

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


def test_every_shipped_page_class_resolves_without_qt():
    """Every key of ``PLOT_CLASSES`` (not only a lifetime fit's pages) imports no Qt."""
    out = _run(
        """
        import sys
        from chisurf.emtk.fit_pages.plots import PLOT_CLASSES, get_plot_class
        for key in PLOT_CLASSES:
            get_plot_class(key)
        import chisurf.chiplot
        print(len(PLOT_CLASSES), sorted(m for m in ("qtpy", "PyQt5") if m in sys.modules))
        """
    )
    count, loaded = out.strip().splitlines()[-1].split(" ", 1)
    assert int(count) >= 22 and loaded == "[]", out


def test_opening_a_fit_window_imports_no_qt():
    out = _run(OPEN_WINDOW)
    assert "LOADED []" in out, out
