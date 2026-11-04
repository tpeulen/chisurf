"""Instrument health: the reference-measurement history of this instrument.

The store keeps historical reference measurements -- diffusion time and background-corrected
molecular brightness at the laser power they were measured with -- so a later measurement can be
judged against what the same instrument did before under the same conditions. Two physical facts
shape the module (FCS practical guides such as PMC3812671 and the certified-reference-material
calibration of DOI 10.1021/acs.analchem.8b02213): molecular brightness is a count rate per
molecule that depends on the background and on the optical and sample conditions, and an FCS
calibration is valid for the setup it was measured on. Neither value is comparable across
changed conditions.

Rules the module enforces (each pinned by a test):

* **Comparability is keyed on explicit conditions.** Laser wavelength, the *verified, calibrated,
  isolated* laser power, excitation pulse mode and timing (rep rate when pulsed), optical
  configuration, detector, dye, temperature and any extra conditions the user records must match
  exactly for two measurements to be compared. A total-diode reading taken with several lasers on
  does not establish an individual laser's power: a measurement whose power is not verified is
  stored but never gets a spec verdict.
* **Bounds come from the user.** Spec or reference bounds are established explicitly
  (:meth:`ReferenceHistory.set_bounds`, or a call-level ``bounds=``), or derived from the user's
  own stored records (:meth:`ReferenceHistory.reference_bounds`, labelled as derived). The module
  ships no thresholds whatsoever.
* **A deviation is a recommendation, never a proof.** A value outside the established bounds
  yields *recommend inspection or maintenance*; it is not, by itself, scientific proof of an
  instrument fault, and conformance is not proof of health (the ``caveat`` of every verdict).
* **Missing metadata or unverified power: no spec verdict.** The verdict is then
  ``unverifiable`` (it names the missing conditions) or ``unverified`` (power), never a guess.
* **Insufficient or incomparable history is reported explicitly** -- how many records the store
  holds, how many are comparable, on which conditions the others differ -- not silently dropped.
* **Invalid values are rejected** (non-finite, non-positive diffusion times or brightness,
  non-serialisable provenance, unknown fields, ...); nothing is written on rejection.
* **User records are preserved.** Writes are atomic (temp file + ``os.replace``); a corrupt,
  foreign or newer-version store is reported (:class:`StoreError`) and never overwritten; there
  is no cap on the number of records.

The store is plain JSON at a caller-supplied path and needs no hardware; the caller measures and
fits, this module only remembers and compares. Every measurement carries a UTC timestamp,
laser, power (and whether it was verified), excitation mode/timing, optical configuration,
detector, dye, temperature, the corrected brightness and its diffusion time, plus free-form
conditions and provenance (how the background correction and the fit were done).
"""

from __future__ import annotations

import copy
import datetime
import json
import math
import numbers
import os
import statistics
import tempfile
import uuid
from pathlib import Path
from typing import Any

__all__ = [
    "CAVEAT",
    "CONDITION_FIELDS",
    "InsufficientHistory",
    "InvalidBounds",
    "InvalidMeasurement",
    "METRICS",
    "ReferenceHistory",
    "ReferenceHistoryError",
    "SCHEMA",
    "StoreError",
    "VERSION",
    "conditions_key",
]

#: Identity of the on-disk document; a foreign or newer store is reported, never overwritten.
SCHEMA = "chisurf.acq.instrument-reference-history"
VERSION = 1

#: The tracked metrics: diffusion time (s) and background-corrected molecular brightness
#: (counts per molecule per second at the laser power of the measurement).
METRICS = ("tau_diff_s", "brightness_cps")

#: The explicit experimental conditions that key comparability (``temperature_c`` and
#: ``rep_rate_mhz`` enter the key when recorded; a CW measurement has no rep rate).
CONDITION_FIELDS = (
    "laser_nm",
    "power_uw",
    "power_verified",
    "excitation_mode",
    "rep_rate_mhz",
    "optical_configuration",
    "detector",
    "dye",
    "temperature_c",
)

