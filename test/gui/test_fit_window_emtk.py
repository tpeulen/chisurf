"""A fit window's content is one emtk surface, driven here through real Qt input.

The window used to be a Qt dock area of tab widgets holding Qt containers: the
plot panels sat in a Qt splitter, the Data table was a Qt table, the Code face
a Qt editor with Qt combo boxes. Now the only Qt inside the window frame is one
``ControlHost``; tabs, regions, pages, the table, the report and the editor are
emtk. These tests press, drag, wheel and type into that host the way a user
does, then read the result back from the fit window's own state.
"""

from __future__ import annotations

import os

import numpy as np
import pytest
from qtpy import QtCore, QtWidgets
from qtpy.QtTest import QTest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.core.data import DataCurve, DataCurveGroup  # noqa: E402
from chisurf.core.fitting.fit import FitGroup  # noqa: E402
from chisurf.core.models.description import tcspc_polarized  # noqa: E402
from chisurf.gui.widgets.fitting.fit_plots_area import LAYOUT_TYPE, FitPlotsArea  # noqa: E402
from chisurf.gui.widgets.fitting.fit_subwindow import FitSubWindow  # noqa: E402

#: Pages of the TCSPC fit window, all of which must draw entirely in emtk.
TCSPC_PAGES = ["Fit", "Data table", "Info", "Parameter scan", "Distribution", "Residuals"]


def _decay_fit():
    t = np.arange(512) * 0.032
    irf = np.exp(-0.5 * ((t - 1.5) / 0.08) ** 2) * 1e4 + 5
    decay = np.convolve(irf, np.exp(-t / 4.0))[:512]
    decay = np.random.default_rng(1).poisson(decay / decay.max() * 1e4 + 20).astype(float)
    curve = DataCurve(x=t, y=decay, ey=np.sqrt(np.maximum(decay, 1)), name="Decay")
    fit = FitGroup(data=DataCurveGroup([curve]), model_class=tcspc_polarized)
    fit.fit_range = (20, 480)
    fit.model.set_dataset("response", DataCurve(x=t, y=irf, name="Prompt"))
    fit.update()
    return fit


@pytest.fixture
def window(qapp, qtbot, tmp_path, monkeypatch):
    import chisurf as cs
    import chisurf.core.settings as settings

    monkeypatch.setattr(settings, "get_path", lambda *_: tmp_path)
    fit = _decay_fit()
    # Registered like a fit the app opened: the fit-range action finds it there.
    monkeypatch.setattr(cs, "fits", [fit])
    controls = QtWidgets.QWidget()
    qtbot.addWidget(controls)
    win = FitSubWindow(fit, QtWidgets.QVBoxLayout(controls))
    win.close_confirm = False
    qtbot.addWidget(win)
    win.resize(900, 650)
    win.show()
    _frames(qapp, win)
    yield win
    win.close()


def _frames(qapp, win, n: int = 3) -> None:
    """Let deferred work run and draw a few frames of the surface."""
    host = win.plot_tab_widget.host
    for _ in range(n):
        qapp.processEvents()
        host.repaint()
    qapp.processEvents()


def _host(win):
    return win.plot_tab_widget.host


def _point(rect) -> QtCore.QPoint:
    x, y, w, h = rect
    return QtCore.QPoint(int(x + w / 2), int(y + h / 2))


def _tab_rect(win, title: str):
    docks = win.plot_tab_widget.surface.docks
    for rects in docks._tab_rects.values():
        for key, rect in rects:
            if key.split(":", 1)[1] == title:
                return rect
    raise AssertionError(f"no tab {title!r} drawn; tabs: {docks._tab_rects}")


def _move(win, point: QtCore.QPoint, buttons=QtCore.Qt.NoButton) -> None:
    """A pointer move delivered as Qt delivers it (QTest.mouseMove crashes offscreen)."""
    from qtpy import QtGui

    event = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(point),
                              QtCore.Qt.NoButton, buttons, QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(_host(win), event)


def _click(qapp, win, point: QtCore.QPoint, button=QtCore.Qt.LeftButton) -> None:
    QTest.mouseClick(_host(win), button, QtCore.Qt.NoModifier, point)
    _frames(qapp, win)


