"""FitPlotsArea: the fit window's one emtk surface behind the plot_tab_widget calls."""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf.gui.widgets.fitting.fit_plots_area import LAYOUT_TYPE, FitPlotsArea


def test_fit_plots_area_tab_management(qapp, qtbot):
    """Pages are added, named, chosen and reported like tabs."""
    area = FitPlotsArea()
    qtbot.addWidget(area)

    w1 = QtWidgets.QLabel("Plot 1")
    w2 = QtWidgets.QLabel("Plot 2")

    signals = []
    area.currentChanged.connect(signals.append)

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
    assert signals == [1]

    area.setTabText(1, "Weighted Residuals")
    assert area.tabText(1) == "Weighted Residuals"
    assert area.surface.docks.window("1:Residuals").title == "Weighted Residuals"


def test_pages_are_built_when_first_asked_for(qapp, qtbot):
    """A page's provider runs once, the first time its plot is needed."""
    area = FitPlotsArea()
    qtbot.addWidget(area)
    built = []

    def provider():
        built.append(1)
        return QtWidgets.QLabel("late")

    area.add_page("Late", provider)
    assert built == []
    page = area.widget(0)
    assert isinstance(page, QtWidgets.QLabel)
    assert area.widget(0) is page
    assert built == [1]


def test_page_widgets_are_hidden_and_only_the_host_shows(qapp, qtbot):
    """What a page widget holds is drawn by the surface; the widget itself never shows."""
    area = FitPlotsArea()
    qtbot.addWidget(area)
    area.addTab(QtWidgets.QLabel("one"), "One")
    area.show()
    qapp.processEvents()
    shown = [w for w in area.findChildren(QtWidgets.QWidget) if w.isVisible()]
    assert shown == [area.host]


def test_fit_plots_area_layout_state_roundtrip(qapp, qtbot):
    """Layout state round-trips: regions, docked pages and the current page."""
    area = FitPlotsArea()
    qtbot.addWidget(area)
    for title in ("Fit", "Residuals", "Parameters"):
        area.addTab(QtWidgets.QLabel(title), title)
    right = area.surface.docks.split_region("center", "right")
    area.surface.docks.dock("1:Residuals", right)
    area.setCurrentIndex(2)

    state = area.get_layout_state()
    assert state["type"] == LAYOUT_TYPE
    assert state["current_index"] == 2

    restored = FitPlotsArea()
    qtbot.addWidget(restored)
    for title in ("Fit", "Residuals", "Parameters"):
        restored.addTab(QtWidgets.QLabel(title), title)
    assert restored.set_layout_state(state, emit_change=False)
    assert restored.surface.docks.region_of("1:Residuals") == right
    assert restored.currentIndex() == 2


def test_a_layout_from_the_qt_dock_area_is_ignored(qapp, qtbot):
    """The old Qt layout format is not this surface's: nothing changes."""
    area = FitPlotsArea()
    qtbot.addWidget(area)
    area.addTab(QtWidgets.QLabel("Fit"), "Fit")
    old = {"type": "emtk_fit_plots_area", "version": 1, "root": {"type": "tab", "tabs": []},
           "current_index": 0}
    assert not area.set_layout_state(old)
    assert area.count() == 1


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
