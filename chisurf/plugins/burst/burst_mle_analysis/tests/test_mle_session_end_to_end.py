"""End-to-end test of the burst MLE-lifetime session on real smFRET data (in-repo BH SPC-132 sample).

Drives the engine the way the workflow does -- set detectors, load a .bur, build the decay, provide IRF/background,
run the fit -- and asserts the results are sane. This catches the silent-failure bugs where the current detector
loses its IRF (so the fit bails) and the decay/plot end up empty. It replaces the end-to-end test of the retired Qt
wizard: the numbers that wizard gave are recorded in ``qt_reference.json`` and compared in ``test_mle_engine.py``;
here are the behaviours.

The data is the in-repository ``burst_selection/tests/data/bh_spc132_sm_dna`` folder (real photons, no download). The
engine writes its result tables next to the burst files, so the tests work on a temporary copy.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.burst.burst_mle_analysis import engine

from .conftest import BURST_TABLE, CHANNEL_SETTINGS, REPO_DATA

DATA = REPO_DATA  # read-only uses (headers); fits run on the temporary copy
BUR = REPO_DATA / BURST_TABLE
HANDOFF = REPO_DATA / "burst_analysis_handoff" / "burst_analysis_handoff.json"

pytestmark = pytest.mark.skipif(
    not (BUR.exists() and HANDOFF.exists()),
    reason="in-repo BH smFRET DNA test data missing",
)


@pytest.fixture
def fitted(sample_copy):
    """A session with channels, a burst file, IRF/bg and one fit run for green (the one-click path).

    ``auto_extract`` is the foolproof workflow: it auto-selects the micro-time binning and fit window and
    estimates the IRF/bg from the non-burst photons.
    """
    s = engine.MleSession()
    s.set_detectors(CHANNEL_SETTINGS["detectors"], CHANNEL_SETTINGS["file_type"])
    s.add_burst_files([sample_copy / BURST_TABLE])
    s.current_detector = "green"
    s.auto_extract()
    return s


def test_detector_state_has_no_empty_detector(fitted):
    # A spurious "" detector must never appear (it shadowed the real one).
    for store in (fitted.irf_np, fitted.bg_np, fitted.det_settings):
        assert "" not in store
        assert None not in store


def test_current_detector_keeps_its_irf(fitted):
    # The regression: the current detector lost its IRF, so the fit silently bailed.
    det = fitted.current_detector
    assert det in fitted.irf_np, "current detector lost its IRF"
    assert det in fitted.bg_np
    assert np.asarray(fitted.irf_np[det]).size > 0


def test_decay_is_built(fitted):
    decay = fitted.decay
    assert decay is not None, "decay was never built (blank Intensity plot)"
    decay = np.asarray(decay)
    assert decay.size > 0 and decay.sum() > 0


def test_fit_produces_a_plausible_lifetime(fitted):
    # tau must move off the initial and land in a physical range; a silent no-fit leaves it at the initial / zero.
    tau = float(fitted.outcome.x[0])
    assert 0.1 < tau < 10.0, f"implausible / non-fit tau={tau}"


def test_auto_extract_coarsens_the_sparse_default_binning(fitted):
    # The bug: at the sparse default binning (1) the ~8.6k burst photons are ~1 count/bin over the 2x4096
    # histogram, and the maximum-likelihood fit rails tau to the excitation period. Auto-selection must coarsen
    # the axis so the bins carry counts (and not below the IRF resolution).
    assert fitted.settings.micro_time_binning > 1


def test_auto_extract_restricts_the_fit_window_to_the_filled_region(fitted):
    # The window must exclude the empty pre-prompt bins and the noise tail, i.e. be genuinely narrower than the
    # whole half.
    sb, eb = fitted.micro_time_range
    n_half = int(np.asarray(fitted.decay).size) // 2
    assert 0 <= sb < eb <= n_half
    assert (eb - sb) < n_half, "window was not restricted to the filled region"


def test_auto_extract_gives_a_physical_lifetime_for_every_colour(fitted):
    # Both the green (donor) and red (acceptor) decays must recover a physical single-molecule lifetime through
    # the one-click path -- no railing.
    for det in ("green", "red"):
        fitted.current_detector = det
        fitted.auto_extract()
        tau = float(fitted.outcome.x[0])
        assert 0.5 < tau < 5.0, f"{det} tau railed/implausible: {tau}"


def test_the_one_click_values_are_the_wizards(fitted, qt_reference):
    # The retired Qt wizard's Auto button (binning and window) and its auto-optimise gave the green one-click
    # values again; both are recorded, so the engine's one-click path is held to them.
    ref = qt_reference["end_to_end"]
    assert fitted.settings.micro_time_binning == ref["green_binning"]
    assert list(fitted.micro_time_range) == ref["green_range"]
    assert float(fitted.outcome.x[0]) == pytest.approx(ref["green_tau"], abs=6e-4)
    assert fitted.settings.micro_time_binning == ref["auto_optimize"]["binning"]
    assert list(fitted.micro_time_range) == ref["auto_optimize"]["range"]
    assert float(fitted.outcome.x[0]) == pytest.approx(ref["auto_optimize"]["tau"], abs=6e-4)
    fitted.current_detector = "red"
    fitted.auto_extract()
    assert float(fitted.outcome.x[0]) == pytest.approx(ref["red_tau"], abs=6e-4)


def _mean_arrival_lifetime(session, chs):
    """Model-free lifetime: mean burst micro-time minus the scatter prompt."""
    tttr = session.current_tttr()
    idx = np.asarray(session.burst_indices(), dtype=int)
    micro = np.asarray(tttr.micro_times)
    rout = np.asarray(tttr.routing_channels)
    micro_ns = tttr.header.micro_time_resolution * 1e9
    in_burst = np.zeros(len(tttr), bool)
    in_burst[idx] = True
    par = chs[0]
    burst = micro[in_burst & (rout == par)] * micro_ns
    prompt_bin = np.bincount(micro[~in_burst & (rout == par)]).argmax()
    return float(burst.mean() - prompt_bin * micro_ns)


def test_auto_extract_lifetime_matches_model_free_estimate(fitted):
    # The regression this guards: an IRF taken straight from the non-burst histogram carries a fluorescence tail
    # (dim/passing molecules), and convolving with it biased the fitted lifetime ~2x short (a ~2.2 ns decay fit as
    # ~1.1 ns). The extraction models the IRF as a tail-free Gaussian at the prompt, so the fitted tau must track
    # the model-free mean-arrival-time lifetime (a robust, IRF-tail-immune reference) to within ~30%.
    for det, chs in (("green", [0, 1]), ("red", [8, 9])):
        fitted.current_detector = det
        fitted.auto_extract()
        tau = float(fitted.outcome.x[0])
        ref = _mean_arrival_lifetime(fitted, chs)
        assert ref > 0
        assert abs(tau - ref) / ref < 0.35, (
            f"{det}: fitted tau={tau:.3f} ns far from model-free {ref:.3f} ns (IRF-tail bias?)"
        )


def test_tail_fit_recovers_a_plausible_lifetime(fitted, qt_reference):
    """The multi-exponential tail fit runs and recovers the lifetime the Qt wizard gave on this sample.

    The tail model (``DecayFitNExp`` with ``tail_start``) is a different estimator family from the fit2x models: it
    fits pure exponentials from a start channel with no IRF deconvolution -- the standard treatment for FRET
    sensitised-emission decays.
    """
    ref = qt_reference["end_to_end"]["tail"]
    fitted.set_model(engine.TAIL_MODEL)
    names, _values, _fixed = fitted.settings.parameter_state()
    assert names == ref["names"]
    assert any(name.startswith("tau") for name in names)
    sb, eb = fitted.micro_time_range
    tail_start = float(sb + max(1, (eb - sb) // 5))
    assert tail_start == ref["tail_start"]
    fitted.settings.edit_parameter("tail_start", tail_start, fixed=False)
    outcome = fitted.fit()
    assert outcome is not None, fitted.status
    tau = float(outcome.x[names.index("tau1")])
    assert 0.2 < tau < 8.0, f"tail-fit tau railed/implausible: {tau}"
    assert tau == pytest.approx(ref["tau1"], rel=1e-6)
    # the model curve was drawn (no blank Intensity panel)
    assert outcome.curves.model.size == ref["model_size"] and outcome.curves.model.any()


def test_burst_result_columns_are_model_specific():
    """The batch export column set follows the fitted model.

    ``fit23`` keeps its historical layout (tau/gamma/r0/rho + the two anisotropy columns); fit24/fit25 drop the
    anisotropy columns and write one column per registry free parameter. ``Tau`` (the best lifetime) is present for
    every model so downstream burst plots key on it uniformly.
    """
    col = engine.burst_result_columns
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


def _synthetic_worker_job(model, method, param_names, x0, fixed, *, n=64, tau_true=2.0, dt=0.05):
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
    irf[0] = 1.0  # delta prompt in VV
    irf[n] = 1.0  # delta prompt in VH
    bg = np.zeros(2 * n, dtype=np.float64)
    cfg = {
        "sb": 0,
        "eb": n,
        "half_len": n,
        "dt": dt,
        "period": n * dt,
        "g_factor": 1.0,
        "l1": 0.0,
        "l2": 0.0,
        "p2s_twoIstar": False,
        "BIFL_scatter": False,
        "min_photons": 1,
        "x0": np.asarray(x0, dtype=np.float64),
        "fixed": np.asarray(fixed, dtype=np.int32),
        "irf": irf,
        "bg": bg,
        "class_lut": class_lut,
        "model": model,
        "method": method,
        "param_names": list(param_names),
    }
    args = (
        "synthetic.spc",
        [(0, int(rc.size))],
        rc_shm.name,
        rc.shape,
        str(rc.dtype),
        mt_shm.name,
        mt.shape,
        str(mt.dtype),
        ["green"],
        {"green": cfg},
        0,
        None,
    )
    return args, [rc_shm, mt_shm]


@pytest.mark.parametrize(
    "model, method, names, x0, fixed",
    [
        (
            "fit24",
            "Fit24",
            ["tau1", "gamma", "tau2", "A2", "offset"],
            [2.0, 0.0, 2.0, 0.0, 0.0],
            [0, 1, 1, 1, 1],
        ),
        (
            "fit25",
            "Fit25",
            ["tau1", "tau2", "tau3", "tau4", "gamma", "r0"],
            [0.5, 1.0, 2.0, 4.0, 0.0, 0.38],
            [1, 1, 1, 1, 1, 1],
        ),
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

    ``Fit23`` measures ``tau`` in units of ``dt`` and convolves over one ``period``; both must be nanoseconds,
    matching the reported lifetime. The channel-definition page cannot supply that (its micro-time field is
    picoseconds and neither field is filled from the header), so the engine derives both from the TTTR header.
    Without this the reported lifetime was in arbitrary units -- a decay that falls in ~1 ns was labelled "5 ns".
    """
    import tttrlib

    spc = DATA / "m000.spc"
    if not spc.exists():
        pytest.skip("raw SPC file not available")
    tttr = tttrlib.TTTR(str(spc), "SPC-130")
    h = tttr.header
    expect_dt = h.micro_time_resolution * 1e9  # ns per channel, binning 1
    expect_period = h.number_of_micro_time_channels * h.micro_time_resolution * 1e9

    for binning in (1, 2, 4):
        dt_ns, period_ns = engine.header_time_ns(tttr, binning)
        assert dt_ns == pytest.approx(expect_dt * binning, rel=1e-9)
        # The period is the full TAC range, independent of binning.
        assert period_ns == pytest.approx(expect_period, rel=1e-9)
        n_binned = h.number_of_micro_time_channels // binning
        assert n_binned * dt_ns == pytest.approx(period_ns, rel=1e-6)

    # These are real nanoseconds, not the 50/50 defaults the page would supply.
    assert expect_dt < 1.0 and 5.0 < expect_period < 200.0


