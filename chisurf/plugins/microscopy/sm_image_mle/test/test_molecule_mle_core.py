"""Headless tests for the Qt-free molecule-wise MLE core.

Driven by the shared synthetic CLSM generator
(:func:`chisurf.core.fluorescence.imaging.simulate.simulate_clsm_molecules`):
immobile fluorophores of known fluorescence lifetime are raster-scanned into a
marker-annotated TTTR, segmented, and fitted molecule-by-molecule.  The recovered
lifetimes must track the ground truth.  Skips cleanly when tttrlib (or its
simulator) is unavailable.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.imaging.simulate import have_simulator, simulate_clsm_molecules

if not have_simulator():
    pytest.skip("tttrlib built without the photon simulator", allow_module_level=True)

from chisurf.plugins.microscopy.sm_image_mle.core import (
    MoleculeMleResult,
    MoleculeMleSettings,
    fit_molecules,
    segment_molecules,
)

# Two molecules, distinct lifetimes, well separated.
MOLECULES = [(8, 8, 1.0), (23, 23, 3.5)]


def _sim():
    return simulate_clsm_molecules(MOLECULES, n_pixel=32)


def _settings(sim, **overrides) -> MoleculeMleSettings:
    kwargs = dict(
        detector_chs=[0],
        micro_time_range=(0, sim.n_micro),
        micro_time_binning=1,
        irf=sim.vv_vh_irf(),
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
    sim = _sim()
    result = fit_molecules(sim.tttr, _settings(sim), clsm=sim.clsm, dt=sim.dt, period=sim.laser_period)

    assert isinstance(result, MoleculeMleResult)
    assert result.intensity_image.shape == (sim.n_pixel, sim.n_pixel)
    # Both molecules were found (well-separated, bright).
    assert result.n_molecules == len(MOLECULES)

    df = result.dataframe
    expected_cols = {
        "label", "centroid_row", "centroid_col", "area", "n_photons_total",
        "tau", "gamma", "r0", "rho", "2I*",
    }
    assert expected_cols.issubset(set(df.columns))

    tau = df["tau"].to_numpy()
    assert np.all(np.isfinite(tau))
    assert np.all(tau > 0.0)
    # The two distinct lifetimes are recovered in the right order and ballpark.
    assert np.allclose(np.sort(tau), np.sort(sim.true_taus), atol=0.6)


def test_batch_fit_matches_per_molecule():
    # keep_curves=False batches every molecule through one fit_many call;
    # keep_curves=True fits per molecule (to also return model curves). Same result.
    sim = _sim()
    batch = fit_molecules(
        sim.tttr, _settings(sim), clsm=sim.clsm, dt=sim.dt, period=sim.laser_period,
        keep_curves=False,
    )
    serial = fit_molecules(
        sim.tttr, _settings(sim), clsm=sim.clsm, dt=sim.dt, period=sim.laser_period,
        keep_curves=True,
    )
    assert batch.n_molecules == serial.n_molecules == len(MOLECULES)
    for col in ("tau", "gamma", "rho", "2I*"):
        np.testing.assert_allclose(
            batch.dataframe[col].to_numpy(), serial.dataframe[col].to_numpy(), atol=1e-6
        )
    # The batch path skips the per-molecule model curves; the serial path keeps them.
    assert batch.model_curves == []
    assert len(serial.model_curves) == len(MOLECULES)


def test_segment_molecules_counts_bright_spots():
    sim = _sim()
    labels = segment_molecules(sim.intensity, seg_sigma=1.0, peak_footprint_size=6)
    assert int(labels.max()) == len(MOLECULES)


def test_irf_length_mismatch_raises():
    sim = _sim()
    bad = _settings(sim, irf=np.zeros(10))
    with pytest.raises(ValueError):
        fit_molecules(sim.tttr, bad, clsm=sim.clsm, dt=sim.dt, period=sim.laser_period)
