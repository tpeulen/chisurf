"""Laser power calibration: raw diode readings to µW, from measured references only.

The Record tool's power diode reports a raw summed reading (CAN counts); the profile's a.u.
scale is not calibrated. This module turns measurements into a per-laser conversion and nothing
else: at each stable drive setting the user reads a **calibrated external power meter at the
objective** and enters the µW it shows, while the diode's raw reading is captured at the same
moment -- one :class:`ReferencePoint` is exactly that simultaneous pair. The **dark offset**
(:class:`DarkOffset`) is its own measurement: the raw reading with the emission blocked.

The rules, none of which the module bends:

* **Nothing is invented.** Every µW in a calibration was typed in from a meter reading. The
  conversion interpolates linearly *between* measured points (and the dark reading, which is
  0 µW by definition of blocked emission) and nowhere else; a straight-line fit through the
  dark-corrected anchors is REPORTED (slope, residuals -- how linear the response is), never
  used as the converter.
* **Bounded.** Beyond the highest measured reference the module does not extrapolate:
  :meth:`PowerCalibration.convert` returns the extended number marked ``extrapolated`` and
  ``valid=False``, and :meth:`PowerCalibration.require_uw` refuses. Below the dark reading is
  refused outright.
* **Per laser, never shared.** A calibration belongs to one laser head at one wavelength
  (:class:`Key`); the same diode raw reading converts under whichever laser's calibration it
  was measured with and no other.
* **Only for the verified setup it was measured in.** A calibration records the verified
  configuration (:class:`ConfigIdentity`: which heads were connected, read back), the
  operating conditions (:class:`LaserConditions`: repetition rate, mode, pulse pattern,
  optical path), and -- per reference and for the dark offset -- an :class:`EmissionState`:
  every connected laser's on/off state as confirmed by hardware readback. The photodiode sums
  ALL lasers, so a single-laser µW claim exists only when every other laser was verified OFF;
  unknown or unverified states block the claim. A configuration or condition change aborts the
  conversion: recalibrate, do not reuse.
* **Expiry.** A calibration is dated and expires three calendar months
  (:data:`LIFETIME_MONTHS`) after its date; an expired or undated calibration hands out no µW.
* **No hardware.** Nothing here switches, opens or applies a laser -- the readings arrive as
  numbers, the emission states as verified attestations. An automatic emission change would
  need the user's explicit consent and readback in the calling layer besides.

Calibration states travel as JSON (:class:`CalibrationSet`); the loader refuses schemas it
does not read and never defaults a missing reading.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

__all__ = [
    "CALIBRATION_SCHEMA", "LASER_WAVELENGTHS_NM", "LIFETIME_MONTHS",
    "CalibrationSet", "ConfigIdentity", "Conversion", "DarkOffset", "EmissionState",
    "HeadIdentity", "Key", "LaserConditions", "LaserEmission", "LinearFit",
    "PowerCalibration", "ReferencePoint",
]

#: File schema of a saved :class:`CalibrationSet`.
CALIBRATION_SCHEMA = "chisurf.power-calibration/1"
_SCHEMA_PREFIX = "chisurf.power-calibration/"

#: The lasers this system can have -- the chooser's choices, NOT what is installed. Calibrate
#: only the heads that are physically connected and in use, verified through hardware readback.
LASER_WAVELENGTHS_NM = (488.0, 530.0, 640.0, 730.0)

#: Calendar months from the calibration date to its expiry.
LIFETIME_MONTHS = 3

#: Two wavelengths within this band are the same laser line (485 nm vs 488 nm heads are not).
_WL_TOLERANCE_NM = 0.5

#: A repetition rate within this relative band is the same rate; any real change mismatches.
_REP_RATE_REL_TOL = 1e-3

#: Warn this many days before the expiry that a fresh measurement is due.
_EXPIRY_WARNING_DAYS = 14


def _add_months(d: date, months: int) -> date:
    """*months* calendar months after *d*, clamped to the end of shorter months."""
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _norm(text: str) -> str:
    return str(text).strip().casefold()


def _require(d: dict, key: str, where: str):
    if key not in d:
        raise ValueError(f"{where}: missing {key!r} -- a calibration records what was "
                         f"measured, nothing is defaulted")
    return d[key]


def _number(d: dict, key: str, where: str) -> float:
    v = _require(d, key, where)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{where}: {key!r} must be a number, got {v!r}")
    return float(v)


def _text(d: dict, key: str, where: str) -> str:
    v = _require(d, key, where)
    if not isinstance(v, str):
        raise ValueError(f"{where}: {key!r} must be a string, got {v!r}")
    return v


def _check_keys(d: dict, known: set[str], where: str) -> None:
    for k in d:
        if k not in known:
            raise ValueError(f"{where}: unknown field {k!r}")


# -------------------------------------------------------------------------------------------
# The verified setup a calibration was measured in
# -------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class LaserConditions:
    """The operating conditions a calibration holds for: the laser, its wavelength, the
    repetition rate, the operating mode, the pulse pattern and the optical path. A change in
    any of them needs its own calibration; :meth:`differences` names what changed."""

    laser: str
    wavelength_nm: float
    repetition_rate_hz: float | None = None
    mode: str = "pulsed"
    pattern: str = ""
    optical_path: str = ""

    def differences(self, other: LaserConditions) -> list[str]:
        """Human-readable mismatches against *other*; empty means the same conditions."""
        out: list[str] = []
        if _norm(self.laser) != _norm(other.laser):
            out.append(f"laser: calibration {self.laser}, now {other.laser}")
        if abs(self.wavelength_nm - other.wavelength_nm) > _WL_TOLERANCE_NM:
            out.append(f"wavelength: calibration {self.wavelength_nm:g} nm, "
                       f"now {other.wavelength_nm:g} nm")
        a, b = self.repetition_rate_hz, other.repetition_rate_hz
        if (a is None) != (b is None):
            out.append("repetition rate: one side states none")
        elif a is not None and not math.isclose(a, b or 0.0, rel_tol=_REP_RATE_REL_TOL,
                                                abs_tol=1.0):
            out.append(f"repetition rate: calibration {a:g} Hz, now {b:g} Hz")
        if _norm(self.mode) != _norm(other.mode):
            out.append(f"mode: calibration {self.mode!r}, now {other.mode!r}")
        if _norm(self.pattern) != _norm(other.pattern):
            out.append(f"pulse pattern: calibration {self.pattern!r}, now {other.pattern!r}")
        if _norm(self.optical_path) != _norm(other.optical_path):
            out.append(f"optical path: calibration {self.optical_path!r}, "
                       f"now {other.optical_path!r}")
        return out

    def to_dict(self) -> dict:
        return {
            "laser": self.laser, "wavelength_nm": self.wavelength_nm,
            "repetition_rate_hz": self.repetition_rate_hz, "mode": self.mode,
            "pattern": self.pattern, "optical_path": self.optical_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> LaserConditions:
        _check_keys(d, {"laser", "wavelength_nm", "repetition_rate_hz", "mode", "pattern",
                        "optical_path"}, "conditions")
        rep = _require(d, "repetition_rate_hz", "conditions")
        if rep is not None and (isinstance(rep, bool) or not isinstance(rep, (int, float))):
            raise ValueError(f"conditions: 'repetition_rate_hz' must be a number, got {rep!r}")
        return cls(
            laser=_text(d, "laser", "conditions"),
            wavelength_nm=_number(d, "wavelength_nm", "conditions"),
            repetition_rate_hz=None if rep is None else float(rep),
            mode=_text(d, "mode", "conditions"),
            pattern=str(d.get("pattern") or ""),
            optical_path=str(d.get("optical_path") or ""),
        )


@dataclass(frozen=True)
class LaserEmission:
    """One laser's state at a capture, as hardware readback reported it."""

    laser: str
    on: bool
    verified: bool


