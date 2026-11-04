"""Laser power calibration: raw diode readings to µW, from measured references only.

The rules the module must keep, each pinned here: every µW in a calibration was typed in by a
person reading a calibrated external meter at the objective (nothing is derived from drive
settings or datasheets), the dark offset is its own measurement, conversion interpolates
*between* measured points and nowhere else (bounded by the measured range; a fit is reported as
quality, never as a converter), anything outside the measured band is marked extrapolated and
invalid, a calibration that fails validation converts nothing, calibrations are strictly per
laser and never shared, they hold only for the verified configuration and conditions they were
measured at (which heads were connected, repetition rate, mode, pulse pattern, optical path),
every reference was captured with every other connected laser verified OFF by readback (the
photodiode sums all lasers), and a calibration expires three calendar months after its date --
an expired, undated, mismatched, reconfigured or unverified claim hands out no µW at all. The
module drives no hardware: nothing here switches, opens or applies a laser.
"""

from __future__ import annotations

import datetime as dt

import pytest

from chisurf.plugins.core.acq.live import power_calibration as P

#: The day the example measurements were taken (the tests' "today" where it matters).
TODAY = dt.date(2026, 10, 30)


def _point(raw: float, uw: float, **kw) -> P.ReferencePoint:
    return P.ReferencePoint(raw=raw, uw=uw, **kw)


def _conds(laser="Red", nm=640.0, rep=40e6, mode="pulsed", **kw) -> P.LaserConditions:
    return P.LaserConditions(laser, nm, repetition_rate_hz=rep, mode=mode, **kw)


def _solo(on_laser="Red", verified=True, extra_off=()) -> P.EmissionState:
    """Verified readback: one laser emitting, every other named laser confirmed off."""
    others = ["Blue", *extra_off] if on_laser == "Red" else ["Red", *extra_off]
    return P.EmissionState(((on_laser, True, verified),
                            *((o, False, verified) for o in others)))


def _alloff(*names, verified=True) -> P.EmissionState:
    names = names or ("Red", "Blue")
    return P.EmissionState(((n, False, verified) for n in names))


#: The verified configuration the examples were calibrated in: two heads, read back.
CONFIG = P.ConfigIdentity((P.HeadIdentity("Red", 640.0, "SN-R"),
                           P.HeadIdentity("Blue", 488.0, "SN-B")))
CONFIG_RED_ONLY = P.ConfigIdentity((P.HeadIdentity("Red", 640.0, "SN-R"),))
CONFIG_BLUE_MOVED = P.ConfigIdentity((P.HeadIdentity("Red", 640.0, "SN-R"),
                                      P.HeadIdentity("Blue", 488.0, "SN-B2")))
CONFIG_THREE = P.ConfigIdentity((P.HeadIdentity("Red", 640.0, "SN-R"),
                                 P.HeadIdentity("Blue", 488.0, "SN-B"),
                                 P.HeadIdentity("Green", 530.0, "SN-G")))

RED_CONDS, BLUE_CONDS = _conds(), _conds("Blue", 488.0)
SOLO, SOLO_BLUE = _solo(), _solo("Blue")
ALLOFF = _alloff()


def _complete(cal: P.PowerCalibration, calibrated="2026-10-30", dark_raw=100.0,
              points=((200.0, 1.0), (400.0, 3.0)), config=CONFIG,
              conditions=None) -> P.PowerCalibration:
    """A calibration a person finished measuring: dated, configured, dark with verified readback."""
    solo = _solo(cal.key.laser, extra_off=tuple(h.name for h in config.heads
                                                if h.name != cal.key.laser))
    all_off = _alloff(*(h.name for h in config.heads))
    cal.calibrated = calibrated
    cal.config = config
    if conditions is not None:
        cal.conditions = conditions
    cal.set_dark(P.DarkOffset(raw=dark_raw, measured=calibrated, emission=all_off))
    for raw, uw in points:
        cal.add_point(_point(raw, uw, meter="PM100D S/N 1234", meter_calibrated="2026-01-15",
                             measured=calibrated, emission=solo))
    return cal


def _measured() -> P.PowerCalibration:
    """Dark + two references on the 640 nm laser at 40 MHz pulsed, dated as measured."""
    return _complete(P.PowerCalibration("Red", 640.0, conditions=RED_CONDS))


