"""Head-less GUI smoke tests for the H2MM tool (collected by the gui suite)."""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qtpy")


@pytest.fixture(scope="module")
def qapp():
    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_h2mm_gui_instantiates(qapp):
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    w = H2mmTool(embedded=True)
    tabs = [w.dock_area.tabText(i) for i in range(3)]
    assert "H2MM Settings" in tabs
    assert "Results" in tabs
    w.close()


def test_h2mm_gui_defaults_to_fastest_engine(qapp):
    """The GUI defaults to the fastest method (float32 EM) with early-stop on."""
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    w = H2mmTool(embedded=True)
    settings = w._gather_settings()
    assert settings.engine == "em-float32"
    assert settings.patience == 1
    w.close()


def test_h2mm_gui_live_scan_plot(qapp):
    """The live-scan helper updates the model-selection and FRET plots."""
    from chisurf.plugins.burst.burst_h2mm.core import h2mm
    from chisurf.plugins.burst.burst_h2mm.core.analysis import StateFit
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    w = H2mmTool(embedded=True)
    fits = [
        StateFit(n_states=k, model=h2mm.factory_model(k, 2, seed=0),
                 loglik=-1.0, bic=100.0 - k, icl=100.0 - k)
        for k in (1, 2, 3)
    ]
    w._plot_scan_live(fits)
    # Model-selection plot has the BIC/ICL curves; FRET plot has state bars.
    assert len(w._p_sel.listDataItems()) >= 2
    assert len(w._p_fret.listDataItems()) + len(w._p_fret.items) > 0
    w.close()


def test_h2mm_gui_nonblocking_fit(qapp, tmp_path, monkeypatch):
    """Run drives a background worker, live progress, and populates results."""
    import time

    from chisurf.plugins.burst.burst_h2mm.backend.services import (
        H2mmAnalysisBundle,
        _result_from_analysis,
    )
    from chisurf.plugins.burst.burst_h2mm.core import h2mm
    from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze
    from chisurf.plugins.burst.burst_h2mm.gui import tool as tool_mod

    # A fake run_analysis that still drives `progress` and returns a real bundle
    # (so we exercise the threading/progress wiring without needing detectors).
    def fake_run_analysis(settings, analysis_folder=None, progress=None, **_):
        gt = h2mm.H2mmModel(
            np.array([0.5, 0.5]),
            np.array([[0.99, 0.01], [0.02, 0.98]]),
            np.array([[0.85, 0.15], [0.20, 0.80]]),
        )
        rng = np.random.default_rng(1)
        times = [
            np.concatenate([[0], np.cumsum(rng.poisson(4, 49) + 1)]).astype(np.int64)
            for _ in range(60)
        ]
        data = h2mm.prepare_bursts(times, h2mm.simulate_bursts(gt, times, seed=2), 2)
        ana = analyze(data, state_counts=(1, 2), n_restarts=1, max_iter=100, progress=progress)
        return _result_from_analysis(ana, settings), H2mmAnalysisBundle(ana, data, settings)

    monkeypatch.setattr(tool_mod, "run_analysis", fake_run_analysis)

    w = tool_mod.H2mmTool(embedded=True)
    w.data_folder = tmp_path
    w._run_analysis()
    assert not w.btn_run.isEnabled()  # disabled while the worker runs

    deadline = time.time() + 60
    while w._result is None and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)

    assert w._result is not None
    assert w._result.n_states in (1, 2)
    assert w.btn_run.isEnabled()             # re-enabled on completion
    assert len(w._p_sel.listDataItems()) >= 2  # results plotted
    w.close()


def test_h2mm_gui_plots_render(qapp):
    import types

    import pandas as pd

    from chisurf.plugins.burst.burst_h2mm.api.models import H2mmSettings
    from chisurf.plugins.burst.burst_h2mm.backend.services import (
        H2mmAnalysisBundle,
        _result_from_analysis,
    )
    from chisurf.plugins.burst.burst_h2mm.core import analysis, h2mm
    from chisurf.plugins.burst.burst_h2mm.core.photons import (
        StreamDef,
        bursts_from_dataframe,
    )
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    gt = h2mm.H2mmModel(
        np.array([0.5, 0.5]),
        np.array([[0.99, 0.01], [0.02, 0.98]]),
        np.array([[0.85, 0.15], [0.20, 0.80]]),
    )
    rng = np.random.default_rng(1)
    times = [
        np.concatenate([[0], np.cumsum(rng.poisson(4, size=59) + 1)]).astype(np.int64)
        for _ in range(120)
    ]
    streams = h2mm.simulate_bursts(gt, times, seed=2)
    macro, chan, micro, rows = [], [], [], []
    off = base = 0
    for t, s in zip(times, streams):
        macro.append(t + base)
        chan.append(s.astype(np.int64))
        micro.append(np.zeros_like(s))
        rows.append(("f.spc", off, off + len(t)))
        off += len(t)
        base += int(t[-1]) + 1000
    hdr = types.SimpleNamespace(tag=lambda k: {"value": 1e-6}, macro_time_resolution=1e-6)
    tttr = types.SimpleNamespace(
        macro_times=np.concatenate(macro),
        routing_channels=np.concatenate(chan),
        micro_times=np.concatenate(micro),
        header=hdr,
    )
    df = pd.DataFrame(rows, columns=["First File", "First Photon", "Last Photon"])
    data = bursts_from_dataframe(
        df, {"f.spc": tttr}, [StreamDef("green", [0]), StreamDef("red", [1])], min_photons=5
    )
    ana = analysis.analyze(data, state_counts=(1, 2), base_time_s=1e-6, n_restarts=1, max_iter=150)

    w = H2mmTool(embedded=True)
    w._result = _result_from_analysis(ana, H2mmSettings())
    w._bundle = H2mmAnalysisBundle(ana, data, H2mmSettings())
    w._update_plots()  # must not raise
    assert w._result.n_states == 2
    # Burst-path viewer is populated and navigates.
    assert w.sb_burst.maximum() == data.n_bursts - 1
    w.sb_burst.setValue(1)  # must not raise (draws a different burst)
    w.cb_dynamic_only.setChecked(True)  # restrict to bursts with transitions
    assert "burst" in w._burst_label.text()
    w.close()