@dataclass(frozen=True)
class EmissionState:
    """Every connected laser's on/off state at a capture, each confirmed by readback.

    Built from ``(name, on, verified)`` tuples. The photodiode sums all lasers, so a
    single-laser µW claim needs :meth:`confirmed_single`: the named laser on, every other
    verified off. Unknown or unverified states block the claim.
    """

    lasers: tuple[LaserEmission, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "lasers", tuple(
            l if isinstance(l, LaserEmission) else LaserEmission(str(l[0]), bool(l[1]),
                                                                 bool(l[2]))
            for l in self.lasers
        ))

    def confirmed_single(self, laser: str) -> tuple[bool, str]:
        """Whether *laser* alone was emitting, everything verified; else why not."""
        if not self.lasers:
            return False, "no emission state recorded: the photodiode sums every laser"
        unverified = [e.laser for e in self.lasers if not e.verified]
        if unverified:
            return False, (f"emission readback unverified for {', '.join(unverified)}: "
                           f"every laser's state must be confirmed by readback")
        key = _norm(laser)
        named = [e for e in self.lasers if _norm(e.laser) == key]
        if not named:
            return False, f"{laser} is not in the recorded emission state"
        if not any(e.on for e in named):
            return False, f"{laser} reads off: there is no light from it to attribute"
        others = [e.laser for e in self.lasers if e.on and _norm(e.laser) != key]
        if others:
            return False, f"{', '.join(others)} was emitting: the photodiode sums every laser"
        return True, ""

    def all_off_confirmed(self) -> tuple[bool, str]:
        """Whether every laser was verified off (the dark offset's state)."""
        if not self.lasers:
            return False, "no emission state recorded: the photodiode sums every laser"
        unverified = [e.laser for e in self.lasers if not e.verified]
        if unverified:
            return False, (f"emission readback unverified for {', '.join(unverified)}: "
                           f"every laser's state must be confirmed by readback")
        on = [e.laser for e in self.lasers if e.on]
        if on:
            return False, f"{', '.join(on)} was emitting: the dark offset needs every laser blocked"
        return True, ""

    def covers(self, *head_names: str) -> list[str]:
        """Which of *head_names* have no verified entry."""
        seen = {_norm(e.laser) for e in self.lasers if e.verified}
        return [n for n in head_names if _norm(n) not in seen]

    def to_dict(self) -> list[dict]:
        return [{"laser": e.laser, "on": e.on, "verified": e.verified} for e in self.lasers]

    @classmethod
    def from_dict(cls, d) -> EmissionState:
        entries = d.get("lasers") if isinstance(d, dict) else d
        if not isinstance(entries, list):
            raise ValueError("emission: expected a list of {laser, on, verified}")
        out = []
        for i, e in enumerate(entries):
            where = f"emission[{i}]"
            if not isinstance(e, dict):
                raise ValueError(f"{where}: expected an object")
            _check_keys(e, {"laser", "on", "verified"}, where)
            for key in ("on", "verified"):
                if not isinstance(e.get(key), bool):
                    raise ValueError(f"{where}: {key!r} must be true or false")
            out.append(LaserEmission(_text(e, "laser", where), e["on"], e["verified"]))
        return cls(tuple(out))