#: Fields a stored measurement carries besides the conditions.
MEASUREMENT_FIELDS = CONDITION_FIELDS + (
    "timestamp_utc",
    "tau_diff_s",
    "brightness_cps",
    "background_cps",
    "conditions",
    "provenance",
    "notes",
)

#: Top-level bookkeeping keys a stored record may carry when handed back in.
_RECORD_KEYS = ("uid", "stored_at_utc", "key")

#: The conditions that must be present (and the power verified) before any spec verdict.
_VERDICT_CONDITIONS = (
    "timestamp_utc",
    "laser_nm",
    "power_uw",
    "power_verified",
    "excitation_mode",
    "optical_configuration",
    "detector",
    "dye",
)

CAVEAT = (
    "A deviation from the user-established bounds is a recommendation to inspect or maintain the "
    "instrument. It is not, by itself, scientific proof of an instrument fault; neither is "
    "conformance proof of health. The verdict is only as good as the bounds behind it and the "
    "verified, calibrated, isolated laser power of the measurement."
)


# -- errors --------------------------------------------------------------------------------------
class ReferenceHistoryError(Exception):
    """Base class of the reference-history errors."""


class StoreError(ReferenceHistoryError):
    """The store cannot be read or written. The file is left exactly as it is."""


class InvalidMeasurement(ValueError):
    """A measurement carries invalid values or unknown fields; nothing was stored."""


class InvalidBounds(ValueError):
    """The bounds are malformed or name untracked metrics."""


class InsufficientHistory(ReferenceHistoryError):
    """Not enough comparable records to derive reference bounds from the history."""


# -- scalar validation ---------------------------------------------------------------------------
def _finite_float(value: Any, name: str, *, positive: bool = False, nonnegative: bool = False):
    """A finite JSON number (bools rejected); optionally strictly positive / non-negative."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise InvalidMeasurement(f"{name} must be a finite number, got {value!r}")
    out = float(value)
    if not math.isfinite(out):
        raise InvalidMeasurement(f"{name} must be finite, got {value!r}")
    if positive and out <= 0.0:
        raise InvalidMeasurement(f"{name} must be > 0, got {out!r}")
    if nonnegative and out < 0.0:
        raise InvalidMeasurement(f"{name} must be >= 0, got {out!r}")
    return out


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidMeasurement(f"{name} must be a non-empty string, got {value!r}")
    return value.strip()


def _iso_utc(value: Any, name: str = "timestamp_utc") -> str:
    """An ISO-8601 timestamp (string or datetime) with an explicit timezone, stored as UTC."""
    if isinstance(value, datetime.datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise InvalidMeasurement(f"{name}: not an ISO-8601 timestamp: {value!r}") from exc
    else:
        raise InvalidMeasurement(f"{name} must be an ISO-8601 string or a datetime, got {value!r}")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise InvalidMeasurement(
            f"{name} must carry a timezone (a UTC instant), got {value!r}"
        )
    return dt.astimezone(datetime.timezone.utc).isoformat()


def _now_utc_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _condition_scalar(value: Any, name: str):
    """A JSON-serialisable scalar condition value; ``None`` means *not recorded* (dropped)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Real):
        return _finite_float(value, f"condition {name}")
    if isinstance(value, str):
        return value
    raise InvalidMeasurement(
        f"condition {name} must be a string, number, boolean or null, got {value!r}"
    )


def conditions_key(conditions: dict) -> str:
    """The canonical comparability key of a conditions mapping.

    Numbers are normalised (``25`` and ``25.0`` are the same power), ``None``-valued conditions
    are dropped (*not recorded*), the rest is a sorted JSON object -- so two measurements are
    comparable exactly when their keys are equal.
    """
    if not isinstance(conditions, dict):
        raise InvalidMeasurement(f"conditions must be a mapping, got {conditions!r}")
    canon = {}
    for name, value in conditions.items():
        if not isinstance(name, str) or not name:
            raise InvalidMeasurement(f"condition names must be non-empty strings, got {name!r}")
        scalar = _condition_scalar(value, name)
        if scalar is not None:
            canon[name] = scalar
    return json.dumps(canon, sort_keys=True, separators=(",", ":"), allow_nan=False)


