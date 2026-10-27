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

#: ``setup_address`` of the channel setup a settings document brought.
SETTINGS_SETUP = "settings"
_OUTPUTS = laser_mod.SEQUENCER_OUTPUTS


def _short(problems: list[str], n: int = 3) -> str:
    return "; ".join(problems[:n]) + (f" (+{len(problems) - n})" if len(problems) > n else "")


class LaserSettingsMixin:
    """Laser control and acquisition settings files for the Record model."""

    def _init_laser_settings(self) -> None:
        self.laser_kind = "auto"
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

    def _sepia_status(self) -> tuple[bool, str]:
        """Whether a Sepia II is there, checked at most every two seconds and never while a laser
        is connected (an options list is drawn every frame; enumerating USB on each would stall
        the window, and must not touch a unit this tool is driving)."""
        if self.laser_connected:
            return True, getattr(self, "_sepia_seen", (True, ""))[1]
        now = time.monotonic()
        if now - getattr(self, "_sepia_at", -1e9) > 2.0:
            self._sepia_at = now
            self._sepia_seen = laser_mod.sepia_available()
        return self._sepia_seen

    def laser_options(self) -> list:
        ok, why = self._sepia_status()
        sepia = tr("Sepia II") if ok else tr("Sepia II (not available)")
        self._sepia_reason = "" if ok else why
        return [
            ("auto", tr("Auto (Sepia II, else simulated)")),
            ("sepia", sepia),
            ("simulated", tr("Simulated laser")),
        ]

    def _new_laser(self) -> laser_mod.LaserBackend:
        if self.laser_kind == "simulated" or (
            self.laser_kind == "auto" and not self._sepia_status()[0]
        ):
            # the simulated driver pulses in step with the simulated measurement (one pulse per
            # half period: PIE)
            n_micro, res = self._clock()
            return laser_mod.SimLaser(base_hz=2.0 / (n_micro * res))
        return laser_mod.open_laser(self.laser_kind)

    def connect_laser(self) -> bool:
        if self.laser_connected:
            return False
        if self.laser_kind in ("sepia", "sepia2"):
            self._sepia_at = -1e9  # look again now
            ok, why = self._sepia_status()
            if not ok:
                self.laser_text, self.laser_detail = tr("Sepia II not available"), why
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
                                                on_change=self.laser_settings_edited, folded=False)

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
        self.status_text = tr("Windows from the laser")
        self.status_detail = ", ".join(f"{k} {v[0]}–{v[1]}" for k, v in patch["windows"].items())
        return True

    def use_proposed_windows(self) -> bool:
        if not self.proposed_windows:
            return False
        self.window_override = dict(self.proposed_windows)
        self.status_text = tr("Windows from the measurement")
        self.status_detail = ", ".join(
            f"{k} {v[0]}–{v[1]}" for k, v in self.window_override.items()
        )
        return True

    def windows_patched(self, setup: dict) -> dict:
        """*setup* with :attr:`window_override` merged into its windows."""
        if not self.window_override:
            return setup
        return {**setup, "windows": {**(setup.get("windows") or {}), **self.window_override}}

    # -- settings files ----------------------------------------------------------------------------
    def settings_options(self) -> list:
        now = time.monotonic()
        if now - getattr(self, "_settings_rows_at", -1e9) > 2.0:
            self._settings_rows_at = now
            rows = [("", tr("Choose settings or a measurement"))]
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

    def load_settings(self) -> bool:
        """Read the chosen settings row and send it to the device and the laser."""
        kind, address = self._picked()
        if kind != "setup":
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
        self._form_from(doc)
        notes: list[str] = []
        try:
            notes = settings_file.apply(
                doc, device=self.device, laser=self.laser if self.laser_connected else None
            )
        except Exception as exc:  # noqa: BLE001 - the form holds them; the hardware said no
            notes = [str(exc)]
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
        if self.laser_program:
            doc["laser"] = dict(self.laser_program)
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
        if action in ("apply_laser_program", "windows_from_laser"):
            return self.laser_connected and not running
        if action == "laser_emission_on":
            return self.laser_connected and self.laser_applied and not self._emission_on
        if action == "load_settings":
            return self._picked()[0] == "setup" and not running
        if action == "use_measurement_settings":
            return self._picked()[0] == "photons" and not running
        if action == "use_proposed_windows":
            return bool(self.proposed_windows) and not running
        if action == "save_settings_as":
            return True
        return None
