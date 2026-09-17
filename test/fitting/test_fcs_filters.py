"""Tests for the FLCS / filtered-FCS lifetime-filter helpers.

Covers the corrected/extended ``chisurf.core.fluorescence.fcs.filtered`` module:
the defining filter orthogonality relation, species-amplitude recovery, the new
uniform (afterpulsing) pattern, per-photon filter weighting, pseudo-inverse
conditioning, and the divide-by-zero guard in the legacy lifetime-filter helper.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fluorescence.fcs.filtered import (
    calc_ffcs_filters,
    calc_lifetime_filter,
    filter_condition_number,
    photon_filter_weights,
    uniform_pattern,
)


def _patterns(n_bins=64, lifetimes=(1.0, 3.0)):
    """Normalised single-exponential micro-time patterns."""
    t = np.linspace(0, 20, n_bins)
    pats = [np.exp(-t / tau) for tau in lifetimes]
    return [p / p.sum() for p in pats]


def test_filters_satisfy_orthogonality_relation():
    """Filters · normalized_patterns == identity (the defining FLCS relation)."""
    pats = _patterns()
    amps = np.array([0.7, 0.3])
    d_norm = np.column_stack(pats)
    total = d_norm @ amps
    filters, _, _ = calc_ffcs_filters(total, pats)
    assert np.allclose(filters @ d_norm, np.eye(2), atol=1e-8)


def test_filters_recover_species_amplitudes():
    """Applying the filters to the total decay returns the species amplitudes."""
    pats = _patterns()
    amps = np.array([0.65, 0.35])
    total = np.column_stack(pats) @ amps
    filters, _, _ = calc_ffcs_filters(total, pats)
    assert np.allclose(filters @ total, amps, atol=1e-8)


def test_uniform_pattern_removes_afterpulsing():
    """A uniform pattern species captures a flat afterpulse/dark-count component."""
    n_bins = 64
    pats = _patterns(n_bins)
    flat = uniform_pattern(n_bins)
    all_patterns = [*pats, flat]
    amps = np.array([0.5, 0.3, 0.2])  # species1, species2, afterpulse
    total = np.column_stack([*pats, flat]) @ amps
    filters, _, _ = calc_ffcs_filters(total, all_patterns)
    # All three amplitudes (including the flat afterpulse) are recovered, so the
    # species filters are orthogonal to the flat component.
    assert np.allclose(filters @ total, amps, atol=1e-8)


def test_uniform_pattern_shape_and_sum():
    """uniform_pattern is flat and normalised."""
    p = uniform_pattern(50)
    assert p.shape == (50,)
    assert np.isclose(p.sum(), 1.0)
    assert np.allclose(p, p[0])
    with pytest.raises(ValueError):
        uniform_pattern(0)


def test_photon_filter_weights_maps_and_clips():
    """Per-photon weights index the filter table and clip out-of-range bins."""
    filters = np.array([[0.0, 1.0, 2.0, 3.0], [10.0, 11.0, 12.0, 13.0]])
    micro = np.array([0, 2, 3, 99, -5])  # 99 and -5 clip to 3 and 0
    w = photon_filter_weights(filters, micro)
    assert w.shape == (2, 5)
    assert np.allclose(w[0], [0.0, 2.0, 3.0, 3.0, 0.0])
    assert np.allclose(w[1], [10.0, 12.0, 13.0, 13.0, 10.0])


def test_condition_number_flags_collinear_patterns():
    """Near-identical patterns give a large normal-matrix condition number."""
    well_separated = _patterns(lifetimes=(1.0, 5.0))
    collinear = _patterns(lifetimes=(2.0, 2.05))
    total_ws = np.column_stack(well_separated) @ np.array([0.5, 0.5])
    total_co = np.column_stack(collinear) @ np.array([0.5, 0.5])
    cond_ws = filter_condition_number(total_ws, well_separated)
    cond_co = filter_condition_number(total_co, collinear)
    assert cond_co > 100 * cond_ws


def test_tikhonov_reduces_filter_magnitude_for_collinear_patterns():
    """Tikhonov regularisation tames noise-amplifying filters on collinear patterns."""
    pats = _patterns(lifetimes=(2.0, 2.05))
    total = np.column_stack(pats) @ np.array([0.5, 0.5])
    f_plain, _, _ = calc_ffcs_filters(total, pats)
    f_reg, _, _ = calc_ffcs_filters(total, pats, tikhonov=1e-3)
    assert np.abs(f_reg).max() < np.abs(f_plain).max()


def test_rcond_pseudoinverse_path_runs():
    """The rcond truncated-SVD inversion path produces finite filters."""
    pats = _patterns()
    total = np.column_stack(pats) @ np.array([0.6, 0.4])
    filters, _, _ = calc_ffcs_filters(total, pats, rcond=1e-10)
    assert np.all(np.isfinite(filters))


def test_calc_lifetime_filter_zero_bin_guard():
    """A zero bin in the total decay no longer yields inf/nan filters."""
    pats = _patterns()
    total = np.column_stack(pats) @ np.array([0.6, 0.4])
    total[5] = 0.0  # would divide by zero without the guard
    filters = calc_lifetime_filter(pats, total)
    assert np.all(np.isfinite(filters))


PAM_REFERENCE = (
    pathlib.Path(__file__).resolve().parents[1] / "data" / "flcs" / "pam_ffcs_filters_reference.npz"
)


CASES = ["two_species_bg", "stacked_par_perp", "dense"]


def _pam_case(case):
    ref = np.load(PAM_REFERENCE)
    decay = ref[f"{case}_decay"].ravel()
    patterns = ref[f"{case}_patterns"]
    return ref, decay, list(patterns.reshape(patterns.shape[0], -1))


def _assert_close(got, expected, rel=1e-10):
    assert got.shape == expected.shape
    assert np.abs(got - expected).max() <= rel * np.abs(expected).max()


@pytest.mark.parametrize("case", CASES)
def test_default_filters_match_pam_burstbrowser(case):
    """A/B against PAM's BurstBrowser ``Calc_fFCS_Filters.m``, run in Octave.

    Empty total-decay bins are set to one and kept (the default). The fixture
    holds inputs and PAM's outputs; generator and the verbatim PAM excerpts are
    in ``test/data/flcs/``. PAM's weighted residual on an empty bin uses the
    substituted one as the measured value, ChiSurf keeps the zero, so residuals
    are compared on the occupied bins.
    """
    ref, decay, patterns = _pam_case(case)
    filters, reconstruction, residuals = calc_ffcs_filters(decay, patterns)
    _assert_close(filters, ref[f"{case}_bb_filters"])
    _assert_close(reconstruction, ref[f"{case}_bb_reconstruction"])
    occupied = decay != 0
    _assert_close(residuals[occupied], ref[f"{case}_bb_weighted_residuals"][occupied])


@pytest.mark.parametrize("case", CASES)
def test_exclude_filters_match_pam_main_window(case):
    """A/B against PAM's main-window fFCS filters (``PAM.m`` ``Update_fFCS_GUI``).

    ``empty_bins="exclude"`` drops empty bins, renormalises the patterns over
    the occupied ones and zeroes the filters there. ``stacked_par_perp`` is
    PAM's joint par/perp layout, passed as the two channels concatenated.
    """
    ref, decay, patterns = _pam_case(case)
    filters, reconstruction, _ = calc_ffcs_filters(decay, patterns, empty_bins="exclude")
    _assert_close(filters, ref[f"{case}_filters"])
    _assert_close(reconstruction, ref[f"{case}_reconstruction"])
    assert np.all(filters[:, decay == 0] == 0.0)


def test_the_two_pam_conventions_differ_only_with_empty_bins():
    """Guard that the fixture exercises the difference it is there to pin."""
    ref, decay, patterns = _pam_case("two_species_bg")
    assert np.abs(ref["two_species_bg_filters"] - ref["two_species_bg_bb_filters"]).max() > 0.1
    ref, decay, patterns = _pam_case("dense")
    _assert_close(ref["dense_filters"], ref["dense_bb_filters"], rel=1e-12)


def test_excluded_empty_bins_are_the_same_as_never_measured():
    """With ``empty_bins="exclude"`` an empty bin is as if it were never measured."""
    pats = _patterns()
    total = np.column_stack(pats) @ np.array([6000.0, 4000.0])
    total[[0, 40]] = 0.0
    keep = total != 0
    full, _, _ = calc_ffcs_filters(total, pats, empty_bins="exclude")
    cut, _, _ = calc_ffcs_filters(total[keep], [p[keep] for p in pats])
    np.testing.assert_allclose(full[:, keep], cut, rtol=1e-12, atol=0)
    # and the relation holds on the occupied bins with patterns renormalised there
    renorm = np.column_stack([p[keep] / p[keep].sum() for p in pats])
    np.testing.assert_allclose(cut @ renorm, np.eye(2), atol=1e-10)


def test_unknown_empty_bin_mode_is_rejected():
    """A misspelt mode fails loudly instead of falling back to a default."""
    pats = _patterns()
    with pytest.raises(ValueError):
        calc_ffcs_filters(np.column_stack(pats) @ np.array([1.0, 1.0]), pats, empty_bins="drop")
