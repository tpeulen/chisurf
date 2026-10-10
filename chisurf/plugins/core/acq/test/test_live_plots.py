"""Click tests of the native live acquisition plots on the simulation device."""

from __future__ import annotations

import queue
import threading

import numpy as np
import pytest
from emtk import im
from emtk.app import ImApp
from emtk.view_form import FormState, draw_sections

from chisurf.plugins.core.acq.gui.live_plots import LivePlots, stream_words
from chisurf.plugins.core.acq.pipeline import AcquisitionPipeline, PipelineConfig
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

SIM = {
    "N_ph_max": 6000, "N_channels": 2, "M": [10.0], "D": [3.0], "q": [300.0, 225.0],
    "dt": 0.01, "psf_type": "analytic_gaussian3d", "analytic_excitation": True,
    "rmt1seed": 43, "rmt2seed": 44, "N_tac_channels": 4096, "tac_dt": 0.004069,
    "decay_lifetimes": [[[1.0, 3.2]]],
}


class PlotsApp(ImApp):
    """Hosts the live plots form the way AcquisitionApp will, polling snapshots."""

    def __init__(self, plots: LivePlots):
        self.model = plots
        self.events: queue.Queue = queue.Queue()
        self.form, self.item_rects = FormState(), {}
        self.form.custom.update({k: plots.draw_plot for k in (
            "live_decay", "live_correlation", "live_count_rate", "live_mcs", "live_macrotime")})
        self.job = type("J", (), {"busy": False})()
        super().__init__(self.render, continuous=False)

    def render(self):
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "snapshot":
                self.model.set_snapshot(payload)
        vp = im.get_main_viewport()
        self.form.rects.clear()
        im.set_next_window_pos(vp.pos, im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin("Live plots", (*vp.pos, *vp.size)):
            draw_sections(self.model.sections, self.model, self.form, titles=True)
        im.end()


def run_simulation(plots: LivePlots, every: int = 8):
    """Start a simulated acquisition on a worker thread; returns (app, pipeline, thread)."""
    from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
        generate_spc132_uint32,
    )

    words = generate_spc132_uint32(SIM)
    config = plots.apply_to_config(PipelineConfig(microtime_resolution_s=0.004069e-9 * 1e9 * 1e-9))
    pipeline = AcquisitionPipeline(config)
    app = PlotsApp(plots)

    def work():
        stream_words(pipeline, words, app.events, every=every)
        pipeline.flush()
        app.events.put(("snapshot", pipeline.snapshot()))

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    return app, pipeline, thread


def finish(app, thread, ui):
    thread.join(timeout=60)
    ui.draw(3)


def test_settings_roundtrip_and_junk_ignored():
    a = LivePlots()
    a.rate_binning, a.mcs_bin_width_ms, a.macro_type, a.corr_a1 = 7, 2.5, "absolute", 9
    saved = a.export_settings()
    b = LivePlots()
    b.restore_settings({**saved, "bogus": 1, "rate_window": "not a number"})
    assert b.export_settings()["rate_binning"] == 7 and b.mcs_bin_width_ms == 2.5
    assert b.macro_type == "absolute" and b.corr_a1 == 9 and b.rate_window == 500


def test_decay_histogram_sums_to_photon_count_and_toggles_hide_curves():
    plots = LivePlots()
    app, pipeline, thread = run_simulation(plots)
    ui = Driver(app, (1100, 760))
    ui.draw(2)
    finish(app, thread, ui)
    snap = plots.snapshot
    assert snap["total_photons"] > 1000
    drawn = plots.drawn["decay"]
    assert len(drawn) == 3
    totals = snap["channel_totals"]
    for (label, x, y), total in zip(drawn, totals):
        assert y.sum() == total
    assert sum(totals[:3]) <= snap["total_photons"]
    assert "Counts" in ui.draw(1).strings
    ui.click("decay_show1")
    ui.draw(2)
    assert plots.decay_show1 is False and len(plots.drawn["decay"]) == 2


def test_log_y_and_update_every_throttle():
    plots = LivePlots()
    app, pipeline, thread = run_simulation(plots, every=2)
    ui = Driver(app, (1100, 760))
    ui.draw(2)
    finish(app, thread, ui)
    ui.type_into("decay_every", "1000")
    before = plots.series["decay"]
    pipeline_snap = pipeline.snapshot()
    for _ in range(3):
        plots.set_snapshot(pipeline_snap)
    assert plots.series["decay"] is before  # throttled: not rebuilt
    ui.click("decay_log_y")
    assert plots.decay_log_y is True


