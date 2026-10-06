"""The native Trace Browser, card T3b: trace plot, annotation, first-row selection, precompute.

Everything runs on temporary COPIES of ``test/data/tttr/BH/132/BH_SPC132.spc`` (the browser writes the
metadata ``.trace_browser_meta.json`` and a trace cache beside the data). The reference for the ALEX setup
on that file is the one the legacy engine gave (recorded in ``test_binning_trace_browser.py``): 6233 bins
of 10 ms with the per-detector sums ``[22443, 56257, 0]`` for ``green``, ``red``, ``yellow``. The plots are
``emtk.implot`` calls; the tests record them by wrapping ``implot.plot_line`` and the axis set-up calls.
"""

import json
import pathlib
import shutil
import time

import numpy as np
import pytest
from emtk import im, implot

from chisurf.plugins.tttr.trace_browser.test.conftest import ALEX
from chisurf.plugins.tttr.trace_browser.test.test_emtk_trace_browser_t2 import (
    BH132,
    ENTRY,
    GUI,
    META,
    SPEC,
    all_sections,
    commit,
    data_dir,  # noqa: F401  (fixture)
    edit_cell,
    fake_dir,  # noqa: F401  (fixture)
    frames,
    pressing,
    table,
)

LABELS = ["green", "red", "yellow"]
SUMS = [22443, 56257, 0]
BINS_10MS = 6233
BINS_1MS = 62329


# ---- helpers ---------------------------------------------------------------------------------
@pytest.fixture
def alex_dir(tmp_path):
    """A temp folder with two copies of the real BH132 sample: ``m000.spc`` and ``m001.spc``."""
    if not BH132.exists():
        pytest.skip("sample TTTR data missing")
    folder = tmp_path / "alex"
    folder.mkdir()
    shutil.copy(BH132, folder / "m000.spc")
    shutil.copy(BH132, folder / "m001.spc")
    return folder


def make_alex_app(precompute=False):
    """The app on its Browser page with the real ALEX setup accepted (the detectors are named)."""
    from chisurf.plugins.tttr.trace_browser.gui.app import TraceBrowserApp

    app = TraceBrowserApp()
    app.model.accept_setup(json.loads(json.dumps(ALEX)))
    app.model.precompute_after_scan = precompute
    return app


def idle(app):
    """True when no worker runs and the trace area shows what the model asks for."""
    return not (
        app.job.busy
        or app._queue
        or app.load_job.busy
        or app.pre_job.busy
        or app.model.precompute_pending
        or app.wanted_trace() not in (None, app._failed, app.shown_trace())
    )


def settle_all(app, size=(1200, 800), timeout=60.0):
    """Draw frames until every job is done and the trace matches the selection; return the last strings."""
    deadline = time.time() + timeout
    frames(app, size, 1)
    while not idle(app) and time.time() < deadline:
        time.sleep(0.02)
        frames(app, size, 1)
    assert idle(app), "the app did not settle"
    return frames(app, size, 2)


class Recorder:
    """Records the implot calls the app makes while drawing (wraps the real functions)."""

    def __init__(self, monkeypatch):
        self.lines: list[tuple] = []
        self.axes: list[tuple] = []
        self.limits: list[tuple] = []
        self.plots: list[str] = []
        for name, store in (
            ("plot_line", self.lines),
            ("setup_axes", self.axes),
            ("setup_axis_limits", self.limits),
            ("begin_plot", self.plots),
        ):
            monkeypatch.setattr(implot, name, self._wrap(getattr(implot, name), store, name))

    @staticmethod
    def _wrap(real, store, name):
        def call(*args, **kwargs):
            if name == "plot_line":
                store.append(
                    (args[0], np.array(args[1], dtype=float), np.array(args[2], dtype=float))
                )
            elif name == "begin_plot":
                store.append(args[0])
            else:
                store.append(args)
            return real(*args, **kwargs)

        return call

    def clear(self):
        for store in (self.lines, self.axes, self.limits, self.plots):
            store.clear()

    def last_frame_lines(self, app, size=(1200, 800)):
        """Draw one frame and return the lines it drew as ``{label: (x, y)}`` (trace plot first)."""
        self.clear()
        frames(app, size, 1)
        return self.lines


@pytest.fixture
def recorder(monkeypatch):
    return Recorder(monkeypatch)


