"""The Record tool: measure, watch the burst histograms build up, keep the run in the project.

``record.view.json`` declares every control; :class:`RecordModel` is its model and owns the
:class:`~chisurf.plugins.core.acq.live.session.RecordSession` of a run. The analysis runs in the
session's worker thread; the window takes a snapshot of its accumulators about five times a second
and draws from that (:meth:`RecordApp._draw_live`), never from photons. The measurement type is
the Experiment setup's preset (single colour, two colour, PIE, µs-ALEX, MFD, three-colour PIE); the
histograms shown are the ones the analyzer keeps for it.

Devices are libphacq's (``live.devices``): PicoQuant MultiHarp / PicoHarp 330 / HydraHarp 500 and
Becker & Hickl SPC cards, natively. Their settings panel is generated from what the connected
device describes (``Device.parameter_schema``), so every setting the driver has is offered; the
Sepia II laser likewise (``live.laser``). The simulator is tttrlib's photon-level simulator.

Image mode scans with the sample scanner of the settings file (the MT200's PI E-725 through
libphacq) while the device records the scanner's line markers, or with the simulated scanner; on
the image the user picks molecules (a click, or *Auto-pick* with the spot finder's single-molecule
workflow) and measures them one by one (``record_points``).
"""

from __future__ import annotations

import json
import time
from dataclasses import fields as _fields
from dataclasses import replace as _replace
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im
from emtk import style as _style
from emtk.app import ImApp
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.core.acq.gui.record_points import ScanPointsMixin
from chisurf.plugins.core.acq.gui.record_settings import SETTINGS_SETUP, LaserSettingsMixin
from chisurf.plugins.core.acq.gui.record_survey import SurveyMixin, draw_survey_map
from chisurf.plugins.core.acq.gui.record_windows import WindowCheckMixin
from chisurf.plugins.core.acq.live import devices
from chisurf.plugins.core.acq.live.analyzer import PRESETS
from chisurf.plugins.core.acq.live.fcs import (
    FcsRecordSession,
    fcs_realism,
    fcs_truth,
    population_for,
)
from chisurf.plugins.core.acq.live.imaging import (
    ImageRecordSession,
    image_replay_source,
    scan_of_file,
)
from chisurf.plugins.core.acq.live.project import recording_dir, workspace_datasets
from chisurf.plugins.core.acq.live.realism import PRESETS as REALISM_PRESETS
from chisurf.plugins.core.acq.live.realism import REALISTIC, Realism
from chisurf.plugins.core.acq.live.scanner import (
    ImageSimSource,
    ImagingSample,
    ScanSettings,
)
from chisurf.plugins.core.acq.live.session import RecordSession
from chisurf.plugins.core.acq.live.window_check import convert_setup_windows
from chisurf.plugins.core.acq.live.setups import (
    PRESET_LABELS,
    BurstParameters,
    Experiment,
    default_setup,
    infer_preset,
)
from chisurf.plugins.core.acq.live.sources import (
    FileReplaySource,
    Population,
    SimulatedPieSource,
    SourceUnavailable,
)

HERE = Path(__file__).resolve().parent
DEFAULT_SETUP = "default"
AUTO_PRESET = "auto"
#: How often the window takes a snapshot of the session's accumulators. A snapshot costs well under a
#: millisecond, so the plots follow the measurement at display rate (at most 30 times a second)
#: instead of jumping every 200 ms.
SNAPSHOT_INTERVAL_S = 1.0 / 30.0
_COLOURS = [
    (0.17, 0.63, 0.17, 1.0),
    (0.84, 0.15, 0.16, 1.0),
    (0.58, 0.40, 0.74, 1.0),
    (0.12, 0.47, 0.71, 1.0),
    (0.9, 0.6, 0.1, 1.0),
    (0.4, 0.4, 0.4, 1.0),
]


def _workspace(kind: str) -> list[Any]:
    return workspace_datasets(kind)


