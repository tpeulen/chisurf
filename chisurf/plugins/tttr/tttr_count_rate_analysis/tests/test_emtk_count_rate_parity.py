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
QT_ROW = {"channel": "all", "mean_khz": 44.72292671613037, "std_khz": 0.0,
          "photons": 6714549, "time_s": 150.13661879999998}


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
        for text in ("44.72", "6714549", "150.137"):              # the Qt cells' formats
            assert text in painter.strings
    finally:
        app.close()


# 2. Remove takes the selected file off the queue and refreshes, as the Qt list did
def test_remove_selected_file(tmp_path):
    app = create_app()
    try:
        a, b = tmp_path / "a.ptu", tmp_path / "b.ptu"
        a.write_bytes(b"x"); b.write_bytes(b"x")
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
        gui.remove_file("/not/queued.ptu")                       # nothing happens
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


# 7. tooltips, over every channel-editor section
def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("tttr_count_rate_analysis")
    for section in range(6):
        app.tool.channel_editor.section = section
        inv = emtk_inventory(app)
        assert inv["controls_without_tooltip"] == [], (section, inv["controls_without_tooltip"])


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
