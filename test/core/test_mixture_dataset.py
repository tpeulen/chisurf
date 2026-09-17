"""The simulated mixture: four blobs, four lifetimes, one field, two channels.

The test set the whole detect-then-fit split is aimed at. It is a *simulation*,
so the answer is known — which is the only way to tell a segmentation that found
four objects from one that found four things, and a fit that recovered a
lifetime from one that returned a number.

Two PTUs: the scan, and the IRF measurement that belongs to it (a simulated
scatterer through the same optics, the same two channels and the same
micro-time axis, so the fit is not handed a noiseless IRF against noisy data).

They are **generated, not committed**. The simulator is seeded, so the files are
reproducible — which is what a test set has to be — and generating them keeps
two megabytes of binary out of the history and, more usefully, keeps the fixture
and the code that makes it from drifting apart: it is the *same* generator the
tools' guided tour calls, so a demo that stops working fails here first.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.microscopy.spot_finder.demo import DEMO_BLOBS, truth_table

#: What was simulated: (ix, iy, tau). The image is indexed (row=iy, col=ix).
BLOBS = DEMO_BLOBS
_TRUTH = truth_table()
N_PIXEL = _TRUTH["n_pixel"]
N_MICRO = _TRUTH["n_micro"]
DT = _TRUTH["dt"]


@pytest.fixture(scope="session")
def demo_files(tmp_path_factory):
    """Generate the test set once per session, into a scratch directory."""
    from chisurf.core.fluorescence.imaging.simulate import have_simulator
    from chisurf.plugins.microscopy.spot_finder.demo import create_demo

    if not have_simulator():
        pytest.skip("tttrlib was built without the photon simulator")
    return create_demo(tmp_path_factory.mktemp("mixture"))


@pytest.fixture(scope="module")
def scan(demo_files):
    """Return the sample scan, reconstructed the way the scanner wrote it."""
    import tttrlib

    from chisurf.core.fluorescence.imaging.simulate import clsm_from_scan

    sample, _irf = demo_files
    tttr = tttrlib.TTTR(str(sample))
    return tttr, clsm_from_scan(tttr, N_PIXEL)


@pytest.fixture(scope="module")
def intensity(scan):
    _tttr, clsm = scan
    return np.asarray(clsm.intensity).sum(axis=0).astype(float)


def test_the_scan_reopens_with_both_detection_channels(scan):
    """A VV/VH estimator needs two channels, and a written file must keep them."""
    tttr, clsm = scan
    channels = sorted(set(np.asarray(tttr.routing_channels).tolist()))

    assert 0 in channels and 1 in channels, channels
    image = np.asarray(clsm.intensity)
    assert image.shape[-2:] == (N_PIXEL, N_PIXEL)
    assert image.sum() > 0, (
        "the image is empty: the markers did not survive, or it was "
        "reconstructed without the scanner's own marker settings"
    )


def test_the_two_channels_carry_different_decays(scan):
    """Anisotropy is what makes VV and VH two measurements rather than one twice."""
    tttr, _clsm = scan
    channels = np.asarray(tttr.routing_channels)
    micro = np.asarray(tttr.micro_times)

    vv = micro[channels == 0]
    vh = micro[channels == 1]

    assert vv.size > 1000 and vh.size > 1000
    # Different populations, not the same curve twice: the parallel channel
    # collects more, and their mean arrival times differ.
    assert vv.size != vh.size
    assert abs(float(vv.mean()) - float(vh.mean())) > 0.1


def test_the_standard_workflow_finds_every_blob(intensity):
    """Segmentation, judged against the truth rather than against a count."""
    from chisurf.core.roi import regionprops
    from chisurf.plugins.microscopy.spot_finder.core.spots import detect_labels
    from chisurf.plugins.microscopy.spot_finder.core.workflow import (
        STANDARD,
        request_from_workflow,
    )

    settings = request_from_workflow(STANDARD).settings
    settings.clear_border = False
    labels, _extra = detect_labels(intensity, settings)

    assert labels.max() == len(BLOBS), (
        f"found {labels.max()} regions for {len(BLOBS)} simulated blobs"
    )

    found = np.asarray([p.centroid for p in regionprops(labels, intensity)])
    for ix, iy, _tau in BLOBS:
        distance = np.hypot(found[:, 0] - iy, found[:, 1] - ix).min()
        assert distance < 2.0, f"nothing within 2 px of the blob at ({iy}, {ix})"


def test_the_region_fit_recovers_each_blob_s_lifetime(scan, intensity, demo_files):
    """The claim the whole pipeline exists to support, end to end.

    Detect the regions, hand them to the fit, and check the lifetimes against
    what was simulated — per blob, not on average. An average would pass for a
    fit that recovered one lifetime and assigned it to everything.
    """
    import tttrlib

    from chisurf.core.datastore import column_names, column_values
    from chisurf.plugins.microscopy.region_mle.core import (
        RegionMleSettings,
        build_irf_vv_vh,
        fit_regions,
    )
    from chisurf.plugins.microscopy.spot_finder.core.spots import detect_labels
    from chisurf.plugins.microscopy.spot_finder.core.workflow import (
        STANDARD,
        request_from_workflow,
    )

    tttr, clsm = scan
    detect = request_from_workflow(STANDARD).settings
    detect.clear_border = False
    labels, _extra = detect_labels(intensity, detect)

    irf_tttr = tttrlib.TTTR(str(demo_files[1]))
    irf_full, background = build_irf_vv_vh(
        irf_tttr,
        detector_chs=[0, 1],
        micro_time_range=(0, N_MICRO),
        micro_time_binning=1,
    )

    settings = RegionMleSettings(
        detector_chs=[0, 1],
        micro_time_range=(0, N_MICRO),
        micro_time_binning=1,
        irf=irf_full,
        background=background,
        regions=labels,
        min_photons=100,
        tau=2.0,
        fix_r0=True,
        fix_rho=True,
        p2s_twoIstar=True,
    )
    result = fit_regions(tttr, settings, clsm=clsm, dt=DT, period=N_MICRO * DT)

    assert result.n_molecules == len(BLOBS)

    table = result.dataframe
    names = column_names(table)
    taus = np.asarray(column_values(table, names.index("tau")), dtype=float)
    rows = np.stack(
        [
            np.asarray(column_values(table, names.index("centroid_row")), dtype=float),
            np.asarray(column_values(table, names.index("centroid_col")), dtype=float),
        ],
        axis=1,
    )

    # Pair each fitted region with the blob it sits on, so the comparison is
    # per object rather than against a sorted list that could line up by luck.
    #
    # 12% covers the real bias rather than hiding it: the short lifetimes come
    # back within half a percent (1.00 -> 1.000, 0.60 -> 0.602) and the long
    # ones a few percent low (3.60 -> 3.302, 2.20 -> 2.084), because a 3.6 ns
    # decay is not finished inside the 8.19 ns excitation period this was
    # simulated with. A looser tolerance would pass for a fit that had stopped
    # working.
    for ix, iy, tau in BLOBS:
        index = int(np.argmin(np.hypot(rows[:, 0] - iy, rows[:, 1] - ix)))
        assert taus[index] == pytest.approx(tau, rel=0.12), (
            f"blob at ({iy}, {ix}) was simulated with tau={tau} ns and fitted "
            f"as {taus[index]:.3f} ns"
        )


def test_the_lifetimes_are_told_apart(scan, intensity, demo_files):
    """Recovering four lifetimes means ordering them, not landing near a mean."""
    import tttrlib

    from chisurf.core.datastore import column_names, column_values
    from chisurf.plugins.microscopy.region_mle.core import (
        RegionMleSettings,
        build_irf_vv_vh,
        fit_regions,
    )
    from chisurf.plugins.microscopy.spot_finder.core.spots import detect_labels
    from chisurf.plugins.microscopy.spot_finder.core.workflow import (
        STANDARD,
        request_from_workflow,
    )

    tttr, clsm = scan
    detect = request_from_workflow(STANDARD).settings
    detect.clear_border = False
    labels, _extra = detect_labels(intensity, detect)
    irf_full, background = build_irf_vv_vh(
        tttrlib.TTTR(str(demo_files[1])),
        detector_chs=[0, 1],
        micro_time_range=(0, N_MICRO),
        micro_time_binning=1,
    )
    result = fit_regions(
        tttr,
        RegionMleSettings(
            detector_chs=[0, 1],
            micro_time_range=(0, N_MICRO),
            micro_time_binning=1,
            irf=irf_full,
            background=background,
            regions=labels,
            min_photons=100,
            tau=2.0,
            fix_r0=True,
            fix_rho=True,
            p2s_twoIstar=True,
        ),
        clsm=clsm,
        dt=DT,
        period=N_MICRO * DT,
    )

    names = column_names(result.dataframe)
    taus = np.sort(np.asarray(column_values(result.dataframe, names.index("tau")), dtype=float))
    truth = np.sort(np.asarray([b[2] for b in BLOBS]))

    # The shortest fitted lifetime belongs to the shortest simulated one, and so
    # on up: a fit that collapsed everything onto one value would fail here
    # while still passing a per-blob tolerance test on the middle two.
    assert np.all(np.diff(taus) > 0.1), f"lifetimes not resolved: {taus}"
    np.testing.assert_allclose(taus, truth, rtol=0.12)