def test_h2mm_gui_alex_es_and_nanotime(qapp):
    """A 3-stream ALEX run renders the E–S scatter, per-state decay, and burst path."""
    import types

    import pandas as pd

    from chisurf.plugins.burst.burst_h2mm.api.models import H2mmSettings
    from chisurf.plugins.burst.burst_h2mm.backend.services import (
        H2mmAnalysisBundle,
        _result_from_analysis,
    )
    from chisurf.plugins.burst.burst_h2mm.core import analysis, h2mm
    from chisurf.plugins.burst.burst_h2mm.core.photons import (
        StreamDef,
        bursts_from_dataframe,
    )
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    gt = h2mm.H2mmModel(
        np.array([0.5, 0.5]),
        np.array([[0.98, 0.02], [0.03, 0.97]]),
        np.array([[0.45, 0.10, 0.45], [0.10, 0.45, 0.45]]),
    )
    rng = np.random.default_rng(5)
    times = [
        np.concatenate([[0], np.cumsum(rng.poisson(4, size=79) + 1)]).astype(np.int64)
        for _ in range(150)
    ]
    sim = h2mm.simulate_bursts(gt, times, seed=6)
    macro, chan, micro, rows = [], [], [], []
    off = base = 0
    for t, s in zip(times, sim):
        macro.append(t + base)
        chan.append(s.astype(np.int64))
        micro.append(rng.exponential(np.where(s == 0, 200.0, 600.0)).astype(np.int64) % 4096)
        rows.append(("f.spc", off, off + len(t)))
        off += len(t)
        base += int(t[-1]) + 2000
    hdr = types.SimpleNamespace(tag=lambda k: {"value": 1e-6}, macro_time_resolution=1e-6)
    tttr = types.SimpleNamespace(
        macro_times=np.concatenate(macro),
        routing_channels=np.concatenate(chan),
        micro_times=np.concatenate(micro),
        header=hdr,
    )
    df = pd.DataFrame(rows, columns=["First File", "First Photon", "Last Photon"])
    streams = [StreamDef("green", [0]), StreamDef("red", [1]), StreamDef("yellow", [2])]
    data, meta = bursts_from_dataframe(df, {"f.spc": tttr}, streams, min_photons=8, return_meta=True)
    ana = analysis.analyze(data, state_counts=(1, 2), base_time_s=1e-6, n_restarts=2, max_iter=200)

    w = H2mmTool(embedded=True)
    w._result = _result_from_analysis(ana, H2mmSettings())
    w._bundle = H2mmAnalysisBundle(ana, data, H2mmSettings())
    w._bundle.meta = meta
    w._update_plots()  # must not raise for the ALEX/PIE + nanotime path
    assert w._result.has_alex
    assert w._p_fret.titleLabel.text == "Dwell E–S scatter"
    # E–S scatter drew per-state clouds; nanotime drew per-state decays.
    assert len(w._p_fret.items) > 0
    assert len(w._p_nano.listDataItems()) >= 1
    assert len(w._p_path.items) > 0

    import pyqtgraph as pg

    # Transition-rate matrix drew value labels; E–S scatter got rate arrows.
    assert any(isinstance(it, pg.TextItem) for it in w._p_rates.items)
    assert any(isinstance(it, pg.ArrowItem) for it in w._p_fret.items)

    # Bootstrap uncertainty overlays error bars on the E–S scatter.
    from chisurf.plugins.burst.burst_h2mm.core.analysis import bootstrap_uncertainty

    w._uncertainty = bootstrap_uncertainty(
        data, ana.best.n_states, n_boot=4, n_restarts=1, max_iter=120,
        aex_streams=(2,), seed=0
    )
    w._plot_dwell_fret(ana)
    assert any(isinstance(it, pg.ErrorBarItem) for it in w._p_fret.items)

    # Profile-likelihood scan builds a dialog with E and S profiles (ALEX data).
    from chisurf.plugins.burst.burst_h2mm.core.analysis import profile_likelihood
    from chisurf.plugins.burst.burst_h2mm.gui.tool import LikelihoodScanDialog

    scans = profile_likelihood(
        data, ana.best.model,
        donor_streams=ana.donor_streams, acceptor_streams=ana.acceptor_streams,
        aex_streams=ana.aex_streams, n_points=11, half_width=0.15,
    )
    assert {s.param for s in scans} == {"E", "S"}
    dlg = LikelihoodScanDialog(scans, w._uncertainty, w._state_color, w)  # must not raise
    dlg.close()
    w.close()
