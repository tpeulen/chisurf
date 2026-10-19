"""The native FCS workflow (the ribbon's FCS entry) driven by real input.

Pointer presses at the drawn controls (the hub's rail and Back / Next, the step apps' buttons, fields and tick boxes),
typed text and the file dialog; the data are the correlator's own demo (:mod:`..demo`, molecules crossing the focus in
0.25 ms) and BH_SPC132.spc where the Qt baseline used it. Hermetic: temp settings, MMFDB and HOME.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest
from emtk import keys
from emtk.testing import RecordingPainter

from chisurf.plugins.emtk_layout import help_close_caption
from chisurf.plugins.fcs.fcs_correlator.correlator_model import CorrelatorSettingsModel
from chisurf.plugins.fcs.fcs_correlator.demo import make_demo
from chisurf.plugins.fcs.fcs_correlator.filter_model import FilterSettingsModel
from chisurf.plugins.fcs.fcs_correlator.gui.app import make_app as make_correlator
from chisurf.plugins.fcs.fcs_correlator.workflow import FcsWorkflow, filter_step_allowed

CTRL_A = 0x04000000
SIZES = [(1200, 800), (800, 600)]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path))


class Hub:
    """The hub at a window size: presses at the hub's own rects and at a child's (offset by the child box)."""

    def __init__(self, app, size=(1200, 800)):
        self.app, self.size, self.last = app, size, None
        self.draw(3)

    def draw(self, frames=2):
        from chisurf.emtk.background_build import join_all

        for _ in range(frames):
            join_all()  # the opening step is made in the background; a host draws again when it lands
            self.last = RecordingPainter()
            self.app.draw(self.last, 0, 0, *self.size)
        return self.last

    @property
    def child(self):
        return self.app.child

    def rect(self, key):
        self.draw(1)
        if key in self.app.item_rects and not key.startswith(("files", "row.", "check.")):
            return self.app.item_rects[key]
        x, y, w, h = self.child.item_rects[key]
        bx, by = self.app.child_box[:2]
        return (bx + x, by + y, w, h)

    def click_at(self, x, y):
        self.app.pointer_move(x, y)
        self.draw(1)
        self.app.press(x, y)
        self.draw(1)
        self.app.release()
        return self.draw(2)

    def click(self, key, fx=0.5, fy=0.5):
        x, y, w, h = self.rect(key)
        return self.click_at(x + w * fx, y + h * fy)

    def nav(self, role):
        return self.click("nav." + role)

    def text_rect(self, label, nth=0):
        hits = [t[:4] for t in self.draw(1).texts if t[5] == label]
        assert hits, f"{label!r} not drawn: {self.last.strings[:80]}"
        return hits[nth]

    def press_text(self, label, nth=0):
        x, y, w, h = self.text_rect(label, nth)
        return self.click_at(x + w / 2, y + h / 2)

    def type_into(self, key, text):
        self.click(key, fx=0.3)
        assert self.child.io.want_capture_keyboard, f"{key} did not take the keyboard"
        self.app.key(0x41, "a", CTRL_A)
        self.draw(1)
        for ch in text:
            self.app.key(ord(ch), ch)
            self.draw(1)
        self.app.key(keys.KEY_RETURN, "\r")
        return self.draw(2)

    def shown(self, text):
        return any(text in s for s in self.draw(1).strings)

    def wait_correlated(self, timeout=120):
        end = time.monotonic() + timeout
        while self.child.running:
            assert time.monotonic() < end, "correlation did not finish"
            time.sleep(0.02)
            self.draw(1)
        return self.draw(2)


def _hub(size=(1200, 800)):
    return Hub(make_correlator(), size)


class RecordingHost:
    """A window that opens the Filter Calculator for a hand-off, as the emtk shell does (:mod:`chisurf.core.plugin.handoff`)."""

    def __init__(self):
        self.handed: list[tuple[str, str, dict]] = []
        self.apps: dict[str, object] = {}

    def accepts(self, plugin_id, kind):
        from chisurf.core.plugin.handoff import accepted

        manifest = Path(__file__).resolve().parents[2] / "fcs_filter_calculator/manifest.json"
        if plugin_id != "fcs_filter_calculator":
            return None
        return accepted(plugin_id, kind, json.loads(manifest.read_text(encoding="utf-8")))

    def hand_off(self, plugin_id, kind, payload, on_delivered=None, new=False):
        from chisurf.core.plugin.handoff import HandoffError, check_payload, deliver
        from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import create_app

        spec = self.accepts(plugin_id, kind)
        if spec is None:
            raise HandoffError(f"{plugin_id} does not accept {kind}")
        check_payload(spec, payload)
        app = self.apps.get(plugin_id) or create_app()
        self.apps[plugin_id] = app
        deliver(app, spec, payload)
        self.handed.append((plugin_id, kind, payload))
        return app


@pytest.fixture
def host():
    from chisurf.core.plugin import handoff

    window = RecordingHost()
    handoff.install_host(window)
    yield window
    handoff.uninstall_host(window)
    for app in window.apps.values():
        app.close()


# ---- the Qt-free workflow -------------------------------------------------------------------------------------------


def test_workflow_hands_photons_filter_and_curves_on(tmp_path):
    spc = make_demo(tmp_path)
    flow = FcsWorkflow()
    flow.set_files([str(spc)], use_filter=True, use_merger=True)
    filt, corr = FilterSettingsModel(), CorrelatorSettingsModel()
    flow.load_files_into_filter(filt)
    kept = int(filt.selected().sum())
    assert 0 < kept < len(filt._tttr)
    flow.apply_to_correlator(corr, filt)
    assert len(corr._tttr) == kept  # the correlator gets the filtered photons
    flow.set_files([str(spc)], use_filter=False, use_merger=True)
    flow.apply_to_correlator(corr, filt)
    assert len(corr._tttr) == len(filt._tttr)  # and the raw ones without the filter step
    corr.n_splits, corr.channel_a, corr.channel_b = 1, "0", "1"
    assert corr.correlate_data() == "1 chunk(s) correlated."
    x, y = np.asarray(corr._correlations[0]["x"]), np.asarray(corr._correlations[0]["y"])
    # the demo's answer: correlated within the 0.25 ms crossing, uncorrelated after a few
    assert np.interp(0.02, x, y) > 1.5 and abs(np.interp(5.0, x, y) - 1.0) < 0.1
    curves, folder = flow.merger_input(corr)
    assert len(curves) == 1 and folder == spc.parent / "cr5"
    assert not filter_step_allowed([str(tmp_path / "x.bst")])


# ---- the hub, real input --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_example_correlate_and_merge(size):
    hub = _hub(size)
    assert hub.app.selected == "files"
    hub.click("load_example")
    files = hub.child
    assert len(files.checked_files) == 1 and files.checked_files[0].endswith("fcs_demo.spc")
    assert not hub.app.panel_enabled("filter")  # off by default, as in Qt
    hub.nav("correlator")
    assert hub.app.selected == "correlator" and hub.shown("photons")
    hub.type_into("channel_a", "0")
    hub.type_into("channel_b", "1")
    hub.type_into("n_splits", "3")
    assert (hub.child.model.channel_a, hub.child.model.channel_b, hub.child.model.n_splits) == (
        "0",
        "1",
        3,
    )
    hub.click("correlate")
    hub.wait_correlated()
    assert len(hub.child.model._correlations) == 3 and hub.shown("3 chunk(s) correlated.")
    hub.click("next")  # Next correlates again, then goes on to the merger (it is on)
    end = time.monotonic() + 120
    while hub.app.selected != "merger":
        assert time.monotonic() < end, "Next did not reach the merger"
        time.sleep(0.02)
        hub.draw(1)
    assert len(hub.child.model.correlations) == 3
    hub.app.close()


def test_steps_switch_the_filter_and_merger_on_and_off():
    hub = _hub()
    hub.click("load_example")
    hub.click("use_filter")
    assert hub.child.use_filter and hub.app.panel_enabled("filter")
    hub.nav("filter")
    assert hub.app.selected == "filter" and hub.shown("photons kept")
    before = int(hub.app.filter_model.selected().sum())
    hub.type_into("min_ph", "40")
    assert hub.app.filter_model.min_ph == 40
    after = int(hub.app.filter_model.selected().sum())
    assert after < before and hub.shown(f"{after:,} /")
    hub.nav("correlator")
    assert len(hub.app.correlator_model._tttr) == after  # the correlator gets what the filter kept
    hub.nav("files")
    hub.click("use_merger")
    assert not hub.app.panel_enabled("merger")
    hub.nav("correlator")
    hub.click("next")  # the merger is off: Next does not open it
    assert hub.app.selected != "merger"
    hub.nav("merger")
    assert hub.app.selected != "merger"  # a switched-off step does not open
    hub.app.close()


def test_file_list_buttons_and_dialogs(tmp_path):
    demo = make_demo(tmp_path / "data")
    (tmp_path / "data" / "notes.txt").write_text("x")
    hub = _hub()
    files = hub.child
    assert hub.app.on_files_dropped([str(demo), str(tmp_path / "data" / "notes.txt")])
    assert files.paths == [str(demo.resolve())]  # a non-TTTR file is not added
    hub.click("check.0")
    assert files.checked_files == []
    hub.click("all")
    assert files.checked_files == [str(demo.resolve())]
    hub.click("none")
    assert files.checked_files == []
    hub.click("row.0", fx=0.6)
    hub.click("remove")
    assert files.paths == []
    hub.click("add_folder")
    assert files.dialogs.dialog is not None
    files.dialogs.dialog.enter(str(tmp_path))
    hub.draw(2)
    hub.press_text("[data]")
    hub.press_text("Choose")
    assert files.paths == [str((tmp_path / "data").resolve())]
    hub.click("clear")
    assert files.paths == []
    hub.click("add_files")
    files.dialogs.dialog.enter(str(tmp_path / "data"))
    hub.draw(2)
    hub.press_text(demo.name)
    hub.press_text("Open")
    assert files.paths == [str(demo.resolve())]
    hub.click("database")
    assert files.picker is not None and files.picker.is_open
    hub.app.close()


def test_bst_files_switch_the_filter_off(tmp_path):
    bst = tmp_path / "a.bst"
    bst.write_text("0 10\n")
    hub = _hub()
    hub.child.add_paths([str(make_demo(tmp_path))])
    hub.click("use_filter")
    assert hub.child.use_filter
    hub.app.on_files_dropped([str(bst)])
    assert not hub.child.use_filter and not hub.app.panel_enabled("filter")
    hub.click("use_filter")
    assert not hub.child.use_filter  # disabled while a .bst file is ticked
    hub.app.close()


def test_lifetime_filters_presets_and_filter_calc(tmp_path, host):
    nbins = 32
    payload = {
        "mode": "single",
        "metadata": {"species_labels": ["Fast", "Slow"]},
        "total_path": None,
        "species_patterns": None,
        "nuisance_count": 1,
        "nuisance_labels": ["BG"],
        "filters": np.random.default_rng(1).random((3, nbins)).tolist(),
        "reconstruction": [0.0] * nbins,
        "weighted_residuals": [0.0] * nbins,
        "total_decay": [0.0] * nbins,
        "species_decays": [[0.0] * nbins] * 2,
    }
    (tmp_path / "filters.json").write_text(json.dumps(payload))
    hub = _hub()
    hub.nav("correlator")
    corr = hub.child
    hub.click("load_filters")
    corr.dialogs.dialog.enter(str(tmp_path))
    hub.draw(2)
    hub.press_text("filters.json")
    hub.press_text("Open")
    assert corr.model.filter_mode and hub.shown("Species mode: filters.json (2 species).")
    assert hub.shown("Species A:")
    hub.click("combo_b")
    hub.press_text("Slow")
    assert corr.model._species_b == 1
    hub.click("unload_filters")
    assert not corr.model.filter_mode
    # a preset fills the channels (presets come from the channel step's setup; one is given here)
    corr.model._fcs_presets = [{"name": "Green ACF", "channel_a": "G", "channel_b": "G"}]
    corr.model._fcs_preset_detectors = {"G": {"chs": [0, 8], "micro_time_ranges": [[0, 2000]]}}
    hub.click("fcs_preset")
    hub.press_text("Green ACF")
    assert corr.model.channel_a == "0,8" and corr.model.microtime_range_a == "0-2000"
    hub.click("filter_calc")
    assert [h[:2] for h in host.handed] == [("fcs_filter_calculator", "fcs_correlator_files")]
    assert hub.app.selected == "correlator", "the calculator opens in a window of its own"
    hub.app.close()


def test_filter_calc_is_greyed_without_a_window_to_open_it_in():
    hub = _hub()
    hub.nav("correlator")
    hub.click("filter_calc")  # no host: the button is disabled and nothing happens
    assert hub.app.selected == "correlator"
    assert not hub.child.tool_available("fcs_filter_calculator")
    hub.app.close()


def test_spc_correlates_like_the_qt_tool():
    """The Qt baseline's file and settings: two chunks, the same numbers as the Qt correlator."""
    spc = Path(__file__).resolve().parents[5] / "test/data/tttr/BH/132/BH_SPC132.spc"
    if not spc.exists():
        pytest.skip("SPC test data not available")
    hub = _hub()
    hub.child.add_paths([str(spc)])
    hub.nav("correlator")
    hub.type_into("n_splits", "2")
    hub.click("correlate")
    hub.wait_correlated()
    native = [np.asarray(c["y"]) for c in hub.child.model._correlations]
    from chisurf.plugins.fcs.fcs_correlator.correlator_model import CorrelatorSettingsModel as Model
    from chisurf.plugins.fcs.fcs_correlator.workflow import FcsWorkflow as Flow

    flow, ref = Flow(), Model()
    flow.set_files([str(spc)], False, True)
    flow.apply_to_correlator(ref)
    ref.n_splits = 2
    ref.correlate_data()
    assert len(native) == 2 and all(
        np.allclose(a, np.asarray(b["y"])) for a, b in zip(native, ref._correlations)
    )
    hub.app.close()


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_every_step_opens_and_its_controls_are_inside(size):
    hub = _hub(size)
    hub.click("load_example")
    hub.click("use_filter")
    bx, by, bw, bh = hub.app.child_box
    for panel in hub.app.tools:
        hub.nav(panel["role"])
        assert hub.app.selected == panel["role"], hub.app.errors
        assert panel["role"] not in hub.app.errors
        hub.draw(2)
        if panel["role"] in ("files", "correlator"):
            for key, (x, y, w, h) in hub.child.item_rects.items():
                if key.startswith(("row.", "check.", "plot", "files")):
                    continue
                assert x + w <= bw + 1 and y + h <= bh + 1, (
                    panel["role"],
                    key,
                    (x, y, w, h),
                    (bw, bh),
                )
    hub.app.close()