def open_and_show(app, folder):
    app.model.request("open_folder", folder)
    return settle_all(app)


# 1. selecting a row loads and draws the trace; the drawn series are the model's series
def test_selecting_a_row_loads_and_draws_the_trace(alex_dir, recorder):
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        model = app.model
        assert model.current_file == alex_dir / "m000.spc"  # first-row selection, no click
        control = table(app)
        control._select_position(1)  # the table reports a click on m001
        assert model.current_file == alex_dir / "m001.spc" and model.trace is None
        assert "Loading m001.spc" in " | ".join(frames(app, n=1))  # the visible loading state
        settle_all(app)
        trace = model.trace
        assert trace["path"] == str(alex_dir / "m001.spc") and trace["labels"] == LABELS
        counts = np.asarray(trace["counts"])
        assert counts.shape == (BINS_10MS, 3) and [int(v) for v in counts.sum(axis=0)] == SUMS
        assert len(trace["time_axis"]) == BINS_10MS and trace["time_window_ms"] == 10.0
        drawn = recorder.last_frame_lines(app)
        # the trace plot draws Sum, then the three detectors; the histogram plot draws the non-empty ones
        trace_lines = drawn[:4]
        assert [label for label, _, _ in trace_lines] == ["Sum"] + LABELS
        assert recorder.plots == ["Intensity trace##tb_trace", "Counts histogram##tb_hist"]
        view = app._view
        assert [e["label"] for e in view.series] == ["Sum"] + LABELS
        assert [int(e["total"]) for e in view.series] == [sum(SUMS)] + SUMS
        # the drawn y values are the series' counts (decimated, so a subset that keeps min and max)
        for (label, x, y), column in zip(trace_lines[1:], counts.T):
            assert len(y) <= 4000 and y.max() == column.max() and y.min() == column.min()
            assert np.all(np.isin(y, column))
        yellow_hist = [entry for entry in drawn[4:] if entry[0] == "yellow"]
        assert not yellow_hist  # an all-zero series has no histogram
    finally:
        app.close()


def test_the_drawn_lines_equal_the_model_counts_when_nothing_is_decimated(
    alex_dir, recorder, monkeypatch
):
    from chisurf.plugins.tttr.trace_browser.gui import app as app_module

    monkeypatch.setattr(app_module, "MAX_POINTS", 10**6)
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        counts = np.asarray(app.model.trace["counts"])
        app._view_for = 0  # rebuild the view with the new limit
        drawn = recorder.last_frame_lines(app)
        for (label, x, y), column in zip(drawn[1:4], counts.T):
            assert np.array_equal(y, column)
            assert np.allclose(x, app.model.trace["time_axis"])
        assert [int(y.sum()) for _, _, y in drawn[1:4]] == SUMS
        assert int(drawn[0][2].sum()) == sum(SUMS)  # the Sum line
    finally:
        app.close()


# 2. the bin window and the y range
def test_a_changed_bin_window_loads_the_trace_again(alex_dir):
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        assert len(app.model.trace["time_axis"]) == BINS_10MS
        commit(app, "window_ms", 1.0)  # the field of the spec
        text = " | ".join(frames(app, n=1))
        assert "Loading m000.spc" in text  # reloading, the old trace is kept meanwhile
        settle_all(app)
        trace = app.model.trace
        assert trace["time_window_ms"] == 1.0 and len(trace["time_axis"]) == BINS_1MS
        assert [int(v) for v in np.asarray(trace["counts"]).sum(axis=0)] == SUMS
        text = " | ".join(frames(app))
        assert "1 ms bins" in text and "Counts / 1 ms" in text
        commit(app, "window_ms", 10.0)  # back: the cached trace is shown again
        settle_all(app)
        assert len(app.model.trace["time_axis"]) == BINS_10MS
    finally:
        app.close()


