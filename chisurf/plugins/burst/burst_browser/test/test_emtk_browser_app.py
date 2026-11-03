"""The native Burst Browser: loading, gating, the Input section, drawing, tooltips.

Rows, gated rows and the E histogram are checked against the burst tables the demo folder
writes (``demo_folder.build``): read back here, gated and binned with numpy.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
from emtk.testing import RecordingPainter  # noqa: E402

from chisurf.core.datastore import row_count  # noqa: E402
from chisurf.plugins.burst.burst_browser.gui.app import create_app  # noqa: E402
from chisurf.plugins.burst.burst_browser.test.demo_folder import build  # noqa: E402
from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory, qt_free  # noqa: E402

GATES = {"e_min": 0.5, "e_max": 0.9, "s_min": 0.3, "s_max": 0.7}


@pytest.fixture
def root(tmp_path):
    return build(tmp_path / "measurement")


def _draw(app, size=(1200, 800), n=2):
    painter = RecordingPainter()
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def _frames_until(app, done, timeout=30.0):
    """Draw frames -- as the host would on request -- until *done*; no manual poll."""
    end = time.monotonic() + timeout
    while not done():
        assert time.monotonic() < end, "not reached by drawing frames"
        time.sleep(0.02)
        _draw(app, n=1)


def _loaded(app, root):
    app.load_folder(root)
    _frames_until(app, lambda: app.table is not None and not app.controller.running)


def _shown(model):
    model.hist_column = "E"
    h = model.histogram()
    return {
        "rows": row_count(model.table),
        "masked": len(model.masked_row_indices()),
        "counts": [int(c) for c in h["counts"]],
        "status": model.status_text(),
    }


def _written(root):
    """E and S of every burst in the demo tables (the zero rows interleave the bursts)."""
    tables = [
        np.loadtxt(path, skiprows=1, delimiter="\t", ndmin=2)
        for path in sorted((root / "bi4_bur").glob("*.bur"))
    ]
    rows = np.vstack(tables)
    rows = rows[rows[:, 3] > 0]  # Number of Photons
    return rows[:, 6], rows[:, 7]


def _expected(e, status_selected, total):
    counts, _edges = np.histogram(e, bins=60)
    return {
        "rows": total,
        "masked": int(e.size),
        "counts": [int(c) for c in counts],
        "status": f"Bursts: {status_selected} / {total} selected",
    }


# 1. the tables as written, ungated and gated on the high-FRET population
def test_loading_and_gating_show_the_written_bursts(root):
    e, s = _written(root)
    app = create_app()
    try:
        _loaded(app, root)
        assert _shown(app.model) == _expected(e, e.size, e.size)
        for key, value in GATES.items():
            setattr(app.model, key, value)
        app.model.refresh()
        inside = (
            (e >= GATES["e_min"]) & (e <= GATES["e_max"]) & (s >= GATES["s_min"]) & (s <= GATES["s_max"])
        )
        assert int(inside.sum()) == 120  # the high-FRET population: 2 of 5 of 300
        assert _shown(app.model) == _expected(e[inside], 120, e.size)
        strings = _draw(app).strings
        assert (
            "Bursts: 120 / 300 selected" in strings and "Bursts: 300 / 300 selected" not in strings
        )
        assert all(hasattr(app, name) for name in ("table", "load_folder", "load_bur"))
    finally:
        app.close()


# 5. end to end: the Input section, a hand-off and the workflow call load by drawing frames alone
def test_a_burst_run_picked_in_the_input_section_loads(tmp_path, monkeypatch):
    """The tour's first step waits for a pick in the Input section; the pick loads the run."""
    from test.gui.burst_workspace import (
        burst_run_in_workspace,
        no_input_dialog,
        pick_row,
        restore_workspace,
    )

    with restore_workspace():
        run = burst_run_in_workspace(tmp_path)
        no_input_dialog(monkeypatch)
        app = create_app()
        try:
            _draw(app)
            app.start_guide()
            assert app.browser_gui.tour.awaiting  # step 1 waits for the Input section
            pick_row(app, "runBursts#1")
            assert not app.browser_gui.tour.awaiting  # the pick released it
            _frames_until(app, lambda: app.table is not None and not app.controller.running)
            assert row_count(app.table) > 0 and app.model.path_text.endswith("runBursts#1")
            assert str(run.address).endswith("runBursts#1")
        finally:
            app.close()