class RecordModel(LaserSettingsMixin, ScanPointsMixin, SurveyMixin, WindowCheckMixin):
    """The state behind ``record.view.json``.

    Parameters
    ----------
    output_dir : str or Path, optional
        Where recordings are written; the acquisition output folder by default.
    realtime : bool
        ``False`` lets simulated and replayed photons arrive as fast as they are made (tests).
    """

    def __init__(self, output_dir: str | Path | None = None, *, realtime: bool = True):
        from chisurf.plugins.core.acq.output_paths import default_acquisition_output_path

        self.output_dir = Path(output_dir or default_acquisition_output_path())
        self.realtime = bool(realtime)
        self.source_kind = "simulator"
        self.sim_e_low = 0.2
        self.sim_e_high = 0.8
        self.sim_s = 0.5
        self.sim_concentration = 1.0
        self.sim_seed = 1
        self.replay_address = ""
        self.speed = 1.0
        self.setup_address = DEFAULT_SETUP
        self.sim_scheme = "pie"
        self.preset = AUTO_PRESET
        self.alex_period_us = 100.0
        self.plot_choice = ""
        # -- Point (smFRET) or Image (a scan) -------------------------------------------------
        self.mode = "point"
        #: Advanced: show the device's thresholds, shifts, timing and markers. Off by default:
        #: a settings file or profile sets them, and a stray edit spoils a calibrated setup.
        self.advanced = False
        # -- the simulated FCS sample: one diffusing species with a known answer -----------------
        self.fcs_n = 4.0
        self.fcs_d_um2_per_s = 80.0
        self.fcs_brightness_khz = 150.0
        self.set_scan(ScanSettings())
        self.img_beads = 24
        self.img_tau_1_ns = 1.0
        self.img_tau_2_ns = 3.5
        self.img_brightness = 40.0
        #: the simulated specimen: beads on a cell, or single molecules on a coverslip
        self.img_sample = "beads"
        #: mean bleaching time of a simulated emitter under the parked focus (s)
        self.img_bleach_s = 3.0
        self.image_map = "Intensity"
        #: the scan of the image file a replay plays (read from its header)
        self.replay_scan: ScanSettings | None = None
        # -- the running smFRET trace: the last trace_window_s seconds in trace_bin_ms bins
        self.trace_window_s = 1.0
        self.trace_bin_ms = 1.0
        # -- realism of the simulated measurement (live.realism): Realistic unless chosen otherwise
        self.realism_preset = "realistic"
        self._set_realism(REALISTIC)
        #: a fresh recording is stored in the project (Embed) unless the user links it
        self.recording_store = "embed"
        self.saved_path: Path | None = None
        self.min_photons = 30
        self.window_photons = 10
        self.window_time_ms = 1.0
        self.duration_s = 60.0
        self.run_name = ""
        self.status_text = tr("Ready")
        self.status_detail = tr("Press Load example, then Start.")
        self.session: RecordSession | None = None
        self.snapshot: dict[str, Any] | None = None
        self._last_snapshot = 0.0
        self._registered = False
        # -- the TCSPC device (libphacq) ----------------------------------------------------------
        #: ``driver:serial`` of the chosen device
        self.device_index = ""
        self.device = None
        self._found: list = []
        self._found_at = -1e9
        self.device_text = tr("No device connected.")
        self._rates_at = 0.0
        #: the device settings the panel edits, phacq's flat ``{name or name[input]: value}``;
        #: kept while disconnected (a settings file can bring them before the device is there)
        self.device_values: dict[str, Any] = {}
        #: the generated settings form of the connected device (``devices.settings_form``)
        self.device_form = None
        self._device_sent: dict[str, Any] = {}
        # -- the laser and the acquisition settings file (record_settings) --------------------
        self._init_laser_settings()
        self._init_window_check()
        # -- the scanner, the picked points and their measurements (record_points) ------------
        self._init_scan_points()
        # -- the survey: tile after tile, picked and measured (record_survey) -------------------
        self._init_survey()

    # -- point or image ---------------------------------------------------------------------------
    _SCAN_FIELDS = ("pixels_x", "pixels_y", "area_x_um", "area_y_um", "x0_um", "y0_um",
                    "dwell_ms", "frames", "bidirectional", "z_planes", "z_step_um")

    def mode_options(self) -> list:
        return [
            ("point", tr("Point (smFRET)")),
            ("fcs", tr("FCS (point)")),
            ("image", tr("Image (scan)")),
        ]

    def mode_changed(self, _value=None) -> None:
        """A mode's sources differ: a replay must pick a file of the new kind again."""
        self.replay_address = ""
        self.replay_scan = None
        self.status_text = tr("Ready")
        self.status_detail = (
            tr("Press Load example, then Start: a simulated scan builds up line by line.")
            if self.mode == "image"
            else tr("Press Load example, then Start: the correlation curve builds up.")
            if self.mode == "fcs"
            else tr("Press Load example, then Start.")
        )

    def set_scan(self, scan) -> None:
        """Put a scan (ScanSettings or its document) into the form."""
        scan = scan if isinstance(scan, ScanSettings) else ScanSettings.from_dict(scan)
        for name in self._SCAN_FIELDS:
            setattr(self, f"scan_{name}", getattr(scan, name))

    def scan_settings(self) -> ScanSettings:
        """The scan: the replayed file's, else the form's."""
        if self.source_kind == "replay" and self.replay_scan is not None:
            return self.replay_scan
        return ScanSettings(**{name: getattr(self, f"scan_{name}") for name in self._SCAN_FIELDS})

    def replay_changed(self, _value=None) -> None:
        """Another file to replay: its scan is read again when needed."""
        self.replay_scan = None

    def scan_summary(self) -> tuple[str, str]:
        """A few words on the scan, details for the tooltip."""
        if self.source_kind == "replay":
            if not self.replay_address:
                return tr("Pick an image to replay"), ""
            if self.replay_scan is None:
                scan, missing = scan_of_file(self.replay_address)
                if scan is None:
                    return tr("Not an image"), "; ".join(missing)
                self.replay_scan = scan
        scan = self.scan_settings()
        text = tr("{nx} × {ny} px · {t:.2f} s per frame").format(
            nx=scan.nx, ny=scan.ny, t=scan.frame_s
        )
        detail = tr(
            "{w:.1f} × {h:.1f} µm, dwell {dwell:.3f} ms, {frames} frame(s), {planes} plane(s), "
            "{direction}; markers: line start {ls}, line stop {le}, frame {fr}"
        ).format(
            w=scan.area_x_um, h=scan.area_y_um, dwell=scan.dwell_ms, frames=scan.frames,
            planes=scan.z_planes, direction=tr("bidirectional") if scan.bidirectional else
            tr("one direction"), ls=scan.line_start_marker, le=scan.line_stop_marker,
            fr=scan.frame_marker or tr("none"),
        )
        return text, detail

    def image_map_options(self) -> list:
        names = list(((self.snapshot or {}).get("images") or {}).keys()) or [
            "Intensity", "Mean arrival time (ns)"
        ]
        return [(n, tr(n)) for n in names]

    def trace_changed(self, _value=None) -> None:
        """The running trace's span or bin changed: a running session starts its trace over."""
        if self.session is not None and self.mode == "point":
            self.session.set_trace(float(self.trace_window_s), float(self.trace_bin_ms) / 1e3)

    # -- options ---------------------------------------------------------------------------------
    def source_options(self) -> list:
        if self.mode == "image":
            return [
                ("simulator", tr("Simulator (scan)")),
                ("replay", tr("Replay an image")),
                ("device", tr("TCSPC device and scanner")
                 if devices.PHACQ else tr("TCSPC device and scanner (libphacq not installed)")),
            ]
        return [
            ("simulator", tr("Simulator (smFRET)")),
            ("replay", tr("Replay a photon stream")),
            (
                "device",
                tr("TCSPC device (PicoQuant, Becker & Hickl)")
                if devices.PHACQ
                else tr("TCSPC device (libphacq not installed)"),
            ),
        ]

    # -- realism ---------------------------------------------------------------------------------
    _REALISM_FIELDS = tuple(
        f.name for f in _fields(Realism) if f.name not in ("name", "ideal", "acceptor_recover_per_ms",
                                                          "irf_tail_fraction", "irf_tail_ns", "jitter_donor_ns",
                                                          "jitter_acceptor_ns", "scatter_acceptor_khz",
                                                          "afterpulse_delay_us", "aggregate_brightness", "beta",
                                                          "focus_w0_um", "focus_z0_um")
    )  # fmt: skip

    def _set_realism(self, realism: Realism) -> None:
        for name in self._REALISM_FIELDS:
            setattr(self, f"real_{name}", getattr(realism, name))

    def realism_options(self) -> list:
        return [
            ("realistic", tr("Realistic")),
            ("ideal", tr("Ideal (no imperfections)")),
            ("custom", tr("Custom")),
        ]

    def apply_realism_preset(self, value: str) -> None:
        if value in REALISM_PRESETS:
            self._set_realism(REALISM_PRESETS[value])

    def realism_edited(self, _value=None) -> None:
        self.realism_preset = "custom"

    def realism(self) -> Realism:
        """The imperfections the simulator adds (the preset's, or the edited values)."""
        if self.realism_preset in REALISM_PRESETS:
            return REALISM_PRESETS[self.realism_preset]
        edited = {name: float(getattr(self, f"real_{name}")) for name in self._REALISM_FIELDS}
        return _replace(REALISTIC, name="custom", **edited)

    def store_options(self) -> list:
        return [("embed", tr("Embed in the project")), ("link", tr("Link to the file"))]

    def scheme_options(self) -> list:
        return [
            ("pie", tr("PIE (green and red pulses)")),
            ("two_color", tr("Two colour (green laser only)")),
        ]

    def preset_options(self) -> list:
        return [(AUTO_PRESET, tr("From the setup"))] + [(p, tr(PRESET_LABELS[p])) for p in PRESETS]

    def plot_options(self) -> list:
        names = list((self.snapshot or {}).get("histograms", {}).keys())
        return [(n, n) for n in names] or [("", tr("Start a run: its histograms appear here"))]

    def attached(self) -> list:
        """The attached devices, enumerated at most every two seconds (not on every frame)."""
        if self.device is not None:  # never enumerate (open) units while one is driven
            return self._found
        now = time.monotonic()
        if now - self._found_at > 2.0:
            self._found, self._found_at = devices.attached_devices(), now
        return self._found

    def device_options(self) -> list:
        found = self.attached()
        if not found:
            return [
                (
                    "",
                    tr("No TCSPC device found")
                    if devices.PHACQ
                    else tr("libphacq is not installed"),
                )
            ]
        return [(e.key, e.label) for e in found]

    @property
    def sync_offset_ps(self) -> float:
        """The sync channel offset the device applies (ps; 0 where it has none)."""
        return float(self.device_values.get("sync_offset_ps") or 0)

    @property
    def device_form_hidden(self) -> bool:
        """The device's settings form is shown for a device source in Advanced only."""
        return self.source_kind != "device" or not self.advanced

    # -- the device --------------------------------------------------------------------------------
    def connect_device(self) -> bool:
        if self.device is not None or not devices.PHACQ:
            return False
        entry = devices.find_device(self.device_index)
        if entry is None:
            self.device_text = tr("Cannot connect: the device is not attached any more.")
            return False
        try:
            dev = devices.open_device(entry)
        except Exception as exc:  # noqa: BLE001 - busy, no permission, unsupported model
            self.device_text = tr("Cannot connect: {e}").format(e=exc)
            return False
        self.device = dev
        self.device_index = entry.key
        notes = devices.apply_settings(dev, self.device_values) if self.device_values else []
        self._device_form_from_device()
        info = dev.information()
        self.device_text = tr("{name}, {n} inputs.").format(
            name=devices.device_label(dev), n=info.number_of_channels
        )
        if notes:
            self.device_text += " " + tr("Not applied: {notes}").format(notes="; ".join(notes))
        self._update_rates(force=True)
        return True

    def _device_form_from_device(self) -> None:
        """Re-read every setting from the device and rebuild its form."""
        self.device_values = dict(self.device.settings())
        self._device_sent = dict(self.device_values)
        self.device_form = devices.settings_form(
            self.device, self.device_values, on_change=self.device_settings_edited
        )

    def device_settings_edited(self) -> None:
        """An edit in the device settings form: send what changed (between runs only)."""
        if self.device is None or self.device_form is None:
            return
        values = self.device_form.params()
        changed = {k: v for k, v in values.items() if self._device_sent.get(k) != v}
        self.device_values.update(values)
        if not changed or self.running:
            return
        notes = devices.apply_settings(self.device, changed)
        head = self.device_text.split(" — ")[0]
        if notes:
            # nothing of the edit reached the device: show the device's values again
            self.device_text = f"{head} — " + "; ".join(notes)
            self._device_form_from_device()
            return
        # the panel follows the device (read-only and derived values included), in place
        self.device_values = dict(self.device.settings())
        self._device_sent = dict(self.device_values)
        self.device_form.update_values(self.device_values)
        self.device_text = head

    def disconnect_device(self) -> bool:
        if self.device is None or self.running:
            return False
        try:
            self.device.close()
        finally:
            self.device = None
            self.device_form = None
            self.device_text = tr("No device connected.")
        return True

    def apply_device_settings(self, dev, exp: Experiment) -> None:
        """Send every device setting the panel holds to *dev* (before a run)."""
        notes = devices.apply_settings(dev, self.device_values)
        if notes:
            raise RuntimeError("; ".join(notes))
        self._device_sent = dict(self.device_values)

    def _update_rates(self, force: bool = False) -> None:
        """Count rates of the connected device while it does not measure (about once a second)."""
        if self.device is None or self.running:
            return
        now = time.monotonic()
        if not force and now - self._rates_at < 1.0:
            return
        self._rates_at = now
        try:
            rates = list(self.device.count_rates())
        except Exception as exc:  # noqa: BLE001 - shown, the device stays connected
            self.device_text = (
                self.device_text.split(" — ")[0] + " — " + tr("rates: {e}").format(e=exc)
            )
            return
        head = self.device_text.split(" — ")[0]
        if not rates:
            self.device_text = head
            return
        if getattr(self.device, "phacq_driver", "") == "bh":  # sync, CFD, TAC, ADC
            names = (tr("sync"), tr("CFD"), tr("TAC"), tr("ADC"))
            text = ", ".join(f"{n} {r / 1e3:.1f} kHz" for n, r in zip(names, rates))
        else:  # sync, then the inputs
            inputs = ", ".join(f"{i + 1}: {r / 1e3:.1f} kHz" for i, r in enumerate(rates[1:]))
            text = tr("sync {sync:.2f} MHz; inputs {rates}").format(
                sync=rates[0] / 1e6, rates=inputs
            )
        self.device_text = f"{head} — {text}"

    def photon_options(self) -> list:
        kind = "image" if self.mode == "image" else "photons"
        rows = [
            (str(d.address), str(getattr(d, "name", "") or d.address)) for d in _workspace(kind)
        ]
        empty = tr("No image in the workspace") if kind == "image" else tr(
            "No photon stream in the workspace"
        )
        return rows or [("", empty)]

    def setup_options(self) -> list:
        rows = [
            (str(d.address), str(getattr(d, "name", "") or d.address)) for d in _workspace("setup")
        ]
        loaded = (
            [(SETTINGS_SETUP, tr("From settings: {name}").format(name=self.settings_name))]
            if self.settings_setup is not None
            else []
        )
        return (
            [
                (
                    DEFAULT_SETUP,
                    tr("Default for the type (channel 0 donor, 1 acceptor; PIE: half periods)"),
                )
            ]
            + loaded
            + rows
        )

    # -- what the run uses -----------------------------------------------------------------------
    def make_image_source(self):
        """The photons and markers of a scan: a simulated scan (a simulated MultiHarp with a
        simulated scanner), or an image file of the workspace replayed."""
        if self.source_kind == "replay":
            if not self.replay_address:
                raise SourceUnavailable(tr("Choose an image of the workspace first."))
            source, scan = image_replay_source(
                self.replay_address, speed=float(self.speed), realtime=self.realtime
            )
            self.replay_scan = scan
            return source
        scan = self.scan_settings()
        problems = scan.validate()
        if problems:
            raise SourceUnavailable("; ".join(problems))
        if self.source_kind == "device":
            # the device records the scanner's line markers; the scanner rasters (live.scanning)
            from chisurf.plugins.core.acq.live.scanning import (
                ScannedSource, line_markers, scanner_scan)

            if self.device is None:
                raise SourceUnavailable(tr("Connect the device first."))
            if self.scanner is None:
                raise SourceUnavailable(tr("Connect the scanner first (a settings file with a "
                                           "scanner section connects it)."))
            try:
                markers = line_markers(self.scanner_section)
            except ValueError as exc:
                raise SourceUnavailable(str(exc)) from exc
            return ScannedSource(devices.DeviceSource(self.device), self.scanner,
                                 scanner_scan(scan, markers))
        return ImageSimSource(
            scan, self.imaging_sample(), self.realism(), speed=float(self.speed),
            realtime=self.realtime
        )

    def img_sample_options(self) -> list:
        return [("beads", tr("Beads on a cell")),
                ("molecules", tr("Single molecules (some pairs)"))]

    def imaging_sample(self) -> ImagingSample:
        """The simulated specimen the Scan panel describes (a running survey's: one sample fixed
        on the stage over the surveyed area)."""
        if self._survey_sample is not None:
            return self._survey_sample
        taus = (float(self.img_tau_1_ns), float(self.img_tau_2_ns))
        if self.img_sample == "molecules":
            sample = ImagingSample.single_molecules(
                int(self.img_beads), brightness=float(self.img_brightness),
                seed=int(self.sim_seed), tau_ns=taus)
            # a few spots hold two molecules: they bleach in two steps
            sample.per_spot = (1, 3)
            return sample
        return ImagingSample(n_beads=int(self.img_beads), tau_ns=taus,
                             bead_brightness=float(self.img_brightness), seed=int(self.sim_seed))

    def fcs_sample(self) -> tuple[Realism, float]:
        """The simulated FCS sample: its realism (the instrument's, no FRET extras) and the
        simulator's population that puts ``fcs_n`` molecules in the focus."""
        real = fcs_realism(self.realism(), float(self.fcs_d_um2_per_s))
        return real, population_for(float(self.fcs_n), real)

    def make_source(self):
        if self.mode == "image":
            return self.make_image_source()
        if self.source_kind == "simulator":
            scheme, realism = self.sim_scheme, self.realism()
            pops = (
                Population(self.sim_e_low, self.sim_s, self.sim_concentration),
                Population(self.sim_e_high, self.sim_s, self.sim_concentration),
            )
            if self.mode == "fcs":
                # one species in the green channel (E = 0), green laser only
                realism, population = self.fcs_sample()
                pops = (Population(0.0, 1.0, population, float(self.fcs_brightness_khz)),)
                scheme = "two_color"
            return SimulatedPieSource(
                pops,
                duration_s=None,
                seed=int(self.sim_seed),
                speed=float(self.speed),
                realtime=self.realtime,
                scheme=scheme,
                realism=realism,
            )
        if self.source_kind == "replay":
            if not self.replay_address:
                raise SourceUnavailable(tr("Choose a photon stream of the workspace first."))
            return FileReplaySource(
                self.replay_address, speed=float(self.speed), realtime=self.realtime
            )
        if not devices.PHACQ:
            raise SourceUnavailable(tr("TCSPC devices need libphacq, which is not installed."))
        if self.device is None:
            raise SourceUnavailable(tr("Connect the device first."))
        return devices.DeviceSource(self.device)

    def _default_preset(self) -> str:
        if self.mode == "fcs" and self.source_kind == "simulator":
            return "two_color"  # the FCS sample is simulated under the green laser only
        if self.source_kind == "simulator":
            return self.sim_scheme
        return "pie"

    def make_experiment(self, n_micro: int, micro_res_s: float | None = None) -> Experiment:
        """The setup (workspace row or the type's default) read with the chosen preset.

        With *micro_res_s* (the device's channel width) a setup whose windows were defined at
        another resolution or binning (its ``tttr_reading.micro_time_resolution``) has them
        converted to the device's channels -- the same nanoseconds -- instead of applied as raw
        channel numbers of another instrument.
        """
        burst = BurstParameters(
            int(self.min_photons), int(self.window_photons), float(self.window_time_ms) / 1e3
        )
        if self.setup_address in ("", DEFAULT_SETUP):
            preset = self.preset if self.preset != AUTO_PRESET else self._default_preset()
            setup, name = default_setup(preset, n_micro), f"default {preset}"
            if self.window_override and preset in ("pie", "three_color_pie"):
                label = getattr(self, "window_override_label", "") or "windows from the laser"
                setup, name = self.windows_patched(setup), f"{name}, {label}"
            realism = self.realism()
            if self.source_kind == "simulator" and not realism.ideal:
                # the simulated instrument is calibrated: its factors give corrected E and S
                setup = {**setup, "corrections": realism.factors()}
        else:
            if self.setup_address == SETTINGS_SETUP and self.settings_setup is not None:
                setup, name = dict(self.settings_setup), self.settings_name
            else:
                from chisurf.plugins.tttr.workspace_io import read_setup

                setup, name = read_setup(self.setup_address), Path(self.setup_address).name
            if micro_res_s:
                setup, note = convert_setup_windows(setup, float(micro_res_s))
                name = f"{name}, {note}" if note else name
            setup = self.windows_patched(setup)
            preset = self.preset if self.preset != AUTO_PRESET else infer_preset(setup)
        return Experiment(
            setup,
            preset,
            burst,
            name=name,
            alex_period_s=float(self.alex_period_us) * 1e-6 if preset == "alex" else None,
            alex_windows_s=(getattr(self, "alex_windows_override", None)
                            if preset == "alex" else None),
        )

    def setup_summary(self) -> tuple[str, str]:
        """A few words on the setup, and its details for the tooltip."""
        if self.session is None:
            try:
                n_micro, res = self._clock()
            except Exception:  # noqa: BLE001 - a device that cannot report: no conversion
                n_micro, res = 400, None
        else:
            n_micro, res = self.session.source.info.n_micro, self.session.source.info.micro_res_s
        try:
            exp = self.make_experiment(n_micro, res)
        except Exception as exc:  # noqa: BLE001 - shown, the run refuses to start
            return tr("Setup cannot be used"), str(exc)
        label = tr(PRESET_LABELS[exp.preset]).split(" (")[0]
        corrected = (
            tr("corrected") if (exp.factors() and exp.preset in ("pie", "alex")) else tr("raw")
        )
        source = getattr(self, "window_override_label", "") or tr("laser windows")
        windows = f" · {source}" if self.window_override else ""
        return f"{label} · {corrected}{windows}", exp.describe()

    # -- actions ---------------------------------------------------------------------------------
    @property
    def busy(self) -> bool:
        """A recording or a point sequence is under way (a survey runs them one after another)."""
        return (self.session is not None and self.session.running) or self.points_running

    @property
    def running(self) -> bool:
        return self.busy or self.survey_active

    def _run_shutters(self, start: bool) -> None:
        """A run's shutters: opened at its start, closed at its end -- once for a whole survey,
        which opens them when it starts and closes them when it ends."""
        if self.survey_active:
            return
        if start:
            self._shutters_at_start()
        else:
            self._shutters_at_end()

    def enabled(self, action: str) -> bool:
        mine = self.laser_settings_enabled(action)
        if mine is not None:
            return mine
        mine = self.points_enabled(action)
        if mine is not None:
            return mine
        mine = self.survey_enabled(action)
        if mine is not None:
            return mine
        mine = self.window_check_enabled(action)
        if mine is not None:
            return mine
        if action == "start":
            if self.mode == "image" and self.source_kind == "device" and self.scanner is None:
                return False  # a real scan needs the scanner
            return not self.running and (self.source_kind != "device" or self.device is not None)
        if action == "connect_device":
            return devices.PHACQ and self.device is None and bool(self.attached()) \
                and not self.connecting
        if action == "disconnect_device":
            return self.device is not None and not self.running
        if action == "stop":
            return self.running
        if action == "load_example":
            return not self.running
        return True

    def load_example(self) -> None:
        if self.mode == "fcs":
            self.source_kind = "simulator"
            self.fcs_n, self.fcs_d_um2_per_s, self.fcs_brightness_khz = 4.0, 80.0, 150.0
            self.duration_s = 30.0
            self.realism_preset = "realistic"
            self._set_realism(REALISTIC)
            self.status_text = tr("Example ready")
            self.status_detail = tr(
                "FCS: one freely diffusing dye, N ≈ 4 in the focus, D = 80 µm²/s "
                "(τD ≈ 0.28 ms), 150 kHz per molecule. Press Start."
            )
            return
        if self.mode == "image":
            self.source_kind = "simulator"
            # Nyquist-sampled: 100 nm pixels under the simulator's 0.25 um (1/e^2) focus, so an
            # FRC of the recording has a crossing to find; 4 frames give two even/odd halves.
            self.set_scan(ScanSettings(pixels_x=64, pixels_y=64, area_x_um=6.4, area_y_um=6.4,
                                       x0_um=10.0, y0_um=10.0, dwell_ms=0.1, frames=4))
            self.img_sample, self.img_beads = "molecules", 16
            self.img_tau_1_ns, self.img_tau_2_ns = 1.0, 3.5
            self.img_brightness, self.img_bleach_s = 60.0, 1.5
            self.point_time_s, self.until_bleached = 5.0, True
            self.realism_preset = "realistic"
            self._set_realism(REALISTIC)
            self.status_text = tr("Example ready")
            self.status_detail = tr(
                "A simulated scan of single molecules (a few spots hold two) with lifetimes of "
                "1.0 and 3.5 ns, 64 × 64 pixels of 100 nm, 4 frames. Press Start, then Auto-pick "
                "and Measure points."
            )
            return
        self.source_kind = "simulator"
        self.sim_e_low, self.sim_e_high, self.sim_s = 0.2, 0.8, 0.5
        self.sim_concentration = 1.0
        self.min_photons, self.window_photons, self.window_time_ms = 30, 10, 1.0
        self.setup_address = DEFAULT_SETUP
        self.sim_scheme, self.preset = "pie", AUTO_PRESET
        self.duration_s = 60.0
        self.realism_preset = "realistic"
        self._set_realism(REALISTIC)
        self.status_text = tr("Example ready")
        self.status_detail = tr(
            "PIE, two FRET populations (E 0.2 and 0.8, S 0.5) in a realistic sample: donor-only and "
            "acceptor-only molecules, bleaching, crosstalk, background. Press Start."
        )

    def start(self) -> bool:
        if self.busy:
            return False
        try:
            if self.source_kind == "device" and self.device is not None:
                self.apply_device_settings(self.device, self.make_experiment(1))
            source = self.make_source()
            experiment = self.make_experiment(source.info.n_micro, source.info.micro_res_s)
        except Exception as exc:  # noqa: BLE001 - the user picks something else
            self.status_text = tr("Cannot start")
            self.status_detail = str(exc)
            return False
        name = self.run_name.strip().replace("{date}", time.strftime("%Y%m%d_%H%M%S"))
        name = self.unique_name(name or time.strftime("record_%Y%m%d_%H%M%S"))
        if self.mode == "image":
            return self._start_image(source, experiment, name)
        if self.mode == "fcs":
            return self._start_fcs(source, experiment, name)
        self.saved_path = recording_dir(self.output_dir) / f"{name}.ptu"
        self._run_shutters(True)
        self.session = RecordSession(
            source,
            experiment,
            duration_s=self.duration_s or None,
            ptu_path=self.saved_path,
            name=name,
            embed=self.recording_store == "embed",
            settings=self._run_settings(),
            header_tags=self.run_header_tags(),
            trace_window_s=float(self.trace_window_s),
            trace_bin_s=float(self.trace_bin_ms) / 1e3,
        )
        try:
            self.session.start()
        except OSError as exc:
            self.status_text = tr("Cannot start")
            self.status_detail = str(exc)
            self.session = None
            return False
        self._registered = False
        self.snapshot = None
        self.window_check_reset()
        self.plot_choice = ""
        self.status_text = tr("Recording…")
        self.status_detail = str(self.saved_path)
        return True

    def _start_fcs(self, source, experiment, name: str) -> bool:
        """Start an FCS point measurement: the correlation builds up; the photons are recorded."""
        self.saved_path = recording_dir(self.output_dir) / f"{name}.ptu"
        truth = None
        if self.source_kind == "simulator":
            real, population = self.fcs_sample()
            truth = fcs_truth(real, population)
        self._run_shutters(True)
        self.session = FcsRecordSession(
            source,
            experiment,
            truth=truth,
            duration_s=self.duration_s or None,
            ptu_path=self.saved_path,
            name=name,
            embed=self.recording_store == "embed",
            settings=self._run_settings(),
            header_tags=self.run_header_tags(),
            trace_window_s=float(self.trace_window_s),
            trace_bin_s=float(self.trace_bin_ms) / 1e3,
        )
        try:
            self.session.start()
        except OSError as exc:
            self.status_text = tr("Cannot start")
            self.status_detail = str(exc)
            self.session = None
            return False
        self._registered = False
        self.snapshot = None
        self.status_text = tr("Recording…")
        self.status_detail = str(self.saved_path)
        return True

    def _start_image(self, source, experiment, name: str) -> bool:
        """Start a scan: a new recording for a simulated (or real) scan; a replay analyses an
        existing image and records nothing."""
        scan = self.scan_settings()
        replay = self.source_kind == "replay"
        real = self.source_kind == "device"
        if real:
            from chisurf.plugins.core.acq.live.scanning import line_markers, scanner_scan

            try:
                markers = line_markers(self.scanner_section)
            except ValueError as exc:
                self.status_text, self.status_detail = tr("Cannot start"), str(exc)
                return False
            scan = scanner_scan(scan, markers)
            note = self._enable_line_markers(scan, rising=markers["edge"] == "rising")
            if note:
                self.status_text, self.status_detail = tr("Cannot start"), note
                return False
        self.saved_path = None if replay else recording_dir(self.output_dir) / f"{name}.ptu"
        windows = (
            dict(experiment.setup.get("windows") or {})
            if self.setup_address not in ("", DEFAULT_SETUP)
            else {}
        )
        # a real scan ends with the scanner's last frame (learning and turnarounds included)
        duration = None if (replay or real) else (scan.total_s + 2 * scan.line_s)
        self._run_shutters(True)
        self.session = ImageRecordSession(
            source,
            scan,
            windows=windows,
            duration_s=duration,
            ptu_path=self.saved_path,
            name=name,
            embed=self.recording_store == "embed",
            settings=None if replay else self._run_settings(),
            # a survey tile's own tags (survey, tile, learning) on top
            header_tags=None if replay else {**self.run_header_tags(), **self._run_tags},
        )
        try:
            self.session.start()
        except OSError as exc:
            self.status_text = tr("Cannot start")
            self.status_detail = str(exc)
            self.session = None
            return False
        self._registered = False
        self.snapshot = None
        self.image_snapshot = None
        self.image_scan = scan
        self.image_ptu, self.image_uid = self.saved_path, ""
        if replay:
            # the replayed image is a dataset already: its container takes the molecules
            row = next((d for d in _workspace("image")
                        if str(getattr(d, "address", "")) == str(self.replay_address)), None)
            self.image_ptu = Path(str(self.replay_address))
            self.image_uid = str(getattr(row, "unique_identifier", "") or "")
        self.image_map = "Intensity"
        self.status_text = tr("Replaying…") if replay else tr("Scanning…")
        self.status_detail = str(self.saved_path or self.replay_address)
        return True

    def unique_name(self, name: str) -> str:
        """*name*, or *name* with ``_2``, ``_3`` ... when a recording of that name exists already
        (two runs in one second -- a survey's tiles -- must not overwrite each other)."""
        folder = recording_dir(self.output_dir)
        taken = {p.stem for p in folder.glob("*.ptu")} if folder.exists() else set()
        stem, k = name, 1
        while stem in taken or f"{stem}_p000" in taken:
            k += 1
            stem = f"{name}_{k}"
        return stem

    def _enable_line_markers(self, scan, rising: bool) -> str:
        """The device's marker inputs of the scan's line markers switched on (a HydraHarp 400
        starts with every marker input off), on the edge the settings file declares; a note when
        the device cannot."""
        values = dict(self.device.settings())
        if "marker_enable" not in values:
            return ""
        bits = (1 << (scan.line_start_marker - 1)) | (1 << (scan.line_stop_marker - 1))
        change = {"marker_enable": int(values["marker_enable"]) | bits}
        if "marker_edges" in values:
            edges = int(values["marker_edges"])
            change["marker_edges"] = edges | bits if rising else edges & ~bits
        change = {k: v for k, v in change.items() if int(values[k]) != v}
        if not change:
            return ""
        notes = devices.apply_settings(self.device, change)
        self.device_values.update(change)
        return "; ".join(notes)

    def _run_settings(self) -> dict | None:
        """The settings document the recording's header carries (``None`` if it cannot be made)."""
        from chisurf.plugins.core.acq.live import settings_file

        doc = self.current_settings()
        return doc if not settings_file.validate(doc) else None

    def stop(self) -> bool:
        if not self.running:
            return False
        if self.survey_active:
            self.survey_stop()  # the tile's run ends; the survey keeps what it has
            if self.points_running:
                self.sequence.stop()
            elif self.busy:
                self.session.stop()
            return True
        if self.points_running:
            self.sequence.stop()
            return True
        self.session.stop()
        return True

    def reveal_saved(self) -> None:
        """Show the recording in the system's file browser."""
        import subprocess
        import sys

        path = self.saved_path
        if path is None or not path.exists():
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
        except OSError:
            pass

    def poll(self, force: bool = False) -> None:
        """Take a snapshot at the display rate; register the run once it ended; advance a
        survey."""
        self._poll_runs(force)
        self.window_check_poll()
        self.survey_step()

    def _poll_runs(self, force: bool = False) -> None:
        self._update_rates()
        if self.sequence is not None and (self.points_running or not self._sequence_finished):
            now = time.monotonic()
            if force or now - self._last_snapshot >= SNAPSHOT_INTERVAL_S:
                self._last_snapshot = now
                self.poll_points()
            return
        session = self.session
        if session is None:
            return
        now = time.monotonic()
        if force or now - self._last_snapshot >= SNAPSHOT_INTERVAL_S:
            self.snapshot = session.snapshot()
            self._last_snapshot = now
            if isinstance(session, ImageRecordSession):
                self.image_snapshot = self.snapshot
        if not session.running and session.result is not None and not self._registered:
            self._registered = True
            # a run's end closes the shutters the settings name (the excitation one); the laser
            # is not touched -- the shutter keeps the light off the sample
            self._run_shutters(False)
            self.snapshot = session.snapshot()
            result = session.result
            if isinstance(session, ImageRecordSession):
                self.image_snapshot = self.snapshot
                self._finish_image(session, result)
                return
            try:
                session.register()
                self.status_detail = (
                    tr("In Datasets, {how}.").format(
                        how=tr("embedded in the project") if session.embed else tr("linked")
                    )
                    if result.dataset_uid
                    else tr("On disk only (no project open).")
                )
            except Exception as exc:  # noqa: BLE001 - the file is written either way
                self.status_detail = tr("On disk; not added to Datasets: {e}").format(e=exc)
            if isinstance(session, FcsRecordSession):
                snap = self.snapshot or {}
                self.status_text = tr("{reason}: {photons:,} photons, N ≈ {n:.2g}, {t:.0f} s").format(
                    reason=result.stop_reason.capitalize(), photons=result.photons,
                    n=float(snap.get("n_focus", float("nan"))), t=result.elapsed_s,
                )
                return
            self.status_text = tr("{reason}: {bursts} bursts, {t:.0f} s").format(
                reason=result.stop_reason.capitalize(), bursts=result.bursts, t=result.elapsed_s
            )

    def _finish_image(self, session, result) -> None:
        snap = self.snapshot or {}
        frames = len(snap.get("lines_in_frame") or []) + (1 if snap.get("line") else 0)
        if result.ptu is None:  # a replay: analysis of an existing image, nothing recorded
            self.status_text = tr("{reason}: {frames} frame(s), {photons:,} photons").format(
                reason=result.stop_reason.capitalize(), frames=frames, photons=result.photons
            )
            self.status_detail = tr("Replayed; nothing new was recorded.")
            return
        try:
            session.register()
            self.image_uid = str(result.dataset_uid or "")
            self.status_detail = (
                tr("In Datasets as an image, {how}.").format(
                    how=tr("embedded in the project") if session.embed else tr("linked")
                )
                if result.dataset_uid
                else tr("On disk only (no project open).")
            )
        except Exception as exc:  # noqa: BLE001 - the file is written either way
            self.status_detail = tr("On disk; not added to Datasets: {e}").format(e=exc)
        self.status_text = tr("{reason}: {frames} frame(s), {photons:,} photons").format(
            reason=result.stop_reason.capitalize(), frames=frames, photons=result.photons
        )

    def close(self) -> None:
        if self.survey_active:
            self.survey_stop()
        if self.points_running:
            self.sequence.stop()
            self.sequence.wait(10.0)
        if self.session is not None and self.session.running:
            self.session.stop()
            self.session.wait(5.0)
        if self.device is not None:
            self.disconnect_device()
        if self.scanner is not None:
            self.disconnect_scanner()
        self._shutters_at_end()
        self.disconnect_shutters()
        self.disconnect_laser()