def _conv(cal: P.PowerCalibration, raw: float, **kw) -> P.Conversion:
    """convert() with every gate satisfied, except the ones the test overrides."""
    solo, conds = (SOLO, RED_CONDS) if cal.key.laser == "Red" else (SOLO_BLUE, BLUE_CONDS)
    kw.setdefault("conditions", conds)
    kw.setdefault("emission", solo)
    kw.setdefault("config", CONFIG)
    kw.setdefault("on", TODAY)
    return cal.convert(raw, **kw)


def _inv(cal: P.PowerCalibration, uw: float, **kw) -> P.Conversion:
    kw.setdefault("conditions", RED_CONDS if cal.key.laser == "Red" else BLUE_CONDS)
    kw.setdefault("emission", SOLO if cal.key.laser == "Red" else SOLO_BLUE)
    kw.setdefault("config", CONFIG)
    kw.setdefault("on", TODAY)
    return cal.raw_for(uw, **kw)


def _req(cal: P.PowerCalibration, raw: float, **kw) -> float:
    kw.setdefault("conditions", RED_CONDS)
    kw.setdefault("emission", SOLO)
    kw.setdefault("config", CONFIG)
    kw.setdefault("on", TODAY)
    return cal.require_uw(raw, **kw)


# -------------------------------------------------------------------------------------------
# The chooser: available lasers are choices -- what is calibrated is what is connected
# -------------------------------------------------------------------------------------------
def test_the_available_choices_are_the_four_known_wavelengths() -> None:
    assert P.LASER_WAVELENGTHS_NM == (488.0, 530.0, 640.0, 730.0)


def test_calibrations_are_kept_per_laser_and_wavelength() -> None:
    book = P.CalibrationSet()
    red = _complete(book.calibration_for("Red", 640.0, conditions=RED_CONDS, create=True),
                    points=((200.0, 1.0),))
    blue = _complete(book.calibration_for("Blue", 488.0, conditions=BLUE_CONDS, create=True),
                     dark_raw=120.0, points=((200.0, 2.0),))
    # The same raw reading belongs to whichever laser measured it -- never to both.
    assert book.calibration_for("red", 640.2, conditions=RED_CONDS) is red
    assert book.calibration_for("BLUE", 488.4, conditions=BLUE_CONDS) is blue
    assert _conv(red, 200.0).uw == pytest.approx(1.0)
    assert _conv(blue, 200.0).uw == pytest.approx(2.0)
    assert book.calibration_for("Green", 640.0) is None
    assert book.calibration_for("Red", 560.0) is None


def test_a_calibration_is_never_reused_across_lasers() -> None:
    book = P.CalibrationSet()
    _complete(book.calibration_for("Old head", 485.0, conditions=_conds("Old head", 485.0),
                                   create=True))
    # The 488 laser is a different laser: the 485 nm calibration is not its calibration.
    assert book.calibration_for("Blue", 488.0, conditions=BLUE_CONDS) is None
    fresh = book.calibration_for("Blue", 488.0, conditions=BLUE_CONDS, create=True)
    assert fresh.points == [], "a new laser starts with no references at all"


def test_the_book_says_which_choices_still_need_a_calibration() -> None:
    book = P.CalibrationSet()
    _complete(book.calibration_for("Red", 640.0, conditions=RED_CONDS, create=True))
    assert book.missing_choices(on=TODAY) == (488.0, 530.0, 730.0)
    # An expired calibration counts as missing: it must be measured again.
    blue = book.calibration_for("Blue", 488.0, conditions=BLUE_CONDS, create=True)
    _complete(blue, calibrated="2026-05-01")
    assert 488.0 in book.missing_choices(on=TODAY)
    assert book.missing_choices(on=dt.date(2026, 7, 1)) == (530.0, 730.0)


def test_the_book_keeps_one_calibration_per_condition_set() -> None:
    book = P.CalibrationSet()
    a = _complete(book.calibration_for("Red", 640.0, conditions=_conds(rep=40e6), create=True))
    b = _complete(book.calibration_for("Red", 640.0, conditions=_conds(rep=20e6), create=True))
    assert a is not b and len(book.matches("Red", 640.0)) == 2
    assert book.calibration_for("Red", 640.0, conditions=_conds(rep=20e6)) is b
    # Two calibrations for one laser and no conditions stated: ambiguous, refused.
    assert book.calibration_for("Red", 640.0) is None


