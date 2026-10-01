"""The native time-window app at parity with the Qt TTTRTimeWindowTool.

Reference: the Qt tool as committed (HEAD ``gui/tool.py``,
``okf/plugins/emtk-ports/tttr_time_windows/scripts/capture_populated.py``) processed
``test/data/clsm/Leica_SP5.ptu`` with a 10 000 ms window into 16 windows and wrote
``Leica_SP5.bst``, 246 bytes, sha256 prefix ``4e4d0add2e46ce4f``.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.tttr.tttr_time_windows.gui.controller import create_app

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
PTU = REPO / "test" / "data" / "clsm" / "Leica_SP5.ptu"
QT_BST_SHA256_PREFIX = "4e4d0add2e46ce4f"
PICTOGRAM = re.compile("[\U0001F000-\U0001FFFF☀-➿️]")


def _draw(app, size=(1200, 800), times=3):
    painter = RecordingPainter()
    for _ in range(times):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


@pytest.fixture
def app():
    app = create_app()
    yield app
    app.close()


# 1. processing writes the Qt tool's file, byte for byte
def test_process_writes_the_qt_tools_bst(app, tmp_path):
    pytest.importorskip("tttrlib")
    if not PTU.exists():
        pytest.skip("sample PTU not available")
    tool = app.tool
    tool.add_paths([PTU])
    tool.time_window_ms = 10000.0
    tool.output_dir_text = str(tmp_path)
    tool._process_all()                 # pressed while the preview of the added file loads
    assert tool.process_pending or tool._job_kind == "process"
    for _ in range(600):                # frames, as the app runs them
        if tool.job.future is not None:
            tool.job.future.result(timeout=300)
        _draw(app, times=1)
        if not tool.job.running and not tool.process_pending:
            break
    written = sorted(tmp_path.rglob("*.bst"))
    assert [w.name for w in written] == ["Leica_SP5.bst"], written
    out = written[0]
    assert out.stat().st_size == 246
    assert hashlib.sha256(out.read_bytes()).hexdigest().startswith(QT_BST_SHA256_PREFIX)
    assert any("16 windows" in line for line in tool._log_lines)


# 2. a status message is a line in the window, not a window over it
def test_a_status_message_does_not_cover_the_tool(app):
    app.tool.notify("Processing complete")
    painter = _draw(app)
    assert "Processing complete" in painter.strings
    for label in ("Process", "TTTR files", "Processing log", "Time window (ms):"):
        assert label in painter.strings, label


def test_the_job_and_file_windows_are_sized(app):
    app.tool._add_files_dialog()
    _draw(app)
    x, y, w, h = app._file_window.box
    assert w < 1200 and h < 800                 # not the whole viewport
    app.tool.dialog = None


# 3/4. labels, both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_labels_have_no_pictograms_and_draw_at_both_sizes(app, size):
    painter = _draw(app, size)
    assert [s for s in painter.strings if PICTOGRAM.search(s)] == []
    assert "Time window (ms):" in painter.strings


def test_process_is_a_plain_button():
    source = (HERE.parent / "gui" / "app.py").read_text(encoding="utf-8")
    assert "push_style_color" not in source


# 6. no Qt
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("tttr_time_windows")
    assert result["ok"], result["output"]


# 7. tooltips
def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inv = emtk_inventory(build_emtk_app("tttr_time_windows"))
    assert inv["controls_without_tooltip"] == []


# 8. persistence: the dock layout (the Qt tool's QSettings "dock_layout"), only when changed
def test_dock_layout_is_kept_only_when_changed(tmp_path, monkeypatch):
    import chisurf.core.settings as settings

    monkeypatch.setattr(settings, "chisurf_settings_path", tmp_path, raising=False)
    target = tmp_path / "tttr_time_windows_layout.json"
    app = create_app()
    _draw(app)
    app.close()
    assert not target.exists()                       # opened and closed: nothing written
    app = create_app()
    _draw(app)
    docks = app.time_window_gui.docks
    docks.focus("summary")
    monkeypatch.setattr(docks, "state", lambda: {"changed": True})
    saved = []
    monkeypatch.setattr(docks, "save", lambda: saved.append(1) or True)
    app.close()
    assert saved == [1]


def test_window_boundaries_are_drawn_only_when_they_can_be_told_apart(app, monkeypatch):
    """15 014 boundaries (10 ms over 150 s) filled the preview and hid the trace (Qt and emtk)."""
    import numpy as np
    from emtk import implot

    from chisurf.plugins.tttr.tttr_time_windows.gui import app as app_module

    drawn = []
    original = implot.plot_inf_lines
    monkeypatch.setattr(implot, "plot_inf_lines", lambda name, values, **k: (drawn.append(len(values)), original(name, values, **k)))
    t = np.linspace(0.0, 150.0, 15014)
    gui = app.time_window_gui
    gui.preview = {"counts": np.ones_like(t), "time_axis": t, "time_window_ms": 10.0}
    _draw(app)
    assert drawn == []
    gui.preview = {"counts": np.ones_like(t), "time_axis": t, "time_window_ms": 10000.0}
    _draw(app)
    assert drawn and max(drawn) == 15 and max(drawn) <= app_module.MAX_BOUNDARY_LINES