def test_the_y_range_is_applied_to_the_trace_axis(alex_dir, recorder):
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        recorder.last_frame_lines(app)
        y_limits = [a for a in recorder.limits if a[0] == implot.AXIS_Y1]
        assert y_limits and all(
            a[1:3] == (0.0, 1000.0) for a in y_limits
        )  # the Qt defaults: 0..1000
        commit(app, "y_min", 5.0)
        commit(app, "y_max", 300.0)
        recorder.last_frame_lines(app)
        y_limits = [a for a in recorder.limits if a[0] == implot.AXIS_Y1]
        assert len(y_limits) == 2 and all(
            a[1:4] == (5.0, 300.0, implot.COND_ALWAYS) for a in y_limits
        )
        recorder.last_frame_lines(app)  # unchanged: ONCE, so a zoom is not undone
        assert all(a[3] == implot.COND_ONCE for a in recorder.limits if a[0] == implot.AXIS_Y1)
        # entered the wrong way round: swapped, as the Qt tool does
        commit(app, "y_min", 400.0)
        recorder.last_frame_lines(app)
        assert [a[1:3] for a in recorder.limits if a[0] == implot.AXIS_Y1] == [(300.0, 400.0)] * 2
        # equal limits: no fixed range, the axis fits the data
        commit(app, "y_min", 50.0)
        commit(app, "y_max", 50.0)
        recorder.last_frame_lines(app)
        assert not [a for a in recorder.limits if a[0] == implot.AXIS_Y1]
        assert all(call[3] & implot.AXIS_FLAGS_AUTO_FIT for call in recorder.axes)
    finally:
        app.close()