@dataclass(frozen=True)
class HeadIdentity:
    """One laser head as the configuration readback saw it."""

    name: str
    wavelength_nm: float
    serial: str = ""


@dataclass(frozen=True)
class ConfigIdentity:
    """The verified configuration a calibration was measured in: which heads were connected.

    Heads are matched by name; a removed, added, rewavelengthed or re-serialled head is a
    configuration change and :meth:`differences` names it. ``identity()`` is a stable short
    hash of the head set, independent of order.
    """

    heads: tuple[HeadIdentity, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "heads", tuple(self.heads))

    def includes(self, laser: str, wavelength_nm: float) -> bool:
        return any(_norm(h.name) == _norm(laser)
                   and abs(h.wavelength_nm - wavelength_nm) <= _WL_TOLERANCE_NM
                   for h in self.heads)

    def missing_from(self, state: EmissionState) -> list[str]:
        return state.covers(*(h.name for h in self.heads))

    def differences(self, other: ConfigIdentity) -> list[str]:
        a = {_norm(h.name): h for h in self.heads}
        b = {_norm(h.name): h for h in other.heads}
        out: list[str] = []
        for key in sorted(set(a) | set(b)):
            if key not in b:
                out.append(f"{a[key].name}: no longer connected")
            elif key not in a:
                out.append(f"{b[key].name}: newly connected")
            else:
                ha, hb = a[key], b[key]
                if abs(ha.wavelength_nm - hb.wavelength_nm) > _WL_TOLERANCE_NM:
                    out.append(f"{ha.name}: wavelength changed from {ha.wavelength_nm:g} "
                               f"to {hb.wavelength_nm:g} nm")
                if ha.serial != hb.serial:
                    out.append(f"{ha.name}: serial number changed from {ha.serial or '?'} "
                               f"to {hb.serial or '?'}")
        return out

    def identity(self) -> str:
        lines = sorted(f"{_norm(h.name)}|{h.wavelength_nm:.1f}|{h.serial}" for h in self.heads)
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {"heads": [{"name": h.name, "wavelength_nm": h.wavelength_nm, "serial": h.serial}
                          for h in self.heads]}

    @classmethod
    def from_dict(cls, d: dict) -> ConfigIdentity:
        if not isinstance(d, dict) or not isinstance(d.get("heads"), list):
            raise ValueError("config: expected {heads: [{name, wavelength_nm, serial}]}")
        heads = []
        for i, h in enumerate(d["heads"]):
            where = f"config.heads[{i}]"
            if not isinstance(h, dict):
                raise ValueError(f"{where}: expected an object")
            _check_keys(h, {"name", "wavelength_nm", "serial"}, where)
            heads.append(HeadIdentity(_text(h, "name", where),
                                      _number(h, "wavelength_nm", where),
                                      str(h.get("serial") or "")))
        return cls(tuple(heads))


# -------------------------------------------------------------------------------------------
# The measurements
# -------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ReferencePoint:
    """One calibration reference: the diode's raw reading captured at the same moment the
    user entered the µW a calibrated external meter showed at the objective.

    ``emission`` is the verified all-lasers state at the capture (the photodiode sums every
    laser: every other laser confirmed OFF, by readback). ``meter``/``meter_calibrated`` are
    the meter's identity and its own calibration date; ``intensity_pct`` records the drive
    setting the point was taken at -- provenance only, never a factor.
    """

    raw: float
    uw: float
    emission: EmissionState = field(default_factory=EmissionState)
    meter: str = ""
    meter_calibrated: str = ""
    measured: str = ""
    intensity_pct: float | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "raw": self.raw, "uw": self.uw, "emission": self.emission.to_dict(),
            "meter": self.meter, "meter_calibrated": self.meter_calibrated,
            "measured": self.measured,
            "intensity_pct": self.intensity_pct, "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ReferencePoint:
        _check_keys(d, {"raw", "uw", "emission", "meter", "meter_calibrated", "measured",
                        "intensity_pct", "note"}, "reference")
        emission = _require(d, "emission", "reference")
        if not isinstance(emission, (dict, list)):
            raise ValueError("reference: 'emission' must record the verified laser states")
        pct = d.get("intensity_pct")
        if pct is not None and (isinstance(pct, bool) or not isinstance(pct, (int, float))):
            raise ValueError(f"reference: 'intensity_pct' must be a number, got {pct!r}")
        return cls(
            raw=_number(d, "raw", "reference"), uw=_number(d, "uw", "reference"),
            emission=EmissionState.from_dict(emission),
            meter=str(d.get("meter") or ""),
            meter_calibrated=str(d.get("meter_calibrated") or ""),
            measured=str(d.get("measured") or ""),
            intensity_pct=None if pct is None else float(pct),
            note=str(d.get("note") or ""),
        )


