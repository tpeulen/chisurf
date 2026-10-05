"""The Qt main window's layout through the toolkit-neutral record (``chisurf.gui.layout_state``)."""

from __future__ import annotations

import pytest

qtpy = pytest.importorskip("qtpy")
from qtpy import QtCore, QtWidgets  # noqa: E402

from chisurf.core.project import ui_layout  # noqa: E402
from chisurf.gui import layout_state  # noqa: E402, F401  (registers the Qt backend)


class _Fit:
    def __init__(self, uid):
        self.unique_identifier = uid


class _FitWindow(QtWidgets.QMdiSubWindow):
    """A fit view as the app has them: a Python subclass carrying its fit (a plain wrapper's attribute is lost)."""

    def __init__(self, uid):
        super().__init__()
        self.fit = _Fit(uid)
        self.setWidget(QtWidgets.QLabel(uid))


def _window():
    win = QtWidgets.QMainWindow()
    win.mdiarea = QtWidgets.QMdiArea()
    win.setCentralWidget(win.mdiarea)
    for name, area in (("datasets", QtCore.Qt.LeftDockWidgetArea), ("analysis", QtCore.Qt.RightDockWidgetArea)):
        dock = QtWidgets.QDockWidget(name)
        dock.setObjectName(name)
        dock.setWidget(QtWidgets.QLabel(name))
        win.addDockWidget(area, dock)
    for uid in ("fit-a", "fit-b"):
        sub = _FitWindow(uid)
        win.mdiarea.addSubWindow(sub)
        sub.show()
    win.setGeometry(40, 50, 900, 600)
    win.show()
    return win


def test_neutral_layout_round_trips_on_a_fresh_qt_window(qapp):
    src = _window()
    analysis = src.findChild(QtWidgets.QDockWidget, "analysis")
    src.addDockWidget(QtCore.Qt.BottomDockWidgetArea, analysis)
    src.findChild(QtWidgets.QDockWidget, "datasets").hide()
    subs = {s.fit.unique_identifier: s for s in src.mdiarea.subWindowList()}
    subs["fit-a"].setGeometry(10, 10, 300, 200)
    subs["fit-b"].showMinimized()
    qapp.processEvents()
    state = ui_layout.capture(src)
    layout = state["layout"]
    assert layout["docks"]["analysis"]["area"] == "bottom" and not layout["docks"]["datasets"]["visible"]
    assert {v["uid"]: v["state"] for v in layout["views"]} == {"fit-a": "normal", "fit-b": "minimized"}
    assert set(state["backend"]["qt"]) == {"geometry", "dock_state"}

    # a project written by another front end: only the neutral layout is there
    dst = _window()
    assert ui_layout.restore(dst, {"layout": layout, "backend": {"emtk": {"docks": "x"}}}) == []
    qapp.processEvents()
    assert dst.dockWidgetArea(dst.findChild(QtWidgets.QDockWidget, "analysis")) == QtCore.Qt.BottomDockWidgetArea
    assert not dst.findChild(QtWidgets.QDockWidget, "datasets").isVisible()
    d_subs = {s.fit.unique_identifier: s for s in dst.mdiarea.subWindowList()}
    assert d_subs["fit-b"].isMinimized()
    g = d_subs["fit-a"].geometry()
    assert (g.width(), g.height()) == (300, 200)
    for w in (src, dst):
        w.close()


def test_a_pre_neutral_project_still_restores_through_its_qt_bytes(qapp):
    src = _window()
    src.addDockWidget(QtCore.Qt.TopDockWidgetArea, src.findChild(QtWidgets.QDockWidget, "datasets"))
    old_state = {"geometry": bytes(src.saveGeometry()).hex(), "dock_state": bytes(src.saveState()).hex()}
    dst = _window()
    assert ui_layout.restore(dst, old_state) == []
    qapp.processEvents()
    assert dst.dockWidgetArea(dst.findChild(QtWidgets.QDockWidget, "datasets")) == QtCore.Qt.TopDockWidgetArea
    for w in (src, dst):
        w.close()


def test_a_dock_or_view_this_window_lacks_is_reported_and_the_rest_applied(qapp):
    win = _window()
    missed = ui_layout.restore(win, {"layout": {
        "docks": {"gone": {"visible": True}, "datasets": {"visible": False}},
        "views": [{"uid": "fit-zz", "state": "normal"}]}})
    assert sorted(missed) == ["dock gone", "view fit-zz"]
    assert not win.findChild(QtWidgets.QDockWidget, "datasets").isVisible()
    win.close()