def test_filter_step_scrolls_to_its_last_plot():
    """At 800x600 the filter step is taller than its window: the wheel reaches the count-rate plot."""
    hub = _hub((800, 600))
    hub.click("load_example")
    hub.click("use_filter")
    hub.nav("filter")
    bh = hub.app.child_box[3]
    for _ in range(15):
        x, y, w, h = hub.child.item_rects["filter_cr_plot"]
        if y + h <= bh:
            break
        cx, cy = hub.app.child_box[0] + 100, hub.app.child_box[1] + 150
        hub.app.pointer_move(cx, cy)
        hub.draw(1)
        hub.app.wheel(cx, cy, -3)
        hub.draw(2)
    x, y, w, h = hub.child.item_rects["filter_cr_plot"]
    assert y + h <= bh + 1, (y, h, bh)
    hub.app.close()


def test_help_guide_and_the_tour_waits_for_the_user():
    hub = _hub()
    hub.click("help")
    assert hub.app.help.open
    hub.press_text(help_close_caption(), nth=-1)
    hub.click("guide")
    tour = hub.app.tour
    assert tour.active and len(tour.steps) >= 5
    hub.press_text("Next ►")
    assert tour.step_idx == 1 and tour.awaiting  # "press Example": waits
    hub.click("load_example")
    assert not tour.awaiting
    hub.press_text("Next ►")
    hub.press_text("Next ►")
    assert tour.awaiting  # "select 4. Correlator"
    hub.nav("correlator")
    assert not tour.awaiting
    hub.press_text("Next ►")
    hub.click("correlate")
    hub.wait_correlated()
    assert not tour.awaiting
    hub.press_text("Next ►")  # the Filter Calc card: it points at the button and opens nothing
    assert not tour.awaiting and hub.app.selected == "correlator"
    hub.press_text("Next ►")
    assert tour.awaiting  # "select 5. FCS Merger"
    hub.nav("merger")
    assert not tour.awaiting
    hub.app.close()


