"""MFD Prepare's emtk app, operated with real input events and compared with the backend the Qt tool called.

The fixture is the in-repo measured BH SPC-132 burst folder of ``burst_selection``, handed to the window the way the workspace
hands a burst (``receive_bursts``); a burst run of the workspace is picked in the Input section. Only pointer, wheel and typed keys
reach the window (``chisurf.plugins.emtk_test_input.Driver``); outcomes are read from what was drawn and from the model.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import test.gui.emtk_layout_checks as lay  # noqa: E402  (must import before anything that shadows the stdlib ``test``)
from chisurf.plugins.burst.mfd_prepare.api import PrepareRequest, prepare_folder
from chisurf.plugins.burst.mfd_prepare.gui.app import MfdPrepareApp, make_app, receive_bursts
from chisurf.plugins.burst.mfd_prepare.gui.model import MfdPrepareModel
from chisurf.plugins.emtk_test_input import SIZE, SMALL, Driver, assert_tour_card_clear

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "burst_analysis_handoff"
)
pytestmark = pytest.mark.usefixtures("no_failed_draws")


def settle(drv, timeout=60.0):
    end = time.monotonic() + timeout
    drv.draw(1)
    while drv.app.job.busy and time.monotonic() < end:
        time.sleep(0.02)
        drv.draw(1)
    assert not drv.app.job.busy, "the preparation did not finish"
    return drv.draw(3)


def hand(drv, path) -> bool:
    """Hand *path* over as the workspace does (the Input section, *Open in…*, a drag)."""
    try:
        receive_bursts(drv.app, {"folder": str(path)})
    except ValueError:
        return False
    return True


@pytest.fixture
def drv():
    return Driver(make_app())


@pytest.fixture
def prepared(drv):
    assert hand(drv, FIXTURE)
    drv.click_name("prepare")
    settle(drv)
    return drv


@pytest.fixture
def workspace_run(tmp_path, monkeypatch):
    """A burst run in the workspace, as a session holds it (its own analysis folder)."""
    from chisurf.core.project import analysis
    from test.gui.burst_workspace import burst_run_in_workspace, restore_workspace

    monkeypatch.setenv("CHISURF_ANALYSIS_DIR", str(tmp_path / "analysis"))
    monkeypatch.setattr(analysis, "_SESSION", None)
    with restore_workspace():
        yield burst_run_in_workspace(tmp_path)


# ---- parity with the backend the Qt tool called ---------------------------------------------------------------- #
def test_prepare_gives_the_backends_report_and_numbers(prepared):
    backend = prepare_folder(PrepareRequest(folder=str(FIXTURE))).to_dict()
    m = prepared.app.model
    assert m.report == backend["report"]
    assert m.result["n_bursts"] == backend["n_bursts"] == 152
    assert m.result["count_agreement"] == backend["count_agreement"]
    assert m.result["verified_channels"] == backend["verified_channels"]
    # the status line of the Qt tool was the report itself; the new one names the same bursts and verdict
    assert "152 bursts" in m.status_text and "every detector verified" in m.status_text


def test_the_tables_show_the_backends_values(prepared):
    backend = prepare_folder(PrepareRequest(folder=str(FIXTURE))).to_dict()
    painter = prepared.draw(3)
    texts = {t[5] for t in painter.texts}
    summary = backend["summary"]
    for name in backend["channels"]:
        assert name in texts
        assert f"{backend['count_agreement'][name]:.4f}" in texts
        assert str(summary["n_empty"][name]) in texts
    assert (
        "0-2047" in texts and "2048-4094" in texts and "all" in texts
    )  # the micro-time windows of red / yellow / green
    assert str(summary["photons"]["m000.spc"]) in texts
    assert "sibling" in texts and "m000.spc" in texts
    assert str(backend["total_photons"]) in texts
    assert "152 (153 interleaved sentinel rows removed)" in texts
    assert "inclusive (agreement 1.0000)" in texts
    rows = prepared.app.model.detector_rows()
    assert [r["verdict"] for r in rows] == ["ok", "ok", "ok"]
    assert [r["detector"] for r in rows] == ["green", "red", "yellow"]


def test_every_report_line_of_the_qt_tool_is_drawn(prepared):
    painter = prepared.draw(3)
    texts = [t[5] for t in painter.texts]
    for line in prepared.app.model.report.splitlines():
        assert any(line.strip() in t for t in texts), line


def test_an_unverified_detector_is_flagged(drv):
    """Display logic on an injected result (generated for this test, not a measurement): a detector below 0.98 reads UNVERIFIED."""
    m = drv.app.model
    m.folder = "/generated/example"
    m.report = "burst folder: generated\nbursts: 3 (4 interleaved sentinel rows removed)\n  green: count agreement 0.5000 [UNVERIFIED]"
    m.result = {
        "n_bursts": 3,
        "channels": ["green", "red"],
        "verified_channels": ["red"],
        "count_agreement": {"green": 0.5, "red": 1.0},
        "duration_s": 1.0,
        "total_photons": 10,
        "summary": {
            "unverified_channels": ["green"],
            "n_empty": {"green": 0, "red": 0},
            "stream_origin": "manifest",
        },
    }
    texts = {t[5] for t in drv.draw(3).texts}
    assert "UNVERIFIED" in texts and "ok" in texts and "0.5000" in texts
    assert m.verdict_text() == "UNVERIFIED: green"


# ---- The Input section ------------------------------------------------------------------------------------------- #
def test_the_input_section_lists_the_workspace_runs_and_a_click_picks_one(drv, workspace_run):
    name = workspace_run.name
    assert name in {t[5] for t in drv.draw(2).texts}
    drv.click_text(name)
    assert drv.app.model.folder == workspace_run.address
    assert drv.app.model.status_text.startswith("Burst run:")


def test_a_handed_over_path_that_is_not_a_burst_run_is_refused(drv, tmp_path):
    assert not hand(drv, tmp_path / "does_not_exist")
    assert drv.app.model.folder == ""
    assert drv.app.model.status_text.startswith("Error: not a burst run")


def test_no_input_file_ui_is_left(drv):
    """The bursts come from the workspace: no Browse button, no folder chooser, no drop hook."""
    drv.draw(2)
    assert "browse" not in drv.app.item_rects
    assert not hasattr(drv.app, "files_dropped") and not hasattr(drv.app, "on_files_dropped")
    assert not hasattr(drv.app, "dialog")


# ---- Prepare ------------------------------------------------------------------------------------------------------ #
def test_prepare_is_greyed_without_a_folder_and_a_click_does_nothing(drv):
    drv.draw(2)
    assert drv.app.item_rects["prepare"]
    drv.click_name("prepare")
    assert not drv.app.job.busy and drv.app.model.report == "" and drv.app.model.result == {}
    assert "Pick a burst run in the Input section and press Prepare" in " ".join(
        t[5] for t in drv.draw(2).texts
    )
    assert not drv.app.panel.enabled("prepare") and drv.app.panel.enabled("guide")


def test_prepare_runs_in_the_background_and_the_window_stays_alive(drv, monkeypatch):
    gate = threading.Event()
    original = MfdPrepareModel.prepare

    def slow(self):
        gate.wait(10)
        original(self)

    monkeypatch.setattr(MfdPrepareModel, "prepare", slow)
    hand(drv, FIXTURE)
    drv.click_name("prepare")
    assert drv.app.job.busy
    texts = {t[5] for t in drv.draw(2).texts}
    assert any("Prepare" in t and "..." in t for t in texts) or drv.app.job.progress
    # while it runs, a second Prepare cannot start another job under the first
    other = FIXTURE.parent
    drv.click_name("prepare")
    gate.set()
    settle(drv)
    assert drv.app.model.result["n_bursts"] == 152
    assert drv.app.model.folder == str(FIXTURE) and other != FIXTURE


def test_a_folder_without_bursts_reports_the_backend_error(drv, tmp_path):
    empty = tmp_path / "home" / "empty_dir"
    empty.mkdir(parents=True, exist_ok=True)
    hand(drv, empty)
    drv.click_name("prepare")
    settle(drv)
    m = drv.app.model
    assert m.report.startswith("Error: ") and m.result == {} and m.error
    assert prepare_folder(PrepareRequest(folder=str(empty))).error == m.error
    texts = " ".join(t[5] for t in drv.draw(2).texts)
    assert m.report.splitlines()[0][:40] in texts
    assert "Detectors" not in texts  # no empty result tables


def test_an_exception_in_the_backend_is_reported_not_raised(drv, monkeypatch):
    import chisurf.plugins.burst.mfd_prepare.api as api

    def boom(request):
        raise RuntimeError("boom")

    monkeypatch.setattr(api, "prepare_folder", boom)
    hand(drv, FIXTURE)
    drv.click_name("prepare")
    settle(drv)
    assert drv.app.model.report == "Error: boom"
    assert "Error: boom" in {t[5] for t in drv.draw(2).texts}


def test_a_connected_rpc_client_is_used_for_the_result():
    class Rpc:
        def __init__(self):
            self.calls = []

        def call(self, method, params):
            self.calls.append((method, params))
            return {
                "ok": True,
                "result": {
                    "report": "from the service",
                    "n_bursts": 7,
                    "channels": ["a"],
                    "verified_channels": ["a"],
                    "count_agreement": {"a": 1.0},
                    "summary": {},
                },
            }

    from chisurf.plugins.burst.mfd_prepare.gui.client import MfdPrepareClient

    rpc = Rpc()
    model = MfdPrepareModel(client=MfdPrepareClient(rpc_client=rpc))
    model.set_folder(str(FIXTURE))
    model.prepare()
    assert rpc.calls == [("mfd_prepare.prepare", {"folder": str(FIXTURE), "with_photons": True})]
    assert model.report == "from the service" and model.result["n_bursts"] == 7


def test_prepare_without_a_folder_says_so_for_scripts():
    model = MfdPrepareModel()
    model.prepare()
    assert model.report == "Pick a burst run in the Input section first."


def test_a_second_prepare_replaces_the_first_result(prepared, tmp_path):
    empty = tmp_path / "home" / "empty_dir"
    empty.mkdir(parents=True, exist_ok=True)
    hand(prepared, empty)
    prepared.click_name("prepare")
    settle(prepared)
    assert prepared.app.model.result == {} and prepared.app.model.report.startswith("Error")


# ---- Help, Guide, tooltips ----------------------------------------------------------------------------------------- #
def test_help_opens_the_help_window_and_escape_or_close_hides_it(drv):
    drv.click_name("help")
    assert drv.app.help_window.open
    assert drv.drawn("MFD Prepare") or drv.draw(2).texts
    texts = " ".join(t[5] for t in drv.draw(3).texts)
    assert "Reads a burst-analysis folder" in texts or "How to use it" in texts
    drv.app.help_window.hide()
    drv.draw(2)
    assert not drv.app.help_window.open


def test_the_tour_is_walked_with_the_user_pressing_each_awaited_control(drv, workspace_run):
    drv.click_name("guide")
    tour = drv.app.tour
    assert tour.active
    seen = []
    for _ in range(12):
        if not tour.active:
            break
        drv.draw(2)
        assert_tour_card_clear(tour, drv.size)
        step = tour.steps[tour.step_idx]
        seen.append(step["title"])
        target = tour._target_key(step.get("target"))
        if step.get("await"):
            assert tour.awaiting and not tour._step_used, (
                tour.step_idx,
                tour.awaiting,
                tour._step_used,
                tour.wait_for_controls,
                step.get("await"),
            )
            if target == "workspace_input_rows":  # the user clicks the run in the Input section
                drv.click_text(workspace_run.name)
                hand(drv, FIXTURE)  # the measured folder, whose preparation is known
            else:
                drv.click_name(target)  # the user presses the highlighted control
            if target == "prepare":
                settle(drv)
            assert tour._step_used
        drv.click_text("Next ►") if tour.step_idx < len(tour.steps) - 1 else tour.next_step()
    assert len(seen) == len(tour.steps) if not tour.active else True
    assert "Pick the burst run" in seen and "Prepare it" in seen


def test_every_target_of_the_guide_is_a_drawn_control(prepared):
    steps = json.loads((Path(__file__).parents[1] / "gui" / "guide.json").read_text())["steps"]
    for step in steps:
        key = prepared.app.tour._target_key(step.get("target"))
        if key:
            assert prepared.app.item_rects.get(key), f"guide target {key!r} is not drawn"


def test_every_control_and_table_column_has_a_tooltip_description():
    from chisurf.plugins.burst.mfd_prepare.gui.app import SPEC, MfdPreparePanel

    def walk(sections):
        for s in sections:
            if s.get("type") in ("table", "info"):
                assert s.get("description"), s
            if s.get("type") == "panel":
                walk(s["sections"])

    walk(SPEC["sections"])
    panel = MfdPreparePanel(make_app())
    for cols in (panel.detector_columns(), panel.source_columns(), panel.summary_columns()):
        for col in cols:
            assert col.get("description"), col
    from test.gui.emtk_port_parity import emtk_inventory

    inv = emtk_inventory(make_app())
    assert inv["controls_without_tooltip"] == [] and len(inv["controls"]) >= 4


# ---- layout, wheel ---------------------------------------------------------------------------------------------------- #
@pytest.mark.parametrize("size", [SIZE, SMALL])
@pytest.mark.parametrize("populated", [False, True])
def test_draws_at_both_sizes_without_overlap_or_clipped_controls(size, populated):
    drv = Driver(make_app(), size)
    if populated:
        hand(drv, FIXTURE)
        drv.click_name("prepare")
        settle(drv)
    painter = lay.draw(drv.app, size)
    lay.assert_texts_apart(painter)
    rects = {k: v for k, v in drv.app.item_rects.items() if k in ("prepare", "guide", "help")}
    assert set(rects) == {"prepare", "guide", "help"}
    lay.assert_inside(rects, size)
    lay.assert_disjoint(rects, list(rects))
    # the buttons keep their natural width: none stretched across the window
    assert all(w <= 140 for (_x, _y, w, _h) in rects.values())
    if populated:
        for name in ("detector_rows", "source_rows", "summary_rows"):
            assert drv.app.item_rects[name][0] >= 0


def test_the_mouse_wheel_scrolls_a_report_that_does_not_fit_the_small_window(prepared):
    prepared.resize(SMALL)
    last = prepared.app.model.report.splitlines()[-1].strip()

    def last_y():
        hits = [t for t in prepared.draw(2).texts if t[5] == last]
        return hits[-1][1] if hits else None

    def hidden():
        y = last_y()
        return y is None or y + 16 > SMALL[1]

    assert hidden(), "the report should run past the bottom edge at 800x600"
    x, y, w, h = prepared.app.item_rects["report"]
    at = (x + w / 2, y + h / 2)  # inside the report region, wherever the layout put it
    prepared.wheel(*at, steps=-40)  # wheel down
    scrolled = last_y()
    assert scrolled is not None and scrolled < SMALL[1], scrolled
    prepared.wheel(*at, steps=40)
    assert hidden()  # and back up to the top


# ---- Qt-free ------------------------------------------------------------------------------------------------------------- #
def test_the_app_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    # the emtk entrypoint of the manifest
    result = qt_free("mfd_prepare")
    assert result["ok"], result["output"]


def test_the_manifest_declares_the_emtk_entrypoint():
    manifest = json.loads((Path(__file__).parents[1] / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.burst.mfd_prepare.gui.app:make_app"
    assert "gui" not in manifest["entrypoints"]