def _plot_correlation(corr: dict, height: float) -> None:
    """The live correlation curve G(tau) - 1 on a logarithmic lag axis."""
    from emtk import implot

    tau = np.asarray(corr.get("tau_s", ()), dtype=float)
    g = np.asarray(corr.get("g", ()), dtype=float)
    width = im.get_content_region_avail()[0]
    if implot.begin_plot("##correlation", (width, height), implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("lag time τ (s)"), tr("G(τ) − 1"))
        implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
        keep = (tau > 0) & np.isfinite(g)
        if keep.any():
            implot.plot_line(tr("correlation"), tau[keep], g[keep])
        implot.end_plot()


def _plot_histogram(hist: dict, height: float) -> None:
    """One of the analyzer's histograms: 1-D as bars, 2-D as a heatmap with both marginals."""
    from emtk import implot

    counts = np.asarray(hist["counts"], dtype=float)
    xe = np.asarray(hist["x_edges"], dtype=float)
    xc = (xe[:-1] + xe[1:]) / 2
    width = im.get_content_region_avail()[0]
    if "y" not in hist:
        if implot.begin_plot("##hist1d", (width, height), implot.FLAGS_NO_TITLE):
            implot.setup_axes(hist["x"], tr("bursts"))
            implot.setup_axis_limits(
                implot.AXIS_X1, float(xe[0]), float(xe[-1]), implot.COND_ALWAYS
            )
            implot.plot_bars(f"##{hist['x']}", xc, counts, bar_size=float(xe[1] - xe[0]))
            implot.end_plot()
        return
    ye = np.asarray(hist["y_edges"], dtype=float)
    yc = (ye[:-1] + ye[1:]) / 2
    side = max(80.0, width * 0.22)
    main = max(160.0, width - side - 12.0)
    marg_h = max(70.0, height * 0.28)
    if implot.begin_plot("##x_marginal", (main, marg_h), implot.FLAGS_NO_TITLE):
        implot.setup_axes(None, tr("bursts"))
        implot.setup_axis_limits(implot.AXIS_X1, float(xe[0]), float(xe[-1]), implot.COND_ALWAYS)
        implot.plot_bars(f"##{hist['x']}", xc, counts.sum(axis=1), bar_size=float(xe[1] - xe[0]))
        implot.end_plot()
    if implot.begin_plot("##hist2d", (main, height - marg_h), implot.FLAGS_NO_TITLE):
        implot.setup_axes(hist["x"], hist["y"])
        implot.setup_axis_limits(implot.AXIS_X1, float(xe[0]), float(xe[-1]), implot.COND_ALWAYS)
        implot.setup_axis_limits(implot.AXIS_Y1, float(ye[0]), float(ye[-1]), implot.COND_ALWAYS)
        grid = np.ascontiguousarray(counts.T[::-1])  # rows: y from top (high) down
        implot.plot_heatmap(
            "##counts",
            grid,
            grid.shape[0],
            grid.shape[1],
            0.0,
            float(max(1.0, grid.max())),
            None,
            (float(xe[0]), float(ye[0])),
            (float(xe[-1]), float(ye[-1])),
        )
        implot.end_plot()
    im.same_line()
    if implot.begin_plot("##y_marginal", (side, height - marg_h), implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("bursts"), None)
        implot.setup_axis_limits(implot.AXIS_Y1, float(ye[0]), float(ye[-1]), implot.COND_ALWAYS)
        # horizontal bars: lengths first, positions second
        implot.plot_bars(
            f"##{hist['y']}",
            counts.sum(axis=0),
            yc,
            bar_size=float(ye[1] - ye[0]),
            flags=implot.BARS_FLAGS_HORIZONTAL,
        )
        implot.end_plot()