def test_the_fcs_entry_is_the_five_step_workflow_and_nothing_else():
    hub = _hub()
    assert [p["role"] for p in hub.app.tools] == [
        "channel_def",
        "files",
        "filter",
        "correlator",
        "merger",
    ]
    assert hub.app.title == "FCS"
    hub.app.close()


def test_filter_calc_reads_the_correlator_files_on_its_own_window(host):
    from chisurf.plugins.fcs.fcs_correlator.gui.app import FILES_HANDOFF

    hub = _hub()
    hub.click("load_example")
    hub.nav("correlator")
    hub.click("filter_calc")
    assert host.handed and host.handed[-1][1] == FILES_HANDOFF
    payload = host.handed[-1][2]
    assert [Path(p).name for p in payload["files"]] == ["fcs_demo.spc"]
    assert payload["microtime_binning"] >= 1
    calc = host.apps["fcs_filter_calculator"]
    for _ in range(300):  # the mixed decay is read on the calculator's worker once it is idle
        calc.draw(RecordingPainter(), 0, 0, 1100, 720)
        if getattr(calc.model, "_total_paths", None):
            break
        time.sleep(0.02)
    assert [p.name for p in calc.model._total_paths] == ["fcs_demo.spc"], (
        calc.model.message,
        calc.job.running,
    )
    assert calc.mixed_from_correlator
    hub.app.close()