# -------------------------------------------------------------------------------------------
# Nothing is usable before it was measured and configured
# -------------------------------------------------------------------------------------------
def test_an_empty_calibration_converts_nothing() -> None:
    cal = P.PowerCalibration("Red", 640.0, conditions=RED_CONDS, config=CONFIG,
                             calibrated="2026-10-30")
    assert not cal.usable
    c = cal.convert(250.0, on=TODAY)
    assert c.valid is False and c.uw is None
    assert c.status == "uncalibrated"
    text = " ".join(cal.validate()).lower()
    assert "dark" in text and "reference" in text
    with pytest.raises(ValueError, match="uncalibrated"):
        cal.require_uw(250.0, on=TODAY)


def test_references_without_a_dark_offset_are_not_usable() -> None:
    cal = P.PowerCalibration("Red", 640.0, conditions=RED_CONDS, config=CONFIG,
                             calibrated="2026-10-30")
    cal.add_point(_point(200.0, 1.0, emission=SOLO))
    assert not cal.usable
    assert cal.convert(200.0, on=TODAY).status == "uncalibrated"
    cal.set_dark(P.DarkOffset(raw=50.0, emission=ALLOFF))
    assert cal.usable, "measuring the dark offset completes the calibration"


def test_an_undated_calibration_is_not_usable() -> None:
    cal = P.PowerCalibration("Red", 640.0, conditions=RED_CONDS, config=CONFIG)
    cal.set_dark(P.DarkOffset(raw=100.0, emission=ALLOFF))
    cal.add_point(_point(200.0, 1.0, emission=SOLO))
    assert not cal.usable
    assert any("date" in p.lower() for p in cal.validate())
    c = cal.convert(200.0, on=TODAY)
    assert c.valid is False and c.uw is None, "an undated calibration must not hand out µW"


def test_a_bad_calibration_date_is_a_problem() -> None:
    cal = P.PowerCalibration("Red", 640.0, conditions=RED_CONDS, config=CONFIG,
                             calibrated="30.10.2026")
    cal.set_dark(P.DarkOffset(raw=100.0, emission=ALLOFF))
    cal.add_point(_point(200.0, 1.0, emission=SOLO))
    assert not cal.usable
    assert any("date" in p.lower() for p in cal.validate())


def test_an_unstated_repetition_rate_or_mode_is_a_problem() -> None:
    common = dict(calibrated="2026-10-30", config=CONFIG)
    dark = P.DarkOffset(raw=100.0, emission=ALLOFF)
    pt = _point(200.0, 1.0, emission=SOLO)
    cal = P.PowerCalibration("Red", 640.0, conditions=_conds(rep=None), **common)
    cal.set_dark(dark)
    cal.add_point(pt)
    assert not cal.usable
    assert any("repetition" in p.lower() for p in cal.validate())
    cal = P.PowerCalibration("Red", 640.0, conditions=_conds(mode=""), **common)
    cal.set_dark(dark)
    cal.add_point(pt)
    assert not cal.usable
    assert any("mode" in p.lower() for p in cal.validate())


def test_a_calibration_without_a_recorded_configuration_is_not_usable() -> None:
    cal = P.PowerCalibration("Red", 640.0, conditions=RED_CONDS, calibrated="2026-10-30")
    cal.set_dark(P.DarkOffset(raw=100.0, emission=ALLOFF))
    cal.add_point(_point(200.0, 1.0, emission=SOLO))
    assert not cal.usable
    assert any("configuration" in p.lower() for p in cal.validate())
    cal.config = CONFIG
    assert cal.usable


def test_the_calibrated_head_must_be_among_the_verified_connected_heads() -> None:
    cal = P.PowerCalibration("Red", 640.0, conditions=RED_CONDS, calibrated="2026-10-30")
    cal.config = CONFIG_RED_ONLY.__class__((P.HeadIdentity("Blue", 488.0, "SN-B"),))
    cal.set_dark(P.DarkOffset(raw=100.0, emission=_alloff("Blue")))
    cal.add_point(_point(200.0, 1.0, emission=_solo("Red")))
    assert not cal.usable
    assert any("red" in p.lower() for p in cal.validate())


def test_a_negative_dark_reading_is_a_problem() -> None:
    cal = _measured()
    cal.set_dark(P.DarkOffset(raw=-5.0, emission=ALLOFF))
    assert not cal.usable
    assert any("dark" in p.lower() for p in cal.validate())


# -------------------------------------------------------------------------------------------
# The photodiode sums every laser: single-laser µW only from verified all-others-off states
# -------------------------------------------------------------------------------------------
def test_a_reference_with_another_laser_emitting_is_a_problem() -> None:
    cal = _measured()
    mixed = P.EmissionState((("Red", True, True), ("Blue", True, True)))
    cal.add_point(_point(300.0, 2.0, emission=mixed))
    assert not cal.usable
    assert any("blue" in p.lower() and "sums" in p.lower() for p in cal.validate())