def test_a_hand_off_and_the_workflow_call_load(root):
    from chisurf.plugins.burst.burst_browser.gui.app import receive_bursts

    app = create_app()
    try:
        assert not hasattr(app, "on_paths_dropped") and not hasattr(app, "files_dropped")
        receive_bursts(app, {"folder": str(root), "datasets": ["uid"]})
        _frames_until(app, lambda: app.table is not None and not app.controller.running)
        assert row_count(app.table) == 300
    finally:
        app.close()
    app = create_app()
    try:
        app.load_bur(root / "bi4_bur" / "m001.bur")
        _frames_until(app, lambda: app.table is not None and not app.controller.running)
        assert row_count(app.table) == 150
    finally:
        app.close()


def test_frames_are_requested_while_a_read_runs(root, monkeypatch):
    import threading

    from chisurf.plugins.burst.burst_browser import view_model

    gate = threading.Event()
    original = view_model.BurstBrowserViewModel.load_folder
    monkeypatch.setattr(
        view_model.BurstBrowserViewModel,
        "load_folder",
        lambda self, folder, cancel_check=None: (
            gate.wait(10),
            original(self, folder, cancel_check),
        )[1],
    )
    app = create_app()
    try:
        app.load_folder(root)
        _draw(app, n=1)
        assert app.controller.running and app.next_frame_in() is not None
        gate.set()
        _frames_until(app, lambda: app.table is not None)
    finally:
        gate.set()
        app.close()


# 2. the dialogs per action, exports, clear, stop
def test_each_action_opens_its_own_dialog():
    app = create_app()
    try:
        expected = {  # only exports: the bursts come from the workspace
            "export_gate": ("Export gated bursts", "save"),
            "export_selected": ("Export selected bursts", "save"),
        }
        for action, (title, mode) in expected.items():
            app.controller.browse(action)
            assert (app.controller.dialog.title, app.controller.dialog.mode) == (title, mode), (
                action
            )
        assert set(app.controller.DIALOGS) == {"export_gate", "export_selected"}
    finally:
        app.close()


def test_exports_write_the_gated_and_the_selected_bursts(root, tmp_path):
    import csv

    app = create_app()
    try:
        _loaded(app, root)
        for key, value in GATES.items():
            setattr(app.model, key, value)
        app.model.refresh()
        gated = tmp_path / "gated.csv"
        app.controller.export(gated)
        with gated.open() as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        assert len(rows) == 120 and all(0.5 <= float(r["E"]) <= 0.9 for r in rows)
        masked = list(app.model.masked_row_indices())
        app.model.selected_indices = [
            masked[0],
            masked[1],
            0,
        ]  # row 0 is low FRET: outside the gate
        picked = tmp_path / "picked.csv"
        app.controller.export(picked, selected=True)
        with picked.open() as fh:
            assert len(list(csv.DictReader(fh, delimiter="\t"))) == 2
        assert app.controller.status == f"Exported 2 bursts: {picked}"
    finally:
        app.close()


def test_errors_reach_the_window(tmp_path):
    app = create_app()
    try:
        app.load_folder(tmp_path / "nowhere")
        assert app.controller.status.startswith("Input does not exist")
        empty = tmp_path / "empty"
        empty.mkdir()
        app.load_folder(empty)
        _frames_until(app, lambda: not app.controller.running)
        assert app.controller.status.startswith("Error:")
        assert any(s.startswith("Error:") for s in _draw(app).strings)
        with pytest.raises(ValueError):
            app.controller.export(tmp_path / "x.csv")
    finally:
        app.close()


# 3. every guide target is drawn
def test_every_guide_target_is_drawn(root):
    app = create_app()
    try:
        _loaded(app, root)
        _draw(app)
        keys = {
            app.browser_gui.tour._target_key(s.get("target")) for s in app.browser_gui.tour.steps
        } - {""}
        assert keys and keys <= set(app.item_rects), keys - set(app.item_rects)
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes; headers fit their columns
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(root, size):
    """Empty and loaded views retain readable headers at normal and narrow sizes."""
    from chisurf.core.datastore import column_names

    app = create_app()
    try:
        strings = _draw(app, size).strings
        assert "No bursts loaded. Open a .bur folder or file." in strings
        _loaded(app, root)
        app.model.hist_column = "E"
        app.model.refresh()
        painter = _draw(app, size)
        strings = painter.strings
        assert "Page 1 / 6 (300 bursts)" in strings and "Bursts: 300 / 300 selected" in strings
        table = app.browser_gui._burst_table.control
        assert [column.key for column in table.columns] == column_names(app.model.table)
        assert len(table._widths) == len(table.columns)
        assert all(
            width > painter.text_width(column.title)
            for column, width in zip(table.columns, table._widths)
        )
    finally:
        app.close()


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    result = qt_free("burst_browser")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    app = build_emtk_app("burst_browser")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
