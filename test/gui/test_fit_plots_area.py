"""Tests for EMTK-based FitPlotsArea and FitSubWindow tabbed plot surface."""

from __future__ import annotations

import numpy as np
import pytest
from emtk.qt_painter import QtPainter
from qtpy import QtCore, QtGui, QtWidgets

import chisurf as cs
from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.models.description import tcspc_polarized
from chisurf.gui.widgets.fitting.fit_plots_area import FitPlotsArea, FitTabBarControl
from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow


def test_fit_plots_area_tab_management(qapp, qtbot):
    """FitPlotsArea manages tabs, switches pages, and emits signals."""
    area = FitPlotsArea()
    qtbot.addWidget(area)

    w1 = QtWidgets.QLabel("Plot 1")
    w2 = QtWidgets.QLabel("Plot 2")

    signals = []
    area.currentChanged.connect(lambda idx: signals.append(idx))

    area.addTab(w1, "Fit")
    area.addTab(w2, "Residuals")

    assert area.count() == 2
    assert area.tabText(0) == "Fit"
    assert area.tabText(1) == "Residuals"
    assert area.widget(0) is w1
    assert area.widget(1) is w2
    assert area.currentIndex() == 0

    area.setCurrentIndex(1)
    assert area.currentIndex() == 1
    assert area.currentWidget() is w2
    assert 1 in signals

    area.setTabText(1, "Weighted Residuals")
    assert area.tabText(1) == "Weighted Residuals"


def test_fit_tab_bar_control_draw_and_interaction(qapp, qtbot):
    """FitTabBarControl renders via EMTK painter and handles click/hover."""
    changes = []
    control = FitTabBarControl(on_change=lambda idx: changes.append(idx))
    control.set_tabs(["Fit", "Data table", "Info"])

    pixmap = QtGui.QPixmap(300, 28)
    pixmap.fill(QtCore.Qt.black)
    painter = QtGui.QPainter(pixmap)
    try:
        surface = QtPainter(painter)
        control.draw(surface, 0.0, 0.0, 300.0, 28.0)
    finally:
        painter.end()

    assert len(control._tab_rects) == 3
    fit_rx, fit_ry, fit_rw, fit_rh = control._tab_rects[0]
    dt_rx, dt_ry, dt_rw, dt_rh = control._tab_rects[1]

    # Test click on second tab
    control.press(dt_rx + dt_rw / 2.0, dt_ry + dt_rh / 2.0)
    assert control.current_index == 1
    assert changes == [1]

    # Test hover
    control.hover(fit_rx + fit_rw / 2.0, fit_ry + fit_rh / 2.0)
    assert control.hovered_index == 0


def test_fit_plots_area_layout_state_roundtrip(qapp, qtbot):
    """Layout state round-trips stably across serialization."""
    area = FitPlotsArea()
    qtbot.addWidget(area)

    w1 = QtWidgets.QLabel("P1")
    w2 = QtWidgets.QLabel("P2")
    w1.setProperty("key", "plot_fit")
    w2.setProperty("key", "plot_res")

    area.addTab(w1, "Fit")
    area.addTab(w2, "Residuals")
    area.setCurrentIndex(1)

    state = area.get_layout_state(key_func=lambda w: w.property("key"))
    assert state["current_index"] == 1
    assert "root" in state

    restored = FitPlotsArea()
    qtbot.addWidget(restored)
    restored.addTab(w1, "Fit")
    restored.addTab(w2, "Residuals")

    assert restored.set_layout_state(state, emit_change=False)
    assert restored.currentIndex() == 1


def test_fit_subwindow_uses_fit_plots_area(tmp_path):
    """FitSubWindow hosts FitPlotsArea and refreshes plots cleanly."""
    import os
    import subprocess
    import sys
    import textwrap
    from pathlib import Path

    script = textwrap.dedent("""
        import numpy as np
        from qtpy import QtWidgets
        import chisurf as cs
        from chisurf.core.data import DataCurve, DataCurveGroup
        from chisurf.core.fitting.fit import FitGroup
        from chisurf.core.models.description import tcspc_polarized
        from chisurf.gui.widgets.fitting.fit_plots_area import FitPlotsArea
        from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        time = np.arange(100, dtype=float) * 0.05
        counts = np.ones(100, dtype=float) * 50.0
        curve = DataCurve(x=time, y=counts, ey=np.sqrt(counts), name="Decay")
        fit = FitGroup(data=DataCurveGroup([curve]), model_class=tcspc_polarized)
        fit.fit_range = (5, 90)
        fit.model.set_dataset("response", DataCurve(x=time, y=counts, name="Prompt"))
        fit.update()

        host = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(host)
        window = FitSubWindow(fit, layout)
        window.close_confirm = False
        assert isinstance(window.plot_tab_widget, FitPlotsArea)
        assert window.plot_tab_widget.count() == len(window._plot_specs)

        # Initial plot created
        window.plot_tab_widget.setCurrentIndex(0)
        window.refresh_current_plot()
        assert window._plots_all[0] is not None

        # Switch to residuals tab
        window.plot_tab_widget.setCurrentIndex(len(window._plot_specs) - 1)
        window.refresh_current_plot()
        assert window._plots_all[-1] is not None

        # Screenshot grab succeeds without error
        pix = window.grab()
        assert not pix.isNull()
    """)

    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        IMP_BFF_GPU="off",
        PYTHONPATH="modules/chimol:modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:.",
        CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
        MMFDB_SETTINGS_DIR=str(tmp_path / "mmfdb"),
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
