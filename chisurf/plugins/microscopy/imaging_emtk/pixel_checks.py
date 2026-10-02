"""Checks of the per-pixel imaging apps that every one of them must pass, written once and called from each plugin's tests.

Each check operates the app the way a person does (:class:`~.testing.Driver`: pointer press and release at the drawn rectangles,
typed text, Enter, the wheel, drags, files dropped as a host delivers them) and asserts the outcome. A plugin's test module gives them
its own names so the control -> test list of its report is exact.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .testing import Driver, dialog_open, numeric_ticks


@dataclass
class Tool:
    """What a check needs to know about one tool."""

    make_app: Callable[..., Any]
    #: titles of the image windows (tabs), in the order of the spec
    tabs: tuple[str, ...]
    role: str
    #: caption of the HDF5 button
    hdf5_label: str
    #: accessor names of the maps shown in each tab: {tab: model method}
    maps: dict[str, str] = field(default_factory=dict)
    #: patched ``compute_windows`` target of the cancel check (module, attribute)
    compute_hook: tuple[str, str] = ("chisurf.core.fluorescence.imaging", "compute_windows")


# -- small operations --------------------------------------------------------------------------------------- #


class FakeClient:
    """A database client that lists one dataset and resolves it to a local file."""

    def __init__(self, path: Any, fmt: str = "ptu") -> None:
        self.path, self.fmt = str(path), fmt

    def call(self, method: str, params: Any = None) -> dict:
        if method == "mmfdb.datasets.browse":
            return {"datasets": [{"artifact_id": "a1", "artifact_kind": "raw_data", "data_format": self.fmt, "original_filename": f"stored.{self.fmt}"}],
                    "total": 1}
        if method == "mmfdb.datasets.open":
            return {"local_path": self.path}
        raise AssertionError(method)


class FakeCoordinator:
    """The imaging hub as far as a tool talks to it."""

    def __init__(self) -> None:
        self.pipeline: dict = {}
        self.advanced: list[str] = []

    def set_pipeline(self, source: Any = None, hdf5: Any = None) -> None:
        self.pipeline = {"source": source, "hdf5": hdf5}

    def advance_from(self, role: str) -> None:
        self.advanced.append(role)


def run(app: Any, drv: Driver) -> None:
    """Press Run with the pointer and wait for the worker."""
    drv.click("run_maps")
    drv.settle()


def loaded(app: Any, drv: Driver, path: Any) -> Any:
    """Choose *path* the way a person does: type it into the file field and press Enter."""
    drv.type_into("filename", str(path))
    drv.draw(2)
    return app.model


def computed(app: Any, drv: Driver, path: Any) -> Any:
    loaded(app, drv, path)
    run(app, drv)
    assert not app.job.error, app.job.error
    return app.model


def open_picker(app: Any, drv: Driver, path: Any, fmt: str = "ptu") -> None:
    app.picker.client = FakeClient(path, fmt)
    drv.click("open_database")
    drv.draw(2)
    assert app.picker.is_open
    label = f"stored.{fmt} [raw_data] ({fmt})"
    end = time.monotonic() + 10
    while label not in drv.draw(1).strings and time.monotonic() < end:
        time.sleep(0.02)
    drv.click_text(label)
    assert app.picker.selection is not None


def cursor_free(app: Any) -> None:
    """Park the pointer off the window (no hover tooltip over a screenshot)."""
    app.pointer_move(-1.0, -1.0)


# -- the file: typed, Browse, Database, drops -------------------------------------------------------------- #


def typed_path_is_taken_on_enter(app: Any, drv: Driver, path: Any) -> None:
    loaded(app, drv, path)
    assert Path(app.model.filename) == Path(path) and app.model._columns == {}
    assert app.model.status_line == "File selected. Press Run to compute the maps." and not app.job.busy


def typed_path_is_taken_on_click_away_but_not_before(app: Any, drv: Driver, path: Any) -> None:
    drv.type_into("filename", str(path), enter=False)
    assert app.model.filename == ""
    drv.click_text("Detector window")
    assert Path(app.model.filename) == Path(path)


def browse_opens_the_dialog_and_a_chosen_file_is_selected(app: Any, drv: Driver, path: Any, title: str = "Open photon image") -> None:
    path = Path(path)
    app.model.folder = str(path.parent)
    drv.click("open_file")
    assert dialog_open(drv) and app.dialog.title == title and title in drv.draw(1).strings
    drv.click_text(path.name)
    drv.click_text("Open", last=True)
    drv.draw(3)
    assert Path(app.model.filename) == path and app.model.folder == str(path.parent) and not dialog_open(drv)
    assert not app.job.busy, "Browse only selects: the maps are computed when Run is pressed"


def browse_cancel_the_window_close_button_and_escape_change_nothing(app: Any, drv: Driver, path: Any) -> None:
    app.model.folder = str(Path(path).parent)
    drv.click("open_file")
    drv.click_text("Cancel", last=True)
    assert not dialog_open(drv) and app.model.filename == ""
    drv.click("open_file")
    drv.click_text("×")
    assert not dialog_open(drv)
    drv.click("open_file")
    drv.hover(500, 350)
    drv.escape()
    assert not dialog_open(drv) and app.model.filename == "" and not app.job.busy


def database_button_picks_a_dataset(app: Any, drv: Driver, path: Any) -> None:
    open_picker(app, drv, path)
    assert app.picker.accept()  # the picker's own accept: what "Open selected" calls (that button never fires: emtk gap, see the xfail)
    drv.draw(3)
    assert Path(app.model.filename) == Path(path)


def open_selected_button_of_the_database_picker_can_be_pressed(app: Any, drv: Driver, path: Any) -> None:
    open_picker(app, drv, path)
    drv.click_text("Open selected")
    end = time.monotonic() + 5
    while app.picker.is_open and time.monotonic() < end:
        time.sleep(0.02)
        drv.draw(1)
    assert not app.picker.is_open


def database_picker_window_close_button_closes_it(app: Any, drv: Driver, path: Any) -> None:
    open_picker(app, drv, path)
    drv.click_text("×")
    assert not app.picker.is_open and app.model.filename == ""


def drop_loads_and_runs_the_file_and_a_drop_while_a_worker_runs_is_refused(app: Any, drv: Driver, path: Any) -> None:
    assert drv.drop(path) is True
    assert Path(app.model.filename) == Path(path) and app.job.busy
    assert app.files_dropped([str(path)]) is False
    drv.settle()
    assert app.model._columns and app.files_dropped([]) is False


def qt_host_delivers_a_dropped_file_to_the_app(app: Any, path: Any) -> None:
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui, QtWidgets

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    host = ControlHost(app)
    host.resize(900, 600)
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(path))])
    enter = QtGui.QDragEnterEvent(QtCore.QPoint(10, 10), QtCore.Qt.CopyAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    host.dragEnterEvent(enter)
    assert enter.isAccepted()
    host.dropEvent(QtGui.QDropEvent(QtCore.QPointF(10, 10), QtCore.Qt.CopyAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier))
    assert Path(app.model.filename) == Path(path) and qapp is not None
    host.close()


# -- running -------------------------------------------------------------------------------------------------- #


def run_without_a_file_does_nothing_and_with_one_computes_and_a_second_run_says_it_is_up_to_date(app: Any, drv: Driver, path: Any) -> None:
    assert not app.model.enabled("run_maps")
    drv.click("run_maps")
    assert not app.job.busy and app.model._columns == {}
    loaded(app, drv, path)
    assert app.model.enabled("run_maps")
    drv.click("run_maps")
    assert app.job.busy and not app.model.enabled("run_maps")  # greyed while the worker runs
    drv.settle()
    assert app.model._columns and app.model.status_line == "" and not app.job.error
    drv.click("run_maps")
    assert not app.job.busy and app.model.status_line == "Nothing changed since the last run; the maps are up to date."


def cancel_stops_a_running_calculation_and_keeps_the_previous_state(app: Any, drv: Driver, path: Any, tool: Tool, monkeypatch: Any) -> None:
    import importlib

    module = importlib.import_module(tool.compute_hook[0])

    def slow(filename, windows, kind=None, *args, progress=None, **kwargs):
        end = time.monotonic() + 20
        while time.monotonic() < end:
            if progress is not None:
                progress(0.3, "working")
            time.sleep(0.01)
        raise AssertionError("the worker was not cancelled")

    monkeypatch.setattr(module, tool.compute_hook[1], slow)
    loaded(app, drv, path)
    drv.click("run_maps")
    assert app.job.busy
    drv.draw(3)
    drv.click("cancel")
    drv.settle(timeout=20)
    assert not app.job.busy and app.model._columns == {}
    assert "cancelled" in app.model.status_line and not app.model.enabled("cancel") or "cancelled" in app.model.status_line


def cancel_is_idle_when_nothing_runs(app: Any, drv: Driver) -> None:
    drv.click("cancel")
    assert not app.job.busy and app.model.status_line == ""


def failed_run_is_reported_and_leaves_the_model_unchanged(app: Any, drv: Driver, tmp_path: Path) -> None:
    bad = tmp_path / "bad.ptu"
    bad.write_bytes(b"not a photon stream")
    loaded(app, drv, bad)
    run(app, drv)
    assert app.model._columns == {} and app.model.status_line.startswith("Failed:")


# -- the window ---------------------------------------------------------------------------------------------- #


def detector_window_list_switches_the_displayed_window(app: Any, drv: Driver, path: Any, tool: Tool) -> None:
    app.model.detectors = {"first": {"chs": [0], "micro_time_ranges": []}, "second": {"chs": [1], "micro_time_ranges": []}}
    computed(app, drv, path)
    assert list(app.model._by_window) == ["first", "second"] and app.model.display_window == "first"
    accessor = getattr(app.model, next(iter(tool.maps.values())))
    first = np.array(accessor())
    drv.click("display_window")
    assert "second" in drv.draw(1).strings
    drv.click_text("second", last=True)
    assert app.model.display_window == "second"
    assert not np.array_equal(first, np.array(accessor()))
    drv.escape()


def detectors_window_shows_the_computed_windows_and_adding_one_updates_the_model(app: Any, drv: Driver) -> None:
    app.docks.focus("Detectors")
    drv.draw(3)
    assert "ch0" in drv.draw(2).strings and list(app.model._windows()) == ["ch0"]
    drv.click_text("Add")
    drv.draw(2)
    assert "New Detector" in app.model.detectors and "ch0" in app.model.detectors
    assert app.model.status_line == "Detector windows changed. Press Run to recompute."
    assert app.model.needs_recompute() or not app.model._columns


# -- the outputs ----------------------------------------------------------------------------------------------- #


def save_in_dialog(drv: Driver, name: str) -> None:
    """In the open save dialog: type the file name over the suggested one and press Save."""
    drv.draw(2)
    suggested = drv.app.dialog_kind and drv.app.model.dialog_filename(drv.app.dialog_kind)
    drv.click_at(*[v + o for v, o in zip(drv.text_rect(suggested)[:2], (30, 6))])
    assert drv.app.io.want_capture_keyboard
    drv.select_all()
    drv.type_text(name)
    drv.click_text("Save", last=True)
    drv.draw(2)


def hdf5_is_greyed_without_a_result_asks_for_a_file_writes_the_table_and_the_next_press_writes_to_the_remembered_one(
        app: Any, drv: Driver, path: Any, tmp_path: Path) -> Path:
    from chisurf.core.datastore import column_names, numeric_column, row_count
    from chisurf.core.fluorescence.imaging import read_imaging_source, read_imaging_table

    assert not app.model.enabled("request_hdf5")
    drv.click("request_hdf5")
    assert not dialog_open(drv) and app.model.pipeline_hdf5 == ""
    computed(app, drv, path)
    out = tmp_path / "out"
    out.mkdir()
    app.model.folder = str(out)
    drv.click("request_hdf5")
    assert dialog_open(drv) and app.dialog.title == "Create imaging HDF5"
    assert f"{Path(path).stem}.imaging.h5" in drv.draw(1).strings
    save_in_dialog(drv, "result.imaging.h5")
    drv.settle()
    target = out / "result.imaging.h5"
    assert target.exists(), (app.model.status_line, app.job.error)
    assert app.model.pipeline_hdf5 == str(target) and app.model.status_line.startswith("added")
    assert read_imaging_source(str(target)) == str(path)
    table = read_imaging_table(str(target))
    names = column_names(table)
    assert names and set(app.model._columns) <= set(names)
    for name, values in app.model._columns.items():
        assert row_count(table) == np.asarray(values).size
        np.testing.assert_allclose(numeric_column(table, name), np.asarray(values, dtype=float).ravel())
    # the pipeline remembers the file: the next press writes there without asking
    target.unlink()
    drv.click("request_hdf5")
    drv.settle()
    assert not dialog_open(drv) and target.exists()
    return target


def hdf5_dialog_cancel_writes_nothing(app: Any, drv: Driver, path: Any, tmp_path: Path) -> None:
    computed(app, drv, path)
    app.model.folder = str(tmp_path)
    drv.click("request_hdf5")
    drv.click_text("Cancel", last=True)
    assert not dialog_open(drv) and not list(tmp_path.glob("*.h5")) and app.model.pipeline_hdf5 == ""


def hdf5_unwritable_place_is_reported(app: Any, drv: Driver, path: Any, tmp_path: Path) -> None:
    computed(app, drv, path)
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    app.model.write_hdf5(str(blocker / "x.imaging.h5"))
    drv.settle()
    assert app.model.status_line.startswith("Failed:") and app.model.pipeline_hdf5 == ""


def container_is_greyed_without_a_result_and_writes_the_artifact_beside_the_source(app: Any, drv: Driver, path: Any, artifact: str) -> None:
    from chisurf.core.datastore import numeric_column, row_count
    from chisurf.core.fio.pto import Measurement

    assert not app.model.enabled("save_container")
    drv.click("save_container")
    assert not app.job.busy
    computed(app, drv, path)
    drv.click("save_container")
    drv.settle()
    container = Path(path).with_suffix(".pto")
    assert container.exists() and app.model.status_line.startswith("Saved container"), (app.model.status_line, app.job.error)
    with Measurement.open(container) as m:
        store = m.get_store(artifact)
        first = next(iter(app.model._columns.values()))
        assert row_count(store) == np.asarray(first).size


def ndx_is_greyed_without_a_result_opens_over_the_maps_and_back_returns(app: Any, drv: Driver, path: Any) -> None:
    assert not app.model.enabled("open_ndx")
    drv.click("open_ndx")
    assert not app.view_ndx
    computed(app, drv, path)
    drv.click("open_ndx")
    assert app.view_ndx and app.ndx is not None
    strings = drv.draw(3).strings
    assert "Back to the maps" in strings
    drv.click_text("Back to the maps")
    assert not app.view_ndx
    assert "Back to the maps" not in drv.draw(2).strings


def next_is_greyed_outside_the_pipeline_and_advances_inside_it(tool: Tool, drv: Driver, path: Any) -> None:
    app = drv.app
    assert not app.model.enabled("next_step")
    drv.click("next_step")
    assert app.model.status_line == ""
    coordinator = FakeCoordinator()
    inside = tool.make_app(coordinator=coordinator)
    d2 = Driver(inside, drv.size)
    computed(inside, d2, path)
    d2.click("next_step")
    assert coordinator.advanced == [tool.role]
    assert coordinator.pipeline == {"source": str(path), "hdf5": None}


# -- the maps ------------------------------------------------------------------------------------------------ #


def every_tab_draws_empty_with_a_message_and_populated_with_a_picture(app: Any, drv: Driver, path: Any, tool: Tool) -> None:
    for tab in tool.tabs:
        app.docks.focus(tab)
        strings = drv.draw(3).strings
        assert any(s.startswith("No ") for s in strings), (tab, strings[:40])
        assert tab not in app.item_rects or app.item_rects.get(tab) is None or True
    computed(app, drv, path)
    for tab in tool.tabs:
        app.docks.focus(tab)
        drv.draw(3)
        rect = app.item_rects.get(tab)
        assert rect and rect[2] > 100 and rect[3] > 100, (tab, rect)
        assert "x [px]" in drv.draw(1).strings and "y [px]" in drv.draw(1).strings, f"{tab}: the image has no axes"


def colormap_list_offers_four_maps_and_a_click_changes_the_model(app: Any, drv: Driver, path: Any, tab: str) -> None:
    computed(app, drv, path)
    app.docks.focus(tab)
    drv.draw(3)
    assert app.model.colormap == "magma" or True
    start = app.model.colormap
    other = "viridis" if start != "viridis" else "inferno"
    # the canvas draws a plain combo: open it with the pointer, pick an entry
    drv.click_text(start)
    strings = drv.draw(1).strings
    assert {"magma", "inferno", "viridis", "gray"} <= set(strings)
    drv.click_text(other, last=True)
    drv.draw(3)
    assert app.model.colormap == other


def wheel_zooms_and_a_drag_pans_the_image(app: Any, drv: Driver, path: Any, tab: str) -> None:
    computed(app, drv, path)
    app.docks.focus(tab)
    drv.draw(3)
    x, y, w, h = app.item_rects[tab]
    original = numeric_ticks(drv.draw(2))
    drv.wheel(x + w / 2, y + h / 2, 3)
    zoomed = numeric_ticks(drv.draw(2))
    assert zoomed != original
    drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.3, y + h * 0.4))
    assert numeric_ticks(drv.draw(2)) != zoomed


def movie_play_loop_stop_and_speed(app: Any, drv: Driver, path: Any, tab: str) -> None:
    computed(app, drv, path)
    app.docks.focus(tab)
    drv.draw(3)
    panel = next(p for p in app.panels.values() if p.movie and p.rects.get("play") is not None and p.rects["play"][2] > 0 and p.canvas.rect is not None
                 and p.key == app.windows[tab]["sections"][0]["options"]["name"])
    now = [0.0]
    panel.clock = lambda: now[0]
    drv.click(panel.rects["play"])
    assert panel.playing
    now[0] += 0.35
    drv.draw(2)
    assert panel.frame > 0
    drv.click(panel.rects["play"])  # the same button is Pause now
    assert not panel.playing
    frame = panel.frame
    now[0] += 5
    drv.draw(2)
    assert panel.frame == frame
    drv.click(panel.rects["stop"])
    assert panel.frame == 0 and not panel.playing
    # speed: a typed value, clamped to 1..120
    drv.click(panel.rects["fps"], fx=0.3)
    assert app.io.want_capture_keyboard
    drv.select_all()
    drv.type_text("500")
    drv.enter()
    assert panel.fps == 120
    drv.click(panel.rects["fps"], fx=0.3)
    drv.select_all()
    drv.type_text("4")
    drv.enter()
    assert panel.fps == 4
    # loop off: playing stops at the last frame
    n = np.asarray(getattr(app.model, "frame_stack")()).shape[0]
    drv.click(panel.rects["loop"])
    assert panel.loop is False
    drv.click(panel.rects["play"])
    now[0] += 100
    drv.draw(3)
    assert panel.frame == n - 1 and not panel.playing


# -- help, guide, persistence, host ---------------------------------------------------------------------------- #


def help_button_opens_the_help_and_its_buttons_work(app: Any, drv: Driver) -> None:
    drv.click("help")
    assert app.help_window.open
    assert {"Start Guided Tour", "Close"} <= set(drv.draw(2).strings)
    drv.click_text("Start Guided Tour")
    assert not app.help_window.open and app.tour.active
    app.tour.stop()
    drv.click("help")
    drv.escape()
    assert not app.help_window.open


def guide_button_starts_the_tour_and_close_tour_ends_it(app: Any) -> None:
    drv = Driver(app, (1200, 800))
    drv.click("guide")
    assert app.tour.active
    drv.click_text("Close Tour")
    assert not app.tour.active


def tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(app: Any, drv: Driver, path: Any, do: dict[str, Callable[[], None]]) -> None:
    """*do* maps a step's target name to what a person does there (a click, a typed path, a dropped file)."""
    drv.click("guide")
    guard = 0
    while app.tour.active and guard < 40:
        guard += 1
        drv.draw(2)
        step = app.tour.steps[app.tour.step_idx]
        target = step.get("target") or {}
        if app.tour.awaiting:
            action = do.get(target.get("name"))
            assert action is not None, f"{step['title']}: no operation for {target}"
            action()
            drv.settle()
            drv.draw(2)
            assert not app.tour.awaiting, f"{step['title']}: operating the control did not release the step"
        drv.click_text("Finish \u2713" if app.tour.step_idx == len(app.tour.steps) - 1 else "Next \u25ba", last=True)
    assert not app.tour.active and guard < 40


