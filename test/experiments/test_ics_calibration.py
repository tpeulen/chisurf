"""Beam-waist calibration against a reference dye.

Calibration runs an image correlation backwards: on a dye whose D is known, fix
D and solve for the waists. These tests pin that inversion, the temperature
correction that decides how right the reference D is, and — the part that turned
out to matter most — that a *wrong* reference cannot be absorbed by rescaling
the waist. A raster scan samples lag times from microseconds (fast axis) to
milliseconds (slow axis), and that spread separates D from w_r, so a bad
reference shows up as a poor fit instead.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from chisurf.core.experiments.ics.calibration import (
    WaistCalibration,
    calibrate_waist,
    cross_channel_calibration,
)
from chisurf.core.experiments.ics.data import IcsCarpet, IcsTiming
from chisurf.core.models.ics.models import image_correlation

TRUE_WR, TRUE_WZ, D_REF = 0.27, 1.35, 300.0
TIMING = IcsTiming(pixel_duration_us=11.1, line_duration_ms=3.33,
                   frame_duration_ms=0.0, pixel_size_nm=50.0)


def _dye_carpet(w_r=TRUE_WR, w_z=TRUE_WZ, d=D_REF, n=2.5, offset=0.01, size=41):
    """Return a synthetic RICS carpet of a freely diffusing reference dye."""
    line, pix = np.indices((size, size))
    line = (line - size // 2).astype(float)
    pix = (pix - size // 2).astype(float)
    g = image_correlation(
        pix[None], line[None], np.zeros((1, 1, 1)),
        n=n, diffusion_coefficient=d, offset=offset, w_r=w_r, w_z=w_z,
        pixel_duration=TIMING.pixel_duration_us,
        line_duration=TIMING.line_duration_ms,
        pixel_size=TIMING.pixel_size_nm,
    )
    return IcsCarpet(
        correlation=np.asarray(g), error=np.ones_like(g),
        pixel_shift=pix, line_shift=line, frame_lags=np.array([0]), timing=TIMING,
    )


# --- the inversion ---------------------------------------------------------
def test_calibration_recovers_the_waists_from_a_known_dye():
    """With D fixed, the waists are identifiable from the correlation shape."""
    cal = calibrate_waist(_dye_carpet(), diffusion_coefficient=D_REF)

    assert cal.success
    assert cal.w_r == pytest.approx(TRUE_WR, rel=1e-4)
    assert cal.w_z == pytest.approx(TRUE_WZ, rel=1e-4)
    assert cal.n_particles == pytest.approx(2.5, rel=1e-4)
    assert cal.structure_parameter == pytest.approx(TRUE_WZ / TRUE_WR, rel=1e-4)


def test_calibration_survives_noise():
    """A few percent of noise still gives a lateral waist good to ~1 %."""
    rng = np.random.default_rng(0)
    carpet = _dye_carpet()
    carpet.correlation = carpet.correlation + rng.normal(
        0.0, 0.01 * float(carpet.correlation.max()), carpet.correlation.shape
    )
    cal = calibrate_waist(carpet, diffusion_coefficient=D_REF)
    # 1 % noise on the correlation costs ~2 % on the waist
    assert cal.w_r == pytest.approx(TRUE_WR, rel=0.04)


def test_fixing_the_axial_waist_holds_it():
    """Released only when the data can constrain it; otherwise it must not move."""
    cal = calibrate_waist(
        _dye_carpet(), diffusion_coefficient=D_REF, w_z=1.8, fit_axial=False
    )
    assert cal.w_z == 1.8
    # the lateral waist is still recovered, since it dominates the shape
    assert cal.w_r == pytest.approx(TRUE_WR, rel=0.05)


def test_a_wrong_reference_d_shows_up_as_a_bad_fit():
    """A wrong reference cannot be absorbed by rescaling the waist.

    This is the useful consequence of D and w_r *not* being degenerate on a
    raster scan: if the dye identity, the temperature or the scan timing is
    wrong, the residual says so. The calibration carries its own check.
    """
    good = calibrate_waist(_dye_carpet(), diffusion_coefficient=D_REF)
    bad = calibrate_waist(_dye_carpet(), diffusion_coefficient=D_REF * 1.5)

    assert good.chi2 < 1e-20, "the correct reference fits essentially exactly"
    assert bad.chi2 > 1e-6, "a 50 % wrong reference must not fit"
    assert bad.chi2 > 1e6 * good.chi2


def test_calibration_needs_a_reference():
    """Neither a dye nor an explicit D means there is nothing to fix."""
    with pytest.raises(ValueError, match="reference dye"):
        calibrate_waist(_dye_carpet())


def test_an_unknown_dye_is_rejected_rather_than_guessed():
    """A species the store does not know must not silently calibrate."""
    with pytest.raises(ValueError, match="no diffusion coefficient"):
        calibrate_waist(_dye_carpet(), dye="not-a-real-dye-xyz")


def test_result_serialises():
    """The calibration is JSON-friendly for storage and RPC."""
    import json

    cal = calibrate_waist(_dye_carpet(), diffusion_coefficient=D_REF, dye="test")
    restored = json.loads(json.dumps(cal.to_dict()))
    assert restored["dye"] == "test"
    assert restored["w_r"] == pytest.approx(TRUE_WR, rel=1e-4)
    assert restored["structure_parameter"] > 1.0


# --- the temperature link --------------------------------------------------
def test_temperature_enters_through_the_reference_value():
    """A colder bench means a slower dye, and therefore a smaller fitted waist.

    This is the systematic the reference implementation asks the temperature
    for, and it is why the correction is not optional.
    """
    from chisurf.core.fluorescence.diffusion import diffusion_at_temperature

    carpet = _dye_carpet()
    warm = calibrate_waist(
        carpet, diffusion_coefficient=diffusion_at_temperature(D_REF, 30.0)
    )
    cold = calibrate_waist(
        carpet, diffusion_coefficient=diffusion_at_temperature(D_REF, 20.0)
    )
    exact = calibrate_waist(
        carpet, diffusion_coefficient=diffusion_at_temperature(D_REF, 25.0)
    )
    # The waist moves with the assumed temperature, monotonically...
    assert cold.w_r < exact.w_r < warm.w_r
    # ...but only slightly, because the scan separates D from w_r. The real
    # signal that the temperature was wrong is the residual.
    assert abs(warm.w_r / cold.w_r - 1.0) < 0.05
    assert exact.chi2 < cold.chi2 and exact.chi2 < warm.chi2


def test_reported_temperature_error_matches_the_sqrt_propagation():
    """w_r goes as sqrt(D), so its error is half the relative error in D."""
    from chisurf.core.fluorescence.diffusion import temperature_sensitivity

    cal = calibrate_waist(_dye_carpet(), diffusion_coefficient=D_REF,
                          temperature_c=25.0)
    assert cal.temperature_error(1.0) == pytest.approx(
        0.5 * temperature_sensitivity(25.0), rel=1e-9
    )
    # about 1.3 % per degree on the waist -- and 2.6 % on any D derived from it
    assert 0.010 < cal.temperature_error(1.0) < 0.017


def test_a_named_dye_goes_through_the_metadata_store():
    """Naming a catalogued species resolves D without an explicit number."""
    from chisurf.core.fluorescence import dyes

    names = [n for n in dyes.dye_names()
             if np.isfinite(dyes.diffusion_coefficient_25C(n))]
    if not names:
        pytest.skip("no reference dyes with diffusion coefficients available")

    name = names[0]
    cal = calibrate_waist(_dye_carpet(), dye=name, temperature_c=22.0)
    assert cal.dye == name
    assert cal.temperature_c == 22.0
    assert np.isfinite(cal.w_r) and cal.w_r > 0
    # the D actually used is the store value corrected to 22 degrees
    from chisurf.core.fluorescence.diffusion import reference_diffusion

    assert cal.diffusion_coefficient == pytest.approx(
        reference_diffusion(name, 22.0), rel=1e-12
    )


# --- two channels ----------------------------------------------------------
def test_cross_channel_waist_lies_between_the_two():
    """The cross-correlation samples the overlap of two differently sized foci."""
    a = WaistCalibration(w_r=0.24, w_z=1.2, diffusion_coefficient=D_REF)
    b = WaistCalibration(w_r=0.32, w_z=1.6, diffusion_coefficient=D_REF)
    cc = cross_channel_calibration(a, b)

    assert a.w_r < cc.w_r < b.w_r
    assert cc.w_r == pytest.approx(math.sqrt(0.5 * (0.24 ** 2 + 0.32 ** 2)), rel=1e-12)
    assert cc.w_z == pytest.approx(math.sqrt(0.5 * (1.2 ** 2 + 1.6 ** 2)), rel=1e-12)


def test_identical_channels_combine_to_themselves():
    """Two equal foci give back the same waist, not a widened one."""
    a = WaistCalibration(w_r=0.27, w_z=1.35, diffusion_coefficient=D_REF)
    cc = cross_channel_calibration(a, a)
    assert cc.w_r == pytest.approx(0.27, rel=1e-12)
    assert cc.w_z == pytest.approx(1.35, rel=1e-12)


def test_calibrated_waists_make_a_sample_measurement_absolute():
    """The end-to-end point: calibrate on a dye, then fit an unknown for D.

    With the waists pinned by the calibration, a second measurement's diffusion
    coefficient is recovered — which it could not be with both free.
    """
    from scipy.optimize import least_squares

    cal = calibrate_waist(_dye_carpet(), diffusion_coefficient=D_REF)

    d_sample = 12.0                        # a slow, labelled species
    sample = _dye_carpet(d=d_sample, n=1.4, offset=0.0)

    def residual(p):
        model = image_correlation(
            sample.pixel_shift[None], sample.line_shift[None], np.zeros((1, 1, 1)),
            n=p[0], diffusion_coefficient=p[1], offset=0.0,
            w_r=cal.w_r, w_z=cal.w_z,            # fixed by the calibration
            pixel_duration=TIMING.pixel_duration_us,
            line_duration=TIMING.line_duration_ms,
            pixel_size=TIMING.pixel_size_nm,
        )
        return (model - sample.correlation).ravel()

    fit = least_squares(residual, [1.0, 1.0], bounds=([1e-9, 1e-9], [np.inf, np.inf]))
    assert fit.x[1] == pytest.approx(d_sample, rel=1e-3)
