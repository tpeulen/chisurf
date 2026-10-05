"""Fit-window document UI is identified by scientific UID, not widget order."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest


@pytest.fixture
def native_ui():
    """Build real MDI views with the supported project plot-state hooks."""
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    area = QtWidgets.QMdiArea()
    windows = []
    for uid, selected in (("fit-a", 1), ("fit-b", 0)):
        window = QtWidgets.QMdiSubWindow()
        window.setWidget(QtWidgets.QWidget())
        window.fit = SimpleNamespace(unique_identifier=uid)
        window.project_view = {
            "version": 1,
            "current_plot_index": selected,
            "plots": [{"index": 0, "controller": {"log_x": True, "log_y": False}}],
            "geometry": [20, 30, 800, 500],
        }
        window.get_project_plot_state = lambda view=window: copy.deepcopy(view.project_view)
        window.set_project_plot_state = lambda state, view=window: (
            setattr(view, "project_view", copy.deepcopy(state)) or True
        )
        area.addSubWindow(window)
        windows.append(window)
    main = SimpleNamespace(mdiarea=area, fit_idx=0)
    yield main, windows, app
    area.close()
    area.deleteLater()
    app.processEvents()


def test_capture_preserves_each_fit_window_state_without_aliasing(native_ui):
    """An ordinary document snapshot includes every plot/control/tab state."""
    from chisurf.core.project.ui_state import get_ui_state

    main, windows, _app = native_ui
    state = get_ui_state(main)
    assert state["fit_windows"] == {
        "fit-a": windows[0].project_view,
        "fit-b": windows[1].project_view,
    }
    windows[0].project_view["plots"][0]["controller"]["log_x"] = False
    assert state["fit_windows"]["fit-a"]["plots"][0]["controller"]["log_x"] is True


def test_restore_addresses_fit_uid_instead_of_mdi_window_order(native_ui):
    """A reordered session applies each controller only to its actual owner."""
    from chisurf.core.project.ui_state import set_ui_state

    main, windows, _app = native_ui
    saved = {
        "fit_windows": {
            "fit-b": {"version": 1, "current_plot_index": 3},
            "fit-a": {"version": 1, "current_plot_index": 2},
        },
    }
    set_ui_state(main, saved)
    assert windows[0].project_view == saved["fit_windows"]["fit-a"]
    assert windows[1].project_view == saved["fit_windows"]["fit-b"]


def test_capture_does_not_silently_drop_a_failing_plot_state(native_ui):
    """A false-success snapshot must not erase the user's GUI model context."""
    from chisurf.core.project.ui_state import get_ui_state

    main, windows, _app = native_ui

    def fail():
        raise RuntimeError("plot capture failed")

    windows[0].get_project_plot_state = fail
    with pytest.raises(Exception, match="plot capture failed"):
        get_ui_state(main)


def test_restore_propagates_plot_application_failure(native_ui):
    """Owner publication must see failed view restoration and roll back."""
    from chisurf.core.project.ui_state import set_ui_state

    main, windows, _app = native_ui

    def fail(state):
        raise RuntimeError("plot publication failed")

    windows[0].set_project_plot_state = fail
    with pytest.raises(Exception, match="plot publication failed"):
        set_ui_state(main, {"fit_windows": {"fit-a": {"version": 1}}})


def test_unknown_fit_ui_is_rejected_before_any_application(native_ui):
    """A malformed fit UID must not partially mutate existing view state."""
    from chisurf.core.project.ui_state import set_ui_state

    main, windows, _app = native_ui
    before = [copy.deepcopy(window.project_view) for window in windows]
    state = {
        "fit_windows": {
            "fit-a": {"version": 1, "current_plot_index": 4},
            "unowned-fit": {"version": 1, "current_plot_index": 9},
        }
    }
    with pytest.raises(Exception, match="unowned-fit"):
        set_ui_state(main, state)
    assert [window.project_view for window in windows] == before


def test_history_browser_presentation_is_restored_without_scientific_navigation(native_ui):
    """Restore the actual browser filter/splitter without moving science's cursor."""
    from chisurf.core.project.ui_state import get_ui_state, set_ui_state
    from chisurf.gui.widgets.history_browser import HistoryBrowserWidget
    from chisurf.history.core import OperationHistory

    main, _windows, app = native_ui
    browser = HistoryBrowserWidget()
    history = OperationHistory()
    browser.set_history(history)
    main.historyBrowser = browser
    browser.filter_edit.setText("slope")
    state = get_ui_state(main)
    browser.filter_edit.setText("different")
    set_ui_state(main, state)
    assert browser.filter_edit.text() == "slope"
    assert history.cursor_index() == -1
    assert history.list_events() == []
    browser.deleteLater()
    app.processEvents()


def test_active_model_panel_tabs_are_captured_and_restored(native_ui):
    """The shown model panel is presentation state, not a global preference."""
    from qtpy import QtWidgets

    from chisurf.core.project.ui_state import get_ui_state, set_ui_state

    main, _windows, app = native_ui
    panel = QtWidgets.QTabWidget()
    panel.addTab(QtWidgets.QWidget(), "Parameters")
    panel.addTab(QtWidgets.QWidget(), "Model")
    main.analysisPanel = panel
    panel.setCurrentIndex(1)
    state = get_ui_state(main)
    assert state["active_tabs"]["analysisPanel"] == 1
    panel.setCurrentIndex(0)
    set_ui_state(main, state)
    assert panel.currentIndex() == 1
    panel.deleteLater()
    app.processEvents()