def test_an_unverified_emission_readback_blocks_a_reference() -> None:
    cal = _measured()
    cal.add_point(_point(300.0, 2.0, emission=_solo(verified=False)))
    assert not cal.usable
    assert any("verif" in p.lower() for p in cal.validate())
    assert _conv(cal, 300.0).status == "invalid"


def test_every_connected_head_must_appear_in_the_verified_readback() -> None:
    def _cal() -> P.PowerCalibration:
        return P.PowerCalibration("Red", 640.0, conditions=RED_CONDS, config=CONFIG_THREE,
                                  calibrated="2026-10-30")

    cal = _cal()
    cal.set_dark(P.DarkOffset(raw=100.0, emission=_alloff("Red", "Blue")))
    cal.add_point(_point(200.0, 1.0, emission=SOLO))
    assert not cal.usable
    assert any("green" in p.lower() for p in cal.validate())
    complete = _cal()
    complete.set_dark(P.DarkOffset(raw=100.0, emission=_alloff("Red", "Blue", "Green")))
    complete.add_point(_point(200.0, 1.0, emission=_solo("Red", extra_off=("Green",))))
    complete.add_point(_point(400.0, 3.0, emission=_solo("Red", extra_off=("Green",))))
    assert complete.usable


def test_a_dark_offset_without_a_verified_all_off_readback_is_a_problem() -> None:
    cal = P.PowerCalibration("Red", 640.0, conditions=RED_CONDS, config=CONFIG,
                             calibrated="2026-10-30")
    cal.add_point(_point(200.0, 1.0, emission=SOLO))
    cal.set_dark(P.DarkOffset(raw=100.0))  # no readback recorded
    assert not cal.usable
    assert any("dark" in p.lower() for p in cal.validate())
    cal.set_dark(P.DarkOffset(raw=100.0, emission=_alloff(verified=False)))
    assert not cal.usable
    cal.set_dark(P.DarkOffset(raw=100.0, emission=ALLOFF))
    assert cal.usable


def test_conversion_blocks_on_unknown_mixed_zero_or_unverified_emission() -> None:
    cal = _measured()
    cases = (
        (None, "emission"),
        (_solo(verified=False), "verif"),
        (P.EmissionState((("Red", True, True), ("Blue", True, True))), "blue"),
        (P.EmissionState((("Red", True, False), ("Blue", False, True))), "verif"),
        (ALLOFF, "off"),  # the calibrated laser itself reads off: no light to attribute
    )
    for emission, needle in cases:
        c = cal.convert(300.0, conditions=RED_CONDS, config=CONFIG, emission=emission, on=TODAY)
        assert c.valid is False and c.uw is None, emission
        assert needle in c.reason.lower()
    with pytest.raises(ValueError, match="emission"):
        _req(cal, 300.0, emission=None)


# -------------------------------------------------------------------------------------------
# A calibration holds only for the verified configuration and conditions it was measured at
# -------------------------------------------------------------------------------------------
def test_conversion_aborts_when_the_configuration_changed() -> None:
    cal = _measured()
    for config, needle in ((CONFIG_RED_ONLY, "blue"), (CONFIG_BLUE_MOVED, "serial")):
        c = cal.convert(300.0, conditions=RED_CONDS, emission=SOLO, config=config, on=TODAY)
        assert c.valid is False and c.uw is None
        assert c.status == "config-changed"
        assert needle in c.reason.lower()
    with pytest.raises(ValueError, match="config"):
        _req(cal, 300.0, config=CONFIG_RED_ONLY)


def test_conversion_requires_the_configuration_identity() -> None:
    cal = _measured()
    c = cal.convert(300.0, conditions=RED_CONDS, emission=SOLO, on=TODAY)
    assert c.valid is False and c.uw is None
    assert c.status == "configuration-unknown"
    assert "configuration" in c.reason.lower()


def test_the_configuration_identity_is_order_insensitive_but_content_sensitive() -> None:
    reordered = P.ConfigIdentity((P.HeadIdentity("Blue", 488.0, "SN-B"),
                                  P.HeadIdentity("Red", 640.0, "SN-R")))
    assert reordered.identity() == CONFIG.identity()
    assert not CONFIG.differences(reordered)
    assert any("serial" in d.lower() for d in CONFIG.differences(CONFIG_BLUE_MOVED))


