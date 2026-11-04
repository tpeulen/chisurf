"""The standalone laser power-calibration panel: measured entries only, explicit
hardware-state gates, and a conversion that refuses everything the measurements do
not back.

This panel is a thin, self-contained view over the existing backends --
:mod:`chisurf.plugins.core.acq.live.power_calibration` (the keyed per-laser
calibration, its verified configuration and emission states, the 3-calendar-month
expiry and the bounded conversion) and :mod:`chisurf.plugins.core.acq.live.calibration`
(the laser inventory and the user-owned metric limits). It adds no science of its
own and owns no thresholds: the quality table judges only by limits the user
configures.

The rules the panel enforces (none of which it bends):

* **Nothing is assumed installed.** A laser is selectable only after the user
  recorded a verification from the hardware configuration
  (:class:`~chisurf.plugins.core.acq.live.calibration.lasers.LaserInventory`).
* **The panel never energizes a laser.** It opens a backend read-only and only
  ever calls ``state()``; there is no emission, drive or program control here.
  The operator drives the laser from the Record tool; this panel only reads.
* **No simulator presented as live.** A simulator may be attached to try the
  panel, clearly labelled; every capture from it is refused -- a simulator's
  readback is not hardware evidence.
* **Every capture is an explicit, evidenced act.** The configuration and the
  all-lasers emission state are captured either from an attached Sepia II
  readback or transcribed by hand from the instrument (the pasted text is the
  evidence); each reference point re-checks the current state and stores its own.
* **The conversion is disabled wherever the backend refuses.** Unverified
  states, changed conditions or configuration, expiry and readings beyond the
  measured band all come back as explicit refusals -- the reason is shown,
  never a number.
* **Quality is a table.** Metric, measured value (raw numbers preserved,
  unavailable/unverified states explicit), the USER's limit, a status and
  actionable guidance -- shipped with no thresholds of its own.

Run standalone::

    python -m chisurf.plugins.core.acq.gui.calibration_panel

or embed the :class:`CalibrationPanel` (see the integration notes at the bottom
of :mod:`chisurf.plugins.core.acq.gui.calibration_panel` usage docs).
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections

from chisurf.plugins.core.acq.live import laser as laser_mod
from chisurf.plugins.core.acq.live.calibration.lasers import AVAILABLE_LASERS_NM, LaserInventory
from chisurf.plugins.core.acq.live.calibration.workflow import MetricLimits
from chisurf.plugins.core.acq.live.power_calibration import (
    CALIBRATION_SCHEMA,
    CalibrationSet,
    ConfigIdentity,
    Conversion,
    DarkOffset,
    EmissionState,
    HeadIdentity,
    Key,
    LaserConditions,
    PowerCalibration,
    ReferencePoint,
)

__all__ = ["CalibrationPanel", "CalibrationPanelModel", "make_app", "main"]

#: Schema of the panel's own sidecar (limits the USER configured; no thresholds ship).
PANEL_FORMAT = "chisurf.power-panel/1"

#: The quality metrics a user may bound: key -> (row label, unit, which bound applies).
#: Shipped EMPTY -- the panel has no thresholds of its own.
LIMIT_METRICS: dict[str, tuple[str, str, str]] = {
    "anchors": ("Measured anchors", "count", "minimum"),
    "residual_rms_uw": ("Residual RMS", "µW", "maximum"),
    "residual_max_uw": ("Residual max", "µW", "maximum"),
}

_ATTACH_CHOICES = [
    ["", "not attached"],
    ["sepia", "Sepia II (readback only)"],
    ["cmc_light", "CMC Light"],
    ["simulated", "Simulator (NOT live)"],
]
_DIODE_SOURCES = [["manual entry", "manual entry"],
                  ["attached device", "attached shutters device"]]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _norm(text: str) -> str:
    return str(text).strip().casefold()


def _num_or_empty(value) -> object:
    """A raw number stays raw; nothing measured renders as a fake zero."""
    return value


class CalibrationPanelModel:
    """The state and the gates behind the panel.

    Parameters
    ----------
    cal_path : str or Path, optional
        Where the calibration book is saved (``chisurf.power-calibration/1``).
        The laser inventory and the user's metric limits are saved beside it as
        ``<stem>.inventory.json`` and ``<stem>.panel.json``.
    """

    def __init__(self, cal_path: str | Path | None = None) -> None:
        from chisurf.plugins.core.acq.output_paths import default_acquisition_output_path

        self.cal_path = str(Path(cal_path) if cal_path
                            else Path(default_acquisition_output_path())
                            / "power-calibration.json")
        self.book = CalibrationSet()
        self.inventory = LaserInventory()
        #: The USER's accept/reject bounds; empty means a value is reported, not judged.
        self.limits: dict[str, MetricLimits] = {key: MetricLimits() for key in LIMIT_METRICS}
        #: The last refusal, shown on the status line. Empty when everything is well.
        self.error = ""

        # -- selection and verification
        self.verify_nm: int = AVAILABLE_LASERS_NM[0]
        self.verify_evidence = ""
        self.laser_nm: int | None = None
        self.head_name = ""

        # -- attached hardware (read-only)
        self.laser = None  # a LaserBackend; the panel only ever reads state()
        self.laser_kind = ""
        self.diode_device = None  # a phacq shutters device (its diode_raw parameter)
        self.diode_section = ""

        # -- conditions the calibration is keyed to
        self.rep_rate_mhz = 0.0
        self.mode = "pulsed"
        self.pattern = ""
        self.optical_path = ""
        self.config_json = ""
        self.emission_json = ""

        # -- captured evidence
        self.config_identity: ConfigIdentity | None = None
        self.config_evidence = ""
        self.config_route = ""
        self.slot_wavelengths: dict[int, float] = {}
        self.emission_state: EmissionState | None = None
        self.emission_evidence = ""
        self.emission_route = ""
        self.emission_captured_at = ""

        # -- the entries of a measurement session
        self.diode_source = "manual entry"
        self.diode_raw = 0.0
        self.new_uw = 0.0
        self.new_drive_pct = 0.0
        self.meter = ""
        self.meter_calibrated = ""
        self.probe_raw = 0.0

        self._draft: PowerCalibration | None = None
        self._probe: Conversion | None = None
        self._points_rev = 0

    # -- the draft ------------------------------------------------------------------------------
    @property
    def key_name(self) -> str:
        return str(self.head_name).strip() or (f"LDH-{int(self.laser_nm)}" if self.laser_nm else "")

    @property
    def draft(self) -> PowerCalibration:
        """The calibration being measured for the selected laser (a fresh one before
        anything is selected -- it validates as incomplete, never as usable)."""
        if self._draft is not None:
            return self._draft
        return PowerCalibration(self.key_name or "—",
                                float(self.laser_nm) if self.laser_nm else float("nan"),
                                conditions=self.conditions())

    def conditions(self) -> LaserConditions:
        return LaserConditions(
            laser=self.key_name or "—",
            wavelength_nm=float(self.laser_nm) if self.laser_nm else float("nan"),
            repetition_rate_hz=(self.rep_rate_mhz * 1e6) if self.rep_rate_mhz > 0 else None,
            mode=self.mode, pattern=self.pattern, optical_path=self.optical_path,
        )

    def _conditions_changed(self, _value=None) -> None:
        if self._draft is not None:
            self._draft.conditions = self.conditions()

    # -- choices --------------------------------------------------------------------------------
    def laser_options(self) -> list[list]:
        """Only heads verified installed: available does NOT mean installed."""
        return [[nm, f"{nm} nm"] for nm in self.inventory.installed()]

    def laser_selected(self, _value=None) -> None:
        self.error = ""
        if self.laser_nm is None:
            self._draft = None
            return
        try:
            self.inventory.select(self.laser_nm)
        except LookupError as exc:
            self.laser_nm = None
            self._draft = None
            self.error = str(exc)
            raise
        # a new head starts a new measurement: its points were measured on another laser
        self._draft = PowerCalibration(self.key_name, float(self.laser_nm),
                                       conditions=self.conditions(),
                                       config=self.config_identity)
        self._points_rev += 1

    def verify_installed(self) -> bool:
        """Record a head as verified installed, from the hardware-configuration readback."""
        self.error = ""
        try:
            self.inventory.verify_installed(self.verify_nm, evidence=self.verify_evidence)
        except (ValueError, LookupError) as exc:
            self.error = f"verification refused: {exc}"
            return False
        return True

    def unverify_installed(self) -> bool:
        self.error = ""
        try:
            self.inventory.unverify_installed(self.verify_nm,
                                              note="unverified from the panel")
        except LookupError as exc:
            self.error = str(exc)
            return False
        if self.laser_nm == self.verify_nm:
            self.laser_nm = None
            self._draft = None
        return True

    def verified_text(self) -> str:
        installed = self.inventory.installed()
        if not installed:
            return tr("No head verified installed yet: read the hardware configuration, "
                      "then record the verification (evidence = the readback). Available "
                      "models {nm} -- available is NOT installed.").format(
                nm=", ".join(str(n) for n in AVAILABLE_LASERS_NM))
        return tr("Verified installed: {list}").format(
            list=", ".join(f"{nm} nm ({self.inventory.record(nm).evidence})" for nm in installed))

    # -- the attached laser (read-only) ----------------------------------------------------------
    def attach_backend(self, backend) -> None:
        """Attach an already-open backend (a host's, or a test's). Read-only here."""
        self.laser = backend
        self.laser_kind = str(getattr(backend, "kind", "") or "")
        if backend is None:
            self.laser_kind = ""

    def attach_laser(self, _value=None) -> bool:
        self.error = ""
        kind = str(self.laser_kind or "")
        if kind == "":
            self.detach_laser()
            return True
        if kind == "simulated":
            # allowed, and never presented as live: every capture refuses it
            self.laser = laser_mod.SimLaser()
            self.laser.open(0)
            return True
        if kind == "sepia":
            ok, why = laser_mod.sepia_available()
            if not ok:
                self.error = why
                self.laser = None
                return False
            try:
                backend = laser_mod.SepiaBackend()
                backend.open(0)
            except Exception as exc:  # noqa: BLE001 - shown; nothing captured
                self.laser = None
                self.error = f"the Sepia II did not open: {exc}"
                return False
            self.laser = backend
            return True
        if kind in ("cmc", "cmc_light"):
            try:
                backend = laser_mod.open_laser("cmc_light", allow_simulated=True)
                backend.open(0)
            except Exception as exc:  # noqa: BLE001
                self.laser = None
                self.error = f"the CMC Light did not open: {exc}"
                return False
            self.laser = backend
            return True
        self.error = f"unknown laser kind {kind!r}"
        return False

    def detach_laser(self) -> None:
        backend, self.laser = self.laser, None
        if backend is not None:
            try:
                backend.close()
            except Exception:  # noqa: BLE001 - a close never blocks the panel
                pass

    def laser_status_text(self) -> str:
        if self.laser is None:
            return tr("No laser attached. Capturing from the hardware needs a connected "
                      "Sepia II -- readback only; this panel never switches anything.")
        kind = str(getattr(self.laser, "kind", ""))
        if kind == "simulated":
            return tr("SIMULATED laser attached -- not live hardware. Every capture is "
                      "refused: the simulator's readback is not evidence.")
        try:
            st = self.laser.state()
        except Exception as exc:  # noqa: BLE001
            return tr("Attached laser does not answer: {e}").format(e=exc)
        return tr("Attached: {model} serial {serial} (readback only).").format(
            model=st.model or "?", serial=st.serial or "?")

    def _readback(self):
        """The attached hardware's state, or why there is none to trust."""
        if self.laser is None:
            return None, "no laser attached: capture from the attached Sepia II, or " \
                         "transcribe the instrument's own readback by hand"
        kind = str(getattr(self.laser, "kind", ""))
        if kind == "simulated":
            return None, "the attached laser is the simulator: its readback is not " \
                         "hardware evidence and is never captured"
        if kind not in ("sepia", "cmc_light"):
            return None, f"the attached backend {kind!r} is not a supported laser driver"
        if not self.laser.is_open:
            return None, "the attached laser is not open"
        try:
            return self.laser.state(), ""
        except Exception as exc:  # noqa: BLE001
            return None, f"the readback failed: {exc}"

    # -- captures ---------------------------------------------------------------------------------
    def capture_configuration(self) -> bool:
        """Which heads are connected, from the hardware readback (or transcribed)."""
        self.error = ""
        state, why = self._readback()
        if state is not None:
            heads = []
            for h in state.heads:
                wl = h.wavelength_nm if h.wavelength_nm is not None \
                    else self.slot_wavelengths.get(h.slot)
                if wl is None:
                    self.error = (f"slot {h.slot}: the readback does not say the head's "
                                  f"wavelength -- assign it above before capturing")
                    return False
                heads.append(HeadIdentity(h.name or f"SLM {h.slot}", float(wl),
                                          str(h.serial or "")))
            identity = ConfigIdentity(tuple(heads))
            evidence = (f"readback of {state.model} serial {state.serial} at {_now_iso()}: "
                        + "; ".join(f"{h.name} {h.wavelength_nm:g} nm S/N {h.serial or '?'}"
                                    for h in identity.heads))
            route = "readback"
        else:
            if self.laser_kind == "simulated":
                self.error = why
                return False
            identity = self._parse(ConfigIdentity.from_dict, self.config_json,
                                   "the configuration readback does not parse: expected "
                                   '{"heads": [{"name", "wavelength_nm", "serial"}]}')
            if identity is None:
                return False
            evidence = "transcribed by hand from the hardware configuration: " \
                       + str(self.config_json or "").strip()
            route = "transcribed"
        # no head name given: adopt the matching head's name from the verified
        # configuration (the readback's name is the head's actual name)
        if not str(self.head_name).strip() and self.laser_nm is not None:
            match = next((h for h in identity.heads
                          if abs(h.wavelength_nm - float(self.laser_nm)) <= 0.5), None)
            if match is not None:
                self.head_name = match.name
        if self.laser_nm is not None and not identity.includes(self.key_name, float(self.laser_nm)):
            self.error = (f"the verified configuration does not include "
                          f"{self.key_name} at {self.laser_nm:g} nm -- the head to "
                          f"calibrate must be among the connected, read-back heads")
            return False
        self.config_identity = identity
        self.config_evidence = evidence
        self.config_route = route
        if self._draft is not None:
            if _norm(self._draft.key.laser) != _norm(self.key_name):
                if self._draft.points or self._draft.dark is not None:
                    self.error = (f"the head's name changed to {self.key_name!r} while "
                                  f"measurements exist for {self._draft.key.laser!r} -- "
                                  f"start the measurement for this head again")
                    return False
                self._draft = PowerCalibration(self.key_name, float(self.laser_nm),
                                               conditions=self.conditions(), config=identity)
            else:
                self._draft.config = identity
        return True

    def capture_emission(self) -> bool:
        """Every connected laser's on/off state, as verified readback reported it."""
        self.error = ""
        if self.laser_kind == "simulated":
            self.error = ("the attached laser is the simulator: its readback is not "
                          "hardware evidence and is never captured")
            return False
        if self.config_identity is None:
            self.error = ("capture the verified configuration first: the emission states "
                          "are checked against the connected heads")
            return False
        state, why = self._readback()
        if state is not None:
            from chisurf.plugins.core.acq.live.power_calibration import LaserEmission

            entries = []
            for h in state.heads:
                name = h.name or f"SLM {h.slot}"
                on = (not state.emission_blocked) and float(h.intensity_pct or 0.0) > 0.0
                entries.append(LaserEmission(name, on, True))
            emission = EmissionState(tuple(entries))
            evidence = (f"readback of {state.model} serial {state.serial} at {_now_iso()}: "
                        f"soft lock {'OPEN' if not state.emission_blocked else 'BLOCKED (all outputs off)'}; "
                        + "; ".join(f"{h.name or f'SLM {h.slot}'} intensity "
                                    f"{float(h.intensity_pct or 0.0):g} %" for h in state.heads))
            route = "readback"
        else:
            if self.laser_kind == "simulated":
                self.error = why
                return False
            emission = self._parse(EmissionState.from_dict, self.emission_json,
                                   "the emission states do not parse: expected a JSON list "
                                   'of {"laser", "on", "verified"} for every connected laser')
            if emission is None:
                return False
            evidence = "transcribed by hand from the instrument's emission readback: " \
                       + str(self.emission_json or "").strip()
            route = "transcribed"
        # keep reported evidence, including unverified states; use remains gated
        reported = {_norm(entry.laser) for entry in emission.lasers}
        missing = [head.name for head in self.config_identity.heads
                   if _norm(head.name) not in reported]
        if missing:
            self.error = (f"no verified readback for {', '.join(missing)}: every "
                          f"connected head's state must be captured")
            return False
        self.emission_state = emission
        self.emission_evidence = evidence
        self.emission_route = route
        self.emission_captured_at = _now_iso()
        return True

    def _parse(self, fn, text, message):
        raw = str(text or "").strip()
        if not raw:
            self.error = message
            return None
        try:
            return fn(json.loads(raw))
        except Exception as exc:  # noqa: BLE001 - shown, never defaulted
            self.error = f"{message} ({exc})"
            return None

    def _emission_gate(self, mode: str) -> EmissionState | None:
        """The captured state, checked for the capture at hand; the refusal says why."""
        emission = self.emission_state
        if emission is None:
            self.error = ("capture the emission readback first: isolation is never "
                          "inferred from the intended state")
            return None
        if self.config_identity is not None:
            missing = self.config_identity.missing_from(emission)
            if missing:
                self.error = (f"unverified emission state for {', '.join(missing)} "
                              f"(the configuration changed? re-capture)")
                return None
        if mode == "dark":
            ok, why = emission.all_off_confirmed()
        else:
            ok, why = emission.confirmed_single(self.key_name)
        if not ok:
            self.error = why
            return None
        return emission

    # -- the diode ------------------------------------------------------------------------------
    def connect_shutters(self, section_json: str) -> bool:
        """Open the shutters/diode device from a settings file's ``shutters`` section."""
        import phacq

        self.error = ""
        try:
            self.diode_device = phacq.DriverRegistry.instance().driver("shutters").open(
                str(section_json))
        except Exception as exc:  # noqa: BLE001 - shown
            self.diode_device = None
            self.error = f"the shutters device did not open: {exc}"
            return False
        self.diode_section = str(section_json)
        return True

    def detach_shutters(self) -> None:
        device, self.diode_device = self.diode_device, None
        self.diode_section = ""
        if device is not None:
            try:
                device.close()
            except Exception:  # noqa: BLE001
                pass

    def read_diode(self) -> float | None:
        """The diode's raw reading from the attached device (read-only)."""
        self.error = ""
        if self.diode_device is None:
            self.error = "no shutters/diode device attached"
            return None
        try:
            value = float(self.diode_device.get_parameter("diode_raw", -1.0))
        except Exception as exc:  # noqa: BLE001
            self.error = f"the diode did not answer: {exc}"
            return None
        if not math.isfinite(value) or value < 0:
            self.error = "the diode reports no reading (yet)"
            return None
        self.diode_raw = value
        return value

    def _staged_diode_raw(self) -> float | None:
        if str(self.diode_source) == "attached device":
            if self.read_diode() is None:
                return None
        raw = float(self.diode_raw)
        if not math.isfinite(raw):
            self.error = "the diode reading is not a number"
            return None
        return raw

    # -- the measurements -------------------------------------------------------------------------
    def capture_dark(self) -> bool:
        """The diode's raw reading with the emission blocked -- the µW zero."""
        self.error = ""
        if self._draft is None:
            self.error = "select a verified laser first"
            return False
        emission = self._emission_gate("dark")
        if emission is None:
            return False
        raw = self._staged_diode_raw()
        if raw is None:
            return False
        self.draft.conditions = self.conditions()
        route = str(self.diode_source)
        self.draft.set_dark(DarkOffset(
            raw=raw, emission=emission, measured=date.today().isoformat(),
            note=f"diode: {route}; emission {self.emission_route}"))
        self._points_rev += 1
        return True

    def capture_point(self) -> bool:
        """One simultaneous capture: the meter's µW at the objective, the diode's raw,
        under the verified single-laser state -- re-checked now."""
        self.error = ""
        if self._draft is None or self.laser_nm is None:
            self.error = "select a verified laser first"
            return False
        emission = self._emission_gate("single")  # the operating state gates everything
        if emission is None:
            return False
        uw = float(self.new_uw)
        if not math.isfinite(uw) or uw <= 0:
            self.error = f"the meter reading must be a positive number of µW, got {self.new_uw}"
            return False
        if not str(self.meter).strip():
            self.error = "record the calibrated external meter first (who read what where)"
            return False
        raw = self._staged_diode_raw()
        if raw is None:
            return False
        dark = self.draft.dark
        if dark is not None and math.isfinite(dark.raw) and raw <= dark.raw:
            self.error = (f"raw {raw:g} is not above the dark offset ({dark.raw:g}); "
                          f"there is no light above dark to attribute")
            return False
        self.draft.conditions = self.conditions()
        self.draft.add_point(ReferencePoint(
            raw=raw, uw=uw, emission=emission,
            meter=str(self.meter), meter_calibrated=str(self.meter_calibrated),
            measured=date.today().isoformat(), intensity_pct=float(self.new_drive_pct),
            note=f"diode: {self.diode_source}; emission {self.emission_route}"))
        self._points_rev += 1
        return True

    def remove_point(self, index_or_record) -> None:
        index = index_or_record.get("_i") if isinstance(index_or_record, dict) \
            else index_or_record
        points = self.draft.points
        if isinstance(index, int) and 0 <= index < len(points):
            points.pop(index)
            self._points_rev += 1

    # -- adopt and save -----------------------------------------------------------------------------
    def adopt_and_save(self) -> list[str]:
        """Adopt the draft as today's calibration and save it; the blockers come back
        (and nothing is written) while it is incomplete."""
        self.error = ""
        if self.laser_nm is None:
            self.error = "select a verified laser first"
            return ["no laser selected"]
        self._draft.conditions = self.conditions()
        self._draft.calibrated = date.today().isoformat()
        problems = self._draft.validate()
        if problems:
            self.error = "the calibration is not complete: " + "; ".join(problems)
            return problems
        # supersede this laser's calibration for the same condition set (a re-measurement
        # replaces it; a different condition set is a different calibration, kept)
        same = [c for c in self.book.calibrations
                if c.key.matches(self._draft.key) and not c.conditions.differences(self._draft.conditions)]
        for c in same:
            self.book._calibrations.remove(c)
        self.book.add(self._draft)
        try:
            self.save_all()
        except Exception as exc:  # noqa: BLE001 - shown; the draft is kept
            self.error = f"the calibration was not saved: {exc}"
            return [str(exc)]
        self._draft = PowerCalibration(self.key_name, float(self.laser_nm),
                                       conditions=self.conditions(),
                                       config=self.config_identity)
        self._points_rev += 1
        return []

    # -- persistence ---------------------------------------------------------------------------------
    @property
    def _inventory_path(self) -> Path:
        return Path(self.cal_path).with_suffix(".inventory.json")

    @property
    def _panel_path(self) -> Path:
        return Path(str(self.cal_path) + ".panel.json")

    def save_all(self) -> None:
        self.book.save(self.cal_path)
        self.inventory.save(self._inventory_path)
        doc = {"format": PANEL_FORMAT,
               "limits": {key: lim.to_dict() for key, lim in self.limits.items()}}
        self._panel_path.write_text(json.dumps(doc, indent=2) + "\n")

    def load_all(self) -> bool:
        """Read the book, the inventory and the panel state; a file that does not parse
        is an error, never a silent default."""
        self.error = ""
        ok = True
        if Path(self.cal_path).exists():
            try:
                self.book = CalibrationSet.load(self.cal_path)
            except Exception as exc:  # noqa: BLE001
                self.error = f"{self.cal_path} does not read as a calibration book: {exc}"
                ok = False
        if self._inventory_path.exists():
            try:
                self.inventory = LaserInventory.load(self._inventory_path)
            except Exception as exc:  # noqa: BLE001
                self.error = f"{self._inventory_path} does not read as an inventory: {exc}"
                ok = False
        if self._panel_path.exists():
            try:
                doc = json.loads(self._panel_path.read_text())
                if doc.get("format") != PANEL_FORMAT:
                    raise ValueError(f"schema {doc.get('format')!r} is not {PANEL_FORMAT}")
                for key, bounds in (doc.get("limits") or {}).items():
                    if key in self.limits:
                        self.limits[key] = MetricLimits(
                            minimum=bounds.get("minimum"), maximum=bounds.get("maximum"))
            except Exception as exc:  # noqa: BLE001
                self.error = f"{self._panel_path} does not read as panel state: {exc}"
                ok = False
        return ok

    # -- limits (the USER's thresholds; shipped empty) ---------------------------------------------
    def set_limit(self, key: str, *, minimum: float | None = None,
                  maximum: float | None = None) -> None:
        if key not in self.limits:
            raise KeyError(f"no user-settable metric {key!r}")
        self.limits[key] = MetricLimits(
            minimum=minimum if minimum is not None else self.limits[key].minimum,
            maximum=maximum if maximum is not None else self.limits[key].maximum,
        )

    def clear_limits(self) -> None:
        self.limits = {key: MetricLimits() for key in LIMIT_METRICS}

    def limits_edited(self, record: dict, key: str, value) -> None:
        metric = str(record.get("key", ""))
        if metric not in self.limits or key not in ("minimum", "maximum"):
            return
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        limits = self.limits[metric]
        self.limits[metric] = MetricLimits(
            minimum=number if key == "minimum" else limits.minimum,
            maximum=number if key == "maximum" else limits.maximum,
        )

    def limits_rows(self) -> list[dict]:
        return [{"metric": LIMIT_METRICS[key][0], "key": key,
                 "minimum": self.limits[key].minimum, "maximum": self.limits[key].maximum}
                for key in LIMIT_METRICS]

    # -- the conversion probe -------------------------------------------------------------------
    def _target(self) -> PowerCalibration | None:
        if self.laser_nm is None:
            return None
        conditions = self.conditions()
        target = self.book.calibration_for(self.key_name, float(self.laser_nm), conditions)
        if target is None and self._draft is not None \
                and self._draft.key.matches(Key.of(self.key_name, float(self.laser_nm))) \
                and not self._draft.conditions.differences(conditions):
            target = self._draft
        return target

    def probe(self, _value=None) -> Conversion:
        """The raw reading converted under the captured evidence -- or the refusal."""
        self._probe = None
        if self.laser_nm is None:
            return Conversion(float(self.probe_raw), None, False, "uncalibrated",
                              "select a verified laser first")
        target = self._target()
        if target is None:
            return Conversion(float(self.probe_raw), None, False, "uncalibrated",
                              f"no calibration for {self.key_name} at {self.laser_nm:g} nm "
                              f"under these conditions")
        self._probe = target.convert(float(self.probe_raw), conditions=self.conditions(),
                                     emission=self.emission_state,
                                     config=self.config_identity)
        return self._probe

    def probe_text(self) -> str:
        result = self._probe
        lines = []
        if result is None:
            lines.append(tr("Enter a raw diode reading and convert."))
        elif result.valid and result.uw is not None:
            line = tr("{raw:g} raw = {uw:.6g} µW ({kind})").format(
                raw=result.raw, uw=result.uw, kind=result.status)
            if result.uncertainty_uw is not None:
                line += tr(", measured non-linearity ±{u:.4g} µW").format(
                    u=result.uncertainty_uw)
            lines.append(line)
        else:
            # the refusal IS the answer: the reason is shown, never a number
            lines.append(tr("No power: {status}").format(status=result.status))
            if result.reason:
                lines.append(str(result.reason))
        if self.emission_state is None:
            lines.append(tr("Operating state: not verified -- capture the emission "
                            "readback (every other laser confirmed off)."))
        else:
            ok, why = self.emission_state.confirmed_single(self.key_name)
            lines.append(tr("Operating state: {state}, captured {at} ({route}).").format(
                state="single-laser verified" if ok else f"unverified ({why})",
                at=self.emission_captured_at or "?", route=self.emission_route))
        return "\n".join(lines)

    # -- the quality table ------------------------------------------------------------------------
    def quality_rows(self) -> list[dict]:
        """One row per quality metric: the raw measured value (never a verdict
        standing in for it), the user's limit, a status and what to do next."""
        # the calibration in point is the adopted one for the selected conditions,
        # the single adopted calibration when one was loaded, or the draft being
        # measured
        if self.laser_nm is not None:
            cal = self._target() or self.draft
        elif len(self.book.calibrations) == 1:
            cal = self.book.calibrations[0]
        else:
            cal = self.draft
        problems = cal.validate() if self.laser_nm is not None else []
        joined = "; ".join(problems).lower()
        fit = cal.linear_fit() if self.laser_nm is not None else None
        today = date.today()
        rows = []

        def limits_text(key: str) -> str:
            lim = self.limits.get(key)
            return "" if lim is None or lim.is_empty() else lim.describe().removeprefix("limits: ")

        def verdict(key: str, value) -> str:
            if value is None:
                return "unavailable"  # an unmeasured value is never 0, never invented
            lim = self.limits.get(key)
            if lim is None or lim.is_empty():
                return "not configured"  # no user limit: the value is reported, not judged
            if (lim.minimum is not None and value < lim.minimum) \
                    or (lim.maximum is not None and value > lim.maximum):
                return "outside bounds"
            return "within bounds"

        n_dark = cal.dark is not None
        n_points = len(cal.points)
        anchors = (1 + n_points) if (n_dark and n_points) else None
        rows.append({
            "metric": "Measured anchors",
            "measured": anchors if anchors is not None else "",
            "unit": "count",
            "limit": limits_text("anchors"),
            "status": verdict("anchors", anchors),
            "guidance": ("" if n_dark else
                         "Block the emission (every laser verified off) and capture the "
                         "dark reading -- the µW zero.")
            if n_dark else
            ("Read the external meter and the diode together at two or more drive "
             "settings, low to high." if n_points < 2 else
             "Capture more points across the working range to strengthen the curve."),
        })
        rows.append({
            "metric": "Linearity slope",
            "measured": float(fit.slope) if fit else "",
            "unit": "µW/count",
            "limit": "",
            "status": "not configured" if fit else "unavailable",
            "guidance": "µW per raw count above dark -- a linearity report only; the "
                        "conversion interpolates between measured points and never uses "
                        "this line.",
        })
        rows.append({
            "metric": "Residual RMS",
            "measured": float(fit.rms_residual_uw) if fit else "",
            "unit": "µW",
            "limit": limits_text("residual_rms_uw"),
            "status": verdict("residual_rms_uw", float(fit.rms_residual_uw) if fit else None),
            "guidance": "How straight the measured response was (needs the dark reading "
                        "and three or more references). Set YOUR limit in the limits "
                        "table; until then the value is reported, not judged.",
        })
        rows.append({
            "metric": "Residual max",
            "measured": float(fit.max_residual_uw) if fit else "",
            "unit": "µW",
            "limit": limits_text("residual_max_uw"),
            "status": verdict("residual_max_uw", float(fit.max_residual_uw) if fit else None),
            "guidance": "The worst deviation of a measured reference from the "
                        "through-origin line. A large residual usually means one "
                        "mis-read meter entry -- re-measure that point.",
        })
        if cal.dark is not None:
            dark_ok, dark_why = cal.dark.emission.all_off_confirmed()
            rows.append({
                "metric": "Dark offset",
                "measured": float(cal.dark.raw),
                "unit": "counts",
                "limit": "",
                "status": "ok" if dark_ok else "unverified",
                "guidance": "The µW zero (emission blocked, every laser verified off)."
                            if dark_ok else f"Not a zero yet: {dark_why}",
            })
        else:
            rows.append({
                "metric": "Dark offset", "measured": "", "unit": "counts", "limit": "",
                "status": "missing",
                "guidance": "Block the emission and capture the diode's dark reading; "
                            "every reference is measured against it.",
            })
        if self.emission_state is None:
            rows.append({
                "metric": "Operating state", "measured": "", "unit": "", "limit": "",
                "status": "unverified",
                "guidance": "Capture the emission readback with ONLY the selected laser "
                            "on -- isolation is never inferred from the intended state.",
            })
        else:
            ok, why = (self.emission_state.confirmed_single(self.key_name)
                       if self.laser_nm is not None else (False, "no laser selected"))
            rows.append({
                "metric": "Operating state",
                "measured": self.emission_captured_at,
                "unit": "",
                "limit": "",
                "status": "verified" if ok else "unverified",
                "guidance": f"Single-laser isolation verified by {self.emission_route} "
                            "readback." if ok else f"Not usable as evidence: {why}",
            })
        if self.config_identity is not None:
            rows.append({
                "metric": "Configuration",
                "measured": len(self.config_identity.heads),
                "unit": "heads",
                "limit": "",
                "status": "verified",
                "guidance": f"Verified configuration {self.config_identity.identity()} "
                            f"({self.config_route}); a head change invalidates every "
                            "calibration measured in it.",
            })
        else:
            rows.append({
                "metric": "Configuration", "measured": "", "unit": "heads", "limit": "",
                "status": "missing",
                "guidance": "Capture which heads are connected from the hardware "
                            "readback; the calibration is bound to that configuration.",
            })
        monotonic = "blocked" if "not monotonic" in joined or "reference conflict" in joined \
            else ("ok" if n_points >= 2 else ("unavailable" if n_points else "missing"))
        rows.append({
            "metric": "References monotonic",
            "measured": ("yes" if monotonic == "ok" else "no") if n_points >= 2 else "",
            "unit": "",
            "limit": "",
            "status": monotonic,
            "guidance": "More drive must read more power. A reversal is usually a "
                        "mis-read entry -- re-measure the offending point."
            if monotonic == "blocked" else
            "The references must rise with the drive for the interpolation to exist.",
        })
        n_above = sum(1 for p in cal.points
                      if cal.dark is None or p.raw > cal.dark.raw)
        rows.append({
            "metric": "Points above dark",
            "measured": n_above if cal.points else "",
            "unit": "count",
            "limit": "",
            "status": ("ok" if n_above == len(cal.points) else "blocked")
                      if cal.points else "missing",
            "guidance": "Every reference needs light above the dark zero; a reading at "
                        "or below it has nothing to attribute."
            if cal.points and n_above != len(cal.points) else
            "Each reference's raw reading must sit above the dark offset.",
        })
        expires = cal.expires_on() if self.laser_nm is not None else None
        if expires is None:
            rows.append({
                "metric": "Calibration expiry", "measured": "undated", "unit": "",
                "limit": "", "status": "undated",
                "guidance": "Adopting records today as the calibration date; the expiry "
                            "needs it (policy: 3 calendar months).",
            })
        else:
            days = (expires - today).days
            if days <= 0:
                status, guidance = "expired", ("Measure a fresh reference for this laser; "
                                               "an expired calibration hands out no µW.")
            elif days <= 14:
                status, guidance = "expiring", (f"Expires in {days} days (policy: 3 "
                                                "calendar months); plan a fresh measurement.")
            else:
                status, guidance = "valid", (f"Valid until {expires.isoformat()} "
                             f"(policy: 3 calendar months).")
            rows.append({"metric": "Calibration expiry",
                         "measured": expires.isoformat(), "unit": "", "limit": "",
                         "status": status, "guidance": guidance})
        return rows

    # -- the tables and the readouts the panel draws ----------------------------------------------
    def points_table(self):
        """The captured points as a table source (``revision`` bumps on every change)."""
        return _PointsTable(self)

    def expiry_text(self) -> str:
        if self.laser_nm is None:
            return ""
        expires = self.draft.expires_on()
        problems = self.draft.validate()
        if problems:
            return tr("Not adoptable yet: {problems}").format(problems="; ".join(problems))
        return tr("Adopting records {today} as the calibration date; it expires "
                  "{expires} (3 calendar months).").format(
            today=date.today().isoformat(),
            expires=expires.isoformat() if expires else "?")

    # -- enablement: a gate is off until its evidence exists --------------------------------------
    def enabled(self, action: str) -> bool:
        checked = {
            "capture_emission": self.config_identity is not None,
            "capture_dark": self.emission_state is not None and self.config_identity is not None,
            "capture_point": (self.emission_state is not None
                              and bool(str(self.meter).strip())
                              and self.laser_nm is not None),
            "adopt_save": (self.laser_nm is not None
                           and self.config_identity is not None
                           and self.emission_state is not None
                           and self.draft.dark is not None
                           and len(self.draft.points) >= 2
                           and bool(str(self.meter).strip())
                           and self.rep_rate_mhz > 0),
            "capture_configuration": self.laser_nm is not None,
        }
        return checked.get(action, True)

    def close(self) -> None:
        self.detach_laser()
        self.detach_shutters()

    def points_table_rows(self) -> list[dict]:
        """The points table's rows (bound by name in the view spec)."""
        return self.points_table().rows()

    def points_table_columns(self) -> list[dict]:
        return self.points_table().columns()