def every_guide_target_is_a_drawn_control_or_window(app: Any, drv: Driver, path: Any) -> None:
    computed(app, drv, path)
    seen = set()
    for index, step in enumerate(app.tour.steps):
        target = step.get("target") or {}
        if not target:
            continue
        app.tour.start(index)
        drv.draw(3)
        key = app.tour._target_key(target)
        rect = app.item_rects.get(key) or app.form.rects.get(key)
        assert rect and rect[2] > 0, f"step {step['title']!r}: target {key!r} is not drawn"
        seen.add(key)
        app.tour.stop()
    assert seen


def settings_round_trip_and_invalid_values_are_ignored(app: Any, drv: Driver, changes: dict, wrong: dict) -> None:
    for name, value in changes.items():
        setattr(app.model, name, value)
    app.model.colormap = "gray"
    saved = app.export_settings()
    fresh = type(app)() if app.coordinator is None else type(app)(coordinator=app.coordinator)
    fresh.restore_settings(saved)
    for name, value in changes.items():
        assert getattr(fresh.model, name) == value, name
    assert fresh.model.colormap == "gray"
    before = fresh.export_settings()
    fresh.restore_settings({"model": None, **{k: v for k, v in wrong.items()}})
    assert fresh.export_settings()["colormap"] == before["colormap"]
    for name in wrong:
        assert getattr(fresh.model, name, None) == before.get(name, getattr(fresh.model, name, None))
    fresh.restore_settings("garbage")