def test_the_window_content_is_one_emtk_host(window):
    area = window.plot_tab_widget
    assert isinstance(area, FitPlotsArea)
    shown = [w for w in area.findChildren(QtWidgets.QWidget) if w.isVisible()]
    assert shown == [area.host], f"Qt widgets shown inside the fit window: {shown}"
    assert getattr(area.host, "is_emtk", False)
    assert [area.tabText(i) for i in range(area.count())] == TCSPC_PAGES


def test_every_tcspc_page_draws_entirely_in_emtk(window, qapp):
    area = window.plot_tab_widget
    for index, title in enumerate(TCSPC_PAGES):
        area.setCurrentIndex(index)
        _frames(qapp, window)
        body = area.surface.page_body(index)
        assert body is not None and body.control is not None, title
        assert body.missing == [], f"{title}: not drawn in emtk: {body.missing}"


def test_clicking_a_tab_shows_its_page_and_its_controls(window, qapp):
    area = window.plot_tab_widget
    seen = []
    area.currentChanged.connect(seen.append)
    _click(qapp, window, _point(_tab_rect(window, "Data table")))
    assert area.currentIndex() == 1
    assert seen and seen[-1] == 1
    table_page = window._plots_all[1]
    assert table_page is not None
    assert window.current_plot_controller is table_page.plot_controller
    assert not window._plots_all[0].plot_controller.isVisibleTo(window._plots_all[0])


def test_the_wheel_zooms_the_decay_panel(window, qapp):
    plot = window._plots_all[0]
    stack = plot.emtk_body()
    decay = plot.panel_items[2]
    before = decay.canvas._drawn["x"]
    _move(window, _point(decay.box))
    _frames(qapp, window)
    pos = _point(decay.box)
    event = _wheel_event(_host(window), pos, 120)
    QtWidgets.QApplication.sendEvent(_host(window), event)
    _frames(qapp, window)
    after = decay.canvas._drawn["x"]
    assert stack is plot.plot_stack
    assert after != before
    assert (after[1] - after[0]) < (before[1] - before[0]), "a wheel notch up should zoom in"


def _wheel_event(widget, pos, delta):
    from qtpy import QtGui

    global_pos = widget.mapToGlobal(pos)
    return QtGui.QWheelEvent(
        QtCore.QPointF(pos), QtCore.QPointF(global_pos), QtCore.QPoint(0, 0),
        QtCore.QPoint(0, delta), QtCore.Qt.NoButton, QtCore.Qt.NoModifier,
        QtCore.Qt.NoScrollPhase, False,
    )


def test_a_right_click_offers_that_panels_menu(window, qapp):
    plot = window._plots_all[0]
    decay = plot.panel_items[2]
    _click(qapp, window, _point(decay.box), QtCore.Qt.RightButton)
    surface = window.plot_tab_widget.surface
    assert surface._menu_panel is decay
    assert surface._menu_panel.plot is plot._panels[2]
    state = surface.storage.get(("__state__", ("context_popup", "##plot-menu-0:Fit")))
    assert state is not None and state.get("open"), "the menu did not open"
    labels = [getattr(e, "label", None) for e in state["popup"].entries]
    assert labels[:3] == ["Export data as CSV…", "Export image…", "Auto-range"]


def test_dragging_the_fit_range_edge_moves_the_range(window, qapp):
    plot = window._plots_all[0]
    decay = plot.panel_items[2]
    region = next(e for e in decay.canvas._entries if e.kind == "region")
    low_px, high_px = region.state["_pixels"]
    y = int(decay.box[1] + decay.box[3] / 2)
    moved = []
    plot.regionChanged.connect(lambda lo, hi: moved.append((lo, hi)))
    start = QtCore.QPoint(int(round(low_px)), y)
    host = _host(window)
    QTest.mousePress(host, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, start)
    _frames(qapp, window, 1)
    _move(window, start + QtCore.QPoint(80, 0), QtCore.Qt.LeftButton)
    _frames(qapp, window, 1)
    QTest.mouseRelease(host, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, start + QtCore.QPoint(80, 0))
    _frames(qapp, window)
    assert moved, "dragging the fit-range edge did not move the range"
    assert moved[-1][0] > 20
    assert window.fit.fit_range[0] == moved[-1][0]