def test_a_repetition_rate_mismatch_does_not_convert() -> None:
    cal = _measured()
    c = cal.convert(300.0, conditions=_conds(rep=20e6), emission=SOLO, config=CONFIG, on=TODAY)
    assert c.valid is False and c.uw is None
    assert c.status == "conditions-mismatch"
    assert "repetition" in c.reason.lower()
    with pytest.raises(ValueError, match="repetition"):
        cal.require_uw(300.0, conditions=_conds(rep=20e6), emission=SOLO, config=CONFIG,
                       on=TODAY)


def test_mode_pattern_and_optical_path_changes_require_their_own_calibration() -> None:
    cal = _measured()
    for changed in (_conds(mode="cw"), _conds(pattern="PIE slot 2"), _conds(optical_path="fibre")):
        c = cal.convert(300.0, conditions=changed, emission=SOLO, config=CONFIG, on=TODAY)
        assert c.status == "conditions-mismatch" and c.uw is None
    assert "optical path" in cal.convert(
        300.0, conditions=_conds(optical_path="fibre"), emission=SOLO, config=CONFIG,
        on=TODAY).reason.lower()


def test_a_claim_without_stated_conditions_is_refused() -> None:
    cal = _measured()
    c = cal.convert(300.0, emission=SOLO, config=CONFIG, on=TODAY)
    assert c.valid is False and c.uw is None
    assert "condition" in c.reason.lower()


def test_matching_conditions_and_configuration_convert() -> None:
    assert _conv(_measured(), 300.0).uw == pytest.approx(2.0)


# -------------------------------------------------------------------------------------------
# Expiry: three calendar months after the calibration date, to the day
# -------------------------------------------------------------------------------------------
def test_a_calibration_expires_three_calendar_months_after_its_date() -> None:
    cal = _measured()  # calibrated 2026-10-30
    assert cal.expires_on() == dt.date(2027, 1, 30)
    assert not cal.is_expired(on=dt.date(2027, 1, 29))
    assert cal.is_expired(on=dt.date(2027, 1, 30)), "the 3-month day itself is expired"
    assert cal.is_expired(on=dt.date(2027, 1, 31))


def test_the_expiry_clamps_to_the_end_of_shorter_months() -> None:
    assert P.PowerCalibration("Red", 640.0, calibrated="2026-08-31").expires_on() \
        == dt.date(2026, 11, 30)
    assert P.PowerCalibration("Red", 640.0, calibrated="2025-11-30").expires_on() \
        == dt.date(2026, 2, 28)


def test_an_expired_calibration_hands_out_no_uw() -> None:
    cal = _measured()
    later = dt.date(2027, 2, 1)
    assert not cal.usable_at(later)
    c = cal.convert(250.0, conditions=RED_CONDS, emission=SOLO, config=CONFIG, on=later)
    assert c.valid is False and c.uw is None, "a stale calibration must not show a µW number"
    assert c.status == "expired" and "2027-01-30" in c.reason
    with pytest.raises(ValueError, match="expired"):
        cal.require_uw(250.0, conditions=RED_CONDS, emission=SOLO, config=CONFIG, on=later)
    with pytest.raises(ValueError, match="expired"):
        cal.require_raw(2.0, conditions=RED_CONDS, emission=SOLO, config=CONFIG, on=later)
    assert any("expired" in p.lower() for p in cal.validate(at=later))
    # ... while the same calibration is fully usable before its expiry.
    assert cal.usable_at(dt.date(2027, 1, 29))
    assert _conv(cal, 250.0, on=dt.date(2027, 1, 29)).uw == pytest.approx(1.5)


def test_expiry_is_per_laser() -> None:
    book = P.CalibrationSet()
    red = _complete(book.calibration_for("Red", 640.0, conditions=RED_CONDS, create=True),
                    calibrated="2026-07-30")  # expires 2026-10-30
    blue = _complete(book.calibration_for("Blue", 488.0, conditions=BLUE_CONDS, create=True),
                     calibrated="2026-10-01")  # good into 2027
    assert red.is_expired(on=TODAY)
    assert not blue.is_expired(on=TODAY)


def test_expiry_soon_is_a_warning_not_a_problem() -> None:
    cal = _measured()  # expires 2027-01-30
    soon = dt.date(2027, 1, 20)
    assert cal.usable_at(soon)
    assert not cal.validate(at=soon)
    assert any("expire" in w.lower() for w in cal.warnings(at=soon))
    assert not any("expire" in w.lower() for w in cal.warnings(at=dt.date(2026, 11, 1)))