# 3. decimation (display only)
def test_decimation_keeps_the_minimum_and_the_maximum_of_every_column():
    from chisurf.plugins.tttr.trace_browser.gui.app import MAX_POINTS, decimate_minmax

    rng = np.random.default_rng(3)
    y = rng.poisson(5, 100_000).astype(float)
    y[12_345] = 400.0  # a burst
    y[77_777] = -3.0  # a dip
    x = np.arange(len(y)) * 0.001
    xd, yd = decimate_minmax(x, y)
    assert len(yd) <= MAX_POINTS and len(xd) == len(yd) and np.all(np.diff(xd) > 0)
    assert yd.max() == 400.0 and yd.min() == -3.0
    assert 12.345 in np.round(xd, 3) and 77.777 in np.round(xd, 3)
    columns = np.array_split(np.arange(len(y)), MAX_POINTS // 2)
    kept = {(round(a, 6), b) for a, b in zip(xd, yd)}
    for column in columns[:50] + columns[-50:]:  # every pixel column keeps both extremes
        assert (round(x[column][np.argmax(y[column])], 6), y[column].max()) in kept
        assert (round(x[column][np.argmin(y[column])], 6), y[column].min()) in kept
    xs, ys = decimate_minmax(x[:3000], y[:3000])  # short traces are untouched
    assert np.array_equal(ys, y[:3000]) and np.array_equal(xs, x[:3000])


def test_the_model_keeps_all_bins_and_the_plot_draws_few(alex_dir, recorder):
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        commit(app, "window_ms", 1.0)
        settle_all(app)
        counts = np.asarray(app.model.trace["counts"])
        assert counts.shape == (BINS_1MS, 3)  # the model keeps every bin
        drawn = recorder.last_frame_lines(app)
        assert all(len(y) <= 4000 for _, _, y in drawn[:4]) and len(drawn[2][2]) > 3000
        assert drawn[2][2].max() == counts[:, 1].max() and drawn[2][2].min() == counts[:, 1].min()
    finally:
        app.close()


# 4. annotation: the same field as the Notes column, persisted to the metadata file
def type_into_annotation(app, text, monkeypatch):
    """Make the annotation box report *text* typed by the user (the real call path of the box)."""
    real = im.input_text_multiline

    def fake(label, value, size=None):
        if label == "##tb_annotation":
            return True, text
        return real(label, value, size)

    monkeypatch.setattr(im, "input_text_multiline", fake)
    frames(app, n=1)
    monkeypatch.setattr(im, "input_text_multiline", real)


def test_an_annotation_edit_persists_and_shows_in_the_notes_cell(alex_dir, monkeypatch):
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        type_into_annotation(app, "good molecule, two bursts", monkeypatch)
        model = app.model
        assert model.get_notes(alex_dir / "m000.spc") == "good molecule, two bursts"
        cell = {r["name"]: r["notes"] for r in model.rows}
        assert cell == {
            "m000.spc": "good molecule, two bursts",
            "m001.spc": "",
        }  # the table's Notes cell
        assert "good molecule, two bursts" in " | ".join(frames(app))
        # debounced: the file is written once the annotation rested, not on every key
        assert app._notes_dirty_at is not None
        time.sleep(0.4)
        frames(app, n=1)
        assert app._notes_dirty_at is None
        saved = json.loads((alex_dir / META).read_text())
        assert saved["m000.spc"]["annotation"] == "good molecule, two bursts"
        # a rescan and a fresh app read it back
        model.request("scan")
        settle_all(app)
        assert {r["name"]: r["notes"] for r in model.rows}[
            "m000.spc"
        ] == "good molecule, two bursts"
    finally:
        app.close()
    other = make_alex_app()
    try:
        open_and_show(other, alex_dir)
        assert other.model.get_notes(alex_dir / "m000.spc") == "good molecule, two bursts"
    finally:
        other.close()


def test_a_notes_cell_edit_shows_in_the_annotation_box_and_the_file(alex_dir, monkeypatch):
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        edit_cell(app, "m000.spc", "notes", "edited in the table")
        assert (
            json.loads((alex_dir / META).read_text())["m000.spc"]["annotation"]
            == "edited in the table"
        )
        seen = []
        real = im.input_text_multiline

        def spy(label, value, size=None):
            if label == "##tb_annotation":
                seen.append(value)
            return real(label, value, size)

        monkeypatch.setattr(im, "input_text_multiline", spy)
        frames(app, n=1)
        assert seen == ["edited in the table"]  # the box shows the Notes cell's text
    finally:
        app.close()


def test_typing_into_the_annotation_box_with_the_keyboard(alex_dir):
    """The real input path: click into the box, type; the model, the table and the file follow."""
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        x, y, w, h = app.item_rects["annotation"]
        io = app.io
        io.mouse_pos = (x + w / 2, y + h / 2)
        io.mouse_clicked[0] = True
        frames(app, n=1)
        io.mouse_clicked[0] = False
        io.key_events = [(0, "hi there", 0)]
        frames(app, n=1)
        io.key_events = []
        frames(app, n=2)
        assert app.model.get_notes(alex_dir / "m000.spc") == "hi there"
        assert {r["name"]: r["notes"] for r in app.model.rows}["m000.spc"] == "hi there"
    finally:
        app.close()


def test_the_annotation_follows_the_selected_file(alex_dir, monkeypatch):
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        type_into_annotation(app, "first", monkeypatch)
        table(app)._select_position(1)  # another file: the first is flushed
        frames(app, n=2)
        assert app._notes_dirty_at is None
        assert json.loads((alex_dir / META).read_text())["m000.spc"]["annotation"] == "first"
        seen = []
        real = im.input_text_multiline
        monkeypatch.setattr(
            im,
            "input_text_multiline",
            lambda label, value, size=None: (seen.append(value), real(label, value, size))[1],
        )
        frames(app, n=1)
        assert seen == [""]  # m001 has no notes
    finally:
        app.close()


def test_closing_flushes_a_pending_annotation(alex_dir, monkeypatch):
    app = make_alex_app()
    open_and_show(app, alex_dir)
    type_into_annotation(app, "unsaved", monkeypatch)
    app.close()
    assert json.loads((alex_dir / META).read_text())["m000.spc"]["annotation"] == "unsaved"


# 5. empty state, errors, first-row selection
def test_empty_state_says_what_to_do_and_draws_no_curve(recorder):
    app = make_alex_app()
    try:
        text = " | ".join(frames(app))
        assert "Open a folder with TTTR files, then select a file to show its trace." in text
        assert "Select a file to write an annotation for it." in text
        assert recorder.lines == [] and recorder.plots == []  # nothing is drawn: no invented curve
        assert app.model.trace is None and app.wanted_trace() is None
    finally:
        app.close()


def test_a_folder_without_a_selection_asks_for_one(alex_dir, recorder):
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        app.model.set_selection([])
        app.model.select_row(None)
        settle_all(app)
        text = " | ".join(frames(app))
        assert "Select a file in the table to show its intensity trace." in text
        recorder.clear()
        frames(app, n=1)
        assert recorder.lines == []
    finally:
        app.close()


def test_a_failing_load_shows_the_error_and_draws_nothing(fake_dir, recorder):  # noqa: F811
    app = make_alex_app()
    try:
        open_and_show(app, fake_dir)  # unreadable stand-in files
        assert app.model.current_file.name == "a.ptu"
        text = " | ".join(frames(app))
        assert "Failed to load a.ptu" in text and "unsupported container type" in text
        assert app.model.trace is None and recorder.lines == []
        assert "Failed to load a.ptu" in app.model.status_line
        # no retry loop: the failed (file, window) is not loaded again every frame
        assert not app.load_job.busy and app._failed == (fake_dir / "a.ptu", 10.0)
        table(app)._select_position(1)  # another file clears the error
        assert app.model.trace_error == ""
        settle_all(app)
        assert "Failed to load b.PTU" in " | ".join(frames(app))
    finally:
        app.close()


def test_a_load_error_from_the_model_is_shown(alex_dir, monkeypatch):
    app = make_alex_app()
    try:

        def boom(path, window_ms=None):
            raise OSError("disk went away")

        monkeypatch.setattr(app.model, "load_trace", boom)
        open_and_show(app, alex_dir)
        text = " | ".join(frames(app))
        assert "Failed to load m000.spc: disk went away" in text
    finally:
        app.close()


def test_a_scan_selects_the_first_row_and_plots_it(alex_dir, recorder):
    app = make_alex_app()
    try:
        assert app.model.current_file is None
        app.model.request("open_folder", alex_dir)
        settle_all(app)
        model = app.model
        first = str(alex_dir / "m000.spc")
        assert model.selected_files == [first] and str(model.current_file) == first
        assert table(app).selected_key == first  # the table shows the selection
        assert (
            model.trace["path"] == first
            and [int(v) for v in np.asarray(model.trace["counts"]).sum(axis=0)] == SUMS
        )
        assert len(recorder.last_frame_lines(app)) >= 4
        # an empty folder clears the selection and the plot
        empty = alex_dir.parent / "empty"
        empty.mkdir()
        model.request("open_folder", empty)
        settle_all(app)
        assert model.selected_files == [] and model.current_file is None and model.trace is None
        assert "No file is listed, so there is no trace to show." in " | ".join(
            frames(app)
        )  # folder open, no rows
        assert table(app).selected_key is None
    finally:
        app.close()


def test_a_filter_that_hides_the_shown_file_clears_the_plot(alex_dir):
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        edit_cell(app, "m001.spc", "rating", "3")
        commit(app, "rating_filter", "≥ 3★★★")  # only m001 passes; m000 was shown
        settle_all(app)
        assert app.model.current_file is None and app.model.trace is None  # as the Qt plot cleared
        assert [r["name"] for r in app.model.rows] == ["m001.spc"]
    finally:
        app.close()


# 6. precompute
def slow_down(model, seconds, monkeypatch):
    """Make every trace computation take *seconds* (so the job can be seen and stopped)."""
    real = model.compute_trace_cached

    def slow(path, window_ms=None):
        time.sleep(seconds)
        return real(path, window_ms)

    monkeypatch.setattr(model, "compute_trace_cached", slow)


@pytest.fixture
def many_dir(tmp_path):
    """Six copies of the sample: m0.spc .. m5.spc."""
    if not BH132.exists():
        pytest.skip("sample TTTR data missing")
    folder = tmp_path / "many"
    folder.mkdir()
    for i in range(6):
        shutil.copy(BH132, folder / f"m{i}.spc")
    return folder


def test_precompute_after_a_scan_reports_progress_and_caches_every_trace(many_dir, monkeypatch):
    app = make_alex_app(precompute=True)
    try:
        slow_down(app.model, 0.15, monkeypatch)
        app.model.request("open_folder", many_dir)
        seen = []
        deadline = time.time() + 60
        while time.time() < deadline:
            frames(app, n=1)
            seen.append(app.model.status_line)
            if idle(app) and app.model.precompute["message"]:
                break
            time.sleep(0.02)
        progress = [s for s in seen if "Precomputing traces" in s]
        assert progress, seen
        assert any("/" in s.split("Precomputing traces")[1] and ".spc" in s for s in progress)
        assert app.model.precompute["running"] is False
        assert app.model.precompute["message"].startswith("Precomputed ")
        assert app.model.status_line.endswith(app.model.precompute["message"])
        cached = list((many_dir / ".tttr_trace_cache").glob("*"))
        assert len(cached) >= 5  # the first row was loaded, the rest precomputed
        # the model did not wait for it: selecting a file shows its cached trace at once
        table(app)._select_position(4)
        settle_all(app)
        assert app.model.trace["path"] == str(many_dir / "m4.spc")
    finally:
        app.close()


def test_the_stop_button_cancels_the_precompute(many_dir, monkeypatch):
    app = make_alex_app(precompute=False)
    try:
        slow_down(app.model, 0.3, monkeypatch)
        open_and_show(app, many_dir)
        assert app.model.enabled("precompute_traces") and not app.model.enabled("stop_precompute")
        with pressing(monkeypatch, "Precompute"):
            frames(app, n=1)
        deadline = time.time() + 30
        while not app.model.precompute["running"] and time.time() < deadline:
            frames(app, n=1)
            time.sleep(0.02)
        while app.model.precompute["done"] < 1 and time.time() < deadline:
            frames(app, n=1)
            time.sleep(0.02)
        assert app.model.precompute["running"] and app.model.enabled("stop_precompute")
        assert "Precomputing traces" in " | ".join(frames(app))
        with pressing(monkeypatch, "Stop"):
            frames(app, n=1)
        while app.pre_job.busy and time.time() < deadline:
            frames(app, n=1)
            time.sleep(0.02)
        message = app.model.precompute["message"]
        assert (
            message.startswith("Precompute stopped after ") and not app.model.precompute["running"]
        )
        computed = int(message.split("after ")[1].split(" ")[0])
        assert 1 <= computed < 5  # stopped before the end (5 files to do)
        assert not app.model.enabled("stop_precompute")
    finally:
        app.close()


def test_a_new_scan_cancels_a_running_precompute(many_dir, monkeypatch):
    app = make_alex_app(precompute=True)
    try:
        slow_down(app.model, 0.3, monkeypatch)
        app.model.request("open_folder", many_dir)
        deadline = time.time() + 30
        while not app.model.precompute["running"] and time.time() < deadline:
            frames(app, n=1)
            time.sleep(0.02)
        assert app.model.precompute["running"]
        app.model.precompute_after_scan = False
        app.model.request("scan")  # a new scan: the running job is told to stop
        settle_all(app)
        assert app.model.precompute["message"].startswith("Precompute stopped after")
    finally:
        app.close()


def test_precompute_runs_without_blocking_edits(many_dir, monkeypatch):
    """The job copies a helper, not the model: a rating set while it runs is still there afterwards."""
    app = make_alex_app(precompute=False)
    try:
        slow_down(app.model, 0.2, monkeypatch)
        open_and_show(app, many_dir)
        app.model.precompute_traces()
        deadline = time.time() + 30
        while not app.model.precompute["running"] and time.time() < deadline:
            frames(app, n=1)
            time.sleep(0.02)
        edit_cell(app, "m3.spc", "rating", "2")
        edit_cell(app, "m3.spc", "notes", "while running")
        settle_all(app)
        assert app.model.get_rating(many_dir / "m3.spc") == 2
        assert {r["name"]: (r["rating"], r["notes"]) for r in app.model.rows}["m3.spc"] == (
            2,
            "while running",
        )
        saved = json.loads((many_dir / META).read_text())
        assert saved["m3.spc"] == {"rating": 2, "annotation": "while running"}
    finally:
        app.close()


def test_the_model_precompute_methods_run_headless(many_dir):
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.apply_setup(json.loads(json.dumps(ALEX)), "PTO")
    assert model.open_folder(many_dir)
    assert model.current_file == many_dir / "m0.spc"  # the scan selected the first row
    assert model.precompute_pending is True  # and asks for the precompute
    assert model.run_precompute() == 6 and model.precompute["message"] == "Precomputed 6 trace(s)."
    assert model.run_precompute() == 0 and "all cached" in model.precompute["message"]
    assert model.background_text == model.precompute["message"] and not model.precompute["running"]
    model.precompute["cancel"] = True
    model.clear_caches()
    model.stop_precompute()
    assert model.run_precompute() <= 1 and model.precompute["message"].startswith(
        "Precompute stopped"
    )


# 7. the page draws populated at both sizes; tooltips; Qt free; Qt agreement
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_the_page_draws_populated_with_the_trace(alex_dir, size):
    app = make_alex_app()
    try:
        text = " | ".join(frames(app, size))
        assert "Open a folder with TTTR files, then select a file" in text
        app.model.request("open_folder", alex_dir)
        text = " | ".join(settle_all(app, size))
        for label in (
            "m000.spc",
            "10 ms bins",
            f"{BINS_10MS} bins",
            "Time (s)",
            "Counts / 10 ms",
            "Counts (log)",
            "green",
            "red",
            "yellow",
            "Sum",
            "Annotation",
            "Precompute",
            "Stop",
            "Precompute after scan",
        ):
            assert label in text, label
        assert "Loading" not in text and "Failed" not in text
    finally:
        app.close()


def test_every_control_has_a_tooltip(alex_dir):
    from test.gui.emtk_port_parity import emtk_inventory

    app = make_alex_app()
    try:
        inv = emtk_inventory(app)
        assert inv["controls_without_tooltip"] == []
        app.model.request("open_folder", alex_dir)
        settle_all(app)
        inv = emtk_inventory(app)
        assert inv["controls_without_tooltip"] == []
        labels = {row["label"] for row in inv["interactive"]}
        assert {"Precompute", "Stop", "Precompute after scan"} <= labels
    finally:
        app.close()
    spec = json.loads(SPEC.read_text())
    walked = 0
    for section in all_sections(spec):
        if section.get("type") in (
            "value",
            "choice",
            "toggle",
            "table",
            "data_table",
            "custom",
            "button_row",
            "info",
        ):
            assert section.get("description"), section.get("attr") or section
            walked += 1
        for button in section.get("buttons", []):
            assert button.get("description"), button
    assert walked >= 11
    # the hand-drawn controls (the plot and the annotation box) carry a tooltip right after drawing
    source = (GUI / "app.py").read_text()
    assert (
        source.count("im.set_item_tooltip") >= 3
        and "implot.end_subplots()\n        im.set_item_tooltip" in source
    )
    assert '"##tb_annotation"' in source and 'self.item_rects["annotation"]' in source


def test_every_new_spec_key_exists_on_the_model():
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    spec = json.loads(SPEC.read_text())
    for section in all_sections(spec):
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
            assert model.enabled(button["action"]) in (True, False)
    assert model.enabled("precompute_traces") is False and model.enabled("stop_precompute") is False
    assert model.precompute_after_scan is True


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("trace_browser", ENTRY)
    assert result["ok"], result["output"]


def test_settings_round_trip_includes_the_precompute_toggle(alex_dir):
    app = make_alex_app()
    try:
        app.model.precompute_after_scan = False
        state = json.loads(json.dumps(app.export_settings()))
        assert state["precompute_after_scan"] is False
        other = make_alex_app(precompute=True)
        try:
            other.restore_settings(state)
            assert other.model.precompute_after_scan is False
        finally:
            other.close()
    finally:
        app.close()


def test_the_qt_widget_and_the_emtk_app_show_the_same_series(alex_dir, qapp, qtbot, monkeypatch):
    """Same file, same setup: the legacy Qt plot and the emtk trace area draw the same series and sums."""
    pytest.importorskip("pyqtgraph")
    from chisurf.plugins.tttr.trace_browser import TraceBrowser

    widget = TraceBrowser()
    qtbot.addWidget(widget)
    widget.detector_page._load_data(json.loads(json.dumps(ALEX)))
    widget._on_continue()
    monkeypatch.setattr(widget, "_precompute_all_traces", lambda *a, **k: None)
    widget._open_folder(alex_dir)
    widget._plot_file(alex_dir / "m000.spc")
    qt_series = {}
    for trace_plot, _ in widget.plot.plots:
        item = trace_plot.listDataItems()[0]
        qt_series[item.name()] = float(np.sum(item.yData))
    app = make_alex_app()
    try:
        open_and_show(app, alex_dir)
        emtk_series = {e["label"]: e["total"] for e in app._view.series}
        assert set(qt_series) == set(emtk_series) == set(LABELS) | {"Sum"}
        assert [qt_series[k] for k in LABELS] == [float(v) for v in SUMS]
        for label in qt_series:
            assert emtk_series[label] == pytest.approx(qt_series[label])
    finally:
        app.close()
