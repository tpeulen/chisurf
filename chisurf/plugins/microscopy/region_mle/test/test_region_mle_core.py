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

from chisurf.core.datastore import column_names, numeric_column

pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.imaging.simulate import have_simulator, simulate_clsm_molecules

if not have_simulator():
    pytest.skip("tttrlib built without the photon simulator", allow_module_level=True)

from chisurf.plugins.microscopy.region_mle.core import (
    RegionMleResult,
    RegionMleSettings,
    fit_regions,
)
from chisurf.plugins.microscopy.spot_finder.core.spots import detect_labels
from chisurf.plugins.microscopy.spot_finder.core.workflow import (
    STANDARD,
    request_from_workflow,
)


def _regions(sim):
    """Return the standard-workflow segmentation of a simulated field.

    The regions come from the spot finder now, which is the point of the split:
    this fit answers for the regions it is handed and finds none of its own.
    """
    labels, _extra = detect_labels(sim.intensity, request_from_workflow(STANDARD).settings)
    return labels

# Two molecules, distinct lifetimes, well separated.
MOLECULES = [(8, 8, 1.0), (23, 23, 3.5)]


def _sim():
    return simulate_clsm_molecules(MOLECULES, n_pixel=32)


def _settings(sim, **overrides) -> RegionMleSettings:
    kwargs = dict(
        detector_chs=[0],
        micro_time_range=(0, sim.n_micro),
        micro_time_binning=1,
        irf=sim.vv_vh_irf(),
        p2s_twoIstar=True,
        regions=_regions(sim),
        min_photons=30,
        tau=2.0,
        fix_r0=True,
        fix_rho=True,
    )
    kwargs.update(overrides)
    return RegionMleSettings(**kwargs)


def test_segments_and_fits_two_simulated_molecules():
    sim = _sim()
    result = fit_regions(sim.tttr, _settings(sim), clsm=sim.clsm, dt=sim.dt, period=sim.laser_period)

    assert isinstance(result, RegionMleResult)
    assert result.intensity_image.shape == (sim.n_pixel, sim.n_pixel)
    # Both molecules were found (well-separated, bright).
    assert result.n_molecules == len(MOLECULES)

    df = result.dataframe
    expected_cols = {
        "label", "centroid_row", "centroid_col", "area", "n_photons_total",
        "tau", "gamma", "r0", "rho", "2I*",
    }
    assert expected_cols.issubset(set(column_names(df)))

    tau = numeric_column(df, "tau")
    assert np.all(np.isfinite(tau))
    assert np.all(tau > 0.0)
    # The two distinct lifetimes are recovered in the right order and ballpark.
    assert np.allclose(np.sort(tau), np.sort(sim.true_taus), atol=0.6)


def _labels_with_an_empty_region(sim):
    """The two real molecules plus a region drawn over bare background.

    A per-region map is only as trustworthy as its worst region, and the worst
    region is one the fit cannot answer for. Segmenting a clean simulation never
    produces one, so it is drawn: a third label on a patch with (almost) no
    photons, which is fitted anyway once ``min_photons`` is dropped.
    """
    labels = np.array(_regions(sim), copy=True)
    labels[0:4, 0:4] = int(labels.max()) + 1
    return labels


@pytest.mark.parametrize("with_a_failing_region", [False, True])
def test_batch_fit_matches_per_molecule(with_a_failing_region):
    """``keep_curves=False`` batches; ``keep_curves=True`` loops. Same table.

    Every numeric column is compared, not a chosen four: the batch path used to
    hard-code ``r_scatter``/``r_experimental`` to NaN because it unpacked the
    batch as a bare 5-tuple, and a test that only looked at ``tau``/``gamma``/
    ``rho``/``2I*`` could not see two columns of the region table going blank.

    The parametrised half adds a region the fit fails on — the case where a batch
    kernel diverges from a loop, and where a dropped or reordered row would
    silently attach one molecule's lifetime to another's centroid.
    """
    sim = _sim()
    common = dict(clsm=sim.clsm, dt=sim.dt, period=sim.laser_period)
    overrides = (
        dict(regions=_labels_with_an_empty_region(sim), min_photons=0)
        if with_a_failing_region else {}
    )
    batch = fit_regions(
        sim.tttr, _settings(sim, **overrides), keep_curves=False, **common
    )
    serial = fit_regions(
        sim.tttr, _settings(sim, **overrides), keep_curves=True, **common
    )
    assert batch.n_molecules == serial.n_molecules
    assert batch.n_molecules == len(MOLECULES) + int(with_a_failing_region)
    assert column_names(batch.dataframe) == column_names(serial.dataframe)
    for col in column_names(batch.dataframe):
        left, right = numeric_column(batch.dataframe, col), numeric_column(serial.dataframe, col)
        np.testing.assert_array_equal(
            left, right, err_msg=f"column {col!r} differs between the batch and the loop"
        )
    # The batch path skips the per-molecule model curves; the serial path keeps them.
    assert batch.model_curves == []
    assert len(serial.model_curves) == batch.n_molecules
    # The derived anisotropies really are reported by the batch, not blanked —
    # the whole column used to be NaN whichever region it described.
    assert np.isfinite(numeric_column(batch.dataframe, "r_scatter")).any()
    if with_a_failing_region:
        # ...and the drawn region really did fail, or this proves nothing. A
        # region with no photons is the estimator's clearest failure: it hands
        # the start value straight back and reports no anisotropy. Both paths
        # must say that about the *same* row — which is what the column-wise
        # comparison above has just checked.
        rows = np.isnan(numeric_column(batch.dataframe, "r_scatter"))
        assert rows.any(), "the drawn region was fitted successfully"
        assert numeric_column(batch.dataframe, "tau")[rows] == pytest.approx(2.0)


