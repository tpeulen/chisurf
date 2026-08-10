"""Inter-frame drift estimation and correction (PAM MIA_Drift port).

Drift matters here for a specific reason: a translation between two frames is
indistinguishable from the decorrelation diffusion produces, so uncorrected
drift inflates the diffusion coefficient fitted from long frame lags — exactly
the region the spatiotemporal correlation carpet exposes. The last test pins
that effect rather than just the mechanics.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage

from chisurf.core.fluorescence.imaging.drift import (
    apply_drift,
    correct_drift,
    estimate_drift,
)
from chisurf.core.roi import RectangleROI


def _drifting_stack(shifts, size=48, seed=0):
    """Return a stack whose frames are the same image rolled by given shifts."""
    rng = np.random.default_rng(seed)
    base = rng.random((size, size))
    return np.stack([np.roll(base, (dy, dx), axis=(0, 1)) for dy, dx in shifts])


def test_estimate_recovers_a_known_drift():
    """The measured drift equals the translation actually applied."""
    truth = [(0, 0), (2, -3), (4, -6), (6, -9)]
    est = estimate_drift(_drifting_stack(truth))
    np.testing.assert_allclose(est, np.array(truth, dtype=float))


def test_the_first_frame_never_drifts_from_itself():
    """Frame 0 is the origin by construction where it *is* the reference."""
    stack = _drifting_stack([(0, 0), (3, 1), (5, 2)])
    for reference in ("first", "previous"):
        np.testing.assert_allclose(estimate_drift(stack, reference=reference)[0], [0, 0])


def test_the_stack_mean_reference_measures_the_first_frame_too():
    """Under ``'mean'`` frame 0 is displaced from the reference like any other.

    The reference is the stack average, which frame 0 is not. Leaving its row
    at ``(0, 0)`` would misalign it from the whole corrected stack by its full
    displacement — silently, since nothing else in the trace looks wrong.
    """
    truth = [(k, 0) for k in range(9)]
    stack = _drifting_stack(truth)
    shifts = estimate_drift(stack, reference="mean")

    # Displacements measured from the mean position, frame 0 included.
    expected = np.array(truth, dtype=float) - np.array(truth, dtype=float).mean(axis=0)
    np.testing.assert_allclose(shifts, expected, atol=1e-9)

    corrected, _ = correct_drift(stack, reference="mean")
    for frame in corrected:
        np.testing.assert_allclose(frame, corrected[0])


def test_previous_frame_referencing_accumulates_to_the_same_answer():
    """Chaining consecutive shifts gives the absolute displacement."""
    truth = [(0, 0), (2, 0), (4, 0), (6, 0)]
    stack = _drifting_stack(truth)
    np.testing.assert_allclose(
        estimate_drift(stack, reference="previous"), np.array(truth, dtype=float)
    )


def test_a_roi_restricts_the_estimate_to_a_structured_patch():
    """Estimating inside a region gives the same answer as the whole frame.

    PAM estimates drift inside the drawn ROI, which matters when most of the
    field is empty; here the point is that restricting does not change a
    well-determined answer.
    """
    truth = [(0, 0), (3, -2)]
    stack = _drifting_stack(truth, size=64)
    whole = estimate_drift(stack)
    inside = estimate_drift(stack, roi=RectangleROI(8, 8, 56, 56))
    np.testing.assert_allclose(inside, whole)


def test_correction_makes_every_frame_match_the_reference():
    """After correction the frames are identical again."""
    stack = _drifting_stack([(0, 0), (2, -3), (4, -6)])
    corrected, shifts = correct_drift(stack)
    for k in range(len(corrected)):
        np.testing.assert_allclose(corrected[k], corrected[0])
    np.testing.assert_allclose(shifts, [[0, 0], [2, -3], [4, -6]])


def test_wrap_mode_conserves_every_photon():
    """Rolling keeps the total intensity; that is why PAM uses it."""
    stack = _drifting_stack([(0, 0), (5, 5)])
    corrected = apply_drift(stack, np.array([[0.0, 0.0], [5.0, 5.0]]), mode="wrap")
    np.testing.assert_allclose(corrected.sum(axis=(1, 2)), stack.sum(axis=(1, 2)))


def test_constant_mode_blanks_the_vacated_strip_instead_of_wrapping():
    """Constant fill is honest about the data that moved out of frame."""
    stack = _drifting_stack([(0, 0), (3, 0)])
    corrected = apply_drift(stack, np.array([[0.0, 0.0], [3.0, 0.0]]),
                            mode="constant", cval=0.0)
    # frame 1 is moved back up by 3 rows, so the last 3 rows have no source
    np.testing.assert_allclose(corrected[1][-3:], 0.0)
    assert corrected[1][:-3].sum() > 0


def test_subpixel_refinement_stays_near_the_integer_peak():
    """The parabolic refinement perturbs, and does not replace, the peak."""
    stack = _drifting_stack([(0, 0), (4, -2)])
    integer = estimate_drift(stack, subpixel=False)
    refined = estimate_drift(stack, subpixel=True)
    assert np.abs(refined - integer).max() < 1.0


def test_shift_array_must_match_the_stack():
    """A mismatched correction is rejected rather than broadcast."""
    stack = _drifting_stack([(0, 0), (1, 1)])
    with pytest.raises(ValueError):
        apply_drift(stack, np.zeros((5, 2)))
    with pytest.raises(ValueError):
        apply_drift(stack, np.zeros((2, 2)), mode="reflect")


def test_unknown_reference_mode_is_rejected():
    """A typo in the reference mode fails loudly."""
    with pytest.raises(ValueError):
        estimate_drift(_drifting_stack([(0, 0), (1, 1)]), reference="latest")


def test_a_single_frame_has_no_drift():
    """Degenerate stacks return a zero displacement rather than failing."""
    np.testing.assert_allclose(estimate_drift(np.zeros((1, 8, 8))), [[0.0, 0.0]])


def test_uncorrected_drift_masquerades_as_decorrelation():
    """Drift decays the frame-lag axis; correcting it restores a flat one.

    This is why the ICS reader offers drift correction at all. The sample here
    is *static* — every frame is the same image translated — so the true
    frame-lag correlation is flat. Uncorrected, it decays with lag, and a
    diffusion model can only absorb that by fitting a larger D.

    The comparison is between corrected and uncorrected *at the same lag*.
    Comparing lag 0 with lag 1 would not isolate drift, because lag 0 also
    carries the shot-noise self-correlation spike that no other lag has.
    """
    from chisurf.core.experiments.ics.data import IcsSettings
    from chisurf.core.experiments.ics.ics_core import compute_ics_carpet

    rng = np.random.default_rng(3)
    yy, xx = np.mgrid[0:32, 0:32]
    base = 50.0 * np.exp(-((yy - 16) ** 2 + (xx - 16) ** 2) / (2 * 5.0 ** 2))
    base = base + rng.poisson(5.0, (32, 32))
    drifting = np.stack([np.roll(base, (3 * k, 0), axis=(0, 1)) for k in range(6)])

    settings = IcsSettings(frame_lags=(0, 1, 2), subtract_average="frame")
    before = compute_ics_carpet(drifting, settings)
    corrected, shifts = correct_drift(drifting)
    after = compute_ics_carpet(corrected, settings)

    np.testing.assert_allclose(shifts[:3, 0], [0, 3, 6])

    iy, ix = before.zero_lag_index()
    g_before = before.correlation[:, iy, ix]
    g_after = after.correlation[:, iy, ix]

    # Uncorrected: monotonic decay with frame lag, from drift alone.
    assert g_before[2] < g_before[1] < g_before[0]
    # Corrected: flat to a few percent, and higher at every non-zero lag.
    assert g_after[1] > g_before[1] and g_after[2] > g_before[2]
    np.testing.assert_allclose(g_after, g_after[0], rtol=0.01)


def test_the_parabolic_refinement_beats_phase_correlation_on_photon_data():
    """Why `drift.py` does not use an upsampled-DFT refinement.

    Phase correlation *whitens* the spectrum, so shot noise at high spatial
    frequencies is amplified to the same weight as signal — precisely wrong for
    a photon-limited sparse image. Measured over 20 random shifts, the parabolic
    fit on the un-whitened cross-correlation is ~20× more accurate on counted
    photons, and the whitened one wins only when there is no noise at all.

    Pinned so the refusal is a measurement rather than an opinion, and so that
    anyone proposing the swap has a harness to re-run.
    """
    skreg = pytest.importorskip("skimage.registration")

    rng = np.random.default_rng(0)
    rows, columns = np.indices((128, 128))
    base = np.zeros((128, 128))
    for y, x, amplitude in rng.uniform([8, 8, 50], [120, 120, 400], (40, 3)):
        base += amplitude * np.exp(
            -((columns - x) ** 2 + (rows - y) ** 2) / 8.0
        )

    parabolic, whitened = [], []
    for _ in range(20):
        dy, dx = rng.uniform(-3, 3, 2)
        moved = ndimage.shift(base, (dy, dx), order=3, mode="constant")
        frames = [
            rng.poisson(np.clip(f, 0, None) / np.clip(f, 0, None).sum() * 200_000).astype(float)
            for f in (base, moved)
        ]
        estimate = estimate_drift(np.stack(frames), subpixel=True)[1]
        reference = -skreg.phase_cross_correlation(*frames, upsample_factor=100)[0]
        parabolic.append(np.hypot(estimate[0] - dy, estimate[1] - dx))
        whitened.append(np.hypot(reference[0] - dy, reference[1] - dx))

    assert np.mean(parabolic) < 0.05
    assert np.mean(parabolic) < np.mean(whitened) / 5


@pytest.mark.parametrize("shift", [13, 14, 15, -13, -14, -15])
def test_a_shift_near_the_unambiguous_limit_is_still_exact(shift):
    """The lag axis is circular, and smoothing has to know that.

    An FFT cross-correlation is periodic: index 0 and index n-1 are neighbours,
    not edges. Smoothing it with the default `reflect` mirrors the peak back
    onto itself, and a peak near the maximum unambiguous lag gets dragged by a
    whole pixel — a true shift of 15 on a 32-pixel frame was read as 16.

    That is invisible in the obvious test, because a mis-corrected frame still
    correlates perfectly *with itself*: only lags that pair it with another
    frame see the error, which is how this survived as a 1.4% residual in an
    ICS flatness check rather than as an obviously wrong shift.
    """
    rng = np.random.default_rng(3)
    rows, columns = np.mgrid[0:32, 0:32]
    base = 50.0 * np.exp(
        -((rows - 16) ** 2 + (columns - 16) ** 2) / (2 * 5.0**2)
    ) + rng.poisson(5.0, (32, 32))
    stack = np.stack([base, np.roll(base, (shift, 0), axis=(0, 1))])

    assert estimate_drift(stack)[1, 0] == float(shift)
    corrected, _ = correct_drift(stack)
    np.testing.assert_array_equal(corrected[1], corrected[0])
