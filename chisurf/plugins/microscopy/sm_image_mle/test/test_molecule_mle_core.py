"""Headless tests for the Qt-free molecule-wise MLE core.

Driven entirely by a *simulated* CLSM image built with tttrlib's photon
simulator (``SimEngine``/``SimScanner``): immobile fluorophores of known
fluorescence lifetime are placed at well-separated pixels, raster-scanned into a
marker-annotated TTTR, segmented, and fitted molecule-by-molecule.  The recovered
lifetimes must track the ground truth.  Skips cleanly when tttrlib (or its
simulator) is unavailable.
"""

from __future__ import annotations

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

if not hasattr(tttrlib, "SimEngine"):
    pytest.skip("tttrlib built without the photon simulator", allow_module_level=True)

from chisurf.core.fluorescence.mle import assemble_jordi
from chisurf.plugins.microscopy.sm_image_mle.core import (
    MoleculeMleResult,
    MoleculeMleSettings,
    fit_molecules,
    segment_molecules,
)

# --- simulation constants ---
N, PX = 32, 0.5  # 32x32 image, 0.5 µm pixels
N_MICRO, DT = 256, 0.032  # 256 micro-time channels, 0.032 ns each
LASER = N_MICRO * DT  # excitation period (ns)
IRF_CENTER, IRF_SIGMA = 10.0, 1.6
# (ix, iy, tau_ns) — two molecules, distinct lifetimes, far apart.
MOLECULES = [(8, 8, 1.0), (23, 23, 3.5)]


def _vd(x):
    return tttrlib.VectorDouble([float(v) for v in x])


def _irf_kernel() -> np.ndarray:
    k = np.exp(-0.5 * ((np.arange(N_MICRO) - IRF_CENTER) / IRF_SIGMA) ** 2)
    return k / k.sum()


def _simulate_clsm_image():
    """Simulate a CLSM raster scan of the molecules; return a marker TTTR."""
    t = np.arange(N_MICRO) * DT
    irf_kernel = _irf_kernel()
    taus = sorted({tau for _, _, tau in MOLECULES})

    sample = tttrlib.SimSystem()
    for tau in taus:
        pattern = np.convolve(np.exp(-t / tau), irf_kernel)[:N_MICRO]
        dec = tttrlib.SimDecay.from_pattern(pattern.tolist(), DT, 0.0)
        sp = tttrlib.SimSpecies()
        sp.D = 0.0
        sp.q = _vd([3000.0])
        sp.r0 = 0.0
        sp.decay = dec
        sample.add_species(sp)
    n_sp = len(taus)
    sample.set_rate_matrices([0.0] * n_sp * n_sp, [0.0] * n_sp * n_sp)
    sample.set_background([0.0])
    for ix, iy, tau in MOLECULES:
        sample.add_fluorophore(ix * PX, iy * PX, 0.0, taus.index(tau), False)

    exc = tttrlib.SimGrid.gaussian3d(0.3, 1.0, 0.8, 1.0, 0.04, 1.0)
    integ = tttrlib.SimIntegrator()
    integ.dt = 0.01
    integ.n_channels = 1
    integ.n_ph_max = 10**9
    integ.n_microtime_channels = N_MICRO
    integ.microtime_resolution = DT
    integ.laser_period = LASER
    engine = tttrlib.SimEngine(sample, exc, tttrlib.VectorSimGrid([]), integ)
    engine.run_scan(
        tttrlib.SimScanner.uniform(N, N, 0.12, PX, PX, 0.0, 0.0, tttrlib.SimMarkerConfig(), False)
    )

    macro = np.asarray(engine.macro_window(), np.uint64)
    micro = np.asarray(engine.micro_time(), np.uint16)
    routing = np.asarray(engine.channel(), np.int8)
    event = np.asarray(engine.event_type(), np.int8)
    data = tttrlib.TTTR(macro, micro, routing, event)
    clsm = tttrlib.CLSMImage(
        tttr_data=data,
        marker_frame_start=[4],
        marker_line_start=1,
        marker_line_stop=2,
        n_pixel_per_line=N,
        use_pixel_markers=True,
        marker_pixel=8,
        settings={"n_lines": N},
    )
    clsm.fill(data, channels=[0])
    return clsm, data


def _settings(**overrides) -> MoleculeMleSettings:
    irf1 = _irf_kernel()
    kwargs = dict(
        detector_chs=[0],
        micro_time_range=(0, N_MICRO),
        micro_time_binning=1,
        irf=assemble_jordi(irf1, irf1),
        p2s_twoIstar=True,
        seg_sigma=1.0,
        peak_footprint_size=6,
        min_photons=30,
        tau=2.0,
        fix_r0=True,
        fix_rho=True,
    )
    kwargs.update(overrides)
    return MoleculeMleSettings(**kwargs)


def test_segments_and_fits_two_simulated_molecules():
    clsm, data = _simulate_clsm_image()
    result = fit_molecules(data, _settings(), clsm=clsm, dt=DT, period=LASER)

    assert isinstance(result, MoleculeMleResult)
    assert result.intensity_image.shape == (N, N)
    # Both molecules were found (well-separated, bright).
    assert result.n_molecules == len(MOLECULES)

    df = result.dataframe
    expected_cols = {
        "label",
        "centroid_row",
        "centroid_col",
        "area",
        "n_photons_total",
        "tau",
        "gamma",
        "r0",
        "rho",
        "2I*",
    }
    assert expected_cols.issubset(set(df.columns))

    tau = df["tau"].to_numpy()
    assert np.all(np.isfinite(tau))
    assert np.all(tau > 0.0)
    # The two distinct lifetimes are recovered in the right order and ballpark.
    taus_sorted = np.sort(tau)
    true_sorted = np.sort([m[2] for m in MOLECULES])
    assert np.allclose(taus_sorted, true_sorted, atol=0.6)


def test_segment_molecules_counts_bright_spots():
    clsm, _ = _simulate_clsm_image()
    intensity = np.asarray(clsm.intensity).sum(axis=0)
    labels = segment_molecules(intensity, seg_sigma=1.0, peak_footprint_size=6)
    assert int(labels.max()) == len(MOLECULES)


def test_irf_length_mismatch_raises():
    _clsm, data = _simulate_clsm_image()
    bad = _settings(irf=np.zeros(10))
    with pytest.raises(ValueError):
        fit_molecules(data, bad, dt=DT, period=LASER)