def test_correlation_of_poisson_stream_is_flat_and_pairs_follow_controls():
    plots = LivePlots()
    plots.corr_a0, plots.corr_b0 = -1, -1
    plots.corr_show1, plots.corr_a1, plots.corr_b1 = True, 8, 9
    config = plots.apply_to_config(PipelineConfig(microtime_resolution_s=4e-12))
    assert config.correlation_pairs == ((0, -1, -1), (1, 8, 9))
    pipeline = AcquisitionPipeline(config)
    rng = np.random.default_rng(1)

    class Decoder:
        def decode(self, words):
            n = len(words)
            macro = np.cumsum(rng.exponential(200.0, n)).astype(np.uint64) + self.t
            self.t = int(macro[-1])
            return macro, rng.integers(0, 4000, n).astype(np.uint16), rng.choice([8, 9], n).astype(np.int32)

        t = 0

    pipeline.decoder = Decoder()
    for _ in range(60):
        pipeline.push(np.zeros(5000, dtype=np.uint32))
    plots.set_snapshot(pipeline.snapshot())
    assert len(plots.series["correlation"]) == 2
    for label, lag, g in plots.series["correlation"]:
        sel = g[lag > 0.01]
        assert sel.size > 5 and abs(np.nanmean(sel) - 1.0) < 0.05, label


def test_count_rate_binning_changes_bin_count_and_set_to_mean_click():
    plots = LivePlots()
    app, pipeline, thread = run_simulation(plots, every=1)
    ui = Driver(app, (1100, 760))
    ui.draw(2)
    finish(app, thread, ui)
    ui.click_text("Count rate")
    ui.draw(2)
    plots.set_snapshot(pipeline.snapshot())
    ui.draw(2)
    n1 = len(plots.drawn["rate"][0][1])
    assert n1 > 20
    ui.type_into("rate_binning", "10")
    ui.draw(2)
    plots.set_snapshot(pipeline.snapshot())
    ui.draw(2)
    assert len(plots.drawn["rate"][0][1]) == n1 // 10
    ui.click("set_mean_0")
    ui.draw(2)
    assert 0 in plots.mean_lines
    assert plots.mean_lines[0] == pytest.approx(float(np.mean(plots.series["rate"][0][2])))
    ui.click("clear_mean_lines")
    assert not plots.mean_lines


def test_mcs_bin_width_reaches_pipeline_and_macrotime_type_switches():
    plots = LivePlots()
    plots.mcs_bin_width_ms = 0.5
    app, pipeline, thread = run_simulation(plots, every=4)
    ui = Driver(app, (1100, 760))
    ui.draw(2)
    finish(app, thread, ui)
    x, _y = pipeline.mcs_trace()
    assert np.diff(x)[0] == pytest.approx(0.5)
    ui.click_text("Macrotime")
    ui.draw(2)
    assert plots.drawn["macro"][0][0] == "dt"
    ui.click("macro_type")
    ui.click_text("Absolute times")
    ui.draw(2)
    plots.set_snapshot(pipeline.snapshot())
    ui.draw(2)
    assert plots.drawn["macro"][0][0] == "t"


def test_real_app_simulation_fills_decay_plot_mid_run_and_persists_settings():
    """Start button in the real app: the decay plot has photons before the run ends."""
    import time

    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel

    model = AcquisitionNativeModel()
    model.photon_limit = 20000
    model.advanced_settings_text = __import__("json").dumps({**SIM, "N_ph_max": 20000})
    app = AcquisitionApp(model)
    try:
        ui = Driver(app, (1200, 900))
        ui.draw(3)
        ui.click("start")
        seen_mid = False
        end = time.monotonic() + 60
        while time.monotonic() < end:
            ui.draw(1)
            drawn = model.live.drawn.get("decay") or []
            if model.running and drawn and sum(float(y.sum()) for _l, _x, y in drawn) > 0:
                seen_mid = True
            if not model.running and model.snapshot is not None and seen_mid:
                break
            time.sleep(0.02)
        assert seen_mid, "decay plot never held photons while the run was still going"
        ui.draw(3)
        assert not model.running and model.snapshot["total_photons"] > 1000
        final = model.live.drawn["decay"]
        assert sum(float(y.sum()) for _l, _x, y in final) <= model.snapshot["total_photons"]
        model.live.rate_binning = 4
        saved = app.export_settings()
        assert saved["live_plots"]["rate_binning"] == 4
        app.restore_settings({**saved, "live_plots": {**saved["live_plots"], "rate_binning": 9}})
        assert model.live.rate_binning == 9
    finally:
        app.close()
