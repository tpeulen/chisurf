"""The Qt front end's window layout, in the toolkit-neutral terms of :mod:`chisurf.core.project.ui_layout`.

Reads and applies the main window's rectangle, its docks (by ``objectName``) and its fit views (by the fit's UID) for a
``QMainWindow``; its exact ``saveGeometry`` / ``saveState`` bytes are kept as the ``qt`` hint, which only a Qt front
end uses. Registered on import.
"""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

from chisurf.core.project.ui_layout import LayoutBackend, register_backend

_AREAS = {
    QtCore.Qt.LeftDockWidgetArea: "left",
    QtCore.Qt.RightDockWidgetArea: "right",
    QtCore.Qt.TopDockWidgetArea: "top",
    QtCore.Qt.BottomDockWidgetArea: "bottom",
}
_QT_AREA = {name: area for area, name in _AREAS.items()}


def _rect(widget) -> list[int]:
    g = widget.geometry()
    return [g.x(), g.y(), g.width(), g.height()]


def _fit_views(window) -> dict:
    """The fit views of the main window's MDI area, by fit UID."""
    mdi = getattr(window, "mdiarea", None)
    views = {}
    for sub in (mdi.subWindowList() if mdi is not None else []):
        uid = getattr(getattr(sub, "fit", None), "unique_identifier", None)
        if isinstance(uid, str) and uid:
            views[uid] = sub
    return views


def matches(window) -> bool:
    return isinstance(window, QtWidgets.QMainWindow)


def capture(window) -> dict:
    g = window.normalGeometry() if window.isMaximized() else window.geometry()
    layout = {"window": {"x": g.x(), "y": g.y(), "width": g.width(), "height": g.height(),
                         "maximized": bool(window.isMaximized())}}
    docks = {}
    for dock in window.findChildren(QtWidgets.QDockWidget):
        name = dock.objectName()
        if not name:
            continue
        docks[name] = {"visible": dock.isVisible(), "floating": dock.isFloating(),
                       "area": _AREAS.get(window.dockWidgetArea(dock), "left"), "rect": _rect(dock)}
    if docks:
        layout["docks"] = docks
    mdi = getattr(window, "mdiarea", None)
    if mdi is not None:
        order = mdi.subWindowList(QtWidgets.QMdiArea.StackingOrder)
        uid_of = {id(sub): uid for uid, sub in _fit_views(window).items()}
        layout["views"] = [
            {"kind": "fit", "uid": uid_of[id(sub)], "rect": _rect(sub),
             "state": "minimized" if sub.isMinimized() else "maximized" if sub.isMaximized() else "normal"}
            for sub in order if id(sub) in uid_of
        ]
    return layout


def apply(window, layout: dict) -> list[str]:
    missed = []
    w = layout.get("window")
    if w:
        window.setGeometry(w["x"], w["y"], w["width"], w["height"])
        if w.get("maximized"):
            window.showMaximized()
    docks = {d.objectName(): d for d in window.findChildren(QtWidgets.QDockWidget) if d.objectName()}
    for name, d in (layout.get("docks") or {}).items():
        dock = docks.get(name)
        if dock is None:
            missed.append(f"dock {name}")
            continue
        if d.get("area") in _QT_AREA and not d.get("floating"):
            window.addDockWidget(_QT_AREA[d["area"]], dock)
        dock.setFloating(bool(d.get("floating")))
        if d.get("floating") and d.get("rect"):
            dock.setGeometry(*d["rect"])
        dock.setVisible(bool(d.get("visible", True)))
    views = _fit_views(window)
    for v in layout.get("views") or []:  # bottom to top: the last one ends in front
        sub = views.get(v["uid"])
        if sub is None:
            missed.append(f"view {v['uid']}")
            continue
        {"maximized": sub.showMaximized, "minimized": sub.showMinimized}.get(v["state"], sub.showNormal)()
        if v["state"] == "normal" and v.get("rect"):
            sub.setGeometry(*v["rect"])
        if v["state"] != "minimized":
            sub.raise_()
    return missed


def capture_hint(window) -> dict:
    return {"geometry": bytes(window.saveGeometry()).hex(), "dock_state": bytes(window.saveState()).hex()}


def apply_hint(window, hint: dict) -> bool:
    done = False
    if hint.get("geometry"):
        done = bool(window.restoreGeometry(QtCore.QByteArray(bytes.fromhex(hint["geometry"])))) or done
    if hint.get("dock_state"):
        done = bool(window.restoreState(QtCore.QByteArray(bytes.fromhex(hint["dock_state"])))) or done
    return done


def capture_arrangement(window) -> dict | None:
    """Which fit view is in front, which is active, how each is shown, and the MDI view mode (by fit UID)."""
    mdi = getattr(window, "mdiarea", None)
    if mdi is None or not hasattr(mdi, "subWindowList"):
        return None
    views = _fit_views(window)
    uid_of = {id(sub): uid for uid, sub in views.items()}
    states = {
        uid: "minimized" if sub.isMinimized() else "maximized" if sub.isMaximized() else "normal"
        for uid, sub in views.items()
    }
    active = mdi.activeSubWindow()
    return {
        "stacking": [uid_of[id(s)] for s in mdi.subWindowList(QtWidgets.QMdiArea.StackingOrder) if id(s) in uid_of],
        "active": uid_of.get(id(active)) if active is not None else None,
        "window_states": states,
        "view_mode": "tabbed" if mdi.viewMode() == QtWidgets.QMdiArea.TabbedView else "windows",
    }


def apply_arrangement(window, arrangement: dict, views: dict) -> None:
    """Apply a validated arrangement: view mode, each window's state, stacking bottom to top, the active one."""
    mdi = window.mdiarea
    mdi.setViewMode(
        QtWidgets.QMdiArea.TabbedView if arrangement.get("view_mode") == "tabbed" else QtWidgets.QMdiArea.SubWindowView
    )
    states = arrangement.get("window_states", {})
    for uid, shown in states.items():
        sub = views[uid]
        {"maximized": sub.showMaximized, "minimized": sub.showMinimized}.get(shown, sub.showNormal)()
    # Bottom to top: raising each in turn leaves the saved front window in front.
    for uid in arrangement.get("stacking", []):
        if states.get(uid) != "minimized":
            views[uid].raise_()
    if arrangement.get("active") is not None:
        mdi.setActiveSubWindow(views[arrangement["active"]])


BACKEND = LayoutBackend("qt", matches, capture, apply, capture_hint, apply_hint, capture_arrangement,
                        apply_arrangement)
register_backend(BACKEND)

__all__ = ["BACKEND"]