class _PointsTable:
    """The captured reference points, as the panel's table source."""

    def __init__(self, model: CalibrationPanelModel) -> None:
        self._model = model
        self.revision = model._points_rev

    def __len__(self) -> int:
        return len(self._model.draft.points)

    def rows(self) -> list[dict]:
        self.revision = self._model._points_rev
        return [{"_i": i, "n": i + 1,
                 "drive_pct": float(p.intensity_pct) if p.intensity_pct is not None else None,
                 "raw": float(p.raw), "uw": float(p.uw),
                 "meter": p.meter, "when": p.measured}
                for i, p in enumerate(self._model.draft.points)]

    def columns(self) -> list[dict]:
        return [
            {"key": "n", "title": "#", "format": "%d", "width": 26},
            {"key": "drive_pct", "title": "Drive %", "format": "%.1f", "width": 58,
             "description": "The drive setting the point was taken at (provenance only)."},
            {"key": "raw", "title": "Diode raw", "format": "%.1f", "width": 70,
             "description": "The diode's raw reading at the moment of the capture."},
            {"key": "uw", "title": "Meter µW", "format": "%.4g", "width": 66,
             "description": "What the calibrated external meter read at the objective."},
            {"key": "meter", "title": "Meter", "width": 90, "collapse_order": 2},
            {"key": "when", "title": "Measured", "width": 80, "collapse_order": 1},
        ]