def test_the_decay_plot_has_data_and_a_curve_for_every_series(fitted):
    # The Intensity panel must show the decay (and model), not be empty; the four overlaid curves (data, model,
    # IRF, background) are what the panel draws under their names.
    curves = fitted.outcome.curves
    assert curves.data.size > 0 and curves.data.sum() > 0
    assert curves.model.size == curves.data.size and curves.model.any()
    assert curves.irf is not None and curves.background is not None


def test_irf_is_not_corrupted_by_detector_switching(fitted):
    # Regression (single-source-of-truth): switching detectors used to capture the *processed* IRF (shift/threshold
    # applied) and restore it as raw, so repeated A->B->A switches steadily corrupted the pattern. irf_np is the
    # sole store and must be byte-for-byte stable across switches.
    fitted.settings.shift = 5  # a non-trivial shift so any re-processing would change the array
    green0 = np.array(fitted.irf_np["green"], copy=True)
    for _ in range(3):
        for det in fitted.detectors:
            fitted.current_detector = det
            fitted.build_decay()
    assert np.array_equal(np.asarray(fitted.irf_np["green"]), green0), (
        "IRF was mutated by detector switching"
    )


def test_irf_survives_a_pattern_refresh_with_no_files(fitted):
    # The real Send-to-MLE regression: an IRF/bg set programmatically (no measured files) must NOT be destroyed
    # when the measured-file patterns are refreshed. Previously the refresh popped the detector, leaving the fit
    # to bail silently.
    det = fitted.current_detector
    n = int(np.asarray(fitted.irf_np[det]).size) or 512
    fitted.irf_np[det] = np.ones(n, float)
    fitted.bg_np[det] = np.ones(n, float)
    fitted.refresh_pattern_files()
    assert det in fitted.irf_np and np.asarray(fitted.irf_np[det]).size > 0
    assert det in fitted.bg_np and np.asarray(fitted.bg_np[det]).size > 0