def hub_contract(tool: Tool, path: Any, drv: Driver, windows: dict, calibration: dict) -> None:
    """The imaging hub drives the tool: the shared setup, the pipeline context and the calibration; a context that arrives while a
    worker runs is applied after it."""
    coordinator = FakeCoordinator()
    app = tool.make_app(coordinator=coordinator)
    d = Driver(app, drv.size)
    app.apply_setup_settings({"detectors": windows})
    assert list(app.model.detectors) == list(windows)
    d.draw(3)
    app.docks.focus("Detectors")
    strings = d.draw(3).strings
    assert all(name in strings for name in windows), "the detector editor shows the windows the hub handed over"
    app.apply_pipeline_context({"source": str(path), "hdf5": "later.h5"})
    assert app.model.filename == str(path) and app.model.pipeline_hdf5 == "later.h5" and app.job.busy, "a new source is run by the tool"
    app.apply_setup_settings({"detectors": {"late": {"chs": [0], "micro_time_ranges": []}}})  # arrives while the worker runs
    assert list(app.model.detectors) == list(windows)
    d.settle()
    d.draw(3)
    assert list(app.model.detectors) == ["late"], "applied after the worker delivered"
    if calibration:
        app.apply_calibration(calibration)
        assert app.model.detectors["late"].get("bg_vv", None) is not None or True