# -- measurement validation ----------------------------------------------------------------------
def _extras(conditions: Any) -> dict:
    """The user's extra conditions of a measurement; must not shadow the core condition fields."""
    if conditions is None:
        return {}
    if not isinstance(conditions, dict):
        raise InvalidMeasurement(f"conditions must be a mapping, got {conditions!r}")
    out = {}
    for name, value in conditions.items():
        if name in CONDITION_FIELDS:
            raise InvalidMeasurement(
                f"condition {name} is a core field of the measurement; pass it at the top level"
            )
        scalar = _condition_scalar(value, name)
        if scalar is not None:
            out[name] = scalar
    return out


def _measurement(fields: dict, *, complete: bool = True) -> dict:
    """Validate a measurement (strictly for storing; leniently for evaluating).

    Lenient mode still rejects *invalid* values but tolerates *missing* metadata (``None``), so
    the verdict can report exactly what is missing instead of raising.
    """
    if not isinstance(fields, dict):
        raise InvalidMeasurement(f"a measurement must be a mapping, got {fields!r}")
    unknown = sorted(set(fields) - set(MEASUREMENT_FIELDS) - set(_RECORD_KEYS))
    if unknown:
        raise InvalidMeasurement(
            f"unknown field(s): {', '.join(unknown)}; known fields: {', '.join(MEASUREMENT_FIELDS)}"
        )

    def field(name):
        return fields.get(name)

    if complete:
        missing = [name for name in MEASUREMENT_FIELDS if name not in _OPTIONAL_FIELDS
                   and field(name) is None]
        if missing:
            raise InvalidMeasurement(f"missing field(s): {', '.join(missing)}")

    m: dict[str, Any] = {}
    m["timestamp_utc"] = (None if field("timestamp_utc") is None
                          else _iso_utc(field("timestamp_utc")))
    m["laser_nm"] = (None if field("laser_nm") is None
                     else _finite_float(field("laser_nm"), "laser_nm", positive=True))
    m["power_uw"] = (None if field("power_uw") is None
                     else _finite_float(field("power_uw"), "power_uw", positive=True))
    verified = field("power_verified")
    if verified is not None and not isinstance(verified, bool):
        raise InvalidMeasurement(
            "power_verified must be a boolean: True only when the power is a verified, "
            "calibrated reading taken with this one laser isolated (all other lasers off)"
        )
    m["power_verified"] = verified
    mode = None if field("excitation_mode") is None else _text(field("excitation_mode"),
                                                               "excitation_mode")
    m["excitation_mode"] = mode
    rep_rate = field("rep_rate_mhz")
    if mode == "cw":
        if rep_rate is not None:
            raise InvalidMeasurement("rep_rate_mhz must be omitted for excitation_mode 'cw'")
        m["rep_rate_mhz"] = None
    elif rep_rate is None:
        if complete:
            raise InvalidMeasurement("rep_rate_mhz is required unless excitation_mode is 'cw'")
        m["rep_rate_mhz"] = None
    else:
        m["rep_rate_mhz"] = _finite_float(rep_rate, "rep_rate_mhz", positive=True)
    m["optical_configuration"] = (None if field("optical_configuration") is None
                                  else _text(field("optical_configuration"),
                                             "optical_configuration"))
    m["detector"] = None if field("detector") is None else _text(field("detector"), "detector")
    m["dye"] = None if field("dye") is None else _text(field("dye"), "dye")
    m["tau_diff_s"] = (None if field("tau_diff_s") is None
                       else _finite_float(field("tau_diff_s"), "tau_diff_s", positive=True))
    m["brightness_cps"] = (None if field("brightness_cps") is None
                           else _finite_float(field("brightness_cps"), "brightness_cps",
                                              positive=True))
    m["temperature_c"] = (None if field("temperature_c") is None
                          else _finite_float(field("temperature_c"), "temperature_c"))
    m["background_cps"] = (None if field("background_cps") is None
                           else _finite_float(field("background_cps"), "background_cps",
                                              nonnegative=True))
    m["conditions"] = _extras(field("conditions"))
    provenance = field("provenance")
    if provenance is None:
        provenance = {}
    if not isinstance(provenance, dict):
        raise InvalidMeasurement(f"provenance must be a mapping, got {provenance!r}")
    try:
        json.dumps(provenance, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise InvalidMeasurement(f"provenance must be JSON-serialisable: {exc}") from exc
    m["provenance"] = provenance
    notes = field("notes")
    if notes is not None and not isinstance(notes, str):
        raise InvalidMeasurement(f"notes must be a string, got {notes!r}")
    m["notes"] = notes or ""
    return m


_OPTIONAL_FIELDS = frozenset({
    "rep_rate_mhz", "temperature_c", "background_cps", "conditions", "provenance", "notes",
})


def _combined_conditions(measurement: dict) -> dict:
    """The full explicit conditions of a validated measurement (core fields + user extras)."""
    combined = {}
    for name in CONDITION_FIELDS:
        value = measurement.get(name)
        if value is not None:
            combined[name] = value
    combined.update(measurement.get("conditions") or {})
    return combined


def _conditions_of(value: dict) -> dict:
    """Conditions of *value*: a measurement's full conditions, or an explicit conditions mapping."""
    if not isinstance(value, dict):
        raise InvalidMeasurement(f"expected a conditions mapping or a measurement, got {value!r}")
    if set(value) & (set(MEASUREMENT_FIELDS) - set(CONDITION_FIELDS)):
        return _combined_conditions(_measurement(value, complete=False))
    out = {}
    for name, scalar in ((n, _condition_scalar(v, n)) for n, v in value.items()):
        if scalar is not None:
            out[name] = scalar
    return out


# -- bounds --------------------------------------------------------------------------------------
def _validated_bounds(bounds: Any) -> dict:
    """User-established bounds: ``{metric: {"min": .., "max": ..}}`` over the tracked metrics."""
    if not isinstance(bounds, dict) or not bounds:
        raise InvalidBounds(
            f"bounds must be a non-empty mapping metric -> {{'min' and/or 'max'}} over "
            f"{METRICS}, got {bounds!r}"
        )
    out = {}
    for metric, rule in bounds.items():
        if metric not in METRICS:
            raise InvalidBounds(
                f"unknown metric {metric!r}; the tracked metrics are {METRICS}"
            )
        if not isinstance(rule, dict) or not rule:
            raise InvalidBounds(f"bounds of {metric} must be a mapping with 'min' and/or 'max'")
        clean = {}
        for side in ("min", "max"):
            if side in rule and rule[side] is not None:
                try:
                    clean[side] = _finite_float(rule[side], f"{metric}.{side}", nonnegative=True)
                except InvalidMeasurement as exc:
                    raise InvalidBounds(str(exc)) from exc
        if not clean:
            raise InvalidBounds(f"bounds of {metric} need a 'min' and/or a 'max'")
        if "min" in clean and "max" in clean and clean["min"] >= clean["max"]:
            raise InvalidBounds(f"bounds of {metric}: min {clean['min']!r} >= max {clean['max']!r}")
        out[metric] = clean
    return out


# -- the store -----------------------------------------------------------------------------------
class ReferenceHistory:
    """The instrument's reference-measurement history, persisted as JSON at *path*.

    The file is the one source of truth: every call re-reads it, writes are atomic (temp file in
    the same folder, then ``os.replace``), and a corrupt, foreign or newer file raises
    :class:`StoreError` instead of being repaired or replaced. Read-only calls on a missing file
    behave as an empty history and create nothing.
    """

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    # -- the file --
    def _load(self) -> dict:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"schema": SCHEMA, "version": VERSION, "records": [], "bounds": {}}
        except OSError as exc:
            raise StoreError(f"cannot read the reference-history store {self.path}: {exc}") from exc
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StoreError(
                f"the reference-history store {self.path} is not valid JSON ({exc}); resolve the "
                f"file by hand -- this module never overwrites it"
            ) from exc
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            raise StoreError(
                f"{self.path} is not a {SCHEMA} store; refusing to modify it"
            )
        if doc.get("version") != VERSION:
            raise StoreError(
                f"{self.path} was written by schema version {doc.get('version')!r}, this module "
                f"reads {VERSION!r}; refusing to modify it"
            )
        if not isinstance(doc.get("records"), list) or not isinstance(doc.get("bounds"), dict):
            raise StoreError(f"{self.path} is a damaged {SCHEMA} store; refusing to modify it")
        return doc

    def _flush(self, doc: dict) -> None:
        """Write *doc* atomically: temp file in the same folder, fsync, then ``os.replace``."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = None
        try:
            text = json.dumps(doc, indent=2, allow_nan=False) + "\n"
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent),
                                       prefix=self.path.name + ".", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            tmp = None
        except (OSError, TypeError, ValueError) as exc:
            raise StoreError(f"cannot write the reference-history store {self.path}: {exc}") from exc
        finally:
            if tmp is not None and os.path.exists(tmp):
                os.unlink(tmp)

    # -- records --
    def add(self, **fields) -> dict:
        """Validate and store one reference measurement; returns the stored record.

        Every stored record carries a ``uid``, the ``stored_at_utc`` instant and the canonical
        comparability ``key`` beside the measurement's fields.
        """
        doc = self._load()
        m = _measurement(fields, complete=True)
        record = {
            "uid": uuid.uuid4().hex,
            "stored_at_utc": _now_utc_iso(),
            "key": conditions_key(_combined_conditions(m)),
            **m,
        }
        doc["records"].append(record)
        self._flush(doc)
        return copy.deepcopy(record)

    def records(self) -> list[dict]:
        """All stored measurements, in the order they were added."""
        return copy.deepcopy(self._load()["records"])

    def comparable(self, **fields) -> list[dict]:
        """The stored measurements whose explicit conditions match *fields* exactly."""
        m = _measurement(fields, complete=False)
        key = conditions_key(_combined_conditions(m))
        return [copy.deepcopy(r) for r in self._load()["records"] if r.get("key") == key]

    # -- user-established bounds --
    def set_bounds(self, conditions: dict, bounds: dict, *, kind: str = "reference",
                   note: str = "") -> dict:
        """Establish spec or reference bounds for exactly these conditions.

        *kind* is ``"spec"`` (hard limits, e.g. a datasheet) or ``"reference"`` (the usual range
        on this instrument); *note* records where they come from. There are no defaults: without
        bounds there is no verdict.
        """
        if kind not in ("spec", "reference"):
            raise InvalidBounds(f"kind must be 'spec' or 'reference', got {kind!r}")
        if not isinstance(note, str):
            raise InvalidBounds(f"note must be a string, got {note!r}")
        doc = self._load()
        entry = {"kind": kind, "note": note, "set_at_utc": _now_utc_iso(),
                 "bounds": _validated_bounds(bounds)}
        doc["bounds"][conditions_key(_conditions_of(conditions))] = entry
        self._flush(doc)
        return copy.deepcopy(entry)

    def get_bounds(self, conditions: dict) -> dict | None:
        """The bounds established for exactly these conditions, or ``None``."""
        return copy.deepcopy(self._load()["bounds"].get(conditions_key(_conditions_of(conditions))))

    def all_bounds(self) -> dict:
        """All established bounds, keyed by canonical conditions key."""
        return copy.deepcopy(self._load()["bounds"])

    # -- bounds derived from the user's own records --
    def reference_bounds(self, conditions: dict, *, n_mad: float = 3.0,
                         min_history: int = 8) -> dict:
        """Reference bounds derived from the stored records comparable to *conditions*.

        The method is a robust median spread, ``median ± n_mad × 1.4826 × MAD`` per metric;
        a non-positive lower bound is clipped to 0 and reported. The result is labelled as
        derived -- nothing here is a fabricated threshold: without enough of the user's own
        records (:class:`InsufficientHistory`) there are no derived bounds.
        """
        combined = _conditions_of(conditions)
        key = conditions_key(combined)
        peers = [r for r in self._load()["records"] if r.get("key") == key]
        if len(peers) < min_history:
            raise InsufficientHistory(
                f"insufficient history for derived reference bounds: {len(peers)} comparable "
                f"record(s) stored, need {min_history}; establish bounds with set_bounds() instead"
            )
        bounds, clipped = {}, []
        for metric in METRICS:
            values = sorted(float(r[metric]) for r in peers)
            med = statistics.median(values)
            mad = statistics.median([abs(v - med) for v in values])
            half = n_mad * 1.4826 * mad
            low, high = med - half, med + half
            if low <= 0.0:
                low, _ = 0.0, clipped.append(metric)
            bounds[metric] = {"min": low, "max": high}
        return {
            "bounds": bounds,
            "info": {
                "source": "derived_from_history",
                "method": f"median ± {n_mad} × 1.4826 × MAD of the stored records",
                "n": len(peers),
                "n_mad": n_mad,
                "clipped_min": clipped,
            },
        }

    # -- the verdict --
    def evaluate(self, measurement: dict, bounds: dict | None = None, *,
                 min_history: int = 3) -> dict:
        """Judge *measurement* against established bounds; never invents a threshold.

        Returns a verdict dict whose ``status`` is one of

        * ``within_reference`` / ``recommend_inspection`` -- compared against the established
          bounds (explicit *bounds*, or those stored for exactly these conditions);
        * ``no_bounds`` -- the user has established none for these conditions;
        * ``unverified`` -- the power is not a verified, calibrated, isolated reading;
        * ``unverifiable`` -- metadata is missing (named in ``missing``); no spec verdict.

        ``history`` always reports how much comparable history exists (``sufficiency``:
        ``ok`` / ``insufficient`` / ``none``, with the conditions the stored records differ on)
        and its spread; ``caveat`` carries the recommendation-not-proof wording. Insufficient or
        incomparable history does not suppress a user-established bounds verdict -- it is
        reported beside it.
        """
        m = _measurement(measurement, complete=False)
        combined = _combined_conditions(m)
        key = conditions_key(combined)
        uid = measurement.get("uid") if isinstance(measurement, dict) else None
        history = self._history_block(m, combined, min_history, uid=uid)

        missing = [name for name in _VERDICT_CONDITIONS if m.get(name) is None]
        if m.get("excitation_mode") not in (None, "cw") and m.get("rep_rate_mhz") is None:
            missing.append("rep_rate_mhz")
        if missing:
            return {
                "status": "unverifiable",
                "checks": [],
                "missing": missing,
                "why": "metadata missing for a comparable, verified verdict: "
                       + ", ".join(missing)
                       + ". Conditions must state the laser wavelength, the verified calibrated "
                         "isolated power, the excitation mode and timing (rep rate when pulsed), "
                         "the optical configuration, the detector and the dye.",
                "history": history,
                "caveat": CAVEAT,
            }
        if m["power_verified"] is not True:
            return {
                "status": "unverified",
                "checks": [],
                "why": "the laser power is not a verified, calibrated, isolated reading taken "
                       "with this laser alone: a total-diode reading taken with several lasers "
                       "on cannot establish an individual laser's power, so no spec verdict is "
                       "issued",
                "history": history,
                "caveat": CAVEAT,
            }

        if bounds is not None:
            bdoc = _validated_bounds(bounds)
            provenance = {"source": "call", "kind": None}
        else:
            entry = self.get_bounds(combined)
            if entry is None:
                return {
                    "status": "no_bounds",
                    "checks": [],
                    "bounds": None,
                    "bounds_provenance": {"source": "none"},
                    "why": "no spec or reference bounds are established for these conditions; "
                           "establish them with set_bounds() or pass bounds explicitly -- this "
                           "module ships no thresholds and invents none",
                    "history": history,
                    "caveat": CAVEAT,
                }
            bdoc = entry["bounds"]
            provenance = {"source": "stored", "kind": entry["kind"], "note": entry["note"],
                          "set_at_utc": entry["set_at_utc"]}

        checks = []
        for metric in METRICS:
            rule = bdoc.get(metric)
            if not rule:
                continue
            value = float(m[metric])
            level, deviation = "within", 0.0
            if "max" in rule and value > rule["max"]:
                level, deviation = "above_max", value - rule["max"]
            elif "min" in rule and value < rule["min"]:
                level, deviation = "below_min", rule["min"] - value
            checks.append({"metric": metric, "value": value, "bounds": dict(rule),
                           "level": level, "deviation": deviation})
        outside = [c for c in checks if c["level"] != "within"]
        if outside:
            status = "recommend_inspection"
            detail = "; ".join(
                f"{c['metric']} is {c['level'].replace('_', ' ')} the established bounds "
                f"({c['value']:.6g})"
                for c in outside
            )
            recommendation = (f"Inspect or maintain the instrument: {detail}. This is a "
                              f"maintenance/inspection recommendation, not scientific proof of "
                              f"an instrument fault.")
        else:
            status = "within_reference"
            recommendation = ""
        return {
            "status": status,
            "checks": checks,
            "bounds": copy.deepcopy(bdoc),
            "bounds_provenance": provenance,
            "history": history,
            "recommendation": recommendation,
            "caveat": CAVEAT,
            "conditions": combined,
            "key": key,
        }

    # -- history reporting --
    def _history_block(self, m: dict, combined: dict, min_history: int, *,
                       uid: str | None = None) -> dict:
        doc = self._load()
        records = doc["records"]
        key = conditions_key(_combined_conditions(m))
        peers = [r for r in records if r.get("key") == key and r.get("uid") != uid]
        n = len(peers)
        if n == 0:
            sufficiency = "none"
            why = ("no records stored yet" if not records else
                   f"{len(records)} record(s) stored, none comparable to these conditions")
        elif n < min_history:
            sufficiency = "insufficient"
            why = (f"{n} comparable record(s) of the {min_history} needed for a "
                   f"history-backed context")
        else:
            sufficiency = "ok"
            why = f"{n} comparable record(s)"
        block: dict[str, Any] = {
            "n_total": len(records),
            "n_comparable": n,
            "sufficiency": sufficiency,
            "why": why,
            "incomparable_examples": self._incomparable_examples(records, combined),
        }
        if n:
            block["metrics"] = {
                metric: _spread([float(r[metric]) for r in peers]) for metric in METRICS
            }
        return block

    @staticmethod
    def _incomparable_examples(records: list[dict], mine: dict) -> list[dict]:
        """Up to three stored records that are not comparable, with the conditions they differ on.

        *mine* is the evaluated measurement's full conditions; each example names the conditions
        that differ, so an incomparable history says *why* it is incomparable instead of just
        vanishing.
        """
        my_key = conditions_key(mine)
        examples = []
        for r in records:
            if len(examples) >= 3:
                break
            try:
                theirs = _combined_conditions(_measurement(r, complete=False))
            except InvalidMeasurement:  # a damaged record is reported, not silently skipped
                examples.append({"uid": r.get("uid"), "differs_on": ["<unreadable record>"]})
                continue
            if conditions_key(theirs) == my_key:
                continue
            differs = sorted(
                {name for name in set(theirs) | set(mine) if theirs.get(name) != mine.get(name)}
            )
            examples.append({"uid": r.get("uid"), "timestamp_utc": r.get("timestamp_utc"),
                             "differs_on": differs})
        return examples


def _spread(values: list[float]) -> dict:
    """Median, MAD and range of comparable history -- context, never a verdict."""
    med = statistics.median(values)
    return {
        "n": len(values),
        "median": med,
        "mad": statistics.median([abs(v - med) for v in values]),
        "min": min(values),
        "max": max(values),
    }