def test_the_panel_displays_each_detectors_g_factor_l1_l2_and_switching_does_not_corrupt_them():
    """The panel shows each detector's G factor / l1 / l2 (read-only text).

    The corrections live on the detector definition. They are read-only (calibration constants, edited in the
    detector setup) and, crucially, switching detectors must NOT corrupt the definition: the Qt setters poked the
    definition's table cells by row/column and **swapped** one detector's l1/l2 onto another on repeated switches
    (so the fit silently ran with the wrong polarisation corrections).
    """
    from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel

    channels = {
        "green": {
            "chs": [0, 1],
            "micro_time_ranges": [],
            "g_factor": 1.15,
            "l1": 0.0308,
            "l2": 0.0368,
        },
        "red": {"chs": [8, 9], "micro_time_ranges": [], "g_factor": 0.92, "l1": 0.05, "l2": 0.06},
    }
    model = MleViewModel()
    model.session.set_detectors(channels, "SPC-130")
    model.session.current_detector = "green"
    for _ in range(3):
        model.current_detector = "green"
        assert model.calibration_text().startswith("G 1.1500, l1 0.0308, l2 0.0368")
        model.current_detector = "red"
        assert model.calibration_text().startswith("G 0.9200, l1 0.0500, l2 0.0600")
    dets = model.session.detectors
    assert (dets["green"]["l1"], dets["green"]["l2"]) == (0.0308, 0.0368)
    assert (dets["red"]["l1"], dets["red"]["l2"]) == (0.05, 0.06)