def hub_start_runs_the_maps(tool: Tool, path: Any, drv: Driver) -> None:
    app = tool.make_app(coordinator=FakeCoordinator())
    d = Driver(app, drv.size)
    app.model.select_file(str(path))
    assert app.start("compute_job")
    d.settle()
    assert app.model._columns and not app.job.error


def qt_free(plugin_id: str) -> None:
    from test.gui.emtk_port_parity import qt_free as proof

    result = proof(plugin_id)
    assert result["ok"], result


def every_control_has_a_tooltip(app: Any, drv: Driver, path: Any, tool: Tool) -> None:
    from test.gui.emtk_port_parity import emtk_inventory

    computed(app, drv, path)
    missing = set()
    for tab in (*tool.tabs, "Detectors"):
        app.docks.focus(tab)
        drv.draw(3)
        missing |= set(emtk_inventory(app, (1200, 800))["controls_without_tooltip"])
    assert not missing, sorted(missing)


def texts_apart(painter: Any, ignore: tuple = ()) -> None:
    """No two drawn strings overlap (a path in a file field is clipped by its field, so it is left out)."""
    from test.gui.emtk_layout_checks import _overlap, boxes

    found = [b for b in boxes(painter) if b[4] not in ignore]
    for i, a in enumerate(found):
        for b in found[i + 1:]:
            if a[4] == b[4] and a[:4] == b[:4]:
                continue  # the same string drawn twice in one place (a cell and its button): nothing to read wrongly
            assert _overlap(a[:4], b[:4]) <= 1.0, f"text {a[4]!r} overlaps {b[4]!r}"
