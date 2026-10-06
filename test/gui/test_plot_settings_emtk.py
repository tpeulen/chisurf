"""The *Plot settings* dock is one emtk surface showing the current page's settings.

Pages are not widgets and bring no Qt controller: a page declares its settings
as an AutoForm spec (``settings_view``) over a plain model, and
:class:`~chisurf.gui.plots.emtk_settings.PlotSettingsHost` draws the current
page's. These drive the dock with real mouse input.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtCore, QtWidgets  # noqa: E402
from qtpy.QtTest import QTest  # noqa: E402

from chisurf.gui.plots.emtk_settings import PlotSettingsHost, host_in  # noqa: E402
from chisurf.gui.plots.lineplot.lineplot import LinePlot  # noqa: E402
from test.gui.test_tcspc_project_visual_roundtrip import _simulated_fit  # noqa: E402


def _frames(qapp, host, n: int = 4) -> None:
    for _ in range(n):
        qapp.processEvents()
        host.host.repaint()


def _click(qapp, host, rect) -> None:
    x, y, w, h = rect
    point = QtCore.QPoint(int(x + min(w, 14) / 2), int(y + h / 2))
    QTest.mouseClick(host.host, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, point)
    _frames(qapp, host)


@pytest.fixture
def lineplot_dock(qapp, qtbot):
    plot = LinePlot(_simulated_fit())
    plot.update()
    host = PlotSettingsHost()
    qtbot.addWidget(host)
    host.resize(440, 640)
    host.show()
    host.show_page(plot)
    _frames(qapp, host)
    return plot, host


def test_a_page_is_not_a_widget():
    assert not issubclass(LinePlot, QtWidgets.QWidget)


def test_the_lineplot_settings_are_drawn_from_its_spec(lineplot_dock):
    plot, host = lineplot_dock
    rects = plot.settings_form.rects
    for name in ("log_x", "log_y", "is_density", "display_group", "reference_mode",
                 "xmin_enabled", "xmax_value", "x_shift", "y_shift"):
        assert name in rects, f"{name} was not drawn"
    assert host.surface.last_error is None


def test_clicking_logx_changes_the_plot(qapp, lineplot_dock):
    plot, host = lineplot_dock
    assert not plot.settings.data_is_log_x
    _click(qapp, host, plot.settings_form.rects["log_x"])
    assert plot.settings.data_is_log_x
    assert plot.settings.get_state()["scale_x"] == "log"


def test_a_curve_unticked_in_the_table_is_hidden(lineplot_dock):
    plot, _host = lineplot_dock
    rows = plot.settings.curve_rows()
    assert rows and all(row["shown"] for row in rows)
    plot.settings.curve_edited(rows[0], "shown", False)
    assert not plot.settings.getCheckState(rows[0]["name"])
    assert plot.settings.get_state()["curve_visibility"][rows[0]["name"]] is False


def test_a_page_without_settings_says_so(qapp, qtbot):
    from chisurf.gui.plots.wr_plot import ResidualPlot

    page = ResidualPlot(_simulated_fit())
    host = PlotSettingsHost()
    qtbot.addWidget(host)
    host.resize(300, 200)
    host.show()
    host.show_page(page)
    _frames(qapp, host)
    assert not page.has_settings()
    assert host.surface.last_error is None


def test_one_host_per_options_layout(qtbot):
    holder = QtWidgets.QWidget()
    qtbot.addWidget(holder)
    layout = QtWidgets.QVBoxLayout(holder)
    assert host_in(layout) is host_in(layout)
    assert layout.count() == 1


def test_the_dock_follows_the_current_tab(qapp, qtbot):
    from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow

    holder = QtWidgets.QWidget()
    qtbot.addWidget(holder)
    window = FitSubWindow(_simulated_fit(), QtWidgets.QVBoxLayout(holder))
    window.close_confirm = False
    qtbot.addWidget(window)
    window.show()
    area = window.plot_tab_widget
    for index in range(area.count()):
        area.setCurrentIndex(index)
        window.on_change_plot()
        assert window.plot_settings.page is window._plots_all[index]


def test_files_dropped_on_the_dock_reach_the_page(qtbot):
    taken = []

    class Page:
        name = "Dropper"

        def has_settings(self):
            return True

        def draw_settings(self):
            pass

        def set_settings_refresh(self, callback):
            pass

        def on_paths_dropped(self, paths):
            taken.extend(paths)

    host = PlotSettingsHost()
    qtbot.addWidget(host)
    host.show_page(Page())
    assert host.surface.on_files_dropped(["/tmp/a.ptu"]) is True
    assert taken == ["/tmp/a.ptu"]
    host.show_page(None)
    assert host.surface.on_files_dropped(["/tmp/b.ptu"]) is False
