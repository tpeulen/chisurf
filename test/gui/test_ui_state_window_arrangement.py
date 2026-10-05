"""A restored project shows its fit windows in the arrangement they were saved in.

Geometry and per-window plot state already round-tripped; which window was on top,
which was active, and which were maximized or minimized did not -- the last window
opened during restore simply ended up in front.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtWidgets  # noqa: E402

from chisurf.core.project.ui_state import get_ui_state, set_ui_state  # noqa: E402


class _FitWindow(QtWidgets.QMdiSubWindow):
    def __init__(self, uid):
        super().__init__()
        self.fit = SimpleNamespace(unique_identifier=uid)
        self.setWidget(QtWidgets.QLabel(uid))

    def get_project_plot_state(self):
        return {}

    def set_project_plot_state(self, state):
        return True


def _main(app, uids):
    main = QtWidgets.QMainWindow()
    main.mdiarea = QtWidgets.QMdiArea()
    main.setCentralWidget(main.mdiarea)
    main.resize(1000, 700)
    for uid in uids:
        window = _FitWindow(uid)
        main.mdiarea.addSubWindow(window)
        window.setGeometry(20, 20, 300, 200)
        window.show()
    main.show()
    app.processEvents()
    return main


def _windows(main):
    return {w.fit.unique_identifier: w for w in main.mdiarea.subWindowList()}


def _stacking(main):
    order = main.mdiarea.subWindowList(QtWidgets.QMdiArea.StackingOrder)
    return [w.fit.unique_identifier for w in order]


def test_stacking_active_and_window_states_are_restored():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    main = _main(app, ["a", "b", "c"])
    windows = _windows(main)
    windows["c"].showMinimized()
    main.mdiarea.setActiveSubWindow(windows["b"])
    main.mdiarea.setActiveSubWindow(windows["a"])
    app.processEvents()
    saved_order = _stacking(main)
    state = get_ui_state(main)

    # The arrangement a fresh restore produces: opened in order, last one in front.
    restored = _main(app, ["a", "b", "c"])
    assert _stacking(restored) != saved_order
    set_ui_state(restored, state)
    app.processEvents()

    assert _stacking(restored) == saved_order
    assert restored.mdiarea.activeSubWindow() is _windows(restored)["a"]
    assert _windows(restored)["c"].isMinimized()
    assert not _windows(restored)["a"].isMinimized()


def test_a_maximized_window_and_the_tabbed_view_mode_are_restored():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    main = _main(app, ["a", "b"])
    _windows(main)["b"].showMaximized()
    main.mdiarea.setActiveSubWindow(_windows(main)["b"])
    app.processEvents()
    state = get_ui_state(main)

    restored = _main(app, ["a", "b"])
    set_ui_state(restored, state)
    app.processEvents()
    assert _windows(restored)["b"].isMaximized()

    main.mdiarea.setViewMode(QtWidgets.QMdiArea.TabbedView)
    tabbed = get_ui_state(main)
    restored = _main(app, ["a", "b"])
    set_ui_state(restored, tabbed)
    assert restored.mdiarea.viewMode() == QtWidgets.QMdiArea.TabbedView