def test_dragging_the_bar_over_the_decay_resizes_and_is_saved(window, qapp):
    plot = window._plots_all[0]
    stack = plot.plot_stack
    bar = stack._bar_boxes[1]
    start = _point(bar)
    data_before = stack._pane_boxes[2][3]
    host = _host(window)
    QTest.mousePress(host, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, start)
    _frames(qapp, window, 1)
    _move(window, start + QtCore.QPoint(0, 60), QtCore.Qt.LeftButton)
    _frames(qapp, window, 1)
    QTest.mouseRelease(host, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, start + QtCore.QPoint(0, 60))
    _frames(qapp, window)
    assert stack._pane_boxes[2][3] < data_before - 40
    assert stack.user_sized
    state = window.get_project_plot_state()
    saved = {rec["index"]: rec for rec in state["plots"]}
    assert "split" in saved[0].get("plot", {})


def test_a_canvas_change_wakes_the_surface(window, qapp):
    surface = window.plot_tab_widget.surface
    surface.wants_frame = False
    window._plots_all[0].panel_items[2].canvas.refresh()
    assert surface.wants_frame


def test_the_layout_roundtrips_and_a_foreign_one_is_refused(window, qapp, qtbot):
    area = window.plot_tab_widget
    docks = area.surface.docks
    right = docks.split_region("center", "right")
    docks.dock("5:Residuals", right)
    area.setCurrentIndex(2)
    state = area.get_layout_state()
    assert state["type"] == LAYOUT_TYPE

    other = FitPlotsArea()
    qtbot.addWidget(other)
    for index, title in enumerate(TCSPC_PAGES):
        other.add_page(title, lambda: None, key=f"{index}:{title}")
    assert other.set_layout_state(state, emit_change=False)
    assert other.surface.docks.region_of("5:Residuals") == right
    assert other.currentIndex() == 2
    # The Qt dock area's format, and a layout for other pages, change nothing.
    assert not other.set_layout_state({"version": 1, "root": {"type": "tab", "tabs": []}})
    wrong = dict(state, keys=state["keys"][:-1])
    assert not other.set_layout_state(wrong)


def test_the_layout_persists_per_model_class(window, qapp, qtbot, tmp_path):
    area = window.plot_tab_widget
    right = area.surface.docks.split_region("center", "right")
    area.surface.docks.dock("5:Residuals", right)
    window.save_fit_dock_layout_state()
    assert (tmp_path / "fit_window_dock_layouts.ini").is_file()

    controls = QtWidgets.QWidget()
    qtbot.addWidget(controls)
    layout = QtWidgets.QVBoxLayout(controls)
    again = FitSubWindow(window.fit, layout)
    again.close_confirm = False
    qtbot.addWidget(again)
    again.show()
    _frames(qapp, again)
    assert again.plot_tab_widget.surface.docks.region_of("5:Residuals") == right
    again.close()


def test_code_shows_the_model_source_on_the_same_surface(window, qapp):
    window.flip_to_code_btn.click()
    _frames(qapp, window)
    area = window.plot_tab_widget
    assert area.code_shown()
    assert window.flip_to_code_btn.text() == "Plots"
    face = window.code_face
    assert face is not None and face.files
    assert face.active_doc is not None and face.active_doc.path.endswith(".py")
    assert len(face.symbols) > 1, "Jump to: lists nothing for the model source"
    assert any(doc.path.endswith(".json") for doc in face.documents), "view.json not opened"
    shown = [w for w in area.findChildren(QtWidgets.QWidget) if w.isVisible()]
    assert shown == [area.host]
    for name in ("agent", "back", "forward", "file", "jump", "apply", "editor"):
        assert name in face.item_rects, f"{name} not drawn"


def test_typing_into_the_code_face_edits_the_file(window, qapp):
    window.show_code_view()
    _frames(qapp, window)
    face = window.code_face
    editor = face.active_doc.editor
    _click(qapp, window, _point(face.item_rects["editor"]))
    before = editor.text
    QTest.keyClicks(_host(window), "#x")
    _frames(qapp, window)
    assert editor.text != before
    assert "#x" in editor.text


