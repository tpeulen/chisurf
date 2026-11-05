"""The Record tool's laser and settings files: the model half of the *Laser* and *Settings* panels.

:class:`LaserSettingsMixin` is mixed into :class:`~chisurf.plugins.core.acq.gui.record_app.RecordModel`.
It owns the laser backend (``live.laser``: Sepia II, or the simulated driver) and the acquisition
settings document (``live.settings_file``):

* **Laser** -- *Connect* opens the backend (all outputs off); the head table and the sequencer
  edit a *program* that only reaches the laser with *Apply*; *Emission on* is offered only after
  that, and *Laser off* is always there. Any edit after *Apply* asks for *Apply* again. A run's end
  and the window's close close the laser (outputs off first).
* **Windows from laser** -- the micro-time windows the applied program implies
  (:func:`~chisurf.plugins.core.acq.live.laser.propose_pie_windows`) replace the Experiment
  setup's windows.
* **Settings** -- *Load* reads an acquisition settings row of the workspace, sends it to the
  connected device and laser and fills the form; *Use settings of this measurement* recovers them
  from a photons row (its PTU header); *Save as…* writes what the form, device and laser hold now.
  The same document goes into every recording's header (``ChiSurf_AcquisitionSettings``).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from emtk.i18n import tr

from chisurf.plugins.core.acq.live import laser as laser_mod
from chisurf.plugins.core.acq.live import settings_file
from chisurf.plugins.core.acq.live.project import workspace_datasets
from chisurf.plugins.core.acq.live.realism import Realism
from chisurf.plugins.core.acq.live.storage_config import StorageConfig, StorageConfigError

#: ``setup_address`` of the channel setup a settings document brought.
SETTINGS_SETUP = "settings"
_OUTPUTS = laser_mod.SEQUENCER_OUTPUTS


def _short(problems: list[str], n: int = 3) -> str:
    return "; ".join(problems[:n]) + (f" (+{len(problems) - n})" if len(problems) > n else "")


from .refreshed import holds_hardware

class LaserSettingsMixin:
    """Laser control and acquisition settings files for the Record model."""

    def _init_laser_settings(self) -> None:
        #: a chosen settings file is being loaded onto the hardware (a worker thread)
        self.connecting = False
        #: its progress, 0..1 (``None``: under way, length unknown), and what it is doing
        self.connect_fraction: float | None = None
        self.connect_text = ""
        self._connect_thread = None
        #: the shutter box and power diode (phacq.shutterbox) a settings file defines
        self.shutters = None
        #: the shutters' form, generated from the box's schema (the settings file's section)
        self.shutter_form = None
        self._shutter_form_at = 0.0
        self.shutter_section: dict | None = None
        self.shutter_text = tr("No shutters")
        self.laser_kind = "auto"
        #: the address of the chosen laser (a serial port, a Sepia serial number, ...; ``""``:
        #: auto-detect) -- set by the Settings dock's laser chooser
        self.laser_address = ""
        self.laser: laser_mod.LaserBackend | None = None
        #: the program the head table and sequencer edit (a settings file's ``laser`` section)
        self.laser_program: dict = {}
        #: whether :attr:`laser_program` is what the laser holds (Emission on needs it)
        self.laser_applied = False
        self.laser_divider = 1
        self.laser_text = tr("No laser connected")
        self.laser_detail = ""
        #: windows that replace the Experiment setup's (from the laser, or from a measurement)
        self.window_override: dict | None = None
        #: detector micro-time gates taken with the windows (device channels; ``{}``: the setup's)
        self.gate_override: dict = {}
        self.proposed_windows: dict | None = None
        self.settings_address = ""
        self.settings_setup: dict | None = None
        self.settings_name = ""
        self.settings_text = tr("No settings loaded")
        self.settings_detail = ""
        self.save_settings_requested = False
        self._emission_on = False
        self._laser_rate_hz: float | None = None
        #: the connected laser driver's own settings form (Sepia II through libphacq)
        self.laser_form = None
        self._laser_sent: dict = {}

    # -- the laser -------------------------------------------------------------------------------
    @property
    def laser_connected(self) -> bool:
        return self.laser is not None and self.laser.is_open

    @property
    def laser_program_shown(self) -> bool:
        """The head table / sequencer program: for a laser without direct controls (the simulated
        one). A Sepia II through libphacq is set with its own controls, which act at once."""
        return self.laser_connected and self.laser_form is None

    def _sepia_status(self, fresh: bool = False) -> tuple[bool, str]:
        """Whether a Sepia II is there, checked at most every two seconds and never while a laser
        is connected (an options list is drawn every frame; enumerating USB on each would stall
        the window, and must not touch a unit this tool is driving)."""
        if self.laser_connected:
            return True, getattr(self, "_sepia_seen", (True, ""))[1]
        if getattr(self, "_sepia_refresh", None) is None:
            from .refreshed import Refreshed

            self._sepia_refresh = Refreshed(
                laser_mod.sepia_available, initial=(False, tr("checking…")), hardware=True,
                skip=lambda: self.laser_connected,
                on_change=getattr(self, "request_frame", None))
        # a frame takes the last check; an action (connect, load) checks now
        self._sepia_seen = self._sepia_refresh.now() if fresh else self._sepia_refresh.get()
        return self._sepia_seen

    def _cmc_status(self, fresh: bool = False) -> tuple[bool, str]:
        """Whether a CMC Light laser is available, checked at most every two seconds."""
        if self.laser_connected and getattr(self.laser, "kind", "") == "cmc_light":
            return True, getattr(self, "_cmc_seen", (True, ""))[1]
        if getattr(self, "_cmc_refresh", None) is None:
            from .refreshed import Refreshed

            self._cmc_refresh = Refreshed(
                laser_mod.cmc_light_available, initial=(False, tr("checking…")), hardware=True,
                skip=lambda: self.laser_connected and getattr(self.laser, "kind", "") == "cmc_light",
                on_change=getattr(self, "request_frame", None))
        self._cmc_seen = self._cmc_refresh.now() if fresh else self._cmc_refresh.get()
        return self._cmc_seen

    def laser_options(self) -> list:
        ok, why = self._sepia_status()
        sepia = tr("Sepia II") if ok else tr("Sepia II (not available)")
        self._sepia_reason = "" if ok else why

        ok_cmc, why_cmc = self._cmc_status()
        cmc = tr("CMC Light") if ok_cmc else tr("CMC Light (not available)")
        self._cmc_reason = "" if ok_cmc else why_cmc

        ok_obis, _why_obis = laser_mod.obis_available()
        return [
            ("auto", tr("Auto (hardware, else simulated)")),
            ("sepia", sepia),
            ("obis", tr("OBIS (Coherent)") + ("" if ok_obis else tr(" (not available)"))),
            ("cmc_light", cmc),
            ("cmc_sim", tr("CMC Light (simulated)")),
            ("simulated", tr("Simulated laser")),
        ]

    def laser_devices(self) -> list[dict]:
        """Every laser system connected to this computer, for the Settings dock's chooser.

        One entry per candidate: ``{key, backend, address, label, detail, connected}``. Hardware
        enumeration never runs per frame (it would stall the window), so the list is cached two
        seconds like the availability checks; which row is in use is always answered live. The
        phacq registry is asked for every laser-ish driver it knows, so new backends (obis, ni)
        show up as their drivers land.
        """
        if getattr(self, "_laser_devices_refresh", None) is None:
            from .refreshed import Refreshed

            self._laser_devices_refresh = Refreshed(
                self._laser_device_rows, initial=self._laser_device_rows_offline(), hardware=True,
                on_change=getattr(self, "request_frame", None))
        rows = self._laser_devices_refresh.get()

        def _connected(backend: str, address: str) -> bool:
            return self.laser_connected and self.laser_kind == backend and (
                not address or self.laser_address == address)

        # which row is in use is answered live, over the cached rows
        return [dict(e, connected=_connected(e["backend"], e["address"])) for e in rows]

    def _laser_device_rows_offline(self) -> list[dict]:
        """The rows that need no hardware (shown until the first enumeration has landed)."""
        return [
            {"key": "auto", "backend": "auto", "address": "",
             "label": tr("Detect automatically"), "detail": tr("hardware, else the simulator")},
            {"key": "simulated", "backend": "simulated", "address": "",
             "label": tr("Simulated laser"), "detail": tr("pulses in step with the simulation")},
        ]

    def _laser_device_rows(self) -> list[dict]:
        """The enumeration itself (see :meth:`laser_devices`; runs on a worker thread holding
        the hardware lock): passive listing only, without the live ``connected`` stamp."""
        entries: list[dict] = self._laser_device_rows_offline()
        try:
            from chisurf.plugins.core.acq.live import devices as devices_mod
            for entry in devices_mod.attached_devices(("sepia",)):
                entries.append({
                    "key": entry.key, "backend": "sepia", "address": entry.serial,
                    "label": tr("Sepia II"), "detail": entry.label})
        except Exception:  # noqa: BLE001 - enumeration must never break the dock
            pass
        try:
            from chisurf.plugins.core.acq.live import devices as devices_mod
            for entry in devices_mod.attached_devices(("obis", "ni")):
                entries.append({
                    "key": entry.key, "backend": entry.driver, "address": entry.serial,
                    "label": entry.label, "detail": entry.label})
        except Exception:  # noqa: BLE001 - drivers not installed yet: no rows, no error
            pass
        mod = laser_mod._cmc_light_module()
        if mod is not None:
            try:
                for port, idn in mod.find_instruments(timeout=0.1):
                    entries.append({
                        "key": f"cmc_light:{port}", "backend": "cmc_light", "address": port,
                        "label": tr("CMC Light"), "detail": f"{idn} @ {port}"})
            except Exception:  # noqa: BLE001 - a missing CMC firmware must not break the list
                pass
        return entries

    def select_laser_device(self, key: str) -> tuple[bool, str]:
        """Make the laser system ``key`` (a :meth:`laser_devices` entry) the one this session
        drives: idle-only, disconnects the current one, then reconnects to the choice."""
        if self.running:
            return False, tr("A recording is running")
        if self.connecting:
            return False, tr("A settings file is loading")
        entry = next((e for e in self.laser_devices() if e["key"] == key), None)
        if entry is None:
            return False, tr("Not connected to this computer")
        if self.laser_connected:
            self.disconnect_laser()
        self.laser_kind = entry["backend"]
        self.laser_address = entry["address"]
        ok = self.connect_laser()
        if not ok:
            return False, self.laser_detail or self.laser_text
        return True, self.laser_text

    def _new_laser(self) -> laser_mod.LaserBackend:
        if self.laser_kind == "simulated" or (
            self.laser_kind == "auto"
            and not self._sepia_status(fresh=True)[0]
            and not (self._cmc_status(fresh=True)[0] and "USB" in self._cmc_status()[1])
        ):
            # the simulated driver pulses in step with the simulated measurement (one pulse per
            # half period: PIE)
            n_micro, res = self._clock()
            return laser_mod.SimLaser(base_hz=2.0 / (n_micro * res))
        if self.laser_kind == "cmc_sim":
            return laser_mod.open_laser("cmc_sim")
        if self.laser_kind in ("cmc", "cmc_light"):
            return laser_mod.open_laser(self.laser_kind, allow_simulated=True,
                                        port=self.laser_address or "")
        if self.laser_kind in ("sepia", "sepia2"):
            return laser_mod.open_laser(self.laser_kind, serial=self.laser_address or "")
        if self.laser_kind == "obis":
            return laser_mod.open_laser(
                "obis", serial=self.laser_address or "", allow_simulated=True
            )
        return laser_mod.open_laser(self.laser_kind)

    @holds_hardware
    def connect_laser(self) -> bool:
        if self.laser_connected:
            return False
        if self.laser_kind in ("sepia", "sepia2"):
            self._sepia_at = -1e9  # look again now
            ok, why = self._sepia_status(fresh=True)
            if not ok:
                self.laser_text, self.laser_detail = tr("Sepia II not available"), why
                return False
        elif self.laser_kind == "cmc_light":
            self._cmc_at = -1e9
            ok, why = self._cmc_status(fresh=True)
            if not ok:
                self.laser_text, self.laser_detail = tr("CMC Light not available"), why
                return False
        try:
            backend = self._new_laser()
            backend.open()
        except Exception as exc:  # noqa: BLE001 - shown; nothing emits
            self.laser = None
            self.laser_text, self.laser_detail = tr("Cannot connect the laser"), str(exc)
            return False
        self.laser = backend
        self.laser_program = backend.capture()
        self._laser_form_from_device()
        self.laser_divider = int((self.laser_program.get("oscillator") or {}).get("divider", 1))
        self.laser_applied = False
        self._laser_status()
        return True

    @holds_hardware
    def disconnect_laser(self) -> bool:
        if self.laser is None:
            return False
        try:
            self.laser.close()
        finally:
            self.laser = None
            self.laser_form = None
            self.laser_applied = self._emission_on = False
            self.laser_text, self.laser_detail = tr("No laser connected"), ""
        return True

    def _laser_form_from_device(self) -> None:
        """The laser driver's own controls, generated from what it describes (pulsed switch,
        repetition rate, intensity per head; the soft lock), when the backend is a device."""
        dev = getattr(self.laser, "device", None)
        if dev is None:
            self.laser_form = None
            return
        from chisurf.plugins.core.acq.live import devices

        self._laser_sent = dict(dev.settings())
        # open: the laser's switches are the quick controls
        self.laser_form = devices.settings_form(dev, self._laser_sent,
                                                on_change=self.laser_settings_edited, folded=False,
                                                advanced=self.advanced)

    def _laser_follow_device(self) -> None:
        """The laser's controls show the laser's values (read-only ones included), in place."""
        dev = getattr(self.laser, "device", None)
        if dev is None or self.laser_form is None:
            return
        self._laser_sent = dict(dev.settings())
        self.laser_form.update_values(self._laser_sent)

    def laser_settings_edited(self) -> None:
        """An edit of the laser's own controls: send what changed now."""
        dev = getattr(self.laser, "device", None)
        if dev is None or self.laser_form is None:
            return
        from chisurf.plugins.core.acq.live import devices

        values = self.laser_form.params()
        changed = {k: v for k, v in values.items() if self._laser_sent.get(k) != v}
        if not changed:
            return
        notes = devices.apply_settings(dev, changed)
        if notes:
            self.laser_text, self.laser_detail = tr("The laser refused"), "; ".join(notes)
            self._laser_form_from_device()
            return
        self._laser_follow_device()
        if "soft_lock" in changed:
            self._emission_on = not bool(changed["soft_lock"])
        self.laser_program = self.laser.capture()
        self._laser_status()

    def laser_off(self) -> None:
        """Block all emission now (never fails)."""
        self._emission_on = False
        if self.laser is not None:
            self.laser.laser_off()
            self._laser_status()

    def apply_laser_program(self) -> bool:
        if not self.laser_connected:
            return False
        try:
            self.laser.apply(self.laser_program)
        except Exception as exc:  # noqa: BLE001 - the backend switched the outputs off
            self.laser_applied = False
            self.laser_text, self.laser_detail = tr("Program refused"), str(exc)
            return False
        self.laser_applied = True
        self._laser_status()
        return True

    def laser_toggle(self) -> bool:
        """The laser button: emission off while it emits, else on (after Apply, as Emission on)."""
        if self._emission_on:
            self.laser_off()
            return True
        return self.laser_emission_on()

    def laser_toggle_label(self) -> str:
        return tr("Laser off") if self._emission_on else tr("Laser on")

    def laser_toggle_role(self) -> str:
        """Red while the laser emits (pressing it blocks emission), green to switch it on."""
        return "danger" if self._emission_on else "success"

    def laser_emission_on(self) -> bool:
        if not (self.laser_connected and self.laser_applied):
            return False
        try:
            self.laser.set_emission(True)
        except Exception as exc:  # noqa: BLE001 - outputs are off again
            self.laser_text, self.laser_detail = tr("Emission refused"), str(exc)
            return False
        self._laser_status()
        return True

    def _laser_status(self) -> None:
        if not self.laser_connected:
            return
        st = self.laser.state()
        heads = ", ".join(
            f"{h.name} {h.wavelength_nm:.0f} nm" if h.wavelength_nm else h.name for h in st.heads
        )
        on = self._emission_on = not st.emission_blocked
        self._laser_rate_hz = self.laser.capture().get("repetition_rate_hz")
        self.laser_text = (
            tr("Emission ON") if on else tr("Applied, emission off")
            if self.laser_applied else tr("Connected, outputs off")
        )  # fmt: skip
        self.laser_detail = "\n".join(
            [f"{st.model} {st.serial} ({self.laser.kind})", heads] + list(st.warnings)
        )
        # the laser's own controls show what it holds now (the soft lock after Laser off ...)
        self._laser_follow_device()

    def laser_light(self) -> str:
        if not self.laser_connected:
            return "grey"
        if self._emission_on:
            return "red"  # light is on: the colour of danger
        return "green" if self.laser_applied else "amber"

    def laser_rate(self) -> tuple[str, str]:
        """The repetition rate the laser runs at (its capture), and the program's for the tooltip."""
        if not self.laser_connected:
            return "", ""
        now = self._laser_rate_hz
        pending = laser_mod.OscillatorState(
            **{
                k: v
                for k, v in (self.laser_program.get("oscillator") or {}).items()
                if k in laser_mod.OscillatorState.__dataclass_fields__
            }
        )
        text = tr("Rate {mhz:.2f} MHz").format(mhz=now / 1e6) if now else tr("Rate unknown")
        detail = tr(
            "The laser's repetition rate now. The program: {mhz:.2f} MHz, one sequence {ns:.1f} ns."
        ).format(mhz=pending.pulse_rate_hz / 1e6, ns=pending.sequence_period_s * 1e9)
        return text, detail

    # -- the program (head table, divider, sequencer) -------------------------------------------
    def _osc(self) -> dict:
        osc = self.laser_program.setdefault("oscillator", {})
        osc.setdefault("burst_lengths", [1] + [0] * (_OUTPUTS - 1))
        osc.setdefault("output_enabled", [False] * _OUTPUTS)
        osc.setdefault("sync_enabled", [True] + [False] * (_OUTPUTS - 1))
        return osc

    def _edited(self) -> None:
        self.laser_applied = False  # the laser holds an older program: Apply again
        if self.laser_connected:
            self.laser.laser_off()
            self._laser_status()

    def laser_heads(self) -> list[dict]:
        rows = []
        for h in self.laser_program.get("heads") or []:
            nm = h.get("wavelength_nm")
            rows.append(
                {
                    "slot": h.get("slot"),
                    "head": f"{nm:.0f} nm" if nm else str(h.get("name", "")),
                    "detail": f"{h.get('name', '')}, slot {h.get('slot')}, output "
                    f"{int(h.get('output', -1)) + 1}",
                    "enabled": bool(h.get("enabled")),
                    "intensity_pct": float(h.get("intensity_pct") or 0.0),
                    "pulsed": bool(h.get("pulsed", True)),
                }
            )
        return rows

    def laser_head_edited(self, record: dict, key: str, value: Any) -> None:
        for h in self.laser_program.get("heads") or []:
            if h.get("slot") != record.get("slot"):
                continue
            if key == "intensity_pct":
                h[key] = min(100.0, max(0.0, float(value)))
            elif key in ("enabled", "pulsed"):
                h[key] = bool(value)
                out = int(h.get("output", -1))
                if key == "enabled" and 0 <= out < _OUTPUTS:
                    self._osc()["output_enabled"][out] = bool(value)
        self._edited()

    def laser_program_edited(self, _value=None) -> None:
        self._osc()["divider"] = max(1, int(self.laser_divider))
        self._edited()

    def laser_outputs(self) -> list[dict]:
        if not self.laser_program:
            return []
        osc = self._osc()
        names = {int(h.get("output", -1)): h.get("name", "") for h in self.laser_program["heads"]}
        return [
            {
                "output": i + 1,
                "head": names.get(i, ""),
                "burst": int(osc["burst_lengths"][i]),
                "enabled": bool(osc["output_enabled"][i]),
                "sync": bool(osc["sync_enabled"][i]),
            }
            for i in range(_OUTPUTS)
        ]

    def laser_output_edited(self, record: dict, key: str, value: Any) -> None:
        osc, i = self._osc(), int(record["output"]) - 1
        if key == "burst":
            osc["burst_lengths"][i] = max(0, int(value))
        elif key == "enabled":
            osc["output_enabled"][i] = bool(value)
            for h in self.laser_program.get("heads") or []:
                if int(h.get("output", -1)) == i:
                    h["enabled"] = bool(value)
        elif key == "sync":
            osc["sync_enabled"][i] = bool(value)
        self._edited()

    # -- micro-time windows ---------------------------------------------------------------------
    def _clock(self) -> tuple[int, float]:
        """``(n_micro, micro-time resolution in s)`` of what will be measured."""
        session = getattr(self, "session", None)
        if session is not None:
            info = session.source.info
            return int(info.n_micro), float(info.micro_res_s)
        if self.source_kind == "device" and self.device is not None:
            res = float(self.device.information().base_resolution_ps) * 1e-12
            period = 0.0
            if self.laser_connected:
                osc = self.laser.state().oscillator
                period = osc.sequence_period_s if osc is not None else 0.0
            return (max(1, int(round(period / res))) if period else 2**15), res
        from chisurf.plugins.core.acq.live.sources import SimulatedPieSource

        info = SimulatedPieSource(duration_s=1.0, realtime=False).info
        return int(info.n_micro), float(info.micro_res_s)

    def windows_from_laser(self) -> bool:
        """The applied program's excitation slots as the setup's micro-time windows."""
        if not self.laser_connected:
            return False
        n_micro, res = self._clock()
        patch = laser_mod.propose_pie_windows(
            self.laser.state(), res, n_micro=n_micro, sync_offset_s=self.sync_offset_ps * 1e-12
        )
        if not patch["windows"]:
            self.status_text = tr("No enabled excitation")
            self.status_detail = tr("Enable a head with pulses in the sequencer, then Apply.")
            return False
        self.window_override = dict(patch["windows"])
        self.window_override_label = tr("windows from the laser")
        self.status_text = tr("Windows from the laser")
        self.status_detail = ", ".join(f"{k} {v[0]}:{v[1]}" for k, v in patch["windows"].items())
        return True

    def use_proposed_windows(self) -> bool:
        if not self.proposed_windows:
            return False
        self.window_override = dict(self.proposed_windows)
        self.window_override_label = tr("windows from the measurement")
        self.status_text = tr("Windows from the measurement")
        self.status_detail = ", ".join(
            f"{k} {v[0]}:{v[1]}" for k, v in self.window_override.items()
        )
        return True

    def windows_patched(self, setup: dict) -> dict:
        """*setup* with its windows replaced by :attr:`window_override` (device channels).

        Replaced, not merged: windows taken from the laser or the data are the whole set (a
        detection may name them ``pulse1``... where the setup had ``prompt``/``delayed``).
        """
        if not self.window_override:
            return setup
        out = {**setup, "windows": dict(self.window_override)}
        gates = getattr(self, "gate_override", None) or {}
        if gates:
            out["detectors"] = {
                k: ({**v, "micro_time_ranges": [list(r) for r in gates[k]]} if k in gates else v)
                for k, v in (setup.get("detectors") or {}).items()
            }
        return out

    # -- settings files ----------------------------------------------------------------------------
    def settings_options(self) -> list:
        now = time.monotonic()
        if now - getattr(self, "_settings_rows_at", -1e9) > 2.0:
            self._settings_rows_at = now
            rows = [("", tr("Choose settings or a measurement"))]
            rows += [(f"profile:{path}", f"★ {name}") for path, name in
                     settings_file.shipped_profiles()]
            rows += [
                (f"setup:{d.address}", f"⚙ {getattr(d, 'name', '') or Path(d.address).name}")
                for d in workspace_datasets("setup")
            ]
            rows += [
                (f"photons:{d.address}", f"⏱ {getattr(d, 'name', '') or Path(d.address).name}")
                for d in workspace_datasets("photons")
            ]
            self._settings_rows = rows
        return self._settings_rows

    def _picked(self) -> tuple[str, str]:
        kind, _, address = str(self.settings_address).partition(":")
        return kind, address

    # -- shutters and power diode (the settings file's ``shutters`` section) -------------------
    @staticmethod
    def _shutter_key(name: str) -> str:
        """A shutter's parameter key, as phacq's shutters driver makes it ("Detector 1" ->
        detector_1)."""
        import re

        return re.sub(r"[^0-9a-z]+", "_", str(name).lower()).strip("_")

    def _shutter_names(self, role: str | None = None) -> list[str]:
        return [str(sh["name"]) for sh in (self.shutter_section or {}).get("shutters") or []
                if role is None or str(sh.get("role", "")) == role]

    def connect_shutters(self, section: dict) -> bool:
        """Open the shutters a ``shutters`` section defines -- phacq's ``shutters`` driver, a
        Device like the others; its settings form is generated from its schema."""
        import json

        try:
            import phacq

            self.shutters = phacq.DriverRegistry.instance().driver("shutters").open(
                json.dumps(section))
        except Exception as exc:  # noqa: BLE001 - shown; a run still records
            self.shutters, self.shutter_text = None, str(exc)
            return False
        self.shutter_section = dict(section)
        self.shutter_text = tr("Shutters: {names}").format(names=", ".join(self._shutter_names()))
        self._shutter_form_from_device()
        return True

    def _shutter_form_from_device(self) -> None:
        from chisurf.plugins.core.acq.live import devices

        self.shutter_form = devices.settings_form(self.shutters, dict(self.shutters.settings()),
                                                  on_change=self.shutter_settings_edited,
                                                  folded=False, advanced=self.advanced)

    def advanced_changed(self, _value: bool | None = None) -> None:
        """Simple / Advanced, for every piece of hardware at once: the device's settings, the
        laser's and the shutters' forms are rebuilt with or without their expert settings."""
        if getattr(self.laser, "device", None) is not None and self.laser_form is not None:
            self._laser_form_from_device()
        if self.shutters is not None:
            self._shutter_form_from_device()
        if getattr(self, "scanner", None) is not None:
            self._scanner_form_from_device()

    @property
    def realism_hidden(self) -> bool:
        """The simulator's sample & instrument realism: an expert's knobs, Advanced only."""
        return self.source_kind != "simulator" or not self.advanced

    def shutter_settings_edited(self) -> None:
        """A checkbox in the shutters' form: send what changed."""
        if self.shutters is None or self.shutter_form is None:
            return
        from chisurf.plugins.core.acq.live import devices

        notes = devices.apply_settings(self.shutters, {
            k: v for k, v in self.shutter_form.params().items() if k.startswith("open_")})
        if notes:
            self.shutter_text = tr("Shutters: {e}").format(e="; ".join(notes))

    def refresh_shutter_form(self, interval_s: float = 0.25) -> None:
        """Show what the hardware reports (and what Start/end of a run did) in the form."""
        if self.shutters is None or self.shutter_form is None:
            return
        now = time.monotonic()
        if now - self._shutter_form_at >= interval_s:
            self._shutter_form_at = now
            try:
                self.shutter_form.update_values(dict(self.shutters.settings()))
            except Exception:  # noqa: BLE001 - the next refresh tries again
                pass

    def set_shutter(self, name: str, open_: bool) -> bool:
        """Open or close one shutter."""
        return self._set_shutters({name: open_})

    def _set_shutters(self, states: dict) -> bool:
        if self.shutters is None:
            return False
        try:
            self.shutters.apply({"open_" + self._shutter_key(n): bool(v)
                                 for n, v in states.items()})
        except Exception as exc:  # noqa: BLE001 - shown on the status line
            self.shutter_text = tr("Shutters: {e}").format(e=exc)
            return False
        return True

    def disconnect_shutters(self) -> None:
        if self.shutters is not None:
            try:
                self.shutters.close()
            finally:
                self.shutters = None
                self.shutter_form = None
                self.shutter_text = tr("No shutters")

    def _shutters_at_start(self) -> None:
        """Before a run: open the shutters the section names (default all), give the diode a
        moment to report through the open excitation shutter, average it afresh."""
        if self.shutters is None:
            return
        names = (self.shutter_section or {}).get("open_at_start") or self._shutter_names()
        if not self._set_shutters({n: True for n in names}):
            return
        end = time.monotonic() + 0.6
        while time.monotonic() < end and self._shutter_value("diode_raw") is None:
            time.sleep(0.02)
        try:
            self.shutters.set_parameter("diode_mark", 1.0)
        except Exception:  # noqa: BLE001 - a definition without a diode
            pass

    def _shutters_at_end(self) -> None:
        """After a run: close the shutters the section names (default the excitation ones). The
        laser is not touched: the shutter keeps the light off the sample."""
        if self.shutters is None:
            return
        names = (self.shutter_section or {}).get("close_at_end") or \
            self._shutter_names("excitation")
        self._set_shutters({n: False for n in names})

    def _shutter_value(self, key: str):
        """A read-only value of the shutters device; ``None`` when it has none (yet)."""
        try:
            v = float(self.shutters.get_parameter(key, -1))
        except Exception:  # noqa: BLE001 - not a parameter of this definition
            return None
        return None if v < 0 else v

    def run_header_tags(self) -> dict:
        """PTU header tags of the laser, the shutters and the power diode for the run to start."""
        tags = laser_mod.ptu_tags(self.laser if self.laser_connected else None,
                                  self.laser_program)
        if self.shutters is not None:
            for name in self._shutter_names():
                state = self._shutter_value("reported_" + self._shutter_key(name))
                if state is not None:
                    tags["ChiSurf_ShutterOpen_" + name.replace(" ", "")] = bool(state)
            raw = self._shutter_value("diode_raw")
            if raw is not None:
                tags["ChiSurf_PowerDiodeRaw"] = float(raw)
                au = self._shutter_value("diode_au")
                if au is not None:
                    tags["UsrPowerDiode"] = float(au)      # SymPhoTime's name and unit (a.u.)
        return tags

    def _progress(self, fraction: float | None, text: str) -> None:
        """Where loading settings onto the hardware is (shown under the settings choice)."""
        self.connect_fraction, self.connect_text = fraction, text

    def settings_chosen(self) -> bool:
        """A settings file or profile picked in the list: load it onto the hardware at once,
        in a worker thread (opening a device takes seconds), with the progress shown."""
        import threading

        if self._picked()[0] not in ("setup", "profile") or self.connecting or self.running:
            return False
        self.connecting = True
        self._progress(0.0, tr("Reading the settings…"))

        def work():
            try:
                self.load_settings()
            except Exception as exc:  # noqa: BLE001 - shown; the form keeps what it had
                self.settings_text, self.settings_detail = tr("Not loaded"), str(exc)
            finally:
                self.connecting = False
                self._progress(None, "")

        self._connect_thread = threading.Thread(target=work, name="record-load-settings",
                                                daemon=True)
        self._connect_thread.start()
        return True

    def wait_connected(self, timeout: float | None = None) -> None:
        """Wait for a :meth:`settings_chosen` load to end (scripts and tests)."""
        if self._connect_thread is not None:
            self._connect_thread.join(timeout)

    def load_settings(self) -> bool:
        """Read the chosen settings row and send it to the device and the laser."""
        kind, address = self._picked()
        if kind not in ("setup", "profile"):
            return False
        try:
            doc = settings_file.load(address)
        except settings_file.SettingsError as exc:
            self.settings_text, self.settings_detail = tr("Not a settings file"), str(exc)
            return False
        return self.adopt_settings(doc, Path(address).name, [])

    def use_measurement_settings(self) -> bool:
        """Settings recovered from the chosen photons row (its header), and its laser's windows."""
        kind, address = self._picked()
        if kind != "photons":
            return False
        ds = next((d for d in workspace_datasets("photons") if str(d.address) == address), None)
        try:
            doc, missing = (
                settings_file.from_dataset(ds)
                if ds is not None
                else settings_file.from_address(address)
            )
        except Exception as exc:  # noqa: BLE001 - shown: an unreadable or foreign header
            self.settings_text, self.settings_detail = tr("No settings in it"), str(exc)
            return False
        name = str(getattr(ds, "name", "") or Path(address).name)
        ok = self.adopt_settings(doc, name, missing)
        self.proposed_windows = None
        if getattr(self, '_instrument_sim', None) is not None:
            return ok
        laser = doc.get("laser") or {}
        if laser.get("oscillator"):
            res_ps = (doc.get("device") or {}).get("resolution_ps")
            n_micro, res = self._clock()
            res = float(res_ps) * 1e-12 if res_ps else res
            sync_ps = ((doc.get("device") or {}).get("sync") or {}).get("offset_ps", 0)
            patch = laser_mod.propose_pie_windows(
                laser, res, n_micro=n_micro, sync_offset_s=float(sync_ps) * 1e-12
            )
            self.proposed_windows = patch["windows"] or None
        return ok

    def adopt_settings(self, doc: dict, name: str, missing: list[str]) -> bool:
        """Fill the form from *doc* and send it to the connected device and laser."""
        problems = settings_file.validate(doc)
        if problems:
            self.settings_text, self.settings_detail = tr("Settings not valid"), "\n".join(problems)
            return False
        notes: list[str] = []
        if getattr(self, '_instrument_sim', None) is not None:
            # Profiles describe real hardware; loading one in simulation must not
            # replace the rig's laser/clock, excitation setup or open hardware.
            safe_doc = {k: v for k, v in doc.items()
                        if k not in ('device', 'laser', 'scanner', 'shutters', 'simulator')}
            experiment = dict(safe_doc.get('experiment') or {})
            for key in ('preset', 'setup', 'alex_period_us', 'alex_windows_s'):
                experiment.pop(key, None)
            safe_doc['experiment'] = experiment
            self._form_from(safe_doc)
            self.settings_name = name
            self.settings_text = tr('Settings: {name}').format(name=name)
            self.settings_detail = tr('SIMULATION ONLY: settings were read without connecting or changing hardware.')
            return True
        self._form_from(doc)
        # A settings file is meant for the hardware: connect what it names and is not yet
        # connected (a failure is a note; the form still holds the values).
        if doc.get("device") and getattr(self, "device", None) is None \
                and getattr(self, "source_kind", "device") == "device":
            from chisurf.plugins.core.acq.live import devices as devices_mod

            section = doc["device"]
            self._progress(0.15, tr("Looking for {name}…").format(
                name=" ".join(str(section.get(k) or "") for k in ("model", "serial")).strip()
                or tr("the device")))
            entry = devices_mod.device_for(section)
            if entry is None:
                wanted = " ".join(str(section.get(k) or "") for k in ("model", "serial")).strip()
                notes.append(tr("Device not connected: {name} is not attached.").format(
                    name=wanted or section.get("driver") or tr("the file's device")))
            else:
                self.device_index = entry.key
                self._progress(0.3, tr("Connecting to {name}…").format(name=entry.label))
                if not self.connect_device():
                    notes.append(tr("Device not connected: {why}").format(
                        why=getattr(self, "device_text", "") or entry.label))
        laser_doc = doc.get("laser") or {}
        real = str(laser_doc.get("backend", "")).startswith("sepia") and self.laser_kind == "auto"
        sepia_ok, sepia_why = self._sepia_status(fresh=True) if real else (True, "")
        if laser_doc and not self.laser_connected and not sepia_ok:
            # the file is for the Sepia II: never stand the simulated laser in for it
            notes.append(tr("Laser not connected: {why}").format(why=sepia_why))
        elif laser_doc and not self.laser_connected:
            self._progress(0.6, tr("Connecting the laser…"))
            if not self.connect_laser():
                notes.append(tr("Laser not connected: {why}").format(
                    why=self.laser_detail or self.laser_text))
        if isinstance(doc.get("scanner"), dict) and getattr(self, "scanner", None) is None:
            # the sample scanner: opening it moves nothing
            self._progress(0.65, tr("Connecting the scanner…"))
            self.scanner_section = dict(doc["scanner"])
            if not self.connect_scanner(doc["scanner"]):
                notes.append(self.scanner_text)
        if doc.get("shutters") and self.shutters is None:
            self._progress(0.7, tr("Connecting the shutters…"))
            if not self.connect_shutters(doc["shutters"]):
                notes.append(tr("Shutters not connected: {why}").format(why=self.shutter_text))
        self._progress(0.8, tr("Applying the settings…"))
        try:
            notes += settings_file.apply(
                doc, device=self.device, laser=self.laser if self.laser_connected else None
            )
        except Exception as exc:  # noqa: BLE001 - the form holds them; the hardware said no
            notes.append(str(exc))
        if self.laser_connected and doc.get("laser"):
            self.laser_applied = not any("laser" in n.lower() for n in notes)
            self._laser_status()
        self.settings_name = name
        self.settings_text = tr("Settings: {name}").format(name=name)
        lines = []
        if notes:
            lines.append(tr("Notes:") + "\n" + "\n".join(notes))
        if missing:
            lines.append(tr("Not recorded by the measurement:") + "\n" + "\n".join(missing))
        self.settings_detail = "\n\n".join(lines) or tr("Applied as written.")
        return True

    def _form_from(self, doc: dict) -> None:
        exp = doc.get("experiment") or {}
        if exp.get("preset"):
            self.preset = str(exp["preset"])
        if isinstance(exp.get("setup"), dict) and exp["setup"]:
            self.settings_setup = dict(exp["setup"])
            self.setup_address = SETTINGS_SETUP
        burst = exp.get("burst") or {}
        self.min_photons = int(burst.get("min_photons", self.min_photons))
        self.window_photons = int(burst.get("window_photons", self.window_photons))
        self.window_time_ms = float(burst.get("window_time_ms", self.window_time_ms))
        if exp.get("alex_period_us"):
            self.alex_period_us = float(exp["alex_period_us"])
        self.alex_windows_override = exp.get("alex_windows_s") or None
        trace = exp.get("trace") or {}
        if trace.get("window_s"):
            self.trace_window_s = float(trace["window_s"])
        if trace.get("bin_ms"):
            self.trace_bin_ms = float(trace["bin_ms"])
        if isinstance(doc.get("scan"), dict):
            self.set_scan(doc["scan"])
            self.mode = "image"
        run = doc.get("run") or {}
        if run.get("mode") in ("point", "image"):
            self.mode = run["mode"]
        if run.get("duration_s") is not None:
            self.duration_s = float(run["duration_s"])
        if run.get("name"):
            self.run_name = str(run["name"])
        if run.get("project_data") in settings_file.PROJECT_DATA:
            self.recording_store = run["project_data"]
        dev = doc.get("device") or {}
        if dev:
            # the device panel's values in phacq's names (readable sync/inputs keys translated)
            self.device_values.update(settings_file.device_settings(dev))
            if dev.get("driver") and dev.get("serial"):
                self.device_index = f"{dev['driver']}:{dev['serial']}"
            if self.device is not None:
                self._device_form_from_device()
        if doc.get("laser"):
            self.laser_program = {**self.laser_program, **doc["laser"]}
            self.laser_divider = int((self.laser_program.get("oscillator") or {}).get("divider", 1))
            self.laser_applied = False
        if doc.get("laser_custom_names"):
            if not hasattr(self, 'laser_custom_names'):
                self.laser_custom_names = {}
            self.laser_custom_names.update(doc["laser_custom_names"])
        sim = doc.get("simulator") or {}
        if sim:
            for key in ("sim_e_low", "sim_e_high", "sim_s", "sim_concentration", "sim_seed"):
                if key in sim:
                    setattr(self, key, type(getattr(self, key))(sim[key]))
            if sim.get("scheme"):
                self.sim_scheme = str(sim["scheme"])
            if isinstance(sim.get("realism"), dict):
                known = Realism.__dataclass_fields__
                self._set_realism(
                    Realism(**{k: v for k, v in sim["realism"].items() if k in known})
                )
                self.realism_preset = str(sim.get("realism_preset") or "custom")

    def form_settings(self) -> dict:
        """What the form holds, as a settings document (the device and laser sections from the
        form's fields; :meth:`current_settings` puts what the hardware reports on top)."""
        try:
            exp = self.make_experiment(self._clock()[0])
            setup, preset = exp.setup, exp.preset
        except Exception:  # noqa: BLE001 - a setup that cannot be read: saved without it
            setup, preset = None, self.preset
        experiment: dict = {
            "preset": preset,
            "burst": {
                "min_photons": int(self.min_photons),
                "window_photons": int(self.window_photons),
                "window_time_ms": float(self.window_time_ms),
            },
        }
        if setup is not None:
            experiment["setup"] = setup
        experiment["trace"] = {
            "window_s": float(self.trace_window_s),
            "bin_ms": float(self.trace_bin_ms),
        }
        if preset == "alex":
            experiment["alex_period_us"] = float(self.alex_period_us)
            if self.alex_windows_override:
                experiment["alex_windows_s"] = dict(self.alex_windows_override)
        doc = settings_file.new_settings(
            name=self.settings_name or (self.run_name or "Record"),
            device={
                "backend": "phacq",
                **(
                    {"driver": self.device_index.partition(":")[0],
                     "serial": self.device_index.partition(":")[2]}
                    if self.device_index else {}
                ),
                "settings": dict(self.device_values),
            },
            experiment=experiment,
            run={
                "duration_s": float(self.duration_s),
                "name": self.run_name,
                "project_data": self.recording_store,
                "mode": self.mode,
            },
        )
        if self.mode == "image":
            doc["scan"] = self.scan_settings().to_dict()
        if self.scanner_section:
            scanner = dict(self.scanner_section)
            if self.scanner is not None:
                from chisurf.plugins.core.acq.live.scanning import SCAN_PANEL_KEYS

                held = dict(self.scanner.device.settings())
                scanner["settings"] = {k: held[k] for k in ("learn_s", "turn_ms", "flyback_ms")
                                       if k in held and k not in SCAN_PANEL_KEYS}
            doc["scanner"] = scanner
        if self.laser_program:
            doc["laser"] = dict(self.laser_program)
        if getattr(self, "laser_custom_names", None):
            doc["laser_custom_names"] = dict(self.laser_custom_names)
        if self.source_kind == "simulator":
            doc["simulator"] = {
                "sim_e_low": float(self.sim_e_low),
                "sim_e_high": float(self.sim_e_high),
                "sim_s": float(self.sim_s),
                "sim_concentration": float(self.sim_concentration),
                "sim_seed": int(self.sim_seed),
                "scheme": self.sim_scheme,
                "realism_preset": self.realism_preset,
                "realism": self.realism().as_dict(),
            }
            if self.mode == "image":
                doc["simulator"]["imaging_sample"] = {
                    "beads": int(self.img_beads),
                    "tau_ns": [float(self.img_tau_1_ns), float(self.img_tau_2_ns)],
                    "brightness": float(self.img_brightness),
                }
        return doc

    def current_settings(self) -> dict:
        """The form's settings with what the connected device and laser report on top."""
        device = self.device
        try:
            return settings_file.capture(
                device=device,
                laser=self.laser if self.laser_connected else None,
                base=self.form_settings(),
            )
        except Exception:  # noqa: BLE001 - a driver that cannot report: the form's view
            return self.form_settings()

    def save_settings_as(self) -> None:
        """Ask where to write the settings (the window opens the save dialog)."""
        self.save_settings_requested = True

    def save_settings_to(self, path: str | Path) -> Path | None:
        path = Path(path)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        try:
            saved = settings_file.save(self.current_settings(), path)
        except Exception as exc:  # noqa: BLE001 - shown
            self.settings_text, self.settings_detail = tr("Not saved"), str(exc)
            return None
        self.settings_name = saved.name
        self.settings_text = tr("Saved settings: {name}").format(name=saved.name)
        self.settings_detail = str(saved)
        return saved

    # -- enabling, and the end of a run ----------------------------------------------------------
    def laser_settings_enabled(self, action: str) -> bool | None:
        """``enabled()`` for this panel's actions; ``None`` for actions it does not own."""
        running = self.running
        if action == "connect_laser":
            return not self.laser_connected
        if action == "disconnect_laser":
            return self.laser is not None and not running
        if action == "laser_off":
            return True
        if action == "laser_toggle":
            # off: always; on: only a connected laser with its program applied
            return self._emission_on or (self.laser_connected and self.laser_applied)
        if action == "apply_laser_program":
            return self.laser_connected
        if action == "windows_from_laser":
            return self.laser_connected and not running
        if action == "laser_emission_on":
            return self.laser_connected and self.laser_applied and not self._emission_on
        if action == "load_settings":
            return self._picked()[0] in ("setup", "profile") and not running \
                and not self.connecting
        if action == "use_measurement_settings":
            return self._picked()[0] == "photons" and not running
        if action == "use_proposed_windows":
            return bool(self.proposed_windows) and not running
        if action == "save_settings_as":
            return True
        return None

    # -- settings files from the file system (the Load … chooser) -------------------------------
    def can_load_settings_file(self) -> bool:
        """Settings application cannot race acquisition, loading or a power servo."""
        servo=getattr(self,'power_servo',None)
        return not (getattr(self,'running',False) or self.connecting
                    or getattr(self,'ui_mode','')=='guided'
                    or (servo is not None and servo.active))

    def request_settings_file(self) -> bool:
        """The *Load …* action: ask the app to open the settings file chooser.

        Sets :attr:`settings_file_requested`; the app's chooser (``gui.settings_file_dialog``)
        opens on it and clears it. Refused while a run or a load is under way and in Guided
        mode (the wizard owns the tool there) -- the flag stays unset, nothing opens.
        """
        if not self.can_load_settings_file():
            return False
        self.settings_file_requested = True
        return True

    def load_settings_path(self, path: str | Path) -> bool:
        """Read the acquisition settings at *path* and adopt them (synchronous form).

        A ``.json`` file is a settings document (:func:`settings_file.load`); anything else is
        a measurement -- a ``.ptu`` file or a PTU member ``file.pto/member.ptu`` of a ``.pto``
        container (recovered as a whole container through the same route) -- whose header is
        recovered (:func:`settings_file.from_address`). Other file types are refused outright.
        The document is validated first, then adopted with the existing
        :meth:`adopt_settings` semantics (it fills the form and connects what the file names;
        the laser's emission stays off). An explicit ``storage`` section sets the local and
        archive directories, like a profile chosen in the workspace does. Refused while a run
        or a load is under way and in Guided mode.

        Scripts and tests may call this directly; the *Load …* chooser's **Open** goes through
        :meth:`load_settings_path_async` so the render frame never blocks on a device open.
        """
        path = Path(path)
        if not self.can_load_settings_file():
            return False
        return self._adopt_settings_path(path)

    def load_settings_path_async(self, path: str | Path) -> bool:
        """The chooser's **Open**: adopt the picked file in a worker thread.

        Same contract as :meth:`settings_chosen`: opening a device takes seconds, so the
        adoption (and its progress) run off the render frame with :attr:`connecting` set,
        which also keeps every settings action refused while it runs.
        """
        import threading

        path = Path(path)
        if not self.can_load_settings_file():
            return False
        self.connecting = True
        self._progress(0.0, tr("Reading the settings…"))

        def work():
            try:
                self._adopt_settings_path(path)
            except Exception as exc:  # noqa: BLE001 - shown; the form keeps what it had
                self.settings_text, self.settings_detail = tr("Not loaded"), str(exc)
            finally:
                self.connecting = False
                self._progress(None, "")

        self._connect_thread = threading.Thread(target=work, name="record-load-settings-file",
                                                daemon=True)
        self._connect_thread.start()
        return True

    def _adopt_settings_path(self, path: Path) -> bool:
        """(unguarded body of :meth:`load_settings_path`): read, validate, adopt."""
        if path.suffix.lower() not in (".json", ".ptu", ".pto"):
            self.settings_text = tr("Unsupported file type")
            self.settings_detail = (f"{path.name}: choose a .json settings file or a "
                                    ".ptu/.pto measurement. Other files are not opened.")
            return False
        try:
            missing: list[str] = []
            if path.suffix.lower() == ".json":
                doc = settings_file.load(path)
            else:
                doc, missing = settings_file.from_address(str(path))
            problems = settings_file.validate(doc)
            if problems:
                raise settings_file.SettingsError(problems, str(path))
            storage = (
                StorageConfig.from_document(doc) if "storage" in doc else None
            )
            # adopt runs inside the guard: a raise here is status text, never a wedged frame
            if not self.adopt_settings(doc, path.name, missing):
                return False
        except (settings_file.SettingsError, StorageConfigError) as exc:
            self.settings_text, self.settings_detail = tr("Not a settings file"), str(exc)
            return False
        except Exception as exc:  # noqa: BLE001 - shown: an unreadable container or header
            self.settings_text, self.settings_detail = tr("No settings in it"), str(exc)
            return False
        if storage is not None and getattr(self, '_instrument_sim', None) is None:
            self.output_dir = Path(storage.local_directory)
            self.archive_directory = storage.archive_directory
        elif storage is not None:
            self.settings_detail += tr(' Profile storage is not used during simulation.')
        #: where this file came from (the workspace pick in :attr:`settings_address` is not it)
        self.settings_file_path = str(path)
        self.settings_address = ''
        return True