# -------------------------------------------------------------------------------------------
# The view
# -------------------------------------------------------------------------------------------
def _quality_columns() -> list[dict]:
    return [
        {"key": "metric", "title": "Metric", "width": 132,
         "description": "The quality metric, computed from what was measured."},
        {"key": "measured", "title": "Measured", "format": "%.6g", "width": 108,
         "description": "The raw measured value (a date, a count, a reading); empty "
                        "means not measured -- never a stand-in zero."},
        {"key": "unit", "title": "Unit", "width": 62},
        {"key": "limit", "title": "User limit", "width": 150,
         "description": "The accept/reject bounds YOU set in the limits table; empty "
                        "means the value is reported, not judged."},
        {"key": "status", "title": "Status", "width": 104,
         "description": "Within/outside YOUR bounds, not configured, unavailable, or "
                        "the gate's own verdict."},
        {"key": "guidance", "title": "Guidance",
         "description": "What to do next."},
    ]


SECTIONS = [
    {"type": "custom", "key": "status",
     "description": "What the panel holds and what blocks a calibration right now."},
    {
        "type": "panel", "title": tr("Calibration file"), "n_col": 1,
        "description": "Where the calibration book is saved, with the laser inventory "
                       "and the panel's user limits beside it.",
        "sections": [
            {"type": "value", "label": tr("File"), "kind": "str", "attr": "cal_path",
             "description": "The calibration JSON (schema " + CALIBRATION_SCHEMA + "). "
                            "Saved beside it: <name>.inventory.json (verified heads) and "
                            "<name>.panel.json (your limits)."},
            {"type": "button_row", "buttons": [
                {"action": "load_all", "label": tr("Load"), "icon": "📂",
                 "description": "Read the book, the inventory and the limits; a file "
                                "that does not parse is an error, never a default."},
                {"action": "save_all", "label": tr("Save"), "icon": "💾", "role": "primary",
                 "description": "Write the adopted calibrations, the inventory and "
                                "the limits."},
            ]},
        ],
    },
    {
        "type": "panel", "title": tr("Laser head"), "n_col": 1,
        "description": "Which head is being calibrated. Available is NOT installed: "
                       "only heads verified from the hardware configuration are offered.",
        "sections": [
            {"type": "choice", "label": tr("Laser (nm)"), "attr": "laser_nm",
             "options_source": "laser_options", "call": "laser_selected",
             "description": "Only heads verified installed are listed and selectable; "
                            "a choice here starts a fresh measurement for that head."},
            {"type": "value", "label": tr("Head name"), "kind": "str", "attr": "head_name",
             "description": "The head's name in the verified configuration "
                            "(empty: LDH-<nm>)."},
            {"type": "value", "label": tr("Verify wavelength (nm)"), "kind": "int",
             "attr": "verify_nm", "minimum": 0,
             "description": "One of 488, 530, 640, 730 -- the models this system can "
                            "have; available does NOT mean installed."},
            {"type": "value", "label": tr("Verification evidence"), "kind": "str",
             "attr": "verify_evidence",
             "description": "The hardware-configuration readback that showed this head "
                            "connected. Recorded with the verification."},
            {"type": "button_row", "buttons": [
                {"action": "verify_installed", "label": tr("Verify installed"), "icon": "✔",
                 "description": "Record the head as verified installed (needs evidence)."},
                {"action": "unverify_installed", "label": tr("Unverify"), "role": "danger",
                 "description": "Remove the verification (after a head exchange)."},
            ]},
            {"type": "info", "source": "verified_text"},
        ],
    },
    {
        "type": "panel", "title": tr("Hardware readback"), "n_col": 1,
        "description": "The verified configuration and emission states the calibration "
                       "is bound to. The panel opens the laser read-only and never "
                       "switches anything; the simulator is never evidence.",
        "sections": [
            {"type": "custom", "key": "laser_status"},
            {"type": "choice", "label": tr("Attach laser"), "attr": "laser_kind",
             "options": _ATTACH_CHOICES, "call": "attach_laser",
             "description": "Attach the Sepia II for readback only, or the simulator "
                            "(labelled, captures refused). Choosing 'not attached' "
                            "detaches."},
            {"type": "custom", "key": "config_slots"},
            {"type": "value", "label": tr("Configuration (transcribed readback)"),
             "kind": "str", "attr": "config_json",
             "description": "Without an attached Sepia II: paste the hardware "
                            "configuration's readback as JSON, e.g. "
                            '{"heads": [{"name": "LDH-640", "wavelength_nm": 640.0, '
                            '"serial": "1234"}]} -- the pasted text is the evidence.'},
            {"type": "button_row", "buttons": [
                {"action": "capture_configuration", "label": tr("Capture configuration"),
                 "icon": "📷",
                 "description": "Which heads are connected, from the readback (or the "
                                "transcribed text when nothing is attached)."},
            ]},
            {"type": "custom", "key": "emission_status"},
            {"type": "value", "label": tr("Emission states (transcribed readback)"),
             "kind": "str", "attr": "emission_json",
             "description": "Without an attached Sepia II: paste every laser's verified "
                            'on/off state as JSON, e.g. [{"laser": "LDH-640", "on": true, '
                            '"verified": true}]. An unverified or unknown state blocks '
                            "the claim."},
            {"type": "button_row", "buttons": [
                {"action": "capture_emission", "label": tr("Capture emission state"),
                 "icon": "📷",
                 "description": "Every connected laser's on/off state, verified; the "
                                "photodiode sums all lasers, so every other head must "
                                "read off."},
            ]},
        ],
    },
    {
        "type": "panel", "title": tr("Conditions"), "n_col": 2,
        "description": "The operating conditions the calibration holds for; a change in "
                       "any of them needs its own calibration.",
        "sections": [
            {"type": "value", "label": tr("Repetition rate (MHz)"), "kind": "float",
             "attr": "rep_rate_mhz", "minimum": 0.0, "call": "_conditions_changed",
             "description": "The laser's repetition rate; the calibration is keyed to "
                            "it (blank/0 = not recorded, which blocks a µW claim)."},
            {"type": "choice", "label": tr("Mode"), "attr": "mode",
             "options": ["pulsed", "cw"], "call": "_conditions_changed",
             "description": "Pulsed or continuous operation."},
            {"type": "value", "label": tr("Pulse pattern"), "kind": "str",
             "attr": "pattern", "call": "_conditions_changed", "n_col": 1,
             "description": "e.g. the PIE pattern or pulse-picker ratio."},
            {"type": "value", "label": tr("Optical path"), "kind": "str",
             "attr": "optical_path", "call": "_conditions_changed", "n_col": 1,
             "description": "Beam splitters and filters in the beam -- the optical "
                            "configuration the calibration holds for."},
        ],
    },
    {
        "type": "panel", "title": tr("Dark offset"), "n_col": 1,
        "description": "The diode's raw reading with the emission blocked -- the µW "
                       "zero every reference is measured against.",
        "sections": [
            {"type": "choice", "label": tr("Diode reading"), "attr": "diode_source",
             "options": _DIODE_SOURCES,
             "description": "Read it from the attached shutters device, or type what "
                            "the instrument shows."},
            {"type": "value", "label": tr("Diode raw"), "kind": "float",
             "attr": "diode_raw",
             "description": "The raw reading staged for the next capture (typed, or "
                            "read by 'Read diode')."},
            {"type": "button_row", "buttons": [
                {"action": "read_diode", "label": tr("Read diode"), "icon": "🔦",
                 "description": "Read diode_raw from the attached device (read-only)."},
                {"action": "capture_dark", "label": tr("Capture dark"), "icon": "⬛",
                 "role": "primary",
                 "description": "Record the zero; needs every laser verified OFF by "
                                "readback at this moment."},
            ]},
            {"type": "custom", "key": "dark_status"},
        ],
    },
    {
        "type": "panel", "title": tr("Objective power meter"), "n_col": 1,
        "description": "The external calibrated meter reading at the objective -- the "
                       "only source of µW this panel accepts.",
        "sections": [
            {"type": "value", "label": tr("Meter"), "kind": "str", "attr": "meter",
             "description": "Model and where it reads (e.g. 'Thorlabs PM100D S121C at "
                            "the objective')."},
            {"type": "value", "label": tr("Meter calibrated"), "kind": "str",
             "attr": "meter_calibrated",
             "description": "The meter's own calibration date (YYYY-MM-DD), recorded "
                            "with every point."},
        ],
    },
    {
        "type": "panel", "title": tr("Reference points"), "n_col": 1,
        "description": "Vary the drive YOURSELF (from the Record tool's Laser panel; "
                       "this panel never touches it) and capture the simultaneous pair "
                       "at each setting, low to high.",
        "sections": [
            {"type": "value", "label": tr("Drive (%)"), "kind": "float",
             "attr": "new_drive_pct", "minimum": 0.0, "maximum": 100.0,
             "description": "The drive setting this point was taken at (provenance "
                            "only, never a factor)."},
            {"type": "value", "label": tr("Meter µW"), "kind": "float", "attr": "new_uw",
             "description": "What the calibrated meter reads at the objective, at this "
                            "drive setting."},
            {"type": "button_row", "buttons": [
                {"action": "capture_point", "label": tr("Capture point"), "icon": "📍",
                 "role": "primary",
                 "description": "Record the (diode raw, meter µW) pair under the "
                                "verified single-laser state -- re-checked now."},
            ]},
            {"type": "custom", "key": "data_table", "options": {
                "source": "points_table_rows",
                "columns_source": "points_table_columns",
                "row_key": "_i",
                "delete_call": "remove_point",
                "editable": False,
                "selection_note": False,
                "fit_rows": True,
                "max_height": 160,
                "min_height": 40,
            },
                "description": "The captured points. ✕ removes a point (before "
                               "adoption)."},
        ],
    },
    {
        "type": "panel", "title": tr("Quality"), "n_col": 1,
        "description": "The calibration's quality as a table: raw measured values, "
                       "YOUR limits, statuses and what to do next. No thresholds ship "
                       "with the panel.",
        "sections": [
            {"type": "custom", "key": "quality_table", "options": {
                "source": "quality_rows",
                "row_key": "metric",
                "editable": False,
                "selection_note": False,
                "height": 210,
                "columns": _quality_columns(),
            },
                "description": "Metric, measured value, your limit, status, guidance."},
            {"type": "custom", "key": "limits_table", "options": {
                "source": "limits_rows",
                "row_key": "key",
                "editable": True,
                "delete_call": "",
                "selection_note": False,
                "fit_rows": True,
                "min_height": 30,
                "columns": [
                    {"key": "metric", "title": "Metric", "width": 150},
                    {"key": "minimum", "title": "Minimum", "editable": True,
                     "format": "%.6g", "width": 90,
                     "description": "Your lower bound (empty: none)."},
                    {"key": "maximum", "title": "Maximum", "editable": True,
                     "format": "%.6g", "width": 90,
                     "description": "Your upper bound (empty: none)."},
                ],
            },
                "description": "Your accept/reject bounds; empty = the value is "
                               "reported, not judged."},
            {"type": "button_row", "buttons": [
                {"action": "clear_limits", "label": tr("Clear limits"), "role": "danger",
                 "description": "Forget every bound: all quality values are reported, "
                                "none judged."},
            ]},
        ],
    },
    {
        "type": "panel", "title": tr("Adopt"), "n_col": 1,
        "description": "Sign off the measured calibration: dated today, expiring in "
                       "three calendar months, bound to the verified setup.",
        "sections": [
            {"type": "button_row", "buttons": [
                {"action": "adopt_save", "label": tr("Adopt & save"), "icon": "🖊",
                 "role": "primary",
                 "description": "Validate, record today as the calibration date and "
                                "save; nothing is written while the calibration is "
                                "incomplete."},
            ]},
            {"type": "info", "source": "expiry_text"},
        ],
    },
    {
        "type": "panel", "title": tr("Curve"), "n_col": 1,
        "description": "The measured anchors: the dark zero and the references. The "
                       "dashed extension marks that nothing converts beyond the "
                       "highest measurement.",
        "sections": [{"type": "custom", "key": "curve"}],
    },
    {
        "type": "panel", "title": tr("Conversion"), "n_col": 1,
        "description": "Convert a raw diode reading under the captured evidence -- or "
                       "read why the calibration refuses. Disabled wherever the "
                       "measurements do not back a number.",
        "sections": [
            {"type": "value", "label": tr("Probe raw"), "kind": "float",
             "attr": "probe_raw", "call": "probe",
             "description": "A raw diode reading to convert (e.g. one from a "
                            "measurement)."},
            {"type": "custom", "key": "probe"},
        ],
    },
]