def test_jump_to_moves_the_caret_and_back_returns(window, qapp):
    window.show_code_view()
    face = window.code_face
    target = face.symbols[-1]
    face.goto_line(int(target.line) - 1)
    assert face.active_doc.editor.cursors.main.end.line == int(target.line) - 1
    assert face.can_go_back()
    face.back()
    assert face.active_doc.editor.cursors.main.end.line == 0


def test_plots_comes_back(window, qapp):
    window.show_code_view()
    window.flip_to_code_btn.click()
    _frames(qapp, window)
    assert not window.plot_tab_widget.code_shown()
    assert window.flip_to_code_btn.text() == "Code"


def test_a_read_only_model_source_is_saved_as_a_startup_override(window, tmp_path, monkeypatch):
    """The copy a read-only install gets is one ``inject_user_models`` applies next start.

    It used to be ``<file>_<timestamp>.py``, a name the startup injection skips,
    so the edit silently vanished on restart although the docs promised it back.
    """
    import sys
    from unittest.mock import patch

    from chisurf.gui.devtools.source_jump import resolve_compute_model_class

    model_class = resolve_compute_model_class(window.fit.model) or window.fit.model.__class__
    module = sys.modules[model_class.__module__]
    source = tmp_path / "readonly_model.py"
    source.write_text("# read-only\n")
    monkeypatch.setattr(module, "_readonly_original", model_class, raising=False)
    code = f"{model_class.__name__} = _readonly_original\n"
    monkeypatch.setattr("chisurf.gui.widgets.fitting.fit_subwindow.os.access", lambda *a: False)
    monkeypatch.setattr("chisurf.core.settings.path_utils.get_path", lambda *_: tmp_path)
    with patch("inspect.getsourcefile", return_value=str(source)), patch(
        "chisurf.gui.widgets.fitting.fit_subwindow.get_fitting_client", return_value=None
    ):
        status = window.save_model_code(str(source), code)
    written = list((tmp_path / "models").glob("*.py"))
    assert len(written) == 1, written
    name = written[0].stem
    module_name, _, timestamp = name.partition("__override__")
    assert module_name == model_class.__module__ and timestamp
    assert written[0].read_text() == code
    assert source.read_text() == "# read-only\n"
    assert status.endswith("model code applied.")


def test_a_page_in_another_region_shows_its_data(window, qapp):
    """Every page in view is filled, not only the current one.

    A page docked into a second region is never "changed to" while the first
    region's tab stays current, so it used to stay an empty 0..1 frame.
    """
    area = window.plot_tab_widget
    docks = area.surface.docks
    right = docks.split_region("center", "right")
    docks.dock("5:Residuals", right)
    area.setCurrentIndex(0)
    _frames(qapp, window, 5)
    assert 5 in area.visible_indices() and 0 in area.visible_indices()
    residuals = window._plots_all[5]
    assert residuals is not None
    x, y = residuals.curves[0].get_data()
    assert len(x) > 0 and np.isfinite(y).any()
    # and a parameter change reaches it too
    window.refresh_current_plot()
    x2, _ = residuals.curves[0].get_data()
    assert len(x2) == len(x)


def test_no_page_leaves_a_panel_as_a_top_level_widget(window, qapp):
    """Every page's chiplot panels belong to the page.

    The surface draws a panel's canvas, so nothing adds the panel to a shown
    layout. Left parentless, LinePlot's three panels were top-level widgets
    that the interpreter destroyed in arbitrary order at exit: a segfault after
    the last test of a run.
    """
    from chisurf.gui.chiplot.canvas import Plot

    area = window.plot_tab_widget
    for index in range(area.count()):
        window.ensure_plot_created(index)
    _frames(qapp, window)
    stray = [w for w in QtWidgets.QApplication.topLevelWidgets() if isinstance(w, Plot)
             and any(w in getattr(p, "_panels", ()) for p in window._plots_all if p is not None)]
    assert stray == []
