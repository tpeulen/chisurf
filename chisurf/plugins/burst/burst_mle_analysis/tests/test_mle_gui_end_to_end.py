"""End-to-end GUI test of the burst MLE-lifetime wizard on real smFRET data.

Drives the wizard the way the workflow does — set detectors, load a .bur, build
the decay, provide IRF/background, run the fit — and asserts the results are
sane. This catches the silent-failure bugs where the current detector loses its
IRF (so update_fit bails) and the decay/plot end up empty.

Skipped when the BH smFRET DNA test data is not present.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

DATA = Path("/Users/tpeulen/dev/tttr-data/bh/bh_spc132_sm_dna")
BUR = DATA / "sliding_window_All 0.1500#60_3" / "bi4_bur" / "m000.bur"
HANDOFF = DATA / "burst_analysis_handoff" / "burst_analysis_handoff.json"

pytestmark = pytest.mark.skipif(
    not (BUR.exists() and HANDOFF.exists()),
    reason="BH smFRET DNA test data not available",
)


# BH SPC-132 dual-colour polarization channel map for this dataset: routing
# channels 0/1 are the green parallel/perpendicular detectors, 8/9 the red. (The
# burst-analysis handoff no longer carries channel_settings, so the test supplies
# the detector definition the channel-definition page would.)
CHANNEL_SETTINGS = {
    "detectors": {
        "green": {"chs": [0, 1], "micro_time_ranges": [],
                  "g_factor": 1.0, "l1": 0.0308, "l2": 0.0368},
        "red": {"chs": [8, 9], "micro_time_ranges": [],
                "g_factor": 1.0, "l1": 0.0308, "l2": 0.0368},
    },
    "windows": {},
    "file_type": "SPC-130",
}


@pytest.fixture
def fitted_wizard(qapp):
    """A wizard with channels, a burst file, IRF/bg and one fit run for green.

    Drives the one-click ``Auto IRF/background`` path (``auto_extract_irf_bg``),
    which is the foolproof workflow: it auto-selects the micro-time binning and
    fit window and estimates the IRF/background from the non-burst photons.
    """
    from qtpy import QtWidgets

    import tttrlib  # noqa: F401  (ensures the extension is importable)
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    w = MLELifetimeAnalysisWizard()
    QtWidgets.QApplication.processEvents()

    w.channel_definer.load_data_into_tables(CHANNEL_SETTINGS)
    w.channel_definer.file_type_combo.setCurrentText("SPC-130")
    w._init_channels_from_wizard()
    w.burst_files_list.add_file(str(BUR))
    w.load_burst_data()
    w.update_burst_files()
    w.comboBox_window.setCurrentText("green")
    QtWidgets.QApplication.processEvents()

    # One-click IRF/background + binning/window auto-selection + fit for green.
    w.auto_extract_irf_bg()
    QtWidgets.QApplication.processEvents()
    return w


def test_detector_state_has_no_empty_detector(fitted_wizard):
    # A spurious "" detector must never appear (it shadowed the real one).
    for store in (fitted_wizard.irf_np, fitted_wizard.bg_np,
                  fitted_wizard.channel_settings):
        assert "" not in store
        assert None not in store


def test_current_detector_keeps_its_irf(fitted_wizard):
    # The regression: the current detector lost its IRF (popped when its file
    # widget was empty), so update_fit silently bailed.
    det = fitted_wizard.current_detector
    assert det in fitted_wizard.irf_np, "current detector lost its IRF"
    assert det in fitted_wizard.bg_np
    assert np.asarray(fitted_wizard.irf_np[det]).size > 0


def test_decay_is_built(fitted_wizard):
    decay = fitted_wizard.decay_of_current_file
    assert decay is not None, "decay was never built (blank Intensity plot)"
    decay = np.asarray(decay)
    assert decay.size > 0 and decay.sum() > 0


def test_fit_produces_a_plausible_lifetime(fitted_wizard):
    # tau must move off the initial and land in a physical range; a silent no-fit
    # leaves it at the initial / zero.
    tau = fitted_wizard.doubleSpinBox_tau_result.value()
    assert 0.1 < tau < 10.0, f"implausible / non-fit tau={tau}"


def test_auto_extract_coarsens_the_sparse_default_binning(fitted_wizard):
    # The bug: at the sparse default binning (1) the ~8.6k burst photons are
    # ~1 count/bin over the 2x4096 Jordi, and the maximum-likelihood fit rails
    # tau to the excitation period. Auto-selection must coarsen the axis so the
    # bins carry counts (and not below the IRF resolution).
    assert fitted_wizard.micro_time_binning > 1


def test_auto_extract_restricts_the_fit_window_to_the_filled_region(fitted_wizard):
    # The window must exclude the empty pre-prompt bins and the noise tail, i.e.
    # be genuinely narrower than the whole half.
    sb, eb = fitted_wizard.micro_time_range
    n_half = int(np.asarray(fitted_wizard.decay_of_current_file).size) // 2
    assert 0 <= sb < eb <= n_half
    assert (eb - sb) < n_half, "window was not restricted to the filled region"


def test_auto_extract_gives_a_physical_lifetime_for_every_colour(fitted_wizard):
    # Both the green (donor) and red (acceptor) decays must recover a physical
    # single-molecule lifetime through the one-click path — no railing.
    w = fitted_wizard
    for det in ("green", "red"):
        w.comboBox_window.setCurrentText(det)
        w.auto_extract_irf_bg()
        tau = w.doubleSpinBox_tau_result.value()
        assert 0.5 < tau < 5.0, f"{det} tau railed/implausible: {tau}"


def test_auto_optimize_button_sets_binning_window_and_fits(fitted_wizard):
    # The general one-click optimiser: with no measured IRF it delegates to the
    # non-burst extraction, so it must leave a coarsened binning, a restricted
    # window and a physical lifetime — the same guarantees as the IRF path.
    w = fitted_wizard
    w.comboBox_window.setCurrentText("green")
    w.auto_optimize()
    assert w.micro_time_binning > 1
    sb, eb = w.micro_time_range
    n_half = int(np.asarray(w.decay_of_current_file).size) // 2
    assert 0 <= sb < eb <= n_half and (eb - sb) < n_half
    assert 0.5 < w.doubleSpinBox_tau_result.value() < 5.0


def _mean_arrival_lifetime(w, det, chs):
    """Model-free lifetime: mean burst micro-time minus the scatter prompt."""
    tttr = next(iter(w.tttrs.values()))
    idx = np.asarray(w.get_burst_indices_for_current_file(), dtype=int)
    micro = np.asarray(tttr.micro_times)
    rout = np.asarray(tttr.routing_channels)
    micro_ns = tttr.header.micro_time_resolution * 1e9
    in_burst = np.zeros(len(tttr), bool)
    in_burst[idx] = True
    par = chs[0]
    burst = micro[in_burst & (rout == par)] * micro_ns
    prompt_bin = np.bincount(micro[~in_burst & (rout == par)]).argmax()
    return float(burst.mean() - prompt_bin * micro_ns)


def test_auto_extract_lifetime_matches_model_free_estimate(fitted_wizard):
    # The regression this guards: an IRF taken straight from the non-burst
    # histogram carries a fluorescence tail (dim/passing molecules), and
    # convolving with it biased the fitted lifetime ~2x short (a ~2.2 ns decay
    # fit as ~1.1 ns). The extraction now models the IRF as a tail-free Gaussian
    # at the prompt, so the fitted tau must track the model-free mean-arrival-time
    # lifetime (a robust, IRF-tail-immune reference) to within ~30%.
    w = fitted_wizard
    for det, chs in (("green", [0, 1]), ("red", [8, 9])):
        w.comboBox_window.setCurrentText(det)
        w.auto_extract_irf_bg()
        tau = w.doubleSpinBox_tau_result.value()
        ref = _mean_arrival_lifetime(w, det, chs)
        assert ref > 0
        assert abs(tau - ref) / ref < 0.35, (
            f"{det}: fitted tau={tau:.3f} ns far from model-free {ref:.3f} ns "
            f"(IRF-tail bias?)"
        )


def test_tail_fit_recovers_a_plausible_lifetime(fitted_wizard):
    """The multi-exponential tail fit runs from the wizard and recovers a tau.

    The tail model (``DecayFitNExp`` with ``tail_start``) is a different
    estimator family from the fit2x models: it fits pure exponentials from a
    start channel with no IRF deconvolution — the standard treatment for FRET
    sensitised-emission decays. Selecting it must rebuild the schema-driven
    editor (a ``tail_start`` channel + lifetime rows), fit, and land a physical
    lifetime in the result field.
    """
    from qtpy import QtWidgets

    w = fitted_wizard
    w.comboBox_window.setCurrentText("green")
    QtWidgets.QApplication.processEvents()

    idx = w.comboBox_fit_model.findData("tail")
    assert idx >= 0, "tail fit not offered in the model combo"
    w.comboBox_fit_model.setCurrentIndex(idx)
    QtWidgets.QApplication.processEvents()

    # the schema-driven editor shows the tail-start channel + a lifetime row
    assert "tail_start" in w._dyn_params
    assert any(k.startswith("tau") for k in w._dyn_params)

    # place the tail start inside the filled fit window and refit
    sb, eb = w.micro_time_range
    w._dyn_params["tail_start"]["spin"].setValue(float(sb + max(1, (eb - sb) // 5)))
    w.update_fit()
    QtWidgets.QApplication.processEvents()

    tau = w._dyn_params["tau1"]["result"].value()
    assert 0.2 < tau < 8.0, f"tail-fit tau railed/implausible: {tau}"

    # the model curve was drawn (no blank Intensity panel)
    items = w.combined_plot.listDataItems()
    assert any(
        (it.getData()[1] is not None and len(it.getData()[1]) > 0) for it in items
    )


def test_burst_result_columns_are_model_specific():
    """The batch export column set follows the fitted model.

    ``fit23`` keeps its historical layout (tau/gamma/r0/rho + the two anisotropy
    columns); fit24/fit25 drop the anisotropy columns and write one column per
    registry free parameter. ``Tau`` (the best lifetime) is present for every
    model so downstream burst plots key on it uniformly.
    """
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    col = MLELifetimeAnalysisWizard._burst_result_columns
    c23 = col("green", "fit23", ["tau", "gamma", "r0", "rho"])
    assert "Tau (green)" in c23
    assert "r0 (green)" in c23 and "rho (green)" in c23
    assert "r Scatter (green)" in c23 and "r Experimental (green)" in c23

    c24 = col("green", "fit24", ["tau1", "gamma", "tau2", "A2", "offset"])
    assert "Tau (green)" in c24
    assert {"tau1 (green)", "tau2 (green)", "A2 (green)", "offset (green)"} <= set(c24)
    # anisotropy columns are fit23-only
    assert "r Scatter (green)" not in c24 and "r0 (green)" not in c24

    c25 = col("green", "fit25", ["tau1", "tau2", "tau3", "tau4", "gamma", "r0"])
    assert {"tau1 (green)", "tau4 (green)", "gamma (green)"} <= set(c25)
    assert "r Experimental (green)" not in c25


def _synthetic_worker_job(model, method, param_names, x0, fixed, *, n=64,
                          tau_true=2.0, dt=0.05):
    """Build a one-burst shared-memory job for ``process_one_file_worker``.

    Emits a mono-exponential parallel/perpendicular decay as a photon list
    (routing 0=P, 1=S) so the worker rebuilds the histogram exactly as it does
    for real data. Returns ``(args, shm_blocks)``; the caller must close/unlink
    the blocks.
    """
    from multiprocessing import shared_memory

    rng = np.random.default_rng(0)
    bins = np.arange(n)
    shape = np.exp(-bins * dt / tau_true)
    cp = rng.poisson(shape * 400).astype(int)
    cs = rng.poisson(shape * 120).astype(int)
    rc = np.concatenate([np.repeat(0, cp.sum()), np.repeat(1, cs.sum())]).astype(np.uint16)
    mt = np.concatenate([np.repeat(bins, cp), np.repeat(bins, cs)]).astype(np.uint16)

    rc_shm = shared_memory.SharedMemory(create=True, size=rc.nbytes)
    np.ndarray(rc.shape, dtype=rc.dtype, buffer=rc_shm.buf)[:] = rc
    mt_shm = shared_memory.SharedMemory(create=True, size=mt.nbytes)
    np.ndarray(mt.shape, dtype=mt.dtype, buffer=mt_shm.buf)[:] = mt

    class_lut = np.array([0, 1], dtype=np.int8)  # rc 0->P, 1->S
    irf = np.zeros(2 * n, dtype=np.float64)
    irf[0] = 1.0            # delta prompt in VV
    irf[n] = 1.0            # delta prompt in VH
    bg = np.zeros(2 * n, dtype=np.float64)
    cfg = {
        'sb': 0, 'eb': n, 'half_len': n,
        'dt': dt, 'period': n * dt,
        'g_factor': 1.0, 'l1': 0.0, 'l2': 0.0,
        'p2s_twoIstar': False, 'BIFL_scatter': False, 'min_photons': 1,
        'x0': np.asarray(x0, dtype=np.float64),
        'fixed': np.asarray(fixed, dtype=np.int32),
        'irf': irf, 'bg': bg, 'class_lut': class_lut,
        'model': model, 'method': method, 'param_names': list(param_names),
    }
    args = ("synthetic.spc", [(0, int(rc.size))],
            rc_shm.name, rc.shape, str(rc.dtype),
            mt_shm.name, mt.shape, str(mt.dtype),
            ["green"], {"green": cfg}, 0, None)
    return args, [rc_shm, mt_shm]


@pytest.mark.parametrize(
    "model, method, names, x0, fixed",
    [
        ("fit24", "Fit24", ["tau1", "gamma", "tau2", "A2", "offset"],
         [2.0, 0.0, 2.0, 0.0, 0.0], [0, 1, 1, 1, 1]),
        ("fit25", "Fit25", ["tau1", "tau2", "tau3", "tau4", "gamma", "r0"],
         [0.5, 1.0, 2.0, 4.0, 0.0, 0.38], [1, 1, 1, 1, 1, 1]),
    ],
)
def test_batch_worker_fits_non_fit23_models(model, method, names, x0, fixed):
    """The multiprocessing worker batch-exports fit24/fit25, not just fit23.

    Runs the real per-file worker on a synthetic mono-exponential burst and
    asserts it produces a finite lifetime and the model's own parameter columns
    (never the fit23-only anisotropy columns), so the export column set and the
    worker records stay in lock-step.
    """
    import tttrlib  # noqa: F401

    from chisurf.plugins.burst.burst_mle_analysis._mp_worker import (
        process_one_file_worker,
    )

    args, blocks = _synthetic_worker_job(model, method, names, x0, fixed)
    try:
        records, n_bursts = process_one_file_worker(args)
    finally:
        for b in blocks:
            b.close()
            b.unlink()

    assert n_bursts == 1
    assert len(records) == 1
    rec = records[0]
    assert rec["Detector"] == "green"
    # a lifetime came back and the fit-quality column is present (its value is
    # whatever tttrlib returns for the model — it can be NaN for some fixed
    # configs, which the worker passes through unchanged).
    assert np.isfinite(rec["Tau (green)"]) and rec["Tau (green)"] > 0
    assert "2I*  (green)" in rec
    # the model's own free-parameter columns are present ...
    for nm in names:
        assert f"{nm} (green)" in rec
    # ... and the fit23-only anisotropy columns are not.
    assert "r Scatter (green)" not in rec
    assert "r Experimental (green)" not in rec


def test_fit_dt_and_period_come_from_the_file_header():
    """The lifetime is only meaningful if ``dt`` and ``period`` are correct.

    ``Fit23`` measures ``tau`` in units of ``dt`` and convolves over one
    ``period``; both must be nanoseconds, matching the reported lifetime. The
    channel-definition page cannot supply that (its micro-time field is
    picoseconds and neither field is filled from the header), so the wizard
    derives both from the TTTR header. Without this the reported lifetime was in
    arbitrary units — a decay that falls in ~1 ns was labelled "5 ns".
    """
    import tttrlib

    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    spc = DATA / "m000.spc"
    if not spc.exists():
        pytest.skip("raw SPC file not available")
    tttr = tttrlib.TTTR(str(spc), "SPC-130")

    # Exercise the real method without building the (Qt-heavy) wizard.
    class _Stub:
        def __init__(self, t, binning):
            self._t = t
            self.micro_time_binning = binning

        def _current_tttr(self):
            return self._t

    _Stub._header_time_ns = MLELifetimeAnalysisWizard._header_time_ns

    h = tttr.header
    expect_dt = h.micro_time_resolution * 1e9          # ns per channel, binning 1
    expect_period = h.number_of_micro_time_channels * h.micro_time_resolution * 1e9

    for binning in (1, 2, 4):
        dt_ns, period_ns = _Stub(tttr, binning)._header_time_ns()
        assert dt_ns == pytest.approx(expect_dt * binning, rel=1e-9)
        # The period is the full TAC range, independent of binning.
        assert period_ns == pytest.approx(expect_period, rel=1e-9)
        n_binned = h.number_of_micro_time_channels // binning
        assert n_binned * dt_ns == pytest.approx(period_ns, rel=1e-6)

    # These are real nanoseconds, not the 50/50 defaults the page would supply.
    assert expect_dt < 1.0 and 5.0 < expect_period < 200.0


def test_intensity_plot_has_data(fitted_wizard):
    # The Intensity panel must show the decay (and model), not be empty.
    items = fitted_wizard.combined_plot.listDataItems()
    assert items, "Intensity plot is empty after a fit"
    assert any(
        it.getData()[1] is not None and len(it.getData()[1]) > 0 for it in items
    )


def test_decay_plot_has_a_labelled_legend(fitted_wizard):
    # The four overlaid curves (data, model, IRF, background) are only
    # distinguishable by a legend; without it the colours are unlabelled. The
    # legend must exist and carry exactly one row per named series, not a fresh
    # stacked set per fit.
    legend = getattr(fitted_wizard, "combined_legend", None)
    assert legend is not None, "decay plot has no legend"
    labels = {lbl.text for _sample, lbl in legend.items}
    assert {"Data (VV|VH)", "Model (fit)", "IRF", "Background"} <= labels

    # A second replot must not duplicate the rows.
    before = len(legend.items)
    fitted_wizard.refit()
    assert len(legend.items) == before, "legend rows duplicated on replot"


def test_irf_is_not_corrupted_by_detector_switching(fitted_wizard):
    # Regression (single-source-of-truth): switching detectors used to capture the
    # *processed* IRF (shift/threshold applied) and restore it as raw, so repeated
    # A->B->A switches steadily corrupted the pattern. irf_np is now the sole
    # store and must be byte-for-byte stable across switches.
    import numpy as np

    w = fitted_wizard
    # a non-trivial shift/threshold so any re-processing would change the array
    w.shift = 5
    dets = list(w.channel_definer.detectors.keys())
    green0 = np.array(w.irf_np["green"], copy=True)
    for _ in range(3):
        for det in dets:
            w.comboBox_window.setCurrentText(det)
    assert np.array_equal(np.asarray(w.irf_np["green"]), green0), \
        "IRF was mutated by detector switching"


def test_irf_survives_ui_refresh_with_empty_file_widget(fitted_wizard):
    # The real Send-to-MLE regression: an IRF/bg set programmatically (no dropped
    # files) must NOT be destroyed when update_irf_files/update_bg_files run with
    # an empty file widget. Previously _update_hist_files popped the detector,
    # leaving update_fit to bail silently.
    import numpy as np

    det = fitted_wizard.current_detector
    n = int(np.asarray(fitted_wizard.irf_np[det]).size) or 512
    fitted_wizard.irf_np[det] = np.ones(n, float)
    fitted_wizard.bg_np[det] = np.ones(n, float)
    fitted_wizard.update_irf_files()
    fitted_wizard.update_bg_files()
    assert det in fitted_wizard.irf_np and np.asarray(fitted_wizard.irf_np[det]).size > 0
    assert det in fitted_wizard.bg_np and np.asarray(fitted_wizard.bg_np[det]).size > 0


def test_action_buttons_live_in_the_top_toolbar(qapp):
    """Run / Auto-optimize / Auto IRF-BG / Optimize / Save live in one toolbar.

    They used to be scattered across the controls column (Run at the bottom, Save
    next to Min photons, Optimize inside the fit-parameter grid, the one-click
    actions in their own row). They are now consolidated into a single wrapping
    action bar at the top of the Burst-MLE page, hosted as a plain widget (not a
    QMainWindow toolbar) so it shows in the embedded workflow too.
    """
    from qtpy import QtWidgets

    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    w = MLELifetimeAnalysisWizard()
    QtWidgets.QApplication.processEvents()

    bar = w.toolBar_mle
    hosted = (
        w.pushButton_process_bursts,
        w.toolButton_auto_optimize,
        w.toolButton_auto_irf,
        w.comboBox_irf_model,
        w.toolButton_goto_irf,
        w.toolButton_hyper_opt,
        w.spinBox_n_h_opt,
        w.toolButton_save_fit,
    )
    for widget in hosted:
        assert widget.parent() is bar, f"{widget} is not in the toolbar"
    # The bar is embedded in the page (works in the embedded workflow), not an
    # addToolBar() top-level toolbar.
    assert w.isAncestorOf(bar)


def test_fit_page_displays_per_detector_g_factor_l1_l2(qapp):
    """The fit page shows each detector's G factor / l1 / l2 (read-only).

    The corrections live on the detector definition; the Detector Definition tab
    is hidden inside the embedded workflow, so the fit page must surface them.
    They are read-only (calibration constants, edited in the setup) and, crucially,
    switching detectors must NOT corrupt the definition: the g/l1/l2 setters used
    to poke the definition's table cells by row/column and **swapped** one
    detector's l1/l2 onto another on repeated switches (so the fit silently ran
    with the wrong polarisation corrections).
    """
    from qtpy import QtWidgets

    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    channels = {
        "detectors": {
            "green": {"chs": [0, 1], "micro_time_ranges": [],
                      "g_factor": 1.15, "l1": 0.0308, "l2": 0.0368},
            "red": {"chs": [8, 9], "micro_time_ranges": [],
                    "g_factor": 0.92, "l1": 0.05, "l2": 0.06},
        },
        "windows": {}, "file_type": "SPC-130",
    }

    w = MLELifetimeAnalysisWizard()
    QtWidgets.QApplication.processEvents()
    w.channel_definer.load_data_into_tables(channels)
    w.channel_definer.file_type_combo.setCurrentText("SPC-130")
    w._init_channels_from_wizard()
    QtWidgets.QApplication.processEvents()

    # The display fields exist and are read-only.
    for sb in (w.doubleSpinBox_g_factor, w.doubleSpinBox_l1, w.doubleSpinBox_l2):
        assert sb.isReadOnly()

    def displayed():
        return (round(w.doubleSpinBox_g_factor.value(), 4),
                round(w.doubleSpinBox_l1.value(), 4),
                round(w.doubleSpinBox_l2.value(), 4))

    # Repeated switches must keep the display correct and the definition intact.
    for _ in range(3):
        w.comboBox_window.setCurrentText("green")
        QtWidgets.QApplication.processEvents()
        assert displayed() == (1.15, 0.0308, 0.0368)
        w.comboBox_window.setCurrentText("red")
        QtWidgets.QApplication.processEvents()
        assert displayed() == (0.92, 0.05, 0.06)

    dets = w.channel_definer.detectors
    assert (dets["green"]["l1"], dets["green"]["l2"]) == (0.0308, 0.0368)
    assert (dets["red"]["l1"], dets["red"]["l2"]) == (0.05, 0.06)