@dataclass(frozen=True)
class DarkOffset:
    """The diode's raw reading with the emission blocked -- the µW zero, its own measurement.

    ``emission`` must confirm every connected laser verified OFF by readback.
    """

    raw: float
    emission: EmissionState = field(default_factory=EmissionState)
    measured: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {"raw": self.raw, "emission": self.emission.to_dict(),
                "measured": self.measured, "note": self.note}

    @classmethod
    def from_dict(cls, d: dict) -> DarkOffset:
        _check_keys(d, {"raw", "emission", "measured", "note"}, "dark offset")
        emission = _require(d, "emission", "dark offset")
        if not isinstance(emission, (dict, list)):
            raise ValueError("dark offset: 'emission' must record the verified laser states")
        return cls(raw=_number(d, "raw", "dark offset"),
                   emission=EmissionState.from_dict(emission),
                   measured=str(d.get("measured") or ""), note=str(d.get("note") or ""))


@dataclass(frozen=True)
class Key:
    """Which laser a calibration belongs to: its name as configured, and its wavelength."""

    laser: str
    wavelength_nm: float

    @classmethod
    def of(cls, laser: str, wavelength_nm: float) -> Key:
        return cls(str(laser).strip(), float(wavelength_nm))

    def matches(self, other: Key, tol_nm: float = _WL_TOLERANCE_NM) -> bool:
        return _norm(self.laser) == _norm(other.laser) \
            and abs(self.wavelength_nm - other.wavelength_nm) <= tol_nm

    def __str__(self) -> str:
        return f"{self.laser} {self.wavelength_nm:g} nm"


@dataclass(frozen=True)
class LinearFit:
    """The straight line through the dark-corrected anchors -- a LINEARITY report, never the
    converter. ``slope`` is µW per raw count above dark; the residuals say how straight the
    measured response was."""

    slope: float
    n_points: int
    max_residual_uw: float
    rms_residual_uw: float


@dataclass(frozen=True)
class Conversion:
    """One conversion attempt. ``status`` says what happened: ``measured`` (exactly a measured
    point or the dark reading), ``interpolated`` (between measured anchors), ``extrapolated``
    (beyond them: number present but ``valid=False``), or a refusal -- ``uncalibrated``,
    ``invalid``, ``expired``, ``conditions-unknown``, ``conditions-mismatch``,
    ``configuration-unknown``, ``config-changed``, ``emission-unknown``,
    ``emission-unverified``, ``below-dark`` -- with ``uw=None`` and the ``reason``.
    For the inverse (:meth:`PowerCalibration.raw_for`), ``raw`` carries the requested µW and
    ``uw`` the raw reading. ``uncertainty_uw`` is the fit's worst residual (the calibration's
    measured non-linearity) when a fit exists."""

    raw: float
    uw: float | None
    valid: bool
    status: str
    reason: str = ""
    uncertainty_uw: float | None = None


def _interpolate(xs: list[float], ys: list[float], x: float) -> tuple[float | None, str]:
    """Bounded piecewise-linear interpolation over measured anchors. Returns
    ``(value, kind)`` with kind ``measured`` / ``interpolated`` / ``extrapolated`` /
    ``below``; the value is ``None`` where nothing honest exists."""
    for xi, yi in zip(xs, ys):
        if math.isclose(x, xi, rel_tol=1e-9, abs_tol=1e-9):
            return yi, "measured"
    if x < xs[0]:
        return None, "below"
    if x > xs[-1]:
        x0, x1 = xs[-2], xs[-1]
        y0, y1 = ys[-2], ys[-1]
        return y1 + (y1 - y0) * (x - x1) / (x1 - x0), "extrapolated"
    for i in range(len(xs) - 1):
        if xs[i] < x < xs[i + 1]:
            f = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + f * (ys[i + 1] - ys[i]), "interpolated"
    return None, "below"