class CalibrationPanel(ImApp):
    """The power-calibration panel as its own emtk window: one scrollable body of
    sections over :class:`CalibrationPanelModel`, drawn with the shared view-form."""

    window_title = "ChiSurf Power Calibration"
    window_size = (780, 980)

    def __init__(self, model: CalibrationPanelModel | None = None) -> None:
        self.model = model or CalibrationPanelModel()
        self.form = FormState()
        self.form.custom["status"] = self._draw_status
        self.form.custom["laser_status"] = self._draw_laser_status
        self.form.custom["config_slots"] = self._draw_config_slots
        self.form.custom["emission_status"] = self._draw_emission_status
        self.form.custom["dark_status"] = self._draw_dark_status
        self.form.custom["curve"] = self._draw_curve
        self.form.custom["probe"] = self._draw_probe
        self.form.custom["quality_table"] = CalibrationPanel._draw_data_table
        self.form.custom["limits_table"] = CalibrationPanel._draw_data_table
        self.form.custom["data_table"] = CalibrationPanel._draw_data_table
        super().__init__(gui=self._render, continuous=False)

    # -- the frame ------------------------------------------------------------------------------
    def _render(self) -> None:
        vp = im.get_main_viewport()
        im.set_next_window_pos(vp.pos, im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        flags = (im.WindowFlags.NO_DECORATION | im.WindowFlags.NO_MOVE
                 | im.WindowFlags.NO_SAVED_SETTINGS)
        if im.begin(tr("Power calibration") + "##panel", None, flags):
            im.text_colored((0.85, 0.85, 0.88, 1.0),
                            tr("Power calibration — measured entries only"))
            im.text_disabled(tr("The laser is driven from the Record tool; this panel "
                                "only reads it and never switches anything."))
            im.separator()
            width, height = im.get_content_region_avail()
            if im.begin_child("##body", (width, height)):
                draw_sections(SECTIONS, self.model, self.form)
                im.end_child()
        im.end()

    def close(self) -> None:
        """Detach the attached hardware (laser readback, diode) — the panel never
        leaves a device open behind it."""
        self.model.close()

    # -- custom drawers --------------------------------------------------------------------------
    @staticmethod
    def _draw_data_table(section, model, state, width: float) -> None:
        from emtk.widgets.data_table import TableBinding, draw_table

        if section.get("description"):
            im.text_wrapped(tr(str(section["description"])))
        options = dict(section.get("options") or {})
        name = str(options.get("source") or section.get("key") or "table")
        binding = state.tables.get(name)
        if binding is None or binding.model is not model:
            binding = state.tables[name] = TableBinding(section, model)
        draw_table(binding, name)
        state.rects[section.get("key") or name] = im.get_current_context() \
            .get_item_rect() or (0, 0, 0, 0)

    def _draw_status(self, section, model: CalibrationPanelModel, state, width: float) -> None:
        draft = model.draft
        head = (f"{model.key_name} {model.laser_nm:g} nm" if model.laser_nm is not None
                else "no laser selected")
        n = len(draft.points)
        dark = f"{draft.dark.raw:g}" if draft.dark is not None else "—"
        im.text(tr("{head} · {n} reference(s) · dark {dark} · conditions "
                   "{rep}{mode}").format(
            head=head, n=n, dark=dark,
            rep=f"{model.rep_rate_mhz:g} MHz, " if model.rep_rate_mhz > 0
            else "rate not recorded, ",
            mode=model.mode))
        if model.error:
            im.text_colored((0.90, 0.25, 0.20, 1.0), tr("⚠ {e}").format(e=model.error))
        elif model.laser_nm is not None and draft.validate() == []:
            im.text_colored((0.30, 0.75, 0.30, 1.0),
                            tr("Complete: ready to adopt (expires {e}).").format(
                                e=draft.expires_on()))
        im.separator()

    def _draw_laser_status(self, section, model: CalibrationPanelModel, state, width) -> None:
        simulated = str(getattr(model.laser, "kind", "")) == "simulated"
        colour = (0.95, 0.70, 0.10, 1.0) if simulated else \
            (0.55, 0.55, 0.58, 1.0) if model.laser is None else (0.30, 0.75, 0.30, 1.0)
        im.text_colored(colour, model.laser_status_text())

    def _draw_config_slots(self, section, model: CalibrationPanelModel, state, width) -> None:
        if model.laser is None or str(getattr(model.laser, "kind", "")) != "sepia":
            return
        try:
            heads = model.laser.state().heads
        except Exception:  # noqa: BLE001 - the next frame tries again
            return
        for h in heads:
            if h.wavelength_nm is not None:
                continue
            current = model.slot_wavelengths.get(h.slot)
            options = [f"{nm} nm" for nm in AVAILABLE_LASERS_NM]
            idx = options.index(f"{int(current)} nm") if current in AVAILABLE_LASERS_NM else 0
            im.set_next_item_width(110)
            changed, idx = im.combo(f"slot {h.slot}##slotwl_{h.slot}", idx, options)
            if changed:
                model.slot_wavelengths[h.slot] = float(AVAILABLE_LASERS_NM[idx])
            im.same_line()
            im.text_disabled(tr("the head's wavelength in slot {slot} "
                                "(the readback does not say)").format(slot=h.slot))

    def _draw_emission_status(self, section, model: CalibrationPanelModel, state, width) -> None:
        if model.emission_state is None:
            im.text_disabled(tr("No emission state captured yet."))
            return
        ok, why = model.emission_state.confirmed_single(model.key_name) \
            if model.laser_nm is not None else (False, "no laser selected")
        colour = (0.30, 0.75, 0.30, 1.0) if ok else (0.90, 0.55, 0.10, 1.0)
        im.text_colored(colour, tr("Captured {at} ({route}): {states}").format(
            at=model.emission_captured_at, route=model.emission_route,
            states="; ".join(f"{e.laser} {'ON' if e.on else 'off'}"
                             f"{'' if e.verified else ' (UNVERIFIED)'}"
                             for e in model.emission_state.lasers)))
        if not ok:
            im.text_colored((0.90, 0.55, 0.10, 1.0), tr("Not usable for {head}: {why}")
                            .format(head=model.key_name, why=why))
        if model.emission_evidence:
            im.text_disabled(model.emission_evidence)

    def _draw_dark_status(self, section, model: CalibrationPanelModel, state, width) -> None:
        dark = model.draft.dark
        if dark is None:
            im.text_disabled(tr("No dark offset captured yet."))
            return
        ok, why = dark.emission.all_off_confirmed()
        im.text_colored((0.30, 0.75, 0.30, 1.0) if ok else (0.90, 0.55, 0.10, 1.0),
                        tr("Dark raw {raw:g} (captured {when})").format(
                            raw=dark.raw, when=dark.measured or "?"))
        if not ok:
            im.text_colored((0.90, 0.55, 0.10, 1.0), tr("Not a zero: {why}").format(why=why))

    def _draw_curve(self, section, model: CalibrationPanelModel, state, width: float) -> None:
        from emtk import implot

        draft = model.draft
        anchors = draft._anchors() if draft.dark is not None and draft.points else None
        avail = im.get_content_region_avail()
        height = max(140.0, min(220.0, avail[1]))
        if not implot.begin_plot("##power_curve", (width, height), implot.FLAGS_NO_TITLE):
            implot.end_plot()
            return
        implot.setup_axes(tr("diode raw (counts)"), tr("power (µW)"))
        if anchors is not None:
            xs, ys = anchors
            implot.setup_axis_limits(0, 0.0, max(xs) * 1.15)
            implot.setup_axis_limits(1, 0.0, max(ys) * 1.25)
            implot.plot_line(tr("measured anchors"), xs, ys)
            implot.plot_scatter(tr("measured (dark + references)"), xs, ys)
            probe = model._probe
            if probe is not None and math.isfinite(probe.raw):
                implot.plot_scatter(tr("probe"), [probe.raw],
                                    [probe.uw if probe.valid else 0.0])
        else:
            implot.setup_axis_limits(0, 0.0, 1.0)
            implot.setup_axis_limits(1, 0.0, 1.0)
        implot.end_plot()
        if anchors is None:
            im.text_disabled(tr("The curve draws the measured anchors: capture the dark "
                                "offset and two or more references."))

    def _draw_probe(self, section, model: CalibrationPanelModel, state, width: float) -> None:
        model.probe()
        text = model.probe_text()
        valid = model._probe is not None and model._probe.valid
        im.text_colored((0.30, 0.75, 0.30, 1.0) if valid else (0.90, 0.60, 0.15, 1.0),
                        text)


def make_app(model: CalibrationPanelModel | None = None) -> CalibrationPanel:
    """The panel as the plugin system would open it."""
    from chisurf.emtk.i18n import install

    install()
    return CalibrationPanel(model)


def main() -> int:
    """Run the panel as its own desktop window."""
    from emtk.native import NativeHost

    app = make_app()
    host = NativeHost(app, title=CalibrationPanel.window_title)
    try:
        host.run()
    finally:
        host.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