def test_the_standard_workflow_finds_the_simulated_molecules():
    sim = _sim()
    assert int(_regions(sim).max()) == len(MOLECULES)


def test_irf_length_mismatch_raises():
    sim = _sim()
    bad = _settings(sim, irf=np.zeros(10))
    with pytest.raises(ValueError):
        fit_regions(sim.tttr, bad, clsm=sim.clsm, dt=sim.dt, period=sim.laser_period)


# --- foreground and background as regions -----------------------------------
def test_an_analysis_roi_confines_the_search():
    """A drawn region restricts which molecules are looked for at all.

    The frame holds two molecules; a rectangle around one of them must find
    exactly that one — this is how a single cell, or one illuminated patch, is
    analysed without the rest of the field taking part.
    """
    from chisurf.core.roi import RectangleROI

    sim = _sim()
    # (x0, y0, x1, y1) around the molecule at (row 8, col 8) only.
    around_first = RectangleROI(0, 0, 16, 16, name="patch")
    result = fit_regions(
        sim.tttr, _settings(sim, roi=around_first), clsm=sim.clsm,
        dt=sim.dt, period=sim.laser_period,
    )
    assert result.n_molecules == 1
    row, col = result.centroids[0]
    assert row < 16 and col < 16
    assert numeric_column(result.dataframe, "tau")[0] == pytest.approx(MOLECULES[0][2], abs=0.6)


def test_a_serialised_roi_survives_the_trip_through_settings():
    """Settings cross an RPC boundary as plain data, so the region must too."""
    from chisurf.core.roi import RectangleROI

    sim = _sim()
    as_dict = RectangleROI(0, 0, 16, 16).to_dict()
    result = fit_regions(
        sim.tttr, _settings(sim, roi=as_dict), clsm=sim.clsm,
        dt=sim.dt, period=sim.laser_period,
    )
    assert result.n_molecules == 1
    assert result.analysis_roi is not None


def test_foreground_and_background_partition_the_frame():
    """The molecules and the region used to judge them are both ROIs.

    Background is not simply "not a molecule": the pixels touching a molecule
    still carry its PSF tail, so the margin has to push them out, or the
    background rate reads high and every molecule looks dimmer than it is.
    """
    sim = _sim()
    result = fit_regions(
        sim.tttr, _settings(sim), clsm=sim.clsm, dt=sim.dt, period=sim.laser_period
    )
    shape = result.intensity_image.shape

    foreground = result.foreground_roi().to_mask(shape)
    background = result.background_roi(margin=2).to_mask(shape)
    assert not (foreground & background).any()
    assert foreground.sum() > 0
    assert background.sum() > foreground.sum()

    # A wider margin can only shrink the background.
    assert result.background_roi(margin=4).to_mask(shape).sum() <= background.sum()

    # ... and the molecules are far brighter than what is left over.
    assert result.background_rate() < numeric_column(result.dataframe, "intensity_mean").min()


def test_the_result_exposes_full_region_measurements():
    """Every molecule is measurable with the shared region properties."""
    sim = _sim()
    result = fit_regions(
        sim.tttr, _settings(sim), clsm=sim.clsm, dt=sim.dt, period=sim.laser_period
    )
    props = result.region_properties()
    assert len(props) == result.n_molecules
    for prop, (_, _, _) in zip(props, MOLECULES):
        assert prop.area > 0
        assert 0.0 <= prop.solidity <= 1.0
        assert prop.intensity_max > 0
    # The table's shape columns are those measurements, not a second opinion.
    np.testing.assert_allclose(
        numeric_column(result.dataframe, "area"), [p.area for p in props]
    )


def test_the_preview_and_the_fit_use_the_same_regions():
    """Not "the same settings" — the same regions, resolved by one call."""
    from chisurf.plugins.microscopy.region_mle.core.region_mle import region_preview

    sim = _sim()
    settings = _settings(sim)
    preview = region_preview(sim.intensity, settings)
    fitted = fit_regions(
        sim.tttr, settings, clsm=sim.clsm, dt=sim.dt, period=sim.laser_period
    )
    assert preview.n_molecules == fitted.n_molecules
    np.testing.assert_array_equal(preview.label_image, fitted.label_image)
    assert np.isnan(numeric_column(preview.dataframe, "tau")).all()
