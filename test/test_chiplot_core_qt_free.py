"""Guard: chiplot's core (:mod:`chisurf.chiplot`) imports no Qt and parses colours as Qt did.

The panel API, the handles, the styles and the emtk backend are the toolkit-free
core; the ``QWidget`` wrappers are the host layer :mod:`chisurf.gui.chiplot`. A fit
window's pages draw through the core, so a Qt import here is what made opening a fit
window load Qt (``okf/subsystems/qt-retirement.md``, item 6).

``style`` used to parse colour names with ``QColor`` and spread ``int_color`` hues with
``QColor.fromHsvF``; without Qt it must give the same bytes, or every categorical
palette and every named pen would shift by a shade.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from chisurf.chiplot import style as S

REPO = Path(__file__).resolve().parents[1]


def test_the_core_imports_no_qt():
    """Importing the core and drawing a panel's display list leaves Qt unloaded."""
    code = textwrap.dedent(
        """
        import sys
        import numpy as np
        from chisurf import chiplot as cp
        from chisurf.chiplot.backends import emtk_backend, base
        panel = cp.Panel(title="decay")
        panel.line(np.arange(5.0), np.arange(5.0) ** 2, pen="cornflowerblue", name="y")
        panel.set_labels(left="counts", bottom="t / ns").set_log(y=True)
        panel.region((1.0, 3.0), movable=True)
        print(sorted(m for m in ("qtpy", "PyQt5") if m in sys.modules))
        """
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=300
    )
    assert out.returncode == 0, out.stderr[-3000:]
    assert out.stdout.strip().splitlines()[-1] == "[]", out.stdout


@pytest.mark.parametrize(
    "spelling, rgba",
    [
        ("red", (255, 0, 0, 255)),
        ("Light Blue", (173, 216, 230, 255)),
        ("CornflowerBlue", (100, 149, 237, 255)),
        ("transparent", (0, 0, 0, 0)),
        ("#abc", (170, 187, 204, 255)),
        ("#a0b1c2", (160, 177, 194, 255)),
        ("#ff000080", (255, 0, 0, 128)),
        ("y", (255, 255, 0, 255)),
    ],
)
def test_colour_names_parse_without_qt(spelling, rgba):
    assert S.to_color(spelling).as_tuple() == rgba


def test_an_unknown_colour_name_is_a_type_error():
    with pytest.raises(TypeError, match="unrecognised color"):
        S.to_color("notacolour")


def test_int_color_hues_are_the_ones_qt_gave():
    """Recorded from ``QColor.fromHsvF(h, 1, 1, 1)`` (Qt 5.15): the rounding cases included."""
    assert S.int_color(19, count=20).as_tuple() == (255, 0, 76, 255)
    assert S.int_color(1, count=36).as_tuple() == (255, 42, 0, 255)
    assert S.int_color(5, count=11).as_tuple() == (0, 255, 185, 255)
    assert S.int_color(2, count=13).as_tuple() == (255, 235, 0, 255)
    assert S.int_color(0).as_tuple() == (255, 0, 0, 255)


def test_int_color_and_names_match_qcolor_when_qt_is_there():
    """Every SVG name and a sweep of hues give QColor's bytes exactly."""
    QtGui = pytest.importorskip("qtpy.QtGui")
    for name in QtGui.QColor.colorNames():
        q = QtGui.QColor(name)
        assert S.to_color(name).as_tuple() == (q.red(), q.green(), q.blue(), q.alpha()), name
    for count in range(1, 64):
        for index in range(count):
            q = QtGui.QColor.fromHsvF((index % count) / float(count), 1.0, 1.0, 1.0)
            assert S.int_color(index, count=count).as_tuple()[:3] == (q.red(), q.green(), q.blue())
    # A QColor itself is still a colour, read by its channels.
    assert S.to_color(QtGui.QColor(1, 2, 3, 4)).as_tuple() == (1, 2, 3, 4)