def test_filter_calc_keeps_a_mixed_decay_of_its_own(host, tmp_path):
    from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import (
        create_app,
        receive_correlator_files,
    )

    calc = create_app()
    try:
        for _ in range(300):  # its own first computation runs when it opens
            calc.draw(RecordingPainter(), 0, 0, 1100, 720)
            if not calc.job.running:
                break
            time.sleep(0.02)
        calc.model._total_paths = [tmp_path / "own.spc"]
        receive_correlator_files(calc, {"files": [str(tmp_path / "other.spc")]})
        calc.draw(RecordingPainter(), 0, 0, 1100, 720)
        for _ in range(300):
            if not calc.correlator_pending:
                break
            calc.draw(RecordingPainter(), 0, 0, 1100, 720)
            time.sleep(0.02)
        assert [p.name for p in calc.model._total_paths] == ["own.spc"]
        assert "Kept the mixed decay" in calc.model.message
    finally:
        calc.close()


def test_next_runs_the_step_and_fast_forward_walks_the_workflow():
    """Next runs the open step (Correlate), then advances; >> walks the rest of the group, waiting for each step."""
    hub = _hub()
    hub.click("load_example")
    hub.nav("correlator")
    hub.click("next")
    end = time.monotonic() + 120
    while hub.app.selected != "merger":
        assert time.monotonic() < end, "Next did not advance after the correlation"
        time.sleep(0.02)
        hub.draw(1)
    assert hub.app.correlator_model._correlations and hub.child.model.correlations
    hub.nav("files")
    hub.app.correlator_model._correlations.clear()
    hub.click("fast_forward")
    while hub.app.fast_forwarding or hub.app._busy():
        assert time.monotonic() < end + 120, "fast-forward did not finish"
        time.sleep(0.02)
        hub.draw(1)
    assert hub.app.selected == "merger" and hub.app.correlator_model._correlations
    assert hub.shown("Fast-forward finished.")
    hub.app.close()


