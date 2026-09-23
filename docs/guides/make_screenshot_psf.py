#!/usr/bin/env python
"""Grab the PSF calculator for docs/guides/72_psf_calculator.md.

Separate from make_screenshots.py because that script forces the offscreen
Qt platform, which has no OpenGL context -- the 3-D view would grab empty. Run
from the repo root in the arm64 env::

    PYTHONPATH="modules/mmfdb/src:modules/chinet:." python docs/guides/make_screenshot_psf.py
"""
from __future__ import annotations

import os
import pathlib
import sys

# The 3-D view is an OpenGL viewport. The offscreen platform has no GL context
# at all ("createPlatformOpenGLContext" unsupported), so the view grabs empty;
# on macOS the cocoa platform renders it into a framebuffer that can be read
# back, with the window parked off-screen.
os.environ.setdefault("QT_QPA_PLATFORM", "cocoa" if sys.platform == "darwin" else "offscreen")
# The default emtk plot backend has no volume renderer yet, and the tool
# raises NotImplementedError on construction without this.
os.environ.setdefault("CHISURF_PLOT_BACKEND", "pyqtgraph")

from qtpy.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

import chisurf.core.settings  # noqa: E402,F401

FIG = pathlib.Path("docs/guides/figures")


def _grab(widget, name):
    """Show *widget*, process events, and save a PNG grab into ``figures/``."""
    widget.show()
    QApplication.instance().processEvents()
    widget.grab().save(str(FIG / name))
    print("wrote", name)


def _grab_psf_calculator():
    """Grab the PSF calculator (guide 72).

    Not the default state: linear x polarization at NA 1.4 on the full
    aperture quadrature, so the figure shows the one thing the vectorial model
    exists for -- a focus longer along the polarization axis than across it --
    and the measured widths in the Result panel. The volume is computed inline rather than on the tool's
    worker thread, so the grab cannot race the computation.
    """
    from chisurf.plugins.calculator.psf_calculator.gui.tool import PSFCalculator

    tool = PSFCalculator()
    QApplication.instance().processEvents()
    tool._timer.stop()
    tool._pool.waitForDone()
    m = tool.model
    m.model, m.polarization, m.na, m.n_immersion = "vectorial", "x", 1.4, 1.518
    m.quality = "full"
    # The polarization strokes are off: the pyqtgraph volume view centres the
    # volume on the origin but draws the strokes in raw voxel coordinates, so
    # they land beside and above the focus instead of on a ring over it.
    m.show_polarization = False
    m.nxy, m.nz, m.pixel_size_nm, m.z_step_nm = 64, 31, 25.0, 50.0
    tool.auto_form.sync_fields()
    QApplication.instance().processEvents()
    tool._timer.stop()
    tool._pool.waitForDone()
    tool._show(m.compute())
    tool.view.set_camera(distance=120, elevation=25, azimuth=40)
    tool.resize(1400, 860)
    tool.move(-3000, -3000)
    tool.show()
    for _ in range(10):
        QApplication.instance().processEvents()

    # QWidget.grab() reads the backing store, which never holds GL content;
    # paint the viewport's own framebuffer over its rectangle.
    from qtpy import QtCore, QtGui

    pixmap = tool.grab()
    gl_widget = tool.view._vv.widget()
    frame = gl_widget.grabFramebuffer()
    origin = gl_widget.mapTo(tool, QtCore.QPoint(0, 0))
    painter = QtGui.QPainter(pixmap)
    painter.drawImage(QtCore.QRect(origin, gl_widget.size()), frame)
    painter.end()
    if pixmap.devicePixelRatio() != 1.0:
        pixmap = pixmap.scaled(tool.size(), QtCore.Qt.IgnoreAspectRatio,
                               QtCore.Qt.SmoothTransformation)
    pixmap.save(str(FIG / "psf_calculator.png"))
    print("wrote psf_calculator.png")
    return tool


if __name__ == "__main__":
    t = _grab_psf_calculator()
    print(t.model.summary_text())