# -------------------------------------------------------------------------------------------
# One laser, one wavelength, one verified setup, one date
# -------------------------------------------------------------------------------------------
class PowerCalibration:
    """The calibration of one laser head at one wavelength, measured in one verified
    configuration, valid for its conditions, for three calendar months."""

    def __init__(self, laser: str, wavelength_nm: float, *, conditions: LaserConditions | None = None,
                 config: ConfigIdentity | None = None, calibrated: str = "") -> None:
        self.key = Key.of(laser, wavelength_nm)
        self.conditions = conditions or LaserConditions(self.key.laser, self.key.wavelength_nm)
        self.config = config or ConfigIdentity()
        self.calibrated = str(calibrated)
        self.points: list[ReferencePoint] = []
        self.dark: DarkOffset | None = None

    # -- captures ---------------------------------------------------------------------------
    def add_point(self, point: ReferencePoint) -> None:
        """Record one simultaneous (raw, meter-µW) capture."""
        self.points.append(point)

    def set_dark(self, dark: DarkOffset) -> None:
        """Record the dark offset (the emission blocked, every laser verified off)."""
        self.dark = dark

    # -- dates ------------------------------------------------------------------------------
    def expires_on(self) -> date | None:
        """The day the calibration expires: three calendar months after its date."""
        if not self.calibrated.strip():
            return None
        try:
            measured = date.fromisoformat(self.calibrated)
        except ValueError:
            return None
        return _add_months(measured, LIFETIME_MONTHS)

    def is_expired(self, on: date | None = None) -> bool:
        on = on or date.today()
        expires = self.expires_on()
        return expires is not None and on >= expires

    # -- validation -------------------------------------------------------------------------
    def validate(self, at: date | None = None) -> list[str]:
        """Everything that blocks a µW claim: missing measurements, bad readings, unverified
        states, a changed setup, expiry. Empty means the calibration may convert."""
        on = at or date.today()
        problems: list[str] = []
        if not self.calibrated.strip():
            problems.append("calibration date: not recorded; the expiry needs the day it "
                            "was measured")
        else:
            try:
                date.fromisoformat(self.calibrated)
            except ValueError:
                problems.append(f"calibration date {self.calibrated!r}: not an ISO date "
                                f"(YYYY-MM-DD)")
        c = self.conditions
        if c.repetition_rate_hz is None:
            problems.append("repetition rate: not recorded; a calibration holds only for "
                            "the rate it was measured at")
        if not c.mode.strip():
            problems.append("operating mode: not recorded (pulsed, cw, ...)")
        if _norm(c.laser) != _norm(self.key.laser) \
                or abs(c.wavelength_nm - self.key.wavelength_nm) > _WL_TOLERANCE_NM:
            problems.append(f"conditions name {c.laser} at {c.wavelength_nm:g} nm but this "
                            f"calibration is {self.key}")
        if not self.config.heads:
            problems.append("configuration: not recorded (which heads were connected, "
                            "verified by hardware readback)")
        elif not self.config.includes(self.key.laser, self.key.wavelength_nm):
            problems.append(f"configuration: {self.key} is not among the verified "
                            f"connected heads")
        dark = self.dark
        if dark is None:
            problems.append("dark offset: not measured yet; block the emission and read "
                            "the diode")
        else:
            if not math.isfinite(dark.raw):
                problems.append("dark offset: raw reading is not a number")
            elif dark.raw < 0:
                problems.append(f"dark offset: negative raw reading ({dark.raw:g})")
            ok, why = dark.emission.all_off_confirmed()
            if not ok:
                problems.append(f"dark offset: {why}")
            missing = self.config.missing_from(dark.emission)
            if missing:
                problems.append(f"dark offset: no verified readback for {', '.join(missing)}")
        if not self.points:
            problems.append("references: none measured yet; read the meter at two or more "
                            "intensities")
        for i, p in enumerate(self.points, 1):
            where = f"reference {i} (raw {p.raw:g})"
            if not math.isfinite(p.raw):
                problems.append(f"reference {i}: raw reading is not a number")
            if not math.isfinite(p.uw):
                problems.append(f"reference {i}: the meter reading is not a number")
            elif p.uw <= 0:
                problems.append(f"reference {i}: the meter read {p.uw:g} µW; a reference "
                                f"needs a positive power")
            if dark is not None and math.isfinite(dark.raw) and math.isfinite(p.raw) \
                    and p.raw <= dark.raw:
                problems.append(f"reference {i}: raw {p.raw:g} is not above the dark "
                                f"offset ({dark.raw:g})")
            ok, why = p.emission.confirmed_single(self.key.laser)
            if not ok:
                problems.append(f"reference {i}: {why}")
            missing = self.config.missing_from(p.emission)
            if missing:
                problems.append(f"reference {i}: no verified readback for "
                                f"{', '.join(missing)}")
        pts = sorted((p for p in self.points if math.isfinite(p.raw) and math.isfinite(p.uw)),
                     key=lambda p: p.raw)
        for a, b in zip(pts, pts[1:]):
            if math.isclose(a.raw, b.raw, rel_tol=0.0, abs_tol=1e-9) \
                    and not math.isclose(a.uw, b.uw, rel_tol=1e-9, abs_tol=1e-12):
                problems.append(f"reference conflict: two references at raw {a.raw:g} read "
                                f"{a.uw:g} and {b.uw:g} µW")
        uniq: list[ReferencePoint] = []
        for p in pts:
            if not uniq or not math.isclose(uniq[-1].raw, p.raw, rel_tol=0.0, abs_tol=1e-9):
                uniq.append(p)
        for a, b in zip(uniq, uniq[1:]):
            if b.uw < a.uw:
                problems.append(f"references are not monotonic: raw {b.raw:g} reads less "
                                f"power ({b.uw:g} µW) than raw {a.raw:g} ({a.uw:g} µW)")
        expires = self.expires_on()
        if expires is not None and on >= expires:
            problems.append(f"the calibration expired on {expires.isoformat()}; measure a "
                            f"fresh reference for this laser")
        return problems

    def warnings(self, at: date | None = None) -> list[str]:
        """Provenance gaps and near expiry -- visible, but not blocking."""
        on = at or date.today()
        out: list[str] = []
        for i, p in enumerate(self.points, 1):
            where = f"reference {i} (raw {p.raw:g})"
            if not p.meter.strip():
                out.append(f"{where}: no meter recorded; note which meter read it")
            if not p.meter_calibrated.strip():
                out.append(f"{where}: the meter's own calibration date is not recorded")
            if not p.measured.strip():
                out.append(f"{where}: no measurement date recorded")
        if len(self.points) == 1:
            out.append("only one reference: the curve rests on the dark reading and that "
                       "single point")
        expires = self.expires_on()
        if expires is not None:
            days = (expires - on).days
            if 0 <= days <= _EXPIRY_WARNING_DAYS:
                out.append(f"the calibration expires on {expires.isoformat()} "
                           f"({days} days); plan a fresh measurement")
        return out

    @property
    def usable(self) -> bool:
        return self.usable_at(date.today())

    def usable_at(self, on: date) -> bool:
        return not self.validate(at=on)

    # -- the curve --------------------------------------------------------------------------
    def _anchors(self) -> tuple[list[float], list[float]] | None:
        """Measured anchors: the dark reading (0 µW) and the references, ascending by raw."""
        if self.dark is None or not self.points:
            return None
        xs, ys = [self.dark.raw], [0.0]
        for p in sorted(self.points, key=lambda p: p.raw):
            if math.isclose(p.raw, xs[-1], rel_tol=0.0, abs_tol=1e-9):
                continue  # a repeated identical reading
            xs.append(p.raw)
            ys.append(p.uw)
        return xs, ys

    def raw_domain(self) -> tuple[float, float] | None:
        """The measured raw range (dark to highest reference); nothing converts outside it."""
        anchors = self._anchors()
        return None if anchors is None else (anchors[0][0], anchors[0][-1])

    def uw_domain(self) -> tuple[float, float] | None:
        """The measured µW range (0 to the highest reference)."""
        anchors = self._anchors()
        return None if anchors is None else (0.0, max(anchors[1]))

    def linear_fit(self) -> LinearFit | None:
        """The through-origin line over the dark-corrected anchors, with residuals -- from
        three measured anchors up. A quality report: how linear the response measured."""
        anchors = self._anchors()
        if anchors is None or len(anchors[0]) < 3:
            return None
        xs, ys = anchors
        dark = xs[0]
        cx = [x - dark for x in xs]
        sxx = sum(v * v for v in cx)
        if sxx <= 0:
            return None
        slope = sum(a * b for a, b in zip(cx, ys)) / sxx
        residuals = [y - slope * x for x, y in zip(cx, ys)]
        return LinearFit(slope, len(residuals),
                         max(abs(r) for r in residuals),
                         math.sqrt(sum(r * r for r in residuals) / len(residuals)))

    # -- conversion -------------------------------------------------------------------------
    def convert(self, raw: float, *, conditions: LaserConditions | None = None,
                emission: EmissionState | None = None, config: ConfigIdentity | None = None,
                on: date | None = None) -> Conversion:
        """A raw diode reading to µW -- only for the laser, conditions, verified configuration
        and verified emission state it was calibrated for. Every µW this returns is inside the
        measured range; beyond it the number comes back marked ``extrapolated``/invalid."""
        on = on or date.today()
        raw = float(raw)
        problems = self.validate(at=on)
        if self.dark is None or not self.points:
            return Conversion(raw, None, False, "uncalibrated",
                              "; ".join(problems) or f"{self.key} is not calibrated")
        if problems:
            expires = self.expires_on()
            if self.is_expired(on) and expires is not None:
                return self._refusal(raw, "expired", f"the calibration expired on "
                                      f"{expires.isoformat()}; measure a fresh "
                                      f"reference for this laser")
            return self._refusal(raw, "invalid", "; ".join(problems))
        if conditions is None:
            return self._refusal(raw, "conditions-unknown",
                                 "state the operating conditions (laser, wavelength, "
                                 "repetition rate, mode, optical path) to claim a power: "
                                 "the photodiode sums every laser")
        if diffs := conditions.differences(self.conditions):
            return self._refusal(raw, "conditions-mismatch", "; ".join(diffs))
        if config is None:
            return self._refusal(raw, "configuration-unknown",
                                 "state the verified configuration (which heads are "
                                 "connected) to claim a power")
        if diffs := config.differences(self.config):
            return self._refusal(raw, "config-changed",
                                 "the configuration changed since the calibration ("
                                 + "; ".join(diffs) + "); recalibrate this laser")
        if emission is None:
            return self._refusal(raw, "emission-unknown",
                                 "no verified emission state: the photodiode sums every "
                                 "laser, so every other laser must be confirmed off by "
                                 "readback")
        ok, why = emission.confirmed_single(self.key.laser)
        if not ok:
            return self._refusal(raw, "emission-unverified", why)
        xs, ys = self._anchors()
        value, kind = _interpolate(xs, ys, raw)
        fit = self.linear_fit()
        uncertainty = fit.max_residual_uw if fit else None
        if kind == "below":
            return Conversion(raw, None, False, "below-dark",
                              f"raw {raw:g} is below the measured dark offset ({xs[0]:g}); "
                              f"no light above dark to convert")
        if value is None:
            return self._refusal(raw, "invalid", "the reading sits outside the measured "
                                 "anchors in a way they do not cover")
        if kind == "extrapolated":
            return Conversion(raw, value, False, "extrapolated",
                              f"raw {raw:g} is beyond the highest measured reference "
                              f"({xs[-1]:g}); the calibration says nothing there",
                              uncertainty)
        return Conversion(raw, value, True, kind, "", uncertainty)

    def raw_for(self, uw: float, *, conditions: LaserConditions | None = None,
                emission: EmissionState | None = None, config: ConfigIdentity | None = None,
                on: date | None = None) -> Conversion:
        """The inverse: a target power to the raw diode reading, under the same gates and the
        same measured band. In the returned :class:`Conversion`, ``uw`` carries the raw
        reading."""
        on = on or date.today()
        uw = float(uw)
        problems = self.validate(at=on)
        if self.dark is None or not self.points:
            return Conversion(uw, None, False, "uncalibrated",
                              "; ".join(problems) or f"{self.key} is not calibrated")
        if problems:
            expires = self.expires_on()
            if self.is_expired(on) and expires is not None:
                return self._refusal(uw, "expired", f"the calibration expired on "
                                      f"{expires.isoformat()}; measure a fresh "
                                      f"reference for this laser")
            return self._refusal(uw, "invalid", "; ".join(problems))
        if conditions is None:
            return self._refusal(uw, "conditions-unknown",
                                 "state the operating conditions (laser, wavelength, "
                                 "repetition rate, mode, optical path) to claim a power")
        if diffs := conditions.differences(self.conditions):
            return self._refusal(uw, "conditions-mismatch", "; ".join(diffs))
        if config is None:
            return self._refusal(uw, "configuration-unknown",
                                 "state the verified configuration (which heads are "
                                 "connected) to claim a power")
        if diffs := config.differences(self.config):
            return self._refusal(uw, "config-changed",
                                 "the configuration changed since the calibration ("
                                 + "; ".join(diffs) + "); recalibrate this laser")
        if emission is None:
            return self._refusal(uw, "emission-unknown",
                                 "no verified emission state: the photodiode sums every "
                                 "laser, so every other laser must be confirmed off by "
                                 "readback")
        ok, why = emission.confirmed_single(self.key.laser)
        if not ok:
            return self._refusal(uw, "emission-unverified", why)
        xs, ys = self._anchors()
        value, kind = _interpolate(ys, xs, uw)  # the anchors, µW -> raw
        if kind == "below":
            return Conversion(uw, None, False, "negative-power",
                              f"a negative power ({uw:g} µW) has no raw reading")
        if value is None:
            return self._refusal(uw, "invalid", "the target sits outside the measured "
                                 "anchors in a way they do not cover")
        if kind == "extrapolated":
            return Conversion(uw, value, False, "extrapolated",
                              f"{uw:g} µW is beyond the highest measured reference "
                              f"({ys[-1]:g} µW); the calibration says nothing there")
        return Conversion(uw, value, True, kind, "")

    def require_uw(self, raw: float, **kwargs) -> float:
        """The µW for a raw reading, or a :exc:`ValueError` naming why there is none."""
        c = self.convert(raw, **kwargs)
        if not c.valid or c.uw is None:
            raise ValueError(f"{self.key}: {c.reason or c.status} [{c.status}]")
        return c.uw

    def require_raw(self, uw: float, **kwargs) -> float:
        """The raw reading for a target µW, or a :exc:`ValueError` naming why there is none."""
        c = self.raw_for(uw, **kwargs)
        if not c.valid or c.uw is None:
            raise ValueError(f"{self.key}: {c.reason or c.status} [{c.status}]")
        return c.uw

    @staticmethod
    def _refusal(raw: float, status: str, reason: str) -> Conversion:
        return Conversion(raw, None, False, status, reason)

    # -- storage ----------------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "laser": self.key.laser, "wavelength_nm": self.key.wavelength_nm,
            "calibrated": self.calibrated,
            "conditions": self.conditions.to_dict(), "config": self.config.to_dict(),
            "dark": self.dark.to_dict() if self.dark is not None else None,
            "points": [p.to_dict() for p in self.points],
        }

    @classmethod
    def from_dict(cls, d: dict) -> PowerCalibration:
        if not isinstance(d, dict):
            raise ValueError("calibration: expected an object")
        _check_keys(d, {"laser", "wavelength_nm", "calibrated", "conditions", "config",
                        "dark", "points"}, "calibration")
        if "calibrated" not in d or not str(d.get("calibrated") or "").strip():
            raise ValueError("calibration: missing 'calibrated' -- the calibration date is "
                             "required")
        conditions = d.get("conditions")
        if not isinstance(conditions, dict):
            raise ValueError("calibration: missing 'conditions' -- the conditions it was "
                             "measured at are required")
        cfg = d.get("config")
        if not isinstance(cfg, dict):
            raise ValueError("calibration: missing 'config' -- the verified configuration "
                             "is required")
        cal = cls(_text(d, "laser", "calibration"), _number(d, "wavelength_nm", "calibration"),
                  conditions=LaserConditions.from_dict(conditions),
                  config=ConfigIdentity.from_dict(cfg), calibrated=str(d["calibrated"]))
        dark = d.get("dark")
        if dark is not None:
            if not isinstance(dark, dict):
                raise ValueError("calibration: 'dark' must be the dark-offset object")
            cal.set_dark(DarkOffset.from_dict(dark))
        for p in d.get("points") or []:
            cal.add_point(ReferencePoint.from_dict(p))
        return cal


