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
    for label in ("Process", "TTTR files", "Processing log", "Time window (ms)"):
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
    assert "Time window (ms)" in painter.strings


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


class _FakeClient:
    """A client that answers like the backend, or fails on request."""

    def __init__(self, fail_preview=False, fail_analyze=False):
        self.fail_preview, self.fail_analyze = fail_preview, fail_analyze
        self.analyzed = []

    def load_preview(self, path, window_ms):
        if self.fail_preview:
            raise OSError("preview broke")
        return {"counts": [1.0, 2.0, 3.0], "time_axis": [0.1, 0.2, 0.3]}

    def analyze_files(self, files, time_window_ms, output_dir=None):
        self.analyzed.append((list(files), time_window_ms, output_dir))
        if self.fail_analyze:
            raise OSError("analysis broke")
        return {"files": [str(f) for f in files], "n_windows": {str(files[0]): 3},
                "output_paths": {}, "metadata": {"output_dir": "/out", "total_windows": 3}}


def _settle(app, times=400):
    tool = app.tool
    for _ in range(times):
        if tool.job.future is not None:
            try:
                tool.job.future.result(timeout=60)
            except Exception:  # noqa: BLE001 - the error is the job's to publish
                pass
        _draw(app, times=1)
        if not tool.job.running and not tool.process_pending:
            return
    raise AssertionError("job did not finish")


# 9. a drop reaches the queue: the hook is on the app, the Qt window's drop accepted folders
def test_dropped_files_and_folders_are_queued(app, tmp_path):
    folder = tmp_path / "set"
    (folder / "sub").mkdir(parents=True)
    a, b = folder / "a.ptu", folder / "sub" / "b.ht3"
    a.write_bytes(b"x"); b.write_bytes(b"x")
    (folder / "notes.txt").write_text("no")
    for name in ("files_dropped", "on_files_dropped", "on_paths_dropped"):
        assert callable(getattr(app, name, None)), name
    app.tool._client = _FakeClient()
    assert app.files_dropped([str(folder)]) is True
    assert sorted(p.name for p in app.tool._file_paths) == ["a.ptu", "b.ht3"]
    assert app.files_dropped([str(a)]) is False                      # already queued
    assert app.files_dropped([str(folder / "notes.txt")]) is False
    assert "Nothing to queue" in app.tool.message
    assert len(app.tool._file_paths) == 2


# 10. the error paths: the status line says what failed, the log says why
def test_a_failing_process_is_reported_not_left_as_processing(tmp_path):
    app = create_app(client=_FakeClient(fail_analyze=True))
    try:
        tool = app.tool
        f = tmp_path / "a.ptu"
        f.write_bytes(b"x")
        tool.add_paths([f])
        _settle(app)
        tool._process_all()
        _settle(app)
        assert tool.message == "Processing failed"
        assert any("analysis broke" in line for line in tool._log_lines)
        assert tool._last_result is None
        painter = _draw(app)
        assert "Processing failed" in painter.strings
    finally:
        app.close()


def test_a_failing_preview_is_reported(tmp_path):
    app = create_app(client=_FakeClient(fail_preview=True))
    try:
        f = tmp_path / "a.ptu"
        f.write_bytes(b"x")
        app.tool.add_paths([f])
        _settle(app)
        assert app.tool.message == "Preview failed"
        assert any("preview broke" in line for line in app.tool._log_lines)
        assert app.tool.preview_data is None
    finally:
        app.close()


def test_process_without_files_says_so_and_a_good_run_logs_the_windows(tmp_path):
    client = _FakeClient()
    app = create_app(client=client)
    try:
        tool = app.tool
        tool._process_all()
        assert tool._log_lines[-1] == "No TTTR files to process. Add files first."
        assert client.analyzed == []
        f = tmp_path / "a.ptu"
        f.write_bytes(b"x")
        tool.add_paths([f])
        _settle(app)
        tool.time_window_ms = 25.0
        tool.output_dir_text = str(tmp_path / "out")
        tool._process_all()
        _settle(app)
        assert client.analyzed == [([f], 25.0, tmp_path / "out")]
        assert tool.message == "Processing complete" and tool.output_dir_text == "/out"
        assert any(l.startswith("Processing 1 file(s) with time window = 25.000 ms") for l in tool._log_lines)
        assert any("Done: 1 file(s), 3 total windows" in line for line in tool._log_lines)
    finally:
        app.close()


# 11. Remove and Clear
def test_remove_and_clear(tmp_path):
    app = create_app(client=_FakeClient())
    try:
        tool = app.tool
        a, b = tmp_path / "a.ptu", tmp_path / "b.ptu"
        a.write_bytes(b"x"); b.write_bytes(b"x")
        tool.add_paths([a, b])
        _settle(app)
        assert app.time_window_gui.preview_index == 0 and tool.preview_data is not None
        tool._remove_preview_file()
        _settle(app)
        assert tool._file_paths == [b] and app.time_window_gui.preview_index == 0
        tool._clear_all()
        assert tool._file_paths == [] and tool.preview_data is None and tool._log_lines == []
        assert tool.message == "Cleared"
        assert "No files queued." in _draw(app).strings
    finally:
        app.close()


# 12. the guide waits for the controls it names, and the tour hears them
def test_guide_waits_for_the_user(app):
    tour = app.time_window_gui.tour
    assert tour.wait_for_controls
    assert len(tour.steps) >= 3 and any(s.get("await") for s in tour.steps)
    _draw(app)
    for step in tour.steps:
        assert isinstance(step["target"], dict), step["title"]
        assert tour._target_key(step["target"]) in app.item_rects, step["title"]
    tour.start(0)
    assert tour.awaiting
    tour.notify_used("process")                                      # another control: still waiting
    assert tour.awaiting
    tour.notify_used("add_files")
    assert not tour.awaiting
    tour.next()
    app.time_window_gui.tool.time_window_ms = 10.0
    _draw(app)
    assert tour.awaiting and tour.steps[tour.step_idx]["target"] == {"action": "time_window"}