# -------------------------------------------------------------------------------------------
# The curve: bounded interpolation between measured points; the fit is a report, not a converter
# -------------------------------------------------------------------------------------------
def test_the_dark_reading_itself_is_zero_and_measured() -> None:
    c = _conv(_measured(), 100.0)
    assert c.valid and c.uw == pytest.approx(0.0)
    assert c.status == "measured"


def test_one_reference_interpolates_between_dark_and_the_point() -> None:
    cal = _complete(P.PowerCalibration("Red", 640.0, conditions=RED_CONDS),
                    points=((200.0, 1.0),))
    # Halfway between the dark reading and the reference, in raw counts and µW alike.
    c = _conv(cal, 150.0)
    assert c.valid and c.status == "interpolated"
    assert c.uw == pytest.approx(0.5)
    # The reference itself: the measured value, to the digit the meter showed.
    c = _conv(cal, 200.0)
    assert c.valid and c.status == "measured" and c.uw == pytest.approx(1.0)


def test_conversion_interpolates_piecewise_through_a_nonlinear_response() -> None:
    cal = _measured()
    cal.add_point(_point(500.0, 3.6, emission=SOLO))
    # Midway between the two references: the segment's own line, not a fit through all points.
    c = _conv(cal, 300.0)
    assert c.valid and c.status == "interpolated"
    assert c.uw == pytest.approx(2.0)
    # A steeper and a shallower segment: each interpolation follows its own neighbours.
    cal.add_point(_point(600.0, 9.6, emission=SOLO))
    assert _conv(cal, 550.0).uw == pytest.approx(6.6)
    assert _conv(cal, 450.0).uw == pytest.approx(3.3)


def test_raw_below_the_dark_offset_is_refused() -> None:
    cal = _measured()
    c = _conv(cal, 80.0)
    assert c.valid is False and c.uw is None
    assert "dark" in c.reason.lower()
    with pytest.raises(ValueError, match="dark"):
        _req(cal, 80.0)


def test_the_fit_reports_slope_and_residuals_over_the_measured_range() -> None:
    exact = _measured()  # dark (100, 0), references (200, 1) and (400, 3): one straight line
    fit = exact.linear_fit()
    assert fit is not None and fit.slope == pytest.approx(0.01)
    assert fit.max_residual_uw < 1e-9 and fit.rms_residual_uw < 1e-9
    assert fit.n_points == 3
    # A nonlinear third reference: the residuals show the response is not a straight line.
    bent = _measured()
    bent.add_point(_point(600.0, 9.6, emission=SOLO))
    fit = bent.linear_fit()
    assert fit.slope == pytest.approx(5800.0 / 350000.0)
    assert fit.max_residual_uw == pytest.approx(1.9714286, abs=1e-4)
    assert bent.linear_fit().n_points == 4


def test_the_fit_needs_three_or_more_measured_anchors() -> None:
    cal = _complete(P.PowerCalibration("Red", 640.0, conditions=RED_CONDS),
                    points=((200.0, 1.0),))
    assert cal.linear_fit() is None
    assert _conv(cal, 150.0).uncertainty_uw is None


def test_conversions_report_the_fit_residual_as_their_uncertainty() -> None:
    bent = _measured()
    bent.add_point(_point(600.0, 9.6, emission=SOLO))
    c = _conv(bent, 300.0)
    assert c.uncertainty_uw == pytest.approx(bent.linear_fit().max_residual_uw)
    exact = _measured()
    assert _conv(exact, 300.0).uncertainty_uw < 1e-9


def test_raw_beyond_the_references_is_extrapolated_and_invalid() -> None:
    cal = _measured()
    c = _conv(cal, 500.0)
    assert c.status == "extrapolated"
    assert c.valid is False
    with pytest.raises(ValueError, match="extrapolat"):
        _req(cal, 500.0)
    assert _conv(cal, 401.0).status == "extrapolated"


def test_the_inverse_conversion_honours_the_same_band() -> None:
    cal = _measured()
    assert _inv(cal, 0.0).uw == pytest.approx(100.0)  # .uw carries the raw reading
    assert _inv(cal, 0.0).status == "measured"
    mid = _inv(cal, 2.0)
    assert mid.valid and mid.status == "interpolated" and mid.uw == pytest.approx(300.0)
    assert _inv(cal, 3.0).status == "measured"
    above = _inv(cal, 5.0)
    assert above.status == "extrapolated" and above.valid is False
    with pytest.raises(ValueError, match="extrapolat"):
        cal.require_raw(5.0, conditions=RED_CONDS, emission=SOLO, config=CONFIG, on=TODAY)
    below = _inv(cal, -0.1)
    assert below.valid is False and "negative" in below.reason.lower()