def _shown_streams(snap: dict, exp: Experiment | None) -> list[str]:
    """The streams the rate and decay plots draw: per window and detector when there are windows
    (PIE: prompt/delayed x green/red), else per detector."""
    names = list((snap.get("decays") or snap.get("background_cps") or {}).keys())
    windowed = [n for n in names if " " in n]
    return windowed or names


def _plot_rates(snap: dict, exp: Experiment | None, size) -> None:
    from emtk import implot

    trace = snap.get("trace") or {}
    if implot.begin_plot("##rates", size, implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("time (s)"), tr("count rate (kHz)"))
        width = float(trace.get("bin_width_s", 0.0))
        for k, name in enumerate(_shown_streams(snap, exp)):
            counts = np.asarray((trace.get("counts") or {}).get(name, ()), dtype=float)
            if counts.size == 0 or width <= 0:
                continue
            t = (trace["first_bin"] + np.arange(counts.size)) * width
            implot.set_next_line_style(_COLOURS[k % len(_COLOURS)])
            implot.plot_line(name, t, counts / width / 1e3)
        implot.end_plot()


def _to_pixels(x: np.ndarray, y: np.ndarray, columns: float, how: str = "max"):
    """*x*, *y* reduced to at most *columns* points (the live plots pass one per two pixels).

    A live plot is redrawn many times a second, and the renderer emits primitives per point: a
    1 ms trace or a 4096-channel decay drawn at full length into a few hundred pixels made the
    window stutter. ``max`` keeps a burst's peak (the trace), ``mean`` a curve's level (a decay).
    Up to one point per column nothing changes.
    """
    n = int(y.size)
    cols = max(int(columns), 16)
    if n <= cols:
        return x, y
    k = -(-n // cols)  # points per column, rounded up
    m = n // k * k
    head = y[:m].reshape(-1, k)
    reduced = head.max(axis=1) if how == "max" else head.mean(axis=1)
    xs = x[:m:k]
    if m < n:  # the remainder is one more column
        tail = y[m:]
        reduced = np.append(reduced, tail.max() if how == "max" else tail.mean())
        xs = np.append(xs, x[m])
    return xs, reduced


#: Detected window edges on the decays (where the data says the windows should be).
_DETECTED_EDGE = (1.0, 0.55, 0.1, 1.0)


def _plot_decays(snap: dict, exp: Experiment | None, size, n_micro: int = 0,
                 detected: dict | None = None) -> None:
    """The live decays per detector over the micro-time channels, with the run's window edges
    and -- when they do not match -- the detected ones.

    The analyzer histograms the micro times in ``len(decay)`` bins over the device's *n_micro*
    channels, so a bin is ``n_micro / len(decay)`` channels wide: the x axis is in channels, the
    unit the windows are in, or a window edge lands that factor away from its pulse.
    """
    from emtk import implot

    decays = snap.get("decays") or {}
    if implot.begin_plot("##decays", size, implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("micro-time channel"), tr("photons"))
        implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
        detectors = [n for n in decays if " " not in n]  # all micro times, per detector
        for k, name in enumerate(detectors):
            y = np.asarray(decays[name], dtype=float)
            if y.size == 0:
                continue
            width = float(n_micro) / y.size if n_micro else 1.0
            implot.set_next_line_style(_COLOURS[k % len(_COLOURS)])
            xs, ys = _to_pixels((np.arange(y.size) + 0.5) * width, y, size[0] / 2, "mean")
            implot.plot_line(name, xs, np.maximum(ys, 0.5))
        windows = (exp.setup.get("windows") or {}) if exp is not None else {}
        if windows:
            edges = sorted({float(v) for r in windows.values() for v in r})
            implot.plot_inf_lines(tr("windows"), np.asarray(edges, dtype=float))
        if detected:
            edges = sorted({float(v) for r in detected.values() for v in r})
            implot.set_next_line_style(_DETECTED_EDGE)
            implot.plot_inf_lines(tr("detected"), np.asarray(edges, dtype=float))
        implot.end_plot()


_LIGHT_COLOURS = {
    "green": (0.25, 0.78, 0.35, 1.0),
    "amber": (1.0, 0.72, 0.15, 1.0),
    "red": (0.95, 0.32, 0.27, 1.0),
    "grey": (0.55, 0.55, 0.55, 1.0),
}
_OVERALL = {
    "green": "Quality: good — continue",
    "amber": "Quality: usable — see the amber notes",
    "red": "Quality: act now — see the red notes",
    "grey": "Quality: no verdict yet",
}


def _draw_qc(qc: dict | None) -> None:
    """The quality checker's verdict: an overall light, then one line per check -- light, name,
    value; what it means and what to do are in the line's tooltip (and in the stored verdict)."""
    if not qc or not qc.get("ready"):
        im.text_colored(_LIGHT_COLOURS["grey"], "●")
        im.same_line()
        im.text(tr("Quality: no verdict yet"))
        im.set_item_tooltip((qc or {}).get("why", "") or tr("Not enough bursts yet."))
        return
    level = qc["level"]
    im.text_colored(_LIGHT_COLOURS[level], "●")
    im.same_line()
    im.text(tr(_OVERALL[level]).split(" — ")[0])
    im.set_item_tooltip(tr(_OVERALL[level]))
    for check in qc["checks"]:
        im.text_colored(_LIGHT_COLOURS.get(check["light"], _LIGHT_COLOURS["grey"]), "●")
        im.same_line()
        im.text_wrapped(f"{check['name']}: {check['value']}")
        tip = check["detail"] + (f"\n\n→ {check['action']}" if check.get("action") else "")
        im.set_item_tooltip(tip)


def _short_line(text: str, tooltip: str, colour=None) -> None:
    """A few words, the details on hover."""
    if colour is None:
        im.text(text)
    else:
        im.text_colored(colour, text)
    if tooltip:
        im.set_item_tooltip(tooltip)


#: The Record tool's docks: key, title, the region it starts in.
DOCKS = (
    ("acquisition", "Acquisition", "settings"),
    ("laser", "Laser", "settings"),
    ("shutters", "Shutters", "settings"),
    ("analysis", "Analysis", "settings"),
    ("plot_hist", "Histogram", "main"),
    ("plot_image", "Image", "main"),
    ("video", "Camera", "main"),
    ("quality", "Quality", "side"),
    ("points", "Points", "side"),
    ("plot_trace", "Trace", "bottom_left"),
    ("plot_decays", "Decays", "bottom_right"),
)
#: Height of the run bar above the docks.
RUN_BAR_H = 30.0


def _layout():
    from emtk.docking import Region, Split

    return Split(
        "h", 0.30, Region("settings"),
        Split("v", 0.62,
              Split("h", 0.56, Region("main"), Region("side")),
              Split("h", 0.5, Region("bottom_left"), Region("bottom_right"))),
    )  # fmt: skip


def _plot_mirrored_trace(trace: dict, size) -> None:
    """The running smFRET trace: donor up, acceptor signals down, the last *window* seconds."""
    from emtk import implot

    if implot.begin_plot("##mirrored_trace", size, implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("time (s)"), tr("photons per bin"))
        t = np.asarray(trace["t"], dtype=float)
        implot.setup_axis_limits(
            implot.AXIS_X1, float(t[0]) - trace["bin_s"], float(t[-1]) + trace["bin_s"],
            implot.COND_ALWAYS,
        )
        # acceptor curves first (AA under DA), the donor last: each sign's main signal on top
        ordered = sorted(trace["streams"], key=lambda st: (st["sign"], ))
        ordered = [st for st in reversed(ordered) if st["sign"] < 0] + [
            st for st in ordered if st["sign"] > 0
        ]
        for stream in ordered:
            # the peak of each pixel column, sign kept (acceptor streams point down)
            y = np.asarray(stream["counts"], dtype=float) * stream["sign"]
            ts, ys = _to_pixels(t, y, size[0] / 2, "max")
            ys = ys * stream["sign"]
            implot.set_next_line_style(stream["colour"])
            implot.set_next_fill_style(stream["colour"], 0.35)
            implot.plot_shaded(tr(stream["name"]), ts, ys, yref=0.0)
            implot.set_next_line_style(stream["colour"])
            implot.plot_stairs(f"##{stream['name']}", ts, ys)
        implot.set_next_line_style((0.6, 0.6, 0.6, 1.0))
        implot.plot_line("##zero", np.asarray([t[0], t[-1]]), np.zeros(2))
        implot.end_plot()


_POINT_COLOURS = {
    "picked": (0.35, 0.85, 1.0, 1.0),
    "measured": (0.4, 1.0, 0.45, 1.0),
    "selected": (1.0, 1.0, 1.0, 1.0),
    "measuring": (1.0, 0.25, 0.85, 1.0),
}
#: a press that moves less than this (pixels) before it is released is a click, not a pan
_CLICK_SLOP = 4.0
_press: dict = {}


def _plot_image(image: np.ndarray, name: str, size, overlay=()) -> tuple[float, float] | None:
    """One map of the live image, with its colour scale and the picked points on it; returns the
    plot position (pixels) of a click on the image (a press released where it began)."""
    from emtk import implot

    img = np.asarray(image, dtype=float)
    finite = img[np.isfinite(img)]
    lo = float(finite.min()) if finite.size else 0.0
    hi = float(finite.max()) if finite.size else 1.0
    if hi <= lo:
        hi = lo + 1.0
    flim = "arrival" in name
    cmap = implot.COLORMAP_JET if flim else implot.COLORMAP_HOT
    shown = np.where(np.isfinite(img), img, lo)
    scale_w = 70.0
    implot.push_colormap(cmap)
    plot_w = max(120.0, size[0] - scale_w - 8.0)
    if implot.begin_plot("##live_image", (plot_w, size[1]),
                         implot.FLAGS_NO_TITLE | implot.FLAGS_EQUAL):
        implot.setup_axes(tr("x (pixel)"), tr("y (line)"), 0, implot.AXIS_FLAGS_INVERT)
        rows, cols = shown.shape
        implot.plot_heatmap("##map", np.ascontiguousarray(shown), rows, cols, lo, hi, None,
                            (0.0, float(rows)), (float(cols), 0.0))
        for kind, colour in _POINT_COLOURS.items():
            pts = [(x, y, n) for x, y, n, k in overlay if k == kind]
            if not pts:
                continue
            xs = np.asarray([p[0] for p in pts], float)
            ys = np.asarray([p[1] for p in pts], float)
            big = kind in ("selected", "measuring")
            # rings: the molecule under the marker stays visible
            implot.set_next_marker_style(implot.MARKER_CIRCLE, 9.0 if big else 6.0,
                                         (0.0, 0.0, 0.0, 0.0), 2.5 if big else 1.5, colour)
            implot.plot_scatter(f"##points_{kind}", xs, ys)
            for x, y, n in pts:
                implot.plot_text(str(n), float(x), float(y), (10.0, -9.0))
        clicked = None
        if implot.is_plot_hovered():
            mouse = im.get_mouse_pos()
            if im.is_mouse_clicked(0):
                _press["at"] = tuple(mouse)
            if im.is_mouse_released(0) and "at" in _press:
                start = _press.pop("at")
                if abs(mouse[0] - start[0]) + abs(mouse[1] - start[1]) <= _CLICK_SLOP:
                    where = implot.get_plot_mouse_pos()
                    clicked = (float(where.x), float(where.y))
        implot.end_plot()
    im.same_line()
    implot.colormap_scale(tr("ns") if flim else tr("photons"), lo, hi, (scale_w, size[1]),
                          cmap=cmap)
    implot.pop_colormap()
    return clicked


def _plot_point_trace(p: dict, size) -> None:
    """A point's live trace: count rate per detector and in total, the bleach rule's threshold,
    and where it called the molecule bleached; under it the FRET efficiency (acceptor over the
    sum, proximity ratio) and the mean arrival time per bin."""
    from emtk import implot

    counts = p["counts"]
    width = float(p["bin_s"])
    n = max((a.size for a in counts.values()), default=0)
    if n == 0:
        im.text(tr("Waiting for photons…"))
        return
    t = np.arange(n) * width
    top_h = max(80.0, size[1] * 0.62)
    if implot.begin_plot("##point_trace", (size[0], top_h), implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("time (s)"), tr("count rate (kHz)"))
        total = np.zeros(n)
        for k, (ch, arr) in enumerate(counts.items()):
            y = np.zeros(n)
            y[: arr.size] = arr
            total += y
            implot.set_next_line_style(_COLOURS[k % len(_COLOURS)])
            implot.plot_stairs(tr("detector {c}").format(c=ch), t, y / width / 1e3)
        implot.set_next_line_style((0.85, 0.85, 0.85, 1.0))
        implot.plot_stairs(tr("total"), t, total / width / 1e3)
        if p.get("threshold_kcps") is not None:
            implot.set_next_line_style((1.0, 0.75, 0.2, 1.0), 1.5)
            implot.plot_inf_lines(tr("bleach threshold"), np.asarray([p["threshold_kcps"]]),
                                  flags=implot.INF_LINES_FLAGS_HORIZONTAL)
        if p.get("bleached_at_s") is not None:
            implot.set_next_line_style((0.95, 0.3, 0.3, 1.0), 2.0)
            implot.plot_inf_lines(tr("bleached"), np.asarray([p["bleached_at_s"]]))
        implot.end_plot()
    if implot.begin_plot("##point_e", (size[0], max(60.0, size[1] - top_h - 6.0)),
                         implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("time (s)"), tr("E"))
        implot.setup_axis(implot.AXIS_Y2, tr("⟨t⟩ (ns)"), implot.AXIS_FLAGS_OPPOSITE)
        implot.setup_axis_limits(implot.AXIS_Y1, -0.05, 1.05, implot.COND_ALWAYS)
        chans = list(counts)
        if len(chans) >= 2:
            d = np.zeros(n)
            a = np.zeros(n)
            d[: counts[chans[0]].size] = counts[chans[0]]
            a[: counts[chans[1]].size] = counts[chans[1]]
            with np.errstate(invalid="ignore", divide="ignore"):
                e = np.where(d + a > 0, a / (d + a), np.nan)
            keep = np.isfinite(e)
            implot.set_next_line_style(_COLOURS[2])
            implot.plot_line(tr("E (proximity ratio)"), t[keep], e[keep])
        mean = np.asarray(p.get("mean_arrival_ns"), float)
        keep = np.isfinite(mean)
        if keep.any():
            implot.set_axes(implot.AXIS_X1, implot.AXIS_Y2)
            implot.set_next_line_style(_COLOURS[4])
            implot.plot_line(tr("mean arrival"), t[: mean.size][keep], mean[keep])
        implot.end_plot()


def _plot_molecule_trace(m, size) -> None:
    """An analysed molecule: its trace per detector and the HMM path, its E per bin."""
    from emtk import implot

    t = np.asarray(m.time_s, float)
    counts = np.asarray(m.counts, float)
    if t.size == 0 or counts.size == 0:
        im.text_wrapped(m.message or tr("No trace."))
        return
    width = float(t[1] - t[0]) if t.size > 1 else 1.0
    top_h = max(80.0, size[1] * 0.62)
    if implot.begin_plot("##molecule_trace", (size[0], top_h), implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("time (s)"), tr("count rate (kHz)"))
        for k in range(counts.shape[1]):
            implot.set_next_line_style(_COLOURS[k % len(_COLOURS)])
            label = m.labels[k] if k < len(m.labels) else f"{k}"
            implot.plot_stairs(label, t, counts[:, k] / width / 1e3)
        implot.set_next_line_style((0.6, 0.6, 0.6, 1.0))
        implot.plot_stairs(tr("total"), t, counts.sum(axis=1) / width / 1e3)
        if np.asarray(m.path_khz).size == t.size:
            implot.set_next_line_style((1.0, 0.85, 0.15, 1.0), 3.0)
            implot.plot_stairs(tr("HMM path"), t, np.asarray(m.path_khz, float))
        if m.bleach_s is not None:
            implot.set_next_line_style((0.95, 0.3, 0.3, 1.0), 2.0)
            implot.plot_inf_lines(tr("bleached"), np.asarray([m.bleach_s]))
        implot.end_plot()
    if implot.begin_plot("##molecule_e", (size[0], max(60.0, size[1] - top_h - 6.0)),
                         implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("time (s)"), tr("E"))
        implot.setup_axis_limits(implot.AXIS_Y1, -0.05, 1.05, implot.COND_ALWAYS)
        if counts.shape[1] >= 2:
            total = counts[:, 0] + counts[:, 1]
            with np.errstate(invalid="ignore", divide="ignore"):
                e = np.where(total > 0, counts[:, 1] / total, np.nan)
            on = t < (m.bleach_s if m.bleach_s is not None else np.inf)
            keep = np.isfinite(e) & on
            implot.set_next_line_style(_COLOURS[2])
            implot.plot_line(tr("E (proximity ratio)"), t[keep], e[keep])
        implot.end_plot()


class RecordApp(ImApp):
    """The Record tool: settings, laser, analysis, quality and every plot in its own dock, with a
    run bar above them that always shows Start, Stop and Laser off."""

    window_title = "ChiSurf Record"

    def __init__(self, model: RecordModel | None = None) -> None:
        from emtk.docking import DockManager

        self.model = model or RecordModel()
        from chisurf.plugins.core.acq.gui.video_panel import VideoPanel

        self.video = VideoPanel()
        self.video.photon_context = lambda: str(self.model.saved_path or "") if self.model.running else ""
        self.video.output = str(self.model.output_dir / self.video.output)
        video_spec = json.loads((HERE / "video.view.json").read_text(encoding="utf-8"))
        #: Advanced shows every control; simple mode shows the video, the record
        #: buttons and the status -- the camera is for watching, not configuring
        self.video_sections = video_spec["sections"]
        self.video_sections_simple = video_spec["simple_sections"]
        self.video_form = FormState()
        self.video_form.custom["video_frame"] = self._draw_video_frame
        self._video_frame = None
        self._video_gain = None
        self._video_texture = None
        self.sections = json.loads((HERE / "record.view.json").read_text(encoding="utf-8"))[
            "sections"
        ]
        self.form = FormState()
        for key, draw in (
            ("live_view", self._draw_hist),
            ("live_image", self._draw_image),
            ("live_trace", self._draw_trace),
            ("live_decays", self._draw_decays),
            ("live_qc", self._draw_quality),
            ("setup_summary", self._draw_setup_summary),
            ("scan_summary", self._draw_scan_summary),
            ("run_status", self._draw_run_status),
            ("laser_status", self._draw_laser_status),
            ("laser_rate", self._draw_laser_rate),
            ("settings_status", self._draw_settings_status),
            ("device_settings", self._draw_device_settings),
            ("laser_settings", self._draw_laser_settings),
            ("shutter_settings", self._draw_shutter_settings),
            ("scanner_settings", self._draw_scanner_settings),
            ("survey_map", self._draw_survey_map),
            ("video_panel", self._draw_video_panel),
        ):
            self.form.custom[key] = draw
        #: the generated device / laser forms: their own form state, their spec per form
        self._sub_forms: dict[str, tuple[Any, dict, FormState]] = {}
        self.save_dialog = None
        self.save_window = None
        self.help_window = EmTkHelpWindow(
            title="Record help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(_layout())
        for key, title, region in DOCKS:
            self.docks.add_window(key, tr(title), self._dock_drawer(key), dock=region)
        self._mode_shown = None
        self._video_seen = False
        #: which dock draws each control (attr, action, custom key): a tour step on a control
        #: of a tab in the back brings that tab forward
        self.control_dock = self._map_controls()
        self._tour_focus: tuple | None = None
        super().__init__(self.render, continuous=True)

    def _map_controls(self) -> dict[str, str]:
        out: dict[str, str] = {}

        def walk(sections, dock):
            for sec in sections:
                for key in (sec.get("attr"), sec.get("action"), sec.get("key")):
                    if key:
                        out.setdefault(str(key), dock)
                for button in sec.get("buttons") or ():
                    if button.get("action"):
                        out.setdefault(str(button["action"]), dock)
                walk(sec.get("sections") or (), dock)

        for panel in self.sections:
            if panel.get("dock"):
                walk([panel], panel["dock"])
        out["live_view"] = "plot_hist"
        out["live_image"] = "plot_image"
        out["point_rows"] = "points"
        out["Survey.fold"] = "points"
        return out

    def focus_dock(self, key: str) -> None:
        """Show the dock *key* and bring it in front of the tabs it shares its region with."""
        self.docks.show(key)
        self.docks.focus(key)

    def _follow_tour(self) -> None:
        """The tour's step points at a control in a dock in the back: bring the dock forward."""
        tour = self.tour
        if not tour.active or not tour.steps:
            self._tour_focus = None
            return
        target = (tour.steps[tour.step_idx].get("target") or {}).get("name")
        dock = self.control_dock.get(str(target)) if target else None
        if dock and self._tour_focus != (tour.step_idx, dock):
            self._tour_focus = (tour.step_idx, dock)
            self.focus_dock(dock)

    # -- docks -------------------------------------------------------------------------------------
    def _panels(self, dock: str) -> list:
        return [s for s in self.sections if s.get("dock") == dock]

    def _dock_drawer(self, dock: str):
        def draw(box) -> None:
            panels = self._panels(dock)
            single = len(panels) == 1 and dock.startswith(("plot_", "quality", "video"))
            if single:
                draw_sections(panels[0]["sections"], self.model, self.form, titles=False)
            else:
                draw_sections(panels, self.model, self.form, titles=True)

        return draw

    def _sync_docks_to_mode(self) -> None:
        """Point shows the histogram dock, Image the image dock (the user may re-open either)."""
        mode = self.model.mode
        if mode == self._mode_shown:
            return
        self._mode_shown = mode
        if mode == "image":
            self.docks.show("plot_image")
            self.docks.hide("plot_hist")
            self.docks.show("points")
            self.docks.focus("points")
        else:
            self.docks.show("plot_hist")
            self.docks.hide("plot_image")
            self.docks.hide("points")

    def _sync_docks_to_video(self) -> None:
        """The camera dock comes forward once a connected source delivers frames, in every
        mode: the preview judges the coverslip distance while photons come from anywhere
        (a device or the simulator)."""
        if self.video.frame is None:
            self._video_seen = False
            return
        if not self._video_seen:
            self._video_seen = True
            self.focus_dock("video")

    def reset_layout(self) -> None:
        """Every dock back where the tool puts it, the stored layout forgotten."""
        self.docks.reset()
        self._mode_shown = None

    # -- the run bar -------------------------------------------------------------------------------
    def _run_bar(self, box) -> None:
        model = self.model
        im.set_next_window_pos((box[0], box[1]), im.Cond.ALWAYS)
        im.set_next_window_size((box[2], RUN_BAR_H), im.Cond.ALWAYS)
        flags = (
            im.WindowFlags.NO_DECORATION | im.WindowFlags.NO_MOVE
            | im.WindowFlags.NO_SCROLLBAR | im.WindowFlags.NO_SAVED_SETTINGS
        )  # fmt: skip
        if im.begin("##record_run_bar", None, flags):
            for action, label, role, tip in (
                ("start", f"▶ {tr('Start')}", "primary", tr("Start measuring.")),
                ("stop", f"⏹ {tr('Stop')}", "danger", tr("Stop measuring.")),
            ):
                enabled = model.enabled(action)
                if not enabled:
                    im.begin_disabled()
                if im.small_button(f"{label}##bar_{action}"):
                    getattr(model, action)()
                    self.tour.notify_used(action)
                if not enabled:
                    im.end_disabled()
                im.set_item_tooltip(tip)
                im.same_line()
            snap = model.snapshot or {}
            elapsed = float(snap.get("elapsed_s", 0.0))
            im.text(f"{model.status_text} · {elapsed:.1f} s")
            im.set_item_tooltip(model.status_detail)
            im.same_line()
            # one laser button: red Laser off while it emits, green Laser on otherwise
            emitting = model._emission_on
            can = model.enabled("laser_toggle")
            im.push_style_color(im.Col.BUTTON, _LIGHT_COLOURS["red" if emitting else "green"])
            if not can:
                im.begin_disabled()
            if im.small_button(f"⏻ {model.laser_toggle_label()}##bar_laser_toggle"):
                model.laser_toggle()
                self.tour.notify_used("laser_off")
            if not can:
                im.end_disabled()
            im.pop_style_color()
            im.set_item_tooltip(
                tr("Switch every laser output off now (always available).") if emitting else
                tr("Switch the laser's emission on (after its program is applied)."))
            self.form.rects["laser_off"] = im.get_item_rect()
            im.same_line()
            if im.small_button(f"📖 {tr('Guide')}"):
                self.tour.start()
            im.set_item_tooltip(tr("A guided tour: it points at each control in turn."))
            im.same_line()
            if im.small_button(f"❓ {tr('Help')}"):
                self.help_window.open()
            im.set_item_tooltip(tr("What every window and control does."))
            im.same_line()
            if im.small_button(tr("Reset layout")):
                self.reset_layout()
                self.tour.notify_used("reset_layout")
            self.form.rects["reset_layout"] = im.get_item_rect()
            im.set_item_tooltip(tr("Put every window back where the Record tool puts it."))
        im.end()

    # -- custom sections ---------------------------------------------------------------------------
    def _draw_setup_summary(
        self, section, model: RecordModel, state: FormState, width: float
    ) -> None:
        top = im.get_cursor_screen_pos()
        label, detail = model.setup_summary()
        _short_line(label, detail, (0.7, 0.7, 0.7, 1.0))
        state.rects["setup_summary"] = (*top, width, 20.0)

    def _draw_scan_summary(self, section, model: RecordModel, state: FormState, width: float):
        top = im.get_cursor_screen_pos()
        label, detail = model.scan_summary()
        _short_line(label, detail, (0.7, 0.7, 0.7, 1.0))
        state.rects["scan_summary"] = (*top, width, 20.0)

    def _draw_run_status(self, section, model: RecordModel, state: FormState, width: float) -> None:
        top = im.get_cursor_screen_pos()
        _short_line(model.status_text, model.status_detail)
        if model.saved_path is not None:
            _short_line(tr("Saved: {name}").format(name=model.saved_path.name), str(model.saved_path),
                        (0.7, 0.7, 0.7, 1.0))  # fmt: skip
            im.same_line()
            if im.small_button(tr("Show file")):
                model.reveal_saved()
            im.set_item_tooltip(tr("Show the recording in the file browser."))
        state.rects["run_status"] = (*top, width, im.get_cursor_screen_pos()[1] - top[1])

    def _draw_laser_status(self, section, model: RecordModel, state: FormState, width: float):
        top = im.get_cursor_screen_pos()
        reason = getattr(model, "_sepia_reason", "")
        detail = model.laser_detail or (
            tr("Sepia II is not available: {why}").format(why=reason) if reason else ""
        )
        _short_line(f"● {model.laser_text}", detail, _LIGHT_COLOURS[model.laser_light()])
        state.rects["laser_status"] = (*top, width, 20.0)

    def _draw_laser_rate(self, section, model: RecordModel, state: FormState, width: float):
        text, detail = model.laser_rate()
        if text:
            _short_line(text, detail, (0.7, 0.7, 0.7, 1.0))

    def _draw_settings_status(self, section, model: RecordModel, state: FormState, width: float):
        top = im.get_cursor_screen_pos()
        _short_line(model.settings_text, model.settings_detail, (0.7, 0.7, 0.7, 1.0))
        state.rects["settings_status"] = (*top, width, 20.0)

    def _draw_generated(self, key: str, form, state: FormState, width: float, empty: str) -> None:
        """Draw a form generated from a device's settings schema (``live.devices.settings_form``)
        in place, under its own form state; the spec is converted once per form."""
        top = im.get_cursor_screen_pos()
        if form is None:
            _short_line(empty, "", (0.7, 0.7, 0.7, 1.0))
            state.rects[key] = (*top, width, 20.0)
            return
        cached = self._sub_forms.get(key)
        if cached is None or cached[0] is not form:
            from chisurf.emtk.reader_settings import native_reader_spec

            spec = native_reader_spec(form.view_spec())
            # every setting sits in a group: the entry's own (title) panel is empty
            spec["sections"] = [p for p in spec["sections"] if p.get("sections")]
            # the form state outlives a rebuilt form: folds opened stay open
            state_kept = cached[2] if cached is not None else FormState()
            cached = (form, spec, state_kept)
            cached[2].on_used = self.form.on_used
            self._sub_forms[key] = cached
        # emtk's in-place form reads ``getattr(model, attr)``: the bound parameter group itself
        draw_sections(cached[1]["sections"], form._params_group, cached[2])
        state.rects[key] = (*top, width, im.get_cursor_screen_pos()[1] - top[1])

    def _draw_device_settings(self, section, model: RecordModel, state: FormState, width: float):
        self._draw_generated("device_settings", model.device_form, state, width,
                             tr("Connect a device: all its settings appear here."))

    def _draw_shutter_settings(self, section, model: RecordModel, state: FormState, width: float):
        self._draw_generated("shutter_settings", model.shutter_form, state, width,
                             tr("Load settings with a shutters section: its shutters appear here."))

    def _draw_scanner_settings(self, section, model: RecordModel, state: FormState, width: float):
        self._draw_generated("scanner_settings", model.scanner_form, state, width,
                             tr("Connect the scanner: its settings appear here."))

    def _draw_survey_map(self, section, model: RecordModel, state: FormState, width: float):
        top = im.get_cursor_screen_pos()
        model.survey_preview()
        x0, y0, w, h = model.survey_area()
        side = max(80.0, min(width - 8.0, 240.0))
        draw_survey_map(model, side, side * min(2.0, h / max(w, 1e-9)))
        n = len(model.survey_tiles)
        _short_line(tr("{n} tile(s) of {w:.1f} × {h:.1f} µm").format(
            n=n, w=float(model.scan_area_x_um), h=float(model.scan_area_y_um)),
            "\n".join(model.survey_log[-12:]) or tr("The survey's log appears here."),
            (0.7, 0.7, 0.7, 1.0))
        state.rects["survey_map"] = (*top, width, im.get_cursor_screen_pos()[1] - top[1])

    def _draw_laser_settings(self, section, model: RecordModel, state: FormState, width: float):
        self._draw_generated("laser_settings", model.laser_form, state, width,
                             tr("The simulated laser is set in the program below."))

    def _avail(self, minimum=(200.0, 120.0)) -> tuple[float, float]:
        w, h = im.get_content_region_avail()[:2]
        return max(minimum[0], w), max(minimum[1], h - 4.0)

    def _placeholder(self, state: FormState, key: str, text: str, width: float) -> None:
        top = im.get_cursor_screen_pos()
        im.text_wrapped(text)
        state.rects[key] = (*top, width, 28.0)

    def _draw_hist(self, section, model: RecordModel, state: FormState, width: float) -> None:
        snap = model.snapshot
        if snap is None or model.mode == "image":
            self._placeholder(state, "live_view", tr("Start a run: the bursts build up here."), width)
            return
        top = im.get_cursor_screen_pos()
        if model.mode == "fcs" or "correlation" in snap:
            _short_line(
                tr("N ≈ {n:.2g} · {b:.1f} kHz per molecule").format(
                    n=float(snap.get("n_focus", float("nan"))),
                    b=float(snap.get("brightness_hz", 0.0)) / 1e3,
                ),
                tr("{photons:,} photons in {t:.1f} s, {r:.0f} kHz").format(
                    photons=snap["photons"], t=snap["elapsed_s"],
                    r=float(snap.get("count_rate_hz", 0.0)) / 1e3,
                ),
            )
            _w, h = self._avail()
            _plot_correlation(snap.get("correlation") or {}, h)
            bottom = im.get_cursor_screen_pos()
            state.rects["live_view"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))
            return
        _short_line(
            f"{tr('Bursts')}: {snap['bursts']:,} · {snap['burst_rate_hz']:.1f} Hz",
            tr("{photons:,} photons in {t:.1f} s").format(photons=snap["photons"],
                                                         t=snap["elapsed_s"]),
        )
        hists = snap.get("histograms") or {}
        if hists and model.plot_choice not in hists:
            two_d = [n for n, h in hists.items() if "y" in h]
            model.plot_choice = (two_d or list(hists))[0]
        _w, h = self._avail()
        if hists:
            _plot_histogram(hists[model.plot_choice], h)
        else:
            im.text_wrapped(tr("This measurement type keeps no histogram."))
        bottom = im.get_cursor_screen_pos()
        state.rects["live_view"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def _draw_video_panel(self, section, model: RecordModel, state: FormState, width: float) -> None:
        top = im.get_cursor_screen_pos()
        sections = self.video_sections if model.advanced else self.video_sections_simple
        draw_sections(sections, self.video, self.video_form, titles=False)
        bottom = im.get_cursor_screen_pos()
        state.rects["video_panel"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def _draw_video_frame(self, section, model: RecordModel, state: FormState, width: float) -> None:
        from emtk import Texture

        frame = self.video.frame
        if frame is None:
            im.text_wrapped(tr("Connect a video source to see its preview."))
            return
        gain = float(self.video.display_gain)
        if not self.model.advanced:
            # a backreflection feed is dim (mean ~10 of 255 measured on the
            # MT200): stretch it for display alone, so the camera is usable in
            # simple mode where there is no gain control. Recordings stay raw.
            top = float(np.percentile(frame.image, 99.5)) or 1.0
            gain = max(gain, min(20.0, 240.0 / top))
        if frame is not self._video_frame or gain != self._video_gain:
            rgb = frame.image
            rgba = np.empty((*rgb.shape[:2], 4), dtype=np.uint8)
            rgba[:, :, :3] = np.clip(rgb.astype(np.float32) * gain, 0, 255).astype(np.uint8)
            rgba[:, :, 3] = 255
            if (self._video_texture is None or self._video_texture.width != rgb.shape[1]
                    or self._video_texture.height != rgb.shape[0]):
                self._video_texture = Texture(rgb.shape[1], rgb.shape[0], rgba.tobytes())
            else:
                self._video_texture.set_rows(0, rgba.tobytes())
            self._video_frame = frame
            self._video_gain = gain
        h, w = frame.image.shape[:2]
        size = min(float(width), 640.0)
        im.image(self._video_texture, (size, size * h / w))

    def _draw_image(self, section, model: RecordModel, state: FormState, width: float) -> None:
        snap = model.image_snapshot
        images = (snap or {}).get("images") or {}
        if not images:
            self._placeholder(state, "live_image", tr("Start a scan: the image builds up here."),
                              width)
            return
        top = im.get_cursor_screen_pos()
        if model.image_map not in images:
            model.image_map = "Intensity"
        _short_line(
            tr("Frame {f} · line {l}/{n}").format(f=snap["frame"] + 1, l=snap["line"], n=snap["ny"]),
            tr("{photons:,} photons, {lines} lines").format(photons=snap["photons"],
                                                           lines=snap["lines_done"]),
        )
        picked = _plot_image(images[model.image_map], model.image_map, self._avail(),
                             overlay=self._image_points(model))
        if picked is not None:
            row = model.pick_at_pixel(*picked)
            if row is not None:
                self.tour.notify_used("live_image")
        bottom = im.get_cursor_screen_pos()
        state.rects["live_image"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def _image_points(self, model: RecordModel) -> list[tuple]:
        """The picked points in image pixels: ``(px, py, number, kind)``, kind ``measuring`` /
        ``selected`` / ``measured`` / ``picked``."""
        seq = model.sequence
        measuring = seq.current.index if (seq is not None and seq.current is not None) else None
        out = []
        for k, p in enumerate(model.points):
            px, py = model.image_um_to_pixel(p["x_um"], p["y_um"])
            kind = ("measuring" if measuring == k else "selected"
                    if model.selected_point == p["index"] else "measured"
                    if p["index"] in model.molecules else "picked")
            out.append((px, py, p["index"] + 1, kind))
        return out

    def _draw_trace(self, section, model: RecordModel, state: FormState, width: float) -> None:
        snap = model.snapshot
        top = im.get_cursor_screen_pos()
        point = (snap or {}).get("point_trace") if model.points_running else None
        molecule = model.molecules.get(model.selected_point) \
            if model.selected_point is not None and not model.points_running else None
        if point is not None or molecule is not None:
            if point is not None:
                p = point
                _short_line(
                    tr("Point {k} · live").format(k=p["index"] + 1),
                    tr("Photons per detector in {b:g} ms bins; the dashed line is the bleach "
                       "rule's threshold, the red line where it called the molecule bleached.")
                    .format(b=p["bin_s"] * 1e3), (0.7, 0.7, 0.7, 1.0))
                _plot_point_trace(p, self._avail())
            else:
                m = molecule
                _short_line(
                    tr("Molecule {k} · {n} states · {s} step(s)").format(
                        k=m.index + 1, n=m.n_states, s=m.steps),
                    tr("The recorded trace per detector and the HMM path (the state's rate per "
                       "bin, black) of the intensity-trace tool's binning and the shared HMM."),
                    (0.7, 0.7, 0.7, 1.0))
                _plot_molecule_trace(m, self._avail())
            bottom = im.get_cursor_screen_pos()
            state.rects["live_trace"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))
            return
        if snap is None:
            self._placeholder(state, "live_trace", tr("The running trace appears during a run."),
                              width)
            return
        exp = model.session.experiment if model.session is not None else None
        if snap.get("live_trace") is not None:
            trace = snap["live_trace"]
            _short_line(
                tr("Last {w:g} s · {b:g} ms bins").format(w=trace["window_s"],
                                                          b=trace["bin_s"] * 1e3),
                tr("Donor up, acceptor down. Span and bin width: Analysis › Running trace."),
                (0.7, 0.7, 0.7, 1.0),
            )
            _plot_mirrored_trace(trace, self._avail())
        else:
            _plot_rates(snap, exp, self._avail())
        bottom = im.get_cursor_screen_pos()
        state.rects["live_trace"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def _draw_decays(self, section, model: RecordModel, state: FormState, width: float) -> None:
        snap = model.snapshot
        top = im.get_cursor_screen_pos()
        if snap is None:
            self._placeholder(state, "live_decays", tr("Decays appear during a run."), width)
            return
        exp = model.session.experiment if model.session is not None else None
        n_micro = model.session.source.info.n_micro if model.session is not None else 0
        check = model.live_windows.check
        detected = check.proposal if (check is not None and check.mismatch) else None
        _plot_decays(snap, exp, self._avail(), n_micro, detected)
        bottom = im.get_cursor_screen_pos()
        state.rects["live_decays"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def _draw_quality(self, section, model: RecordModel, state: FormState, width: float) -> None:
        top = im.get_cursor_screen_pos()
        snap = model.snapshot or {}
        healthy = not snap.get("dropped") and not snap.get("source_error")
        if snap:
            _short_line(
                tr("● healthy") if healthy else tr("● data lost"),
                tr("{batches} batches, {dropped} dropped, {queued} buffered.").format(
                    batches=snap.get("batches", 0), dropped=snap.get("dropped", 0),
                    queued=snap.get("queued", 0)),
                _LIGHT_COLOURS["green" if healthy else "red"],
            )
            if snap.get("source_error"):
                im.text_colored(_style.TEXT_DANGER, str(snap["source_error"]))
        _draw_qc(snap.get("qc"))
        bottom = im.get_cursor_screen_pos()
        state.rects["live_qc"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    # -- the settings file save dialog ---------------------------------------------------------------
    def _open_save_dialog(self) -> None:
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        self.model.save_settings_requested = False
        title = tr("Save acquisition settings")
        # not-input: where the acquisition settings file is written, an output
        self.save_dialog = FileDialog(
            title,
            mode="save",
            filters=[(tr("Acquisition settings"), ["*.json"])],
            directory=str(self.model.output_dir),
            filename=f"{self.model.run_name.strip() or 'acquisition'}.settings.json",
        )
        self.save_window = DialogWindow(title, size=(720, 500))
        self.save_window.show()

    def _draw_save_dialog(self, box) -> None:
        if self.model.save_settings_requested:
            self._open_save_dialog()
        if self.save_dialog is None:
            return
        pressed = self.save_window.begin(box)
        result = self.save_dialog.draw()
        self.save_window.end()
        if result:
            self.model.save_settings_to(result[0])
            self.save_dialog = None
        elif result is False or pressed == "close":
            self.save_dialog = None

    # -- the windows review (From a measurement…) ---------------------------------------------------
    def _draw_windows_review(self, box) -> None:
        review = self.model.windows_review_requested
        if review is not None:
            from chisurf.emtk.excitation_windows import WindowsReviewDialog

            self.model.windows_review_requested = None
            if getattr(self, "windows_review", None) is None:
                self.windows_review = WindowsReviewDialog(
                    tr("Windows from a measurement"), key="record_windows"
                )
            self.windows_review.show(review)
        if getattr(self, "windows_review", None) is not None:
            self.windows_review.draw(box)

    # -- one frame ---------------------------------------------------------------------------------
    def render(self) -> None:
        self.model.poll()
        self.model.refresh_shutter_form()
        self._persist_loaded_settings()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self._sync_docks_to_mode()
        self._sync_docks_to_video()
        self._follow_tour()
        self._run_bar(box)
        self.docks.draw((box[0], box[1] + RUN_BAR_H, box[2], max(100.0, box[3] - RUN_BAR_H)))
        self._draw_save_dialog(box)
        self._draw_windows_review(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _persist_loaded_settings(self) -> None:
        """Save the tool's state as soon as settings were loaded onto the hardware: it is
        otherwise written only when the tool closes cleanly, and a crashed or killed window
        would forget what to load on the next start."""
        model = self.model
        loaded = (model.settings_address, model.settings_name)
        if model.connecting or not model.settings_name or loaded == getattr(
                self, "_persisted_load", None):
            return
        self._persisted_load = loaded
        plugin_id = getattr(self, "_native_state_id", None)
        if plugin_id:
            from chisurf.emtk.state import save_settings

            save_settings(plugin_id, self.export_settings())

    def export_settings(self) -> dict[str, Any]:
        keys = (
            "source_kind",
            "sim_e_low",
            "sim_e_high",
            "sim_s",
            "sim_concentration",
            "sim_seed",
            "speed",
            "setup_address",
            "sim_scheme",
            "preset",
            "alex_period_us",
            "realism_preset",
            "recording_store",
            "min_photons",
            "window_photons",
            "window_time_ms",
            "duration_s",
            "laser_kind",
            "mode",
            "trace_window_s",
            "trace_bin_ms",
            "img_beads",
            "img_tau_1_ns",
            "img_tau_2_ns",
            "img_brightness",
            "img_sample",
            "img_bleach_s",
            "point_time_s",
            "until_bleached",
            "autopick_max",
            "autopick_min",
            "autopick_max_brightness",
            "scanner_address",
            "survey_area_kind",
            "survey_x0_um",
            "survey_y0_um",
            "survey_w_um",
            "survey_h_um",
            "survey_overlap_um",
            "survey_order",
            "survey_learning",
            "survey_centre",
            "survey_guard_px",
            "survey_min_molecules",
            "survey_max_tiles",
            "survey_max_molecules",
            "survey_max_minutes",
            "survey_max_empty",
            "survey_reimage",
            "settings_address",
            "advanced",
        ) + tuple(f"scan_{name}" for name in RecordModel._SCAN_FIELDS)
        saved = {k: getattr(self.model, k) for k in keys}
        saved["video"] = {k: getattr(self.video, k) for k in ("address", "output", "fps", "display_gain")}
        return saved

    def restore_settings(self, settings: dict[str, Any]) -> None:
        for key, value in (settings or {}).get("video", {}).items():
            if key in ("address", "output", "fps", "display_gain"):
                setattr(self.video, key, value)
        for key, value in (settings or {}).items():
            if hasattr(self.model, key) and not key.startswith("_"):
                setattr(self.model, key, value)
        # The settings last used on the hardware are loaded again on start: device and laser
        # connected, the form filled (only for a device source; a simulation connects nothing).
        if (settings or {}).get("settings_address") and self.model.source_kind == "device":
            self.model.settings_chosen()

    def close(self) -> None:
        self.video.close()
        self.model.close()


def make_app() -> RecordApp:
    """The acq plugin's window: the Record tool."""
    from chisurf.emtk.i18n import install

    install()
    return RecordApp()