def test_stop_is_clickable_while_a_correlation_runs(monkeypatch):
    """Correlate starts the job, the Stop button replaces it, a real press on it ends the run.

    The job is held open chunk by chunk (it only ends when ``progress`` answers False), so the press cannot
    land after a fast run finished: the run ends *because* Stop was pressed.
    """
    chunks = {"done": 0}

    def slow_correlate(self, progress=None):
        for i in range(1, 2000):
            chunks["done"] = i
            if progress is not None and not progress(i, 2000):
                return f"stopped after {i} chunk(s)."
            time.sleep(0.01)
        return "finished"

    monkeypatch.setattr(CorrelatorSettingsModel, "correlate_data", slow_correlate)
    hub = _hub()
    hub.click("load_example")
    hub.nav("correlator")
    hub.click("correlate")
    deadline = time.monotonic() + 10
    while "stop" not in hub.child.item_rects and time.monotonic() < deadline:
        hub.draw(1)
    assert hub.child.running and "stop" in hub.child.item_rects
    assert hub.shown("Stop")
    hub.click("stop")
    assert hub.child._stop, "pressing the drawn Stop button did not reach the job"
    hub.wait_correlated(timeout=10)
    assert not hub.child.running and hub.shown("stopped after")
    assert chunks["done"] < 2000
    hub.app.close()