def test_the_measured_range_spans_dark_to_the_highest_reference() -> None:
    cal = _measured()
    assert cal.raw_domain() == (100.0, 400.0)
    assert cal.uw_domain() == (0.0, 3.0)
    empty = P.PowerCalibration("Red", 640.0)
    assert empty.raw_domain() is None and empty.uw_domain() is None


def test_every_valid_conversion_stays_inside_the_measured_powers() -> None:
    cal = _measured()
    cal.add_point(_point(500.0, 3.6, emission=SOLO))
    lo, hi = 0.0, 3.6
    for raw in (100, 120, 150, 199, 200, 250, 300, 350, 399, 400, 450, 499, 500):
        c = _conv(cal, float(raw))
        if c.valid:
            assert lo - 1e-9 <= c.uw <= hi + 1e-9, raw


# -------------------------------------------------------------------------------------------
# Validation: bad measurements are named, never smoothed over
# -------------------------------------------------------------------------------------------
def test_a_non_positive_meter_reading_is_a_problem() -> None:
    cal = _measured()
    cal.add_point(_point(300.0, 0.0, emission=SOLO))
    assert not cal.usable
    assert any("positive" in p.lower() for p in cal.validate())
    assert _conv(cal, 250.0).status == "invalid"


def test_a_reference_not_above_the_dark_offset_is_a_problem() -> None:
    cal = _measured()
    cal.add_point(_point(80.0, 0.5, emission=SOLO))
    assert not cal.usable
    assert any("dark" in p.lower() for p in cal.validate())


def test_the_same_raw_with_two_powers_is_a_conflict() -> None:
    cal = _measured()
    cal.add_point(_point(200.0, 2.5, emission=SOLO))
    assert not cal.usable
    assert any("conflict" in p.lower() for p in cal.validate())


def test_non_monotonic_references_are_a_problem() -> None:
    cal = P.PowerCalibration("Red", 640.0, conditions=RED_CONDS, config=CONFIG,
                             calibrated="2026-10-30")
    cal.set_dark(P.DarkOffset(raw=100.0, emission=ALLOFF))
    cal.add_point(_point(200.0, 3.0, emission=SOLO))
    cal.add_point(_point(400.0, 1.0, emission=SOLO))
    assert not cal.usable
    assert any("monotonic" in p.lower() for p in cal.validate())
    assert _conv(cal, 300.0).status == "invalid"


def test_nan_and_infinite_readings_are_problems() -> None:
    cal = _measured()
    cal.add_point(_point(float("nan"), 2.0, emission=SOLO))
    cal.add_point(_point(300.0, float("inf"), emission=SOLO))
    assert not cal.usable
    assert len(cal.validate()) >= 2


def test_repeated_identical_readings_collapse_without_conflict() -> None:
    cal = _measured()
    cal.add_point(_point(400.0, 3.0, emission=SOLO))
    assert cal.usable
    assert _conv(cal, 400.0).uw == pytest.approx(3.0)


def test_the_module_exposes_no_way_to_switch_a_laser() -> None:
    """The calibration records and judges readings; switching anything is another module's job,
    and an automatic emission change would need the user's explicit consent besides."""
    banned = ("laser_off", "set_emission", "set_head", "set_oscillator", "apply", "open_",
              "connect")
    names = [n for n in vars(P)
             if not n.startswith("_") and any(b in n.lower() for b in banned)]
    assert not names, f"the calibration module must not drive hardware: {names}"


# -------------------------------------------------------------------------------------------
# Provenance: each reading carries its source
# -------------------------------------------------------------------------------------------
def test_a_reference_records_where_its_numbers_came_from() -> None:
    pt = _point(
        200.0, 1.0, meter="PM100D S/N 1234", meter_calibrated="2026-01-15",
        measured="2026-10-30", intensity_pct=47.0,
        note="at the objective, emission head on", emission=SOLO,
    )
    assert pt.meter and pt.meter_calibrated and pt.measured and pt.intensity_pct == 47.0
    cal = _measured()
    cal.add_point(_point(500.0, 3.6, emission=SOLO))  # no meter, no dates
    assert cal.usable, "a provenance gap is a warning, not a wrong number"
    warns = " ".join(cal.warnings(at=dt.date(2026, 11, 1))).lower()
    assert "meter" in warns and "500" in warns and "calibrat" in warns