# -------------------------------------------------------------------------------------------
# The book: one calibration per laser and condition set
# -------------------------------------------------------------------------------------------
class CalibrationSet:
    """Every laser's calibrations. One laser may carry several -- one per condition set (a
    repetition-rate change needs its own) -- never one shared across lasers."""

    def __init__(self, calibrations=()) -> None:
        self._calibrations: list[PowerCalibration] = list(calibrations)

    @property
    def calibrations(self) -> tuple[PowerCalibration, ...]:
        return tuple(self._calibrations)

    def add(self, calibration: PowerCalibration) -> None:
        self._calibrations.append(calibration)

    def matches(self, laser: str, wavelength_nm: float,
                conditions: LaserConditions | None = None) -> list[PowerCalibration]:
        key = Key.of(laser, wavelength_nm)
        out = [c for c in self._calibrations if c.key.matches(key)]
        if conditions is not None:
            out = [c for c in out if not c.conditions.differences(conditions)]
        return out

    def calibration_for(self, laser: str, wavelength_nm: float,
                        conditions: LaserConditions | None = None,
                        create: bool = False) -> PowerCalibration | None:
        """The calibration for a laser, its conditions stated; ``None`` when ambiguous (say
        the conditions) or absent (``create`` starts an empty one -- a new laser begins with
        no references)."""
        found = self.matches(laser, wavelength_nm, conditions)
        if found:
            return found[0] if conditions is not None or len(found) == 1 else None
        if create:
            cal = PowerCalibration(laser, wavelength_nm, conditions=conditions)
            self._calibrations.append(cal)
            return cal
        return None

    def missing_choices(self, on: date | None = None) -> tuple[float, ...]:
        """Which of :data:`LASER_WAVELENGTHS_NM` (the available choices, not necessarily
        installed) has no currently usable calibration."""
        on = on or date.today()
        out = []
        for wl in LASER_WAVELENGTHS_NM:
            if not any(abs(c.key.wavelength_nm - wl) <= _WL_TOLERANCE_NM
                       and c.usable_at(on) for c in self._calibrations):
                out.append(wl)
        return tuple(out)

    def to_dict(self) -> dict:
        return {"schema": CALIBRATION_SCHEMA,
                "calibrations": [c.to_dict() for c in self._calibrations]}

    @classmethod
    def from_dict(cls, d: dict) -> CalibrationSet:
        if not isinstance(d, dict):
            raise ValueError("power calibration: expected an object")
        schema = d.get("schema")
        if not schema or not str(schema).startswith(_SCHEMA_PREFIX):
            raise ValueError(f"schema: {schema!r} is not a power-calibration file")
        try:
            version = int(str(schema).split("/", 1)[1])
        except ValueError:
            raise ValueError(f"schema: {schema!r} is not a power-calibration file") from None
        if version > 1:
            raise ValueError(f"schema: version {schema!r} is newer than this ChiSurf reads "
                             f"({CALIBRATION_SCHEMA})")
        book = cls()
        for c in d.get("calibrations") or []:
            book.add(PowerCalibration.from_dict(c))
        return book

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path) -> CalibrationSet:
        return cls.from_dict(json.loads(Path(path).read_text()))
