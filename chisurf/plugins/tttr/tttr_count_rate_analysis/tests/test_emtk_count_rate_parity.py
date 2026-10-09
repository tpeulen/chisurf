"""The native count-rate app at parity with the Qt CountRateAnalyzer.

Reference numbers: the Qt tool as committed (HEAD tool.py + view_model.py,
``okf/plugins/emtk-ports/tttr_count_rate_analysis/scripts/capture_populated.py``)
on ``test/data/clsm/Leica_SP5.ptu`` with one channel ``all`` holding every used
routing channel printed ``mean_khz 44.72292671613037, std_khz 0.0,
photons 6714549, time_s 150.13661879999998``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.tttr.tttr_count_rate_analysis.gui import app as app_module
from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
PTU = REPO / "test" / "data" / "clsm" / "Leica_SP5.ptu"
QT_ROW = {
    "channel": "all",
    "mean_khz": 44.72292671613037,
    "std_khz": 0.0,
    "photons": 6714549,
    "time_s": 150.13661879999998,
}


def _draw(app, size=(1200, 800), times=3):
    painter = RecordingPainter()
    for _ in range(times):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def _channels():
    tttrlib = pytest.importorskip("tttrlib")
    if not PTU.exists():
        pytest.skip("sample PTU not available")
    routing = [int(c) for c in tttrlib.TTTR(str(PTU)).get_used_routing_channels()]
    return {"all": [{"detector_chs": routing, "micro_time_range": None, "window_range": None}]}


def _wait(tool):
    tool.job.future.result(timeout=120)
    tool.job.poll()


# 1. the Calculate path gives the Qt tool's numbers
def test_calculate_gives_the_qt_tools_row(monkeypatch):
    channels = _channels()
    app = create_app()
    try:
        monkeypatch.setattr(app.tool, "channels", lambda: channels)
        app.tool.add_paths([PTU])
        assert app.tool.calculate()
        _wait(app.tool)
        rows = app.tool._model.results_rows()
        assert len(rows) == 1
        assert rows[0]["channel"] == QT_ROW["channel"]
        assert rows[0]["photons"] == QT_ROW["photons"]
        assert rows[0]["mean_khz"] == pytest.approx(QT_ROW["mean_khz"], rel=1e-9)
        assert rows[0]["time_s"] == pytest.approx(QT_ROW["time_s"], rel=1e-9)
        painter = _draw(app)
        for text in ("44.72", "6714549", "150.137"):  # the Qt cells' formats
            assert text in painter.strings
    finally:
        app.close()


# 2. Remove takes the selected file off the queue and refreshes, as the Qt list did
def test_remove_selected_file(tmp_path):
    app = create_app()
    try:
        a, b = tmp_path / "a.ptu", tmp_path / "b.ptu"
        a.write_bytes(b"x")
        b.write_bytes(b"x")
        app.tool.add_paths([a, b])
        gui = app.count_rate_gui
        events = []
        app.tool._model.add_observer(events.append)
        painter = _draw(app)
        assert "Remove" in painter.strings
        gui.selected_file = str(a)
        gui.remove_file(gui.selected_file)
        assert app.tool._model.files == [str(b)]
        assert gui.selected_file is None and "files" in events
        gui.remove_file("/not/queued.ptu")  # nothing happens
        assert app.tool._model.files == [str(b)]
    finally:
        app.close()


def test_calculate_is_a_plain_button():
    """Default style: the button carries no data, so no colour of its own."""
    source = Path(app_module.__file__).read_text(encoding="utf-8")
    assert "push_style_color" not in source


# 3. the results table is the spec's data_table with the Qt columns
def test_results_table_is_declared_with_the_qt_columns():
    section = app_module.RESULTS_TABLE["sections"][0]
    assert section["key"] == "data_table" and section["description"]
    titles = [c["title"] for c in section["options"]["columns"]]
    assert titles == ["Channel", "Mean (kHz)", "Std (kHz)", "#Photons", "Time (s)"]
    assert all(c.get("description") for c in section["options"]["columns"])


# 4. draws, empty and populated, both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(monkeypatch, size):
    channels = _channels()
    app = create_app()
    try:
        painter = _draw(app, size)
        assert "No files queued." in painter.strings
        monkeypatch.setattr(app.tool, "channels", lambda: channels)
        app.tool.add_paths([PTU])
        assert app.tool.calculate()
        _wait(app.tool)
        painter = _draw(app, size)
        assert "Leica_SP5.ptu" in painter.strings and "#Photons" in painter.strings
    finally:
        app.close()


# 6. no Qt
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("tttr_count_rate_analysis")
    assert result["ok"], result["output"]


# 7. tooltips, with every channel-editor section folded and unfolded
def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("tttr_count_rate_analysis")
    for opened in (False, True):
        app.tool.channel_editor.open_sections = dict.fromkeys(
            app.tool.channel_editor.open_sections, opened
        )
        inv = emtk_inventory(app)
        assert inv["controls_without_tooltip"] == [], (opened, inv["controls_without_tooltip"])


# 8. persistence
def test_settings_round_trip(tmp_path):
    a = tmp_path / "a.ptu"
    a.write_bytes(b"x")
    app = create_app()
    try:
        app.tool.add_paths([a])
        saved = json.loads(json.dumps(app.export_settings()))
        other = create_app()
        try:
            other.restore_settings(saved)
            assert other.tool._model.files == [str(a)]
        finally:
            other.close()
    finally:
        app.close()


# 9. a drop reaches the model: the host hook is on the app (it sat on the controller's tool)
def test_dropped_files_and_folders_are_queued(tmp_path):
    app = create_app()
    try:
        folder = tmp_path / "set"
        (folder / "sub").mkdir(parents=True)
        a, b = folder / "a.ptu", folder / "sub" / "b.ht3"
        a.write_bytes(b"x")
        b.write_bytes(b"x")
        (folder / "notes.txt").write_text("no")
        assert callable(getattr(app, "files_dropped", None))  # what the native/web hosts call
        assert callable(getattr(app, "on_files_dropped", None))  # what the Qt host prefers
        assert app.files_dropped([str(folder)]) is True  # a folder is expanded
        assert sorted(Path(f).name for f in app.tool._model.files) == ["a.ptu", "b.ht3"]
        assert app.files_dropped([str(folder / "notes.txt")]) is False  # nothing queued
        assert "supported" in app.tool.message
        assert len(app.tool._model.files) == 2
    finally:
        app.close()


# 10. the error paths of Calculate and Save, shown on the status line
def test_calculate_and_save_errors_reach_the_status_line(tmp_path):
    app = create_app()
    try:
        tool = app.tool
        assert tool.calculate() is False
        assert tool.message == "Please load TTTR files first."
        a = tmp_path / "a.ptu"
        a.write_bytes(b"x")
        tool.add_paths([a])
        tool.channel_editor.model.get_settings = lambda: {}  # no detector in the setup
        tool.message = ""
        assert tool.calculate() is False
        assert "detector setup" in tool.message
        tool.message = ""
        tool.save_dialog()  # nothing computed yet
        assert tool.message == "There is no data to save." and tool.dialog is None
        painter = _draw(app)
        assert "There is no data to save." in painter.strings
    finally:
        app.close()


# 11. a failing read is reported, not swallowed; Save writes the Qt tool's table
def test_failing_read_is_reported_and_save_writes_the_table(tmp_path):
    channels = {"all": [{"detector_chs": [0], "micro_time_range": None, "window_range": None}]}

    def broken(path):
        raise OSError("cannot read " + str(path))

    app = create_app(reader=broken)
    try:
        a = tmp_path / "a.ptu"
        a.write_bytes(b"x")
        app.tool.channels = lambda: channels
        app.tool._model.channels_provider = app.tool.channels
        app.tool.add_paths([a])
        assert app.tool.calculate()
        with pytest.raises(OSError):
            app.tool.job.future.result(timeout=30)
        app.tool.job.poll()
        assert "cannot read" in app.tool.message
        assert app.tool._model.results_rows() == []
    finally:
        app.close()
    # the table text the Qt tool wrote, for the model both tools share
    from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.view_model import CountRateViewModel

    model = CountRateViewModel()
    model.files = ["f.ptu"]
    model._per_file = {"f.ptu": {"all": 44722.9}}
    model._per_file_photons = {"f.ptu": {"all": 6714549}}
    model._meas_times = {"f.ptu": 150.1366}
    model._channel_order = ["all"]
    out = tmp_path / "t.txt"
    app = create_app()
    try:
        app.tool._model = model
        assert app.tool.save(out)
        app.tool.job.future.result(timeout=30)
        app.tool.job.poll()
        lines = out.read_text().splitlines()
        assert lines[0].split("\t")[0] == "Channel"
        assert lines[1] == "all\t44.72\t0.00\t6714549\t150.137"
        assert str(out) in app.tool.message
    finally:
        app.close()


# 12. the guide waits for the buttons it names, and the tour is wired to hear them
def test_guide_waits_for_the_user():
    app = create_app()
    try:
        tour = app.count_rate_gui.tour
        assert tour.wait_for_controls
        steps = tour.steps
        assert len(steps) >= 3 and any(s.get("await") for s in steps)
        for step in steps:
            assert isinstance(step["target"], dict), step["title"]
        _draw(app)
        for step in steps:  # the targets are drawn controls
            key = tour._target_key(step["target"])
            if key != "results":  # the table exists after Calculate
                assert key in app.item_rects, key
        tour.start(0)
        assert tour.awaiting
        app.count_rate_gui.on_add_files = lambda: None
        tour.notify_used("calculate")  # another control: still waiting
        assert tour.awaiting
        tour.notify_used("add_files")
        assert not tour.awaiting
    finally:
        app.close()