# -------------------------------------------------------------------------------------------
# Storage: strict round trips, a file format that refuses what it does not understand
# -------------------------------------------------------------------------------------------
def test_a_calibration_round_trips_through_its_dict() -> None:
    cal = _measured()
    cal.add_point(_point(500.0, 3.6, meter="PM100D", meter_calibrated="2026-01-15",
                         measured="2026-10-31", intensity_pct=95.0, note="full drive",
                         emission=SOLO))
    back = P.PowerCalibration.from_dict(cal.to_dict())
    assert back.key == cal.key
    assert back.calibrated == cal.calibrated
    assert back.conditions == cal.conditions
    assert back.config == cal.config
    assert back.dark == cal.dark
    assert list(back.points) == list(cal.points)


def test_a_calibration_book_round_trips_through_a_file(tmp_path) -> None:
    book = P.CalibrationSet()
    cal = _complete(book.calibration_for("Red", 640.0, conditions=RED_CONDS, create=True))
    path = tmp_path / "power_calibration.json"
    book.save(path)
    back = P.CalibrationSet.load(path)
    red = back.calibration_for("Red", 640.0, conditions=RED_CONDS)
    assert red is not None and red.calibrated == cal.calibrated
    assert red.conditions == cal.conditions and red.config == cal.config
    assert red.dark == cal.dark
    assert list(red.points) == list(cal.points)


def test_loading_refuses_a_schema_it_does_not_read(tmp_path) -> None:
    import json

    path = tmp_path / "old.json"
    path.write_text(json.dumps({"schema": "something.else/9", "calibrations": []}))
    with pytest.raises(ValueError, match="schema"):
        P.CalibrationSet.load(path)
    path.write_text(json.dumps({"schema": "chisurf.power-calibration/2", "calibrations": []}))
    with pytest.raises(ValueError, match="newer"):
        P.CalibrationSet.load(path)


def _book_doc(**cal_overrides) -> dict:
    cal = {
        "laser": "Red", "wavelength_nm": 640.0, "calibrated": "2026-10-30",
        "conditions": {"laser": "Red", "wavelength_nm": 640.0,
                       "repetition_rate_hz": 40e6, "mode": "pulsed"},
        "config": {"heads": [{"name": "Red", "wavelength_nm": 640.0, "serial": "SN-R"},
                             {"name": "Blue", "wavelength_nm": 488.0, "serial": "SN-B"}]},
        "dark": {"raw": 100.0,
                 "emission": [{"laser": "Red", "on": False, "verified": True},
                              {"laser": "Blue", "on": False, "verified": True}]},
        "points": [{"raw": 200.0, "uw": 1.0,
                    "emission": [{"laser": "Red", "on": True, "verified": True},
                                 {"laser": "Blue", "on": False, "verified": True}]}],
    }
    cal.update(cal_overrides)
    return {"schema": P.CALIBRATION_SCHEMA, "calibrations": [cal]}


def test_loading_never_invents_a_missing_reading_date_state_or_configuration() -> None:
    with pytest.raises(ValueError, match="calibrated"):
        P.CalibrationSet.from_dict(_book_doc(calibrated=""))
    with pytest.raises(ValueError, match="conditions"):
        P.CalibrationSet.from_dict(_book_doc(conditions=None))
    with pytest.raises(ValueError, match="configuration"):
        P.CalibrationSet.from_dict(_book_doc(config=None))
    doc = _book_doc()
    del doc["calibrations"][0]["points"][0]["uw"]
    with pytest.raises(ValueError, match="uw"):
        P.CalibrationSet.from_dict(doc)
    doc = _book_doc()
    del doc["calibrations"][0]["points"][0]["emission"]
    with pytest.raises(ValueError, match="emission"):
        P.CalibrationSet.from_dict(doc)
    doc = _book_doc()
    del doc["calibrations"][0]["dark"]["raw"]
    with pytest.raises(ValueError, match="raw"):
        P.CalibrationSet.from_dict(doc)
    doc = _book_doc()
    del doc["calibrations"][0]["dark"]["emission"]
    with pytest.raises(ValueError, match="emission"):
        P.CalibrationSet.from_dict(doc)


def test_loading_refuses_unknown_fields_and_non_numeric_readings() -> None:
    with pytest.raises(ValueError, match="wavelenght"):
        P.CalibrationSet.from_dict(_book_doc(wavelenght_nm=640.0))
    doc = _book_doc()
    doc["calibrations"][0]["points"][0]["raw"] = "much"
    with pytest.raises(ValueError, match="raw"):
        P.CalibrationSet.from_dict(doc)
