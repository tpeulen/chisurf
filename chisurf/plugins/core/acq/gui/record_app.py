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
import math
import sys
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
from chisurf.plugins.core.acq.gui.refreshed import holds_hardware
from chisurf.plugins.core.acq.gui.record_survey import SurveyMixin, draw_survey_map
from chisurf.plugins.core.acq.gui.record_windows import WindowCheckMixin
from chisurf.plugins.core.acq.gui.power_controls import AveragePowerMixin
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


class RecordModel(AveragePowerMixin, LaserSettingsMixin, ScanPointsMixin, SurveyMixin, WindowCheckMixin):
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
        self.archive_directory: str | None = None  # provided explicitly by the selected profile
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
        self.laser_custom_names: dict[int, str] = {}
        # -- Point (smFRET) or Image (a scan) -------------------------------------------------
        self.mode = "point"
        self.pol_g_factor = 1.0
        self.pol_l1 = 0.0
        self.pol_l2 = 0.0
        self.pol_ref_r = 0.0
        self.pol_par_channel = 0
        self.pol_perp_channel = 1
        #: Advanced: show the device's thresholds, shifts, timing and markers. Off by default:
        #: a settings file or profile sets them, and a stray edit spoils a calibrated setup.
        self.advanced = False
        self.ui_mode = "simple"
        self._last_ui_mode = "simple"
        self._guided_start_authorized = False
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
        #: a fresh recording is kept as its own .ptu file the project links (the default: the
        #: photons stay a separate file on disk, the archive picks them up from there); Embed
        #: stores a copy inside the project instead
        self.recording_store = "link"
        self.saved_path: Path | None = None
        #: every recording started from this window, handed to the archive when the tool closes
        self.recorded_paths: list[Path] = []
        #: stop a run after Duration (off by default: a run measures until Stop, truly
        #: indefinitely -- nothing stops it in the background)
        self.stop_after = False
        # -- adjustable plot viewing ranges (0 = the data's full range) ----------------------------
        self.rates_x_min = self.rates_x_max = self.rates_y_max = 0.0
        self.decays_x_min = self.decays_x_max = self.decays_y_max = 0.0
        self.decay_bursts_only = False
        self.hist_x_min = self.hist_x_max = self.hist_y_max = 0.0
        self.hist_scale = 1  # 0 linear, 1 log10(1 + counts)
        self.hist_colormap = 0
        self.hist_count_cap = 0.0  # 0 uses the full data range
        # -- the session's metadata, collected at startup, carried in every recording's header -----
        self.operator_name = ""
        self.project_name = ""
        self.sample_name = ""
        self.experiment_type = ""
        self.dye_names = ""
        # -- the archive transfer (the data-management backend registers the hook) ------------------
        #: ``hook(paths, progress)`` copies the session's recordings to the archive drive; this
        #: tool itself never moves or deletes anything
        self.transfer_hook = None
        self.transfer_status = tr("No transfer backend registered; recordings stay in place.")
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
        #: the connected device's input count rates (Hz, sync first), captured by the once-a-second
        #: poll while it does not measure -- the count-rate dock shows them before a run
        self.device_rates_hz: list[float] = []
        #: the device settings the panel edits, phacq's flat ``{name or name[input]: value}``;
        #: kept while disconnected (a settings file can bring them before the device is there)
        self.device_values: dict[str, Any] = {}
        #: the generated settings form of the connected device (``devices.settings_form``)
        self.device_form = None
        self._device_sent: dict[str, Any] = {}
        # -- the laser and the acquisition settings file (record_settings) --------------------
        self._init_laser_settings()
        self.init_average_power()
        self._init_window_check()
        # -- the scanner, the picked points and their measurements (record_points) ------------
        self._init_scan_points()
        # -- the survey: tile after tile, picked and measured (record_survey) -------------------
        self._init_survey()
        self._active_source_kind = self.source_kind
        self.test_mode = False
        self.overcount_alert = False
        self.overcount_message = ""
        self.overcount_override = False

    # -- point or image ---------------------------------------------------------------------------
    _SCAN_FIELDS = ("pixels_x", "pixels_y", "area_x_um", "area_y_um", "x0_um", "y0_um",
                    "dwell_ms", "frames", "bidirectional", "z_planes", "z_step_um")

    def mode_options(self) -> list:
        return [
            ("point", tr("smFRET (point)")),
            ("fcs", tr("FCS (correlation)")),
            ("pol", tr("Polarization (single-molecule)")),
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
            else tr("Press Load example, then Start: anisotropy and lifetime build up.")
            if self.mode == "pol"
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
        return [("link", tr("Separate PTU file (default)")),
                ("embed", tr("Embed in the project"))]

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
    @holds_hardware
    def connect_device(self) -> bool:
        if getattr(self, '_instrument_sim', None) is not None:
            self.device_text = tr('Select the device source before connecting a real device.')
            return False
        if self.device is not None or not devices.PHACQ:
            return False
        entry = devices.find_device(self.device_index)
        if entry is None:
            self.device_text = tr("Cannot connect: the device is not attached any more.")
            return False
        try:
            dev = devices.open_device(entry)
        except Exception as exc:  # noqa: BLE001 - busy, no permission, unsupported model
            import traceback

            traceback.print_exc()  # the launcher log carries it (acquisition.log)
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
            self.device_rates_hz = []
            self.device_text = tr("No device connected.")
        return True

    def apply_device_settings(self, dev, exp: Experiment) -> None:
        """Send every device setting the panel holds to *dev* (before a run)."""
        notes = devices.apply_settings(dev, self.device_values)
        if notes:
            raise RuntimeError("; ".join(notes))
        self._device_sent = dict(self.device_values)

    def update_device_parameter(self, key: str, value: Any) -> None:
        """Update a phacq device setting: applies to connected hardware or records in device_values."""
        self.device_values[key] = value
        if self.device is not None and not self.running:
            try:
                notes = devices.apply_settings(self.device, {key: value})
                self.device_values = dict(self.device.settings())
                if self.device_form is not None:
                    self.device_form.update_values(self.device_values)
                if notes:
                    head = self.device_text.split(" — ")[0]
                    self.device_text = f"{head} — " + "; ".join(notes)
            except Exception:
                pass

    def apply_device_preset(self, preset_name: str) -> None:
        """Apply a hardware preset (nim, ttl, spad, zero_offsets) across sync and detector channels."""
        n_ch = 4
        if self.device is not None:
            try:
                n_ch = self.device.information().number_of_channels
            except Exception:
                pass
        p = preset_name.lower()
        updates = {}
        if p == "nim":
            updates["sync_level_mv"] = -50
            updates["sync_cfd_discr_mv"] = -50
            updates["sync_edge"] = 0
            for i in range(n_ch):
                updates[f"input_level_mv[{i}]"] = -50
                updates[f"input_cfd_discr_mv[{i}]"] = -50
                updates[f"input_edge[{i}]"] = 0
        elif p == "ttl":
            updates["sync_level_mv"] = 1500
            updates["sync_cfd_discr_mv"] = 1500
            updates["sync_edge"] = 1
            for i in range(n_ch):
                updates[f"input_level_mv[{i}]"] = 1500
                updates[f"input_cfd_discr_mv[{i}]"] = 1500
                updates[f"input_edge[{i}]"] = 1
        elif p == "spad":
            updates["sync_level_mv"] = -50
            updates["sync_cfd_discr_mv"] = -50
            updates["sync_edge"] = 0
            for i in range(n_ch):
                updates[f"input_level_mv[{i}]"] = -80
                updates[f"input_cfd_discr_mv[{i}]"] = -80
                updates[f"input_edge[{i}]"] = 0
                updates[f"input_dead_time_ps[{i}]"] = 800
        elif p == "zero_offsets":
            updates["sync_offset_ps"] = 0
            for i in range(n_ch):
                updates[f"input_offset_ps[{i}]"] = 0

        self.device_values.update(updates)
        if self.device is not None and not self.running:
            try:
                devices.apply_settings(self.device, updates)
                self.device_values = dict(self.device.settings())
                if self.device_form is not None:
                    self.device_form.update_values(self.device_values)
            except Exception:
                pass

    def sync_rate_display(self) -> tuple[float, str, str]:
        """Live sync rate, formatted string, and health status ('ok', 'warn', 'none')."""
        rate = 0.0
        if getattr(self, "device_rates_hz", None):
            rate = float(self.device_rates_hz[0])
        elif getattr(self, "source_kind", "") == "simulator":
            try:
                n_micro, res = self._clock()
                rate = 1.0 / (n_micro * res) if (n_micro * res) > 0 else 80e6
            except Exception:
                rate = 80e6
        if rate >= 1e6:
            return rate, f"{rate / 1e6:.2f} MHz", "ok"
        elif rate >= 1e3:
            return rate, f"{rate / 1e3:.1f} kHz", "warn"
        elif rate > 0:
            return rate, f"{rate:.0f} Hz", "warn"
        return 0.0, "0 Hz (No Sync)", "none"

    def channel_info_list(self) -> list[dict]:
        """List of detector channels with live rates, thresholds, offsets, and overload status."""
        n_ch = 4
        if self.device is not None:
            try:
                n_ch = self.device.information().number_of_channels
            except Exception:
                pass
        rates = self.device_rates_hz[1:] if len(getattr(self, "device_rates_hz", [])) > 1 else []
        out = []
        for i in range(n_ch):
            rate_hz = float(rates[i]) if i < len(rates) else 0.0
            en = bool(self.device_values.get(f"input_enable[{i}]", True))
            lvl = int(self.device_values.get(f"input_level_mv[{i}]", self.device_values.get(f"input_cfd_discr_mv[{i}]", -50)))
            zx = int(self.device_values.get(f"input_cfd_zerox_mv[{i}]", 0))
            off = int(self.device_values.get(f"input_offset_ps[{i}]", 0))
            dt = int(self.device_values.get(f"input_dead_time_ps[{i}]", 800))
            rate_str = f"{rate_hz / 1e3:.1f} kHz" if rate_hz >= 1e3 else (f"{rate_hz:.0f} Hz" if rate_hz > 0 else "0 Hz")
            out.append({
                "index": i,
                "name": f"Det {i}",
                "enabled": en,
                "rate_hz": rate_hz,
                "rate_str": rate_str,
                "overload": rate_hz > 1e6,
                "level_mv": lvl,
                "zero_cross_mv": zx,
                "offset_ps": off,
                "dead_time_ps": dt,
            })
        return out

    def _update_rates(self, force: bool = False) -> None:
        """Count rates of the connected device while it does not measure (about once a second)."""
        if self.running:
            source = getattr(self.session, "source", None)
            rates = source.status().get("count_rates_hz") if source is not None else None
            if rates is not None:
                self.device_rates_hz = list(rates)
            return
        if self.device is None:
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
        self.device_rates_hz = [float(r) for r in rates]
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
            + self.library_setup_options()
            + rows
        )

    # The setups created in ChiSurf Settings (Detector setup): the same library Burst Analysis reads.
    LIBRARY_PREFIX = "library:"

    @staticmethod
    def _read_library() -> dict:
        from chisurf.core.setup_channel_definition import ChannelDefinition

        store = ChannelDefinition()
        store.refresh_setups()
        return dict(store.setups)

    def library_setups(self, fresh: bool = False) -> dict:
        """The setups of the Settings library: the last read at once (a frame), or read now
        (*fresh*, for an action). Reading opens the setup database -- ~0.2 s, never in a frame."""
        if getattr(self, "_library_refresh", None) is None:
            from .refreshed import Refreshed

            self._library_refresh = Refreshed(
                self._read_library, initial={}, on_change=getattr(self, "request_frame", None))
        if fresh:
            try:
                return self._library_refresh.now()
            except Exception:  # noqa: BLE001 - no store: the last list
                return self._library_refresh.value or {}
        return self._library_refresh.get() or {}

    def library_setup_options(self) -> list:
        return [
            (self.LIBRARY_PREFIX + name, tr("Setup: {name}").format(name=name))
            for name in sorted(self.library_setups())
        ]

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
        source = ImageSimSource(
            scan, self.imaging_sample(), self.realism(), speed=float(self.speed),
            realtime=self.realtime
        )
        if self.simulation_connected:
            from chisurf.plugins.core.acq.live.instrument_sim import SimulatedImagingIllumination
            return SimulatedImagingIllumination(self._instrument_sim, source, seed=self.sim_seed)
        return source

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

    @property
    def simulation_connected(self):
        rig=getattr(self,'_instrument_sim',None)
        return bool(rig is not None and self.laser is rig.laser and self.shutters is rig.shutters
                    and self.laser_connected and not rig.shutters.closed)

    def connect_instrument_simulator(self):
        if self.running or self.connecting:
            self.status_detail=tr('Stop local acquisition before changing the simulated instrument.')
            return False
        if self.simulation_connected:return True
        if self.device is not None or self.scanner is not None or self.shutters is not None or (self.laser_connected and self.laser.kind!='simulated'):
            self.status_detail=tr('Disconnect real instrument connections before using the complete simulator. No hardware was changed.')
            return False
        from chisurf.plugins.core.acq.live.instrument_sim import SimulationRig
        if self.laser_connected:self.laser.close()
        self._simulation_previous={key:getattr(self,key) for key in
            ('output_dir','archive_directory','setup_address','preset','window_override','gate_override','settings_setup','laser_kind')}
        self.output_dir=Path(self.output_dir)/'simulator' if Path(self.output_dir).name!='simulator' else Path(self.output_dir)
        self.archive_directory = None
        rig=self._instrument_sim=SimulationRig()
        self.laser,self.shutters=rig.laser,rig.shutters
        self.laser_kind='simulated'
        self.laser_form=None
        self.laser_program=self.laser.capture()
        self.laser_applied=True
        self.shutter_section=dict(rig.shutter_section)
        self._shutter_form_from_device()
        self.shutter_text=tr('SIMULATED excitation, green and red shutters + diode')
        self.source_kind='simulator';self.sim_scheme='pie'
        self.setup_address=DEFAULT_SETUP;self.preset=AUTO_PRESET
        self.window_override=None;self.gate_override={};self.settings_setup=None
        rig.seed_power_book(self.power_book)
        self.calibrate_max_power(max_uw=1000.0)
        # The operator's default powers (60 µW blue / 25 µW red) are the heads' targets:
        # the drives stay at zero while idle (passive dark capture), and starting a run
        # applies them together with the simulated emission.
        from chisurf.plugins.core.acq.live.instrument_sim import DEFAULT_LASER_TARGETS_UW
        self.power_targets_uw = {
            h.slot: DEFAULT_LASER_TARGETS_UW[int(h.wavelength_nm)]
            for h in self.laser.state().heads if h.wavelength_nm
            and int(h.wavelength_nm) in DEFAULT_LASER_TARGETS_UW
        }
        protocol=self.output_dir/'guided-protocol.json'
        if not protocol.exists():protocol.write_text(json.dumps(rig.default_protocol(),indent=2))
        self.power_poll(force=True)
        self.power_selected_slot=rig.laser.state().heads[0].slot
        self._laser_status()
        self.status_detail=tr('SIMULATION ONLY: two PIE heads, sequencer, shutters and diode. Synthetic calibration/results stay in the simulator folder.')
        return True

    def disconnect_instrument_simulator(self):
        if self.running or self.connecting or (self.power_servo is not None and self.power_servo.active):return False
        if getattr(self, '_instrument_sim', None) is None:return False
        self._instrument_sim.close()
        self._instrument_sim=None
        self.laser=None;self.shutters=None;self.shutter_form=None;self.shutter_section=None
        self.laser_applied=False;self._emission_on=False
        for key,value in self._simulation_previous.items():
            if key != 'output_dir' or Path(self.output_dir) == Path(value) / 'simulator':
                setattr(self,key,value)
        self._simulation_previous = {}
        self._power_book=None
        self.power_poll(force=True)
        self.status_detail=tr('Simulator disconnected. No real instrument was opened.')
        return True

    def source_changed(self, _value=None):
        """Change the source and its simulated instrument together, only while idle."""
        previous = self._active_source_kind
        selected = self.source_kind
        if selected not in ('simulator', 'replay', 'device'):
            self.source_kind = previous
            return False
        if self.running or self.connecting or (self.power_servo is not None and self.power_servo.active):
            self.source_kind = previous
            self.status_detail = tr('Stop acquisition and power adjustment before changing source.')
            return False
        if selected == 'simulator':
            if not self.connect_instrument_simulator():
                self.source_kind = previous
                return False
        elif getattr(self, '_instrument_sim', None) is not None:
            if not self.disconnect_instrument_simulator():
                self.source_kind = previous
                return False
        self._active_source_kind = selected
        self.replay_address = ''
        self.replay_scan = None
        return True

    def make_source(self):
        if self.mode == "image":
            return self.make_image_source()
        if self.source_kind == "simulator":
            if self.simulation_connected:
                populations = (Population(self.sim_e_low, self.sim_s, self.sim_concentration),
                               Population(self.sim_e_high, self.sim_s, self.sim_concentration))
                realism = self.realism()
                if self.mode == 'fcs':
                    realism, population = self.fcs_sample()
                    populations = (Population(0.0, 1.0, population, float(self.fcs_brightness_khz)),)
                return self._instrument_sim.source(seed=int(self.sim_seed),realtime=self.realtime,
                    speed=float(self.speed),duration_s=self._run_duration(),
                    populations=populations, realism=realism, scheme="two_color" if self.mode == "fcs" else "pie")
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
            elif self.setup_address.startswith(self.LIBRARY_PREFIX):
                name = self.setup_address[len(self.LIBRARY_PREFIX):]
                library = self.library_setups(fresh=True)  # it may have been edited in Settings
                if name not in library:
                    raise ValueError(f"The setup {name!r} is no longer in the Settings library.")
                setup = dict(library[name])
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
        if action == 'source_kind':
            return not self.running and not self.connecting and not (self.power_servo is not None and self.power_servo.active)
        if getattr(self, '_instrument_sim', None) is not None and action in (
                'laser_kind', 'connect_laser', 'disconnect_laser', 'connect_scanner', 'connect_device'):
            return False
        if action=='request_settings_file':return self.can_load_settings_file()
        if action=='connect_instrument_simulator':return not self.running and not self.simulation_connected
        if action=='disconnect_instrument_simulator':return not self.running and self.simulation_connected
        if self.ui_mode == "guided" and action in ("start", "start_pause", "connect_device", "load_example", "load_settings"):
            return False
        if action == "ui_mode":
            return not self.running and not (self.power_servo is not None and self.power_servo.active)
        if action in ("power_selected_slot", "power_target_uw", "set_power_target", "isolate_power_laser"):
            return not (self.power_servo is not None and self.power_servo.active)
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
        if action == "start_pause":
            return (self.mode == "point" and not self.points_running) if self.running else self.enabled("start")
        if action == "start":
            if self.power_servo is not None and self.power_servo.active:
                return False
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

    def ui_mode_options(self):
        return [("simple", tr("Simple")), ("advanced", tr("Advanced")), ("guided", tr("Guided"))]

    def ui_mode_changed(self, _value=None):
        if self.running or (self.power_servo is not None and self.power_servo.active):
            self.ui_mode = self._last_ui_mode
            self.status_detail = tr("Stop the measurement or power adjustment before changing user mode.")
            return False
        if self.ui_mode not in ("simple", "advanced", "guided"):
            self.ui_mode = "simple"
        if self.ui_mode=='guided' and self.source_kind=='simulator' and not self.simulation_connected:
            if not self.connect_instrument_simulator():
                self.ui_mode=self._last_ui_mode
                return False
        if self.ui_mode == 'guided' and self._last_ui_mode != 'guided':
            self._guided_configure_allowed = self._last_ui_mode == 'advanced'
        self._last_ui_mode = self.ui_mode
        self.advanced = self.ui_mode == "advanced"
        self.advanced_changed()
        return True

    def load_example(self) -> None:
        """Set the example's source and setup up; the run's length (Stop after, Duration) is
        the user's and is not touched."""
        self.source_kind = "simulator"
        if self.mode == "fcs":
            self.source_kind = "simulator"
            self.sim_scheme = "two_color"
            self.fcs_n, self.fcs_d_um2_per_s, self.fcs_brightness_khz = 4.0, 80.0, 150.0
            if self.laser is not None:
                self.laser.set_head(200, enabled=True, intensity_pct=100.0)
                self.laser.set_emission(True)
            if self.shutters is not None:
                self.shutters.set_parameter("open_excitation", True)
                self.shutters.set_parameter("open_green", True)
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
            if self.laser is not None:
                self.laser.set_head(200, enabled=True, intensity_pct=100.0)
                self.laser.set_emission(True)
            if self.shutters is not None:
                self.shutters.set_parameter("open_excitation", True)
                self.shutters.set_parameter("open_green", True)
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
        self.sim_e_low, self.sim_e_high, self.sim_s = 0.25, 0.75, 0.5
        self.sim_concentration = 1.0
        self.min_photons, self.window_photons, self.window_time_ms = 30, 10, 1.0
        self.setup_address = DEFAULT_SETUP
        self.sim_scheme, self.preset = "pie", AUTO_PRESET
        if self.laser is not None:
            self.laser.set_head(200, enabled=True, intensity_pct=100.0)
            self.laser.set_head(300, enabled=True, intensity_pct=100.0)
            self.laser.set_emission(True)
        if self.shutters is not None:
            self.shutters.set_parameter("open_excitation", True)
            self.shutters.set_parameter("open_green", True)
            self.shutters.set_parameter("open_red", True)
        self.realism_preset = "realistic"
        self._set_realism(REALISTIC)
        self.status_text = tr("Example ready")
        self.status_detail = tr(
            "PIE, two FRET populations (E 0.25 and 0.75, S 0.5) in a realistic sample: donor-only and "
            "acceptor-only molecules, bleaching, crosstalk, background. Press Start."
        )

    def load_settings(self) -> bool:
        """Load a chosen profile and adopt its explicitly configured storage paths."""
        from chisurf.plugins.core.acq.live import settings_file
        from chisurf.plugins.core.acq.live.storage_config import StorageConfig, StorageConfigError

        kind, address = self._picked()
        if kind not in ("setup", "profile"):
            return False
        try:
            doc = settings_file.load(address)
            storage = StorageConfig.from_document(doc) if "storage" in doc else None
        except (settings_file.SettingsError, StorageConfigError) as exc:
            self.settings_text, self.settings_detail = tr("Not a settings file"), str(exc)
            return False
        if not self.adopt_settings(doc, Path(address).name, []):
            return False
        if storage is not None and getattr(self, '_instrument_sim', None) is None:
            self.output_dir = Path(storage.local_directory)
            self.archive_directory = storage.archive_directory
        elif storage is not None:
            self.settings_detail += tr(' Profile storage is not used during simulation.')
        return True

    def _run_duration(self) -> float | None:
        """The duration a run is limited to: Duration with Stop after checked, else unlimited."""
        if not self.stop_after:
            return None
        return float(self.duration_s) or None

    def _device_backend_limit(self) -> str:
        """Why an unattended run on the connected device is *not* known to be unlimited, or
        ``""`` with no such device.

        Prefer the driver's declared single-acquisition limit. Current pqusb advertises
        100 hours; legacy builds without that capability used a one-hour fallback. Neither
        finite timer is represented as unlimited, and no timestamp-resetting restarts are
        silently used to extend a recording.
        """
        dev = self.device
        if dev is None:
            return ""
        limit=getattr(dev,'acquisition_limit_s',None)
        try:
            hours=float(limit)/3600. if limit is not None else 0.
        except (ValueError,TypeError):
            hours=0.
        if np.isfinite(hours) and hours>0:
            return tr('This backend supports one acquisition of up to {hours:g} h. An unchecked run uses that maximum; it is not unlimited. No timer restarts or timestamp splices are performed.').format(hours=hours)
        try:
            info = dev.information()
            features = {str(f) for f in getattr(info, "features", ()) or ()}
            model = str(getattr(info, "model", "") or "")
        except Exception:  # noqa: BLE001 - a device that cannot describe itself: stay careful
            features, model = set(), ""
        driver = str(getattr(dev, "phacq_driver", "") or "")
        if "pqusb" in features or driver == "pqusb" or model == "HydraHarp 400":
            return tr(
                "This unit's pqusb backend measures a fixed time (an unchecked run gets 1 h, "
                "then the hardware stops itself): it is not unlimited. Tick Stop after for a "
                "chosen length, or stop the run yourself before the hour ends."
            )
        return tr(
            "No backend here demonstrates a truly unlimited acquisition: an unchecked run may "
            "end on the hardware's own timer. Tick Stop after for a guaranteed length."
        )

    @property
    def device_limit_text(self) -> str:
        """The unattended-run caveat of the device source, shown in the Run panel."""
        if self.source_kind != "device":
            return ""
        return self._device_backend_limit()

    def _note_backend_limit(self) -> None:
        """An unchecked run on a device is finite (the backend starts a fixed time): say so
        where the run's status is read."""
        if self.source_kind == "device" and self._run_duration() is None:
            note = self._device_backend_limit()
            if note:
                self.status_detail = f"{self.status_detail} — {note}"

    def start(self) -> bool:
        from chisurf.plugins.core.acq.live.image_storage import validate_name

        name = self.run_name.strip().replace("{date}", time.strftime("%Y%m%d_%H%M%S"))
        name = name or time.strftime("record_%Y%m%d_%H%M%S")
        try:
            validate_name(name)
        except ValueError as exc:
            self.status_text, self.status_detail = tr("Cannot start"), str(exc)
            return False
        if getattr(self, '_instrument_sim', None) is not None and not self.simulation_connected:
            self.status_detail = tr('The simulated instrument is disconnected. Select the simulator again while idle.')
            return False
        if self.source_kind != 'simulator' and getattr(self, '_instrument_sim', None) is not None:
            self.status_detail = tr('Select the source while idle before starting.')
            return False
        if self.power_servo is not None and self.power_servo.active:
            self.status_detail = tr("Wait for the power target to be verified, or cancel power adjustment first.")
            return False
        if self.ui_mode == "guided" and not self._guided_start_authorized:
            self.status_detail = tr("Guided measurements can be started only by the current wizard step.")
            return False
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
        name = self.unique_name(name)
        self.overcount_alert = False
        self.overcount_message = ""
        if not self.advanced:
            all_shutters = self._shutter_names()
            if all_shutters:
                self._set_shutters({n: True for n in all_shutters})
            else:
                self.set_shutter('Excitation', True)
        if self.simulation_connected and self.laser is not None:
            # Simulated light only: a run switches the (simulated) emission on and applies
            # the default powers to heads the operator left at zero, so Start measures
            # instead of recording dark. Real hardware is never touched here; its emission
            # stays bound to the operator's explicit gestures.
            try:
                from chisurf.plugins.core.acq.live.instrument_sim import (
                    laser_diode_drive_for_power,
                )
                from chisurf.plugins.core.acq.live.laser import laser_diode_threshold

                max_uw = max((p[1] for name in self.power_book.lasers()
                              for p in self.power_book.points(name)),
                             default=1000.0) or 1000.0
                for head in self.laser.state().heads:
                    target = self.power_targets_uw.get(head.slot)
                    if target and head.intensity_pct <= 0.0:
                        drive = laser_diode_drive_for_power(
                            float(target), float(max_uw), laser_diode_threshold(head))
                        if drive > 0.0:
                            self.laser.set_head(head.slot, enabled=True, intensity_pct=drive)
                if self.laser.state().emission_blocked:
                    self.laser.set_emission(True)
                self.power_poll(force=True)
            except Exception:  # noqa: BLE001 - a run must not fail on the sim's laser bookkeeping
                pass
        if self.mode == "image":
            return self._start_image(source, experiment, name)
        if self.mode == "fcs":
            return self._start_fcs(source, experiment, name)
        if self.test_mode:
            self.saved_path = None
        else:
            self.saved_path = recording_dir(self.output_dir) / f"{name}.ptu"
            self.recorded_paths.append(self.saved_path)
        self._run_shutters(True)
        session_type=RecordSession
        session_options={}
        if self._guided_start_authorized:
            from chisurf.plugins.core.acq.live.guided_analysis import GuidedRecordSession
            session_type=GuidedRecordSession
            session_options={'stage':self._guided_analysis_stage,'reference_limits':self._guided_analysis_limits}
        self.session = session_type(
            source,
            experiment,
            duration_s=self._run_duration(),
            ptu_path=self.saved_path,
            name=name,
            embed=self.recording_store == "embed",
            settings=self._run_settings(),
            header_tags=self.run_header_tags(),
            trace_window_s=float(self.trace_window_s),
            trace_bin_s=float(self.trace_bin_ms) / 1e3,
            **session_options,
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
        if self.test_mode:
            self.status_text = tr("Testing…")
            self.status_detail = tr("Test mode: no data written to disk")
        else:
            self.status_text = tr("Recording…")
            self.status_detail = str(self.saved_path)
        self._note_backend_limit()
        return True

    def _start_fcs(self, source, experiment, name: str) -> bool:
        """Start an FCS point measurement: the correlation builds up; the photons are recorded."""
        if self.test_mode:
            self.saved_path = None
        else:
            self.saved_path = recording_dir(self.output_dir) / f"{name}.ptu"
            self.recorded_paths.append(self.saved_path)
        truth = None
        if self.source_kind == "simulator":
            real, population = self.fcs_sample()
            truth = fcs_truth(real, population)
        self._run_shutters(True)
        self.session = FcsRecordSession(
            source,
            experiment,
            truth=truth,
            duration_s=self._run_duration(),
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
        if self.test_mode:
            self.status_text = tr("Testing…")
            self.status_detail = tr("Test mode: no data written to disk")
        else:
            self.status_text = tr("Recording…")
            self.status_detail = str(self.saved_path)
        self._note_backend_limit()
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
        if replay or self.test_mode:
            self.saved_path = None
        else:
            from chisurf.plugins.core.acq.live.image_storage import allocate_image

            try:
                name, self.saved_path = allocate_image(recording_dir(self.output_dir), name)
            except OSError as exc:
                self.status_text, self.status_detail = tr("Cannot start"), str(exc)
                return False
        if self.saved_path is not None:
            self.recorded_paths.append(self.saved_path)
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

    def run_header_tags(self) -> dict:
        """The settings' tags, plus the session's metadata (who measured what, in the header of
        every recording -- what the archive's transfer reads)."""
        tags = super().run_header_tags()
        if self.simulation_connected:
            tags['ChiSurf_Simulation']=json.dumps({'simulation':True,'stage':self._instrument_sim.stage,
                'notice':'Synthetic instrument and calibration. Not a laboratory reference.'})
        for key, value in (
            ("Operator", self.operator_name),
            ("Project", self.project_name),
            ("Sample", self.sample_name),
            ("ExperimentType", self.experiment_type),
            ("Dyes", self.dye_names),
        ):
            if str(value).strip():
                tags[f"ChiSurf_{key}"] = str(value).strip()
        return tags

    #: The status words of the quality lights, per check row of the quality table.
    _QUALITY_STATUS = {
        "green": tr("good"),
        "amber": tr("watch"),
        "red": tr("act now"),
        "grey": tr("no verdict"),
    }

    def count_rate_rows(self) -> list[dict]:
        """One aligned row per hardware input, with live-analysis fallback and a mean."""
        rates = []
        snap=self.snapshot or {}
        raw_t = float(snap.get('received_elapsed_s', 0.0))
        mean = (float(snap['received_photons']) / raw_t if raw_t > 0 else None) if 'received_photons' in snap else snap.get('count_rate_hz')
        if 'received_photons' not in snap and mean is None and snap.get('photons') is not None and float(snap.get('elapsed_s',0))>0:
            mean=float(snap['photons'])/float(snap['elapsed_s'])
        detected = detector_rates(self.snapshot)
        if detected:
            rates = []
            if self.device_rates_hz:
                rates.append((tr('Sync'), self.device_rates_hz[0]))
            rates.extend([(row['name'], row['khz'] * 1e3)
                          for row in detected])
            if mean is None and 'received_photons' not in snap:
                mean_khz = overall_mean_khz(self.snapshot)
                mean = mean_khz * 1e3 if mean_khz is not None else None
        elif self.device_rates_hz:
            rates = [(tr('Sync') if i == 0 else tr('Detector {n}').format(n=i-1), hz)
                     for i, hz in enumerate(self.device_rates_hz)]
        if mean is not None:
            rates.append((tr('Mean recorded'), mean))
        rows = []
        for channel, hz in rates:
            hz = float(hz)
            if not np.isfinite(hz) or hz < 0:
                rows.append({'channel': channel, 'value': '—', 'unit': ''})
                continue
            divisor, unit = ((1e6, 'MHz') if hz >= 1e6 else
                             (1e3, 'kHz') if hz >= 1e3 else (1., 'Hz'))
            rows.append({'channel': channel, 'value': hz / divisor, 'unit': unit})
        return rows or [{'channel': tr('Not connected'), 'value': '—', 'unit': ''}]

    def align_count_rate(self, row) -> bool:
        """Request the read-only alignment monitor for the activated rate row."""
        if not isinstance(row,dict) or not row.get('channel'):
            return False
        self.alignment_channel=str(row['channel'])
        self.alignment_requested=True
        return True

    def quality_rows(self) -> list[dict]:
        """The quality checker's checks as the Quality dock's table rows: the metric, its
        measured value, the configured acceptable range (only what the checker itself
        configures -- none is invented here), the status light as a word, and the guidance.

        Rows carry ``detail`` for the tooltip; with no verdict yet there is one row saying why.
        """
        qc = (self.snapshot or {}).get("qc") or {}
        if not qc.get("ready"):
            return [{
                "metric": tr("quality"),
                "value": "—",
                "acceptable": "—",
                "status": tr("no verdict"),
                "guidance": qc.get("why") or tr("Not enough bursts yet."),
                "detail": qc.get("why") or tr("Not enough bursts yet."),
            }]
        rows = []
        for check in qc.get("checks") or ():
            guidance = str(check.get("action") or check.get("detail") or "")
            detail = str(check.get("detail") or "")
            if check.get("action"):
                detail = f"{detail}\n\n{check['action']}".strip()
            rows.append({
                "metric": str(check.get("name", "")),
                "value": str(check.get("value", "")),
                # the checker's own configured range when it names one; never a made-up bound
                "acceptable": str(check.get("range") or "—"),
                "status": self._QUALITY_STATUS.get(str(check.get("light", "grey")),
                                                   tr("no verdict")),
                "guidance": guidance,
                "detail": detail,
            })
        return rows or [{
            "metric": tr("quality"), "value": "—", "acceptable": "—",
            "status": tr("no verdict"), "guidance": tr("This measurement type has no checks."),
            "detail": "",
        }]

    def transfer_pending(self, paths: list[Path] | None = None) -> bool:
        """Hand this session's recordings to the registered transfer hook (the archive drive's
        backend). This tool itself never moves or deletes: the hook copies; a failure leaves
        every file in place, is reported in the status and logged beside the recordings for a
        retry. Returns whether a transfer went through."""
        if self.transfer_hook is None:
            self.transfer_status = tr("No transfer backend registered; recordings stay in place.")
            return False
        files = [Path(p) for p in (paths or self.recorded_paths)]
        files = [p for p in files if p.exists()]
        if not files:
            self.transfer_status = tr("Nothing to transfer.")
            return False

        def progress(fraction: float, note: str = "") -> None:
            self.transfer_status = tr("Transferring… {p:.0f} %").format(
                p=float(fraction) * 100.0) + (f" · {note}" if note else "")

        try:
            self.transfer_hook(files, progress)
        except Exception as exc:  # noqa: BLE001 - nothing is lost: the files stay
            self.transfer_status = tr(
                "Transfer failed ({e}); the recordings stay in place.").format(e=exc)
            self._log_transfer("failed", files, str(exc))
            return False
        self.transfer_status = tr("Transferred {n} recording(s).").format(n=len(files))
        self._log_transfer("transferred", files, "")
        return True

    def _log_transfer(self, status: str, files: list[Path], error: str) -> None:
        """One JSON line beside the recordings: what was transferred, or what to retry."""
        try:
            log = recording_dir(self.output_dir) / "transfer_log.jsonl"
            entry = json.dumps({
                "status": status, "error": error,
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "files": [str(p) for p in files],
            })
            with log.open("a", encoding="utf-8") as fh:
                fh.write(entry + "\n")
        except OSError:
            pass  # a log is best effort; the transfer's result stands either way

    def _run_settings(self) -> dict | None:
        """The settings document the recording's header carries (``None`` if it cannot be made)."""
        from chisurf.plugins.core.acq.live import settings_file

        doc = self.current_settings()
        return doc if not settings_file.validate(doc) else None

    def start_pause(self) -> bool:
        """Start a new file, or mark an analysis pause while recording continues."""
        if not self.running:
            return self.start()
        if self.mode != "point" or self.points_running or type(self.session) is not RecordSession:
            self.status_detail = tr("Analysis pause is available for point photon recordings only.")
            return False
        requested = self.session._pause_requested.is_set()
        ok = self.session.resume() if requested else self.session.pause()
        if ok:
            self.status_text = tr("Ending pause" if requested else "Pausing analysis")
            self.status_detail = tr("Raw photons continue to be saved. Live analysis remains incomplete after a pause; start a new run to resume it.")
        else:
            self.status_detail = self.session.pause_error
        return ok

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
        self.power_poll(force)
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
            if self.snapshot.get("source_error"):
                self.status_detail = self.snapshot["source_error"]
            elif self.snapshot.get("analysis_warning"):
                self.status_detail = self.snapshot["analysis_warning"]
            if type(session) is RecordSession and session.running:
                self.status_text = tr("Analysis paused; recording" if session.paused else "Recording")
            if isinstance(session, ImageRecordSession):
                self.image_snapshot = self.snapshot
        # Count rate limit (> 1 MHz/ch) detector protection in simple/basic mode
        if session.running and not self.advanced and not getattr(self, "overcount_override", False):
            rates = []
            if self.device_rates_hz and len(self.device_rates_hz) > 1:
                rates.extend(self.device_rates_hz[1:])
            snap = self.snapshot or {}
            for r in detector_rates(snap):
                rates.append(float(r.get("khz", 0.0)) * 1e3)
                rates.append(float(r.get("mean_khz", 0.0)) * 1e3)
            if snap.get("count_rate_hz") is not None:
                rates.append(float(snap["count_rate_hz"]))
            if any(rate > 1_000_000.0 for rate in rates):
                self.set_shutter("Excitation", False)
                self.overcount_alert = True
                self.overcount_message = tr("Count rate exceeded 1 MHz per channel! Excitation shutter closed to protect detectors.")
                self.status_detail = tr("Count rate > 1 MHz/ch — Excitation shutter closed.")
        if not session.running and session.result is not None and not self._registered:
            self._registered = True
            # a run's end closes the shutters the settings name (the excitation one); the laser
            # is not touched -- the shutter keeps the light off the sample
            self._run_shutters(False)
            self.snapshot = session.snapshot()
            if getattr(self, "test_mode", False):
                self.status_text = tr("Finished")
                self.status_detail = tr("Test measurement finished (no data written to disk).")
                return
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
            recording_error = session.error or (self.snapshot or {}).get("source_error")
            if recording_error:
                self.status_text = tr("Recording error")
                self.status_detail += " " + str(recording_error)
                return
            if not result.analysis_complete:
                self.status_text = tr("Live analysis incomplete")
                warning = (self.snapshot or {}).get("analysis_warning")
                self.status_detail += " " + (warning or tr("Live analysis contains a gap; raw recording status is reported separately."))
                return
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
            if session.error or snap.get("source_error"):
                self.status_text = tr("Recording error")
                self.status_detail += " " + str(session.error or snap["source_error"])
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
        self.status_text = tr("{reason}: {frames} frame(s), {photons:,} analyzed photons").format(
            reason=result.stop_reason.capitalize(), frames=frames, photons=result.photons
        )
        if session.error or snap.get("source_error"):
            self.status_text = tr("Recording error")
            self.status_detail += " " + str(session.error or snap["source_error"])
            return
        if not result.analysis_complete:
            self.status_text = tr("Live image analysis incomplete")
            self.status_detail += " " + (snap.get("analysis_warning") or tr("Live image analysis contains a gap."))

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


def _amplitude(tau: np.ndarray, g: np.ndarray) -> float:
    """G(0)-1 read on the plateau between 10 us and 50 us (past afterpulsing, before diffusion)."""
    tau = np.asarray(tau, dtype=float)
    g = np.asarray(g, dtype=float)
    sel = (tau >= 1e-5) & (tau <= 5e-5) & np.isfinite(g)
    if not sel.any():
        sel = np.isfinite(g) & (tau > 0)
        if not sel.any():
            return 0.0
        return float(np.nanmax(g[sel]))
    return float(np.nanmedian(g[sel]))


def _estimate_diffusion_time_s(tau, g) -> float | None:
    """Estimate empirical diffusion time tau_D (s) as lag where G(tau)-1 decays to half of plateau."""
    tau = np.asarray(tau, dtype=float)
    g = np.asarray(g, dtype=float)
    sel = (tau >= 1e-5) & (tau <= 5e-5) & np.isfinite(g)
    amp = float(np.nanmedian(g[sel])) if sel.any() else (float(np.nanmax(g[tau > 0])) if (tau > 0).any() else 0.0)
    if amp <= 0:
        return None
    half = amp / 2.0
    post = (tau >= 1e-5) & np.isfinite(g)
    if not post.any():
        return None
    post_tau, post_g = tau[post], g[post]
    idx = np.where(post_g <= half)[0]
    if len(idx) > 0:
        i = idx[0]
        if i == 0:
            return float(post_tau[0])
        t0, t1 = float(post_tau[i - 1]), float(post_tau[i])
        g0, g1 = float(post_g[i - 1]), float(post_g[i])
        if g1 != g0:
            return float(t0 + (half - g0) / (g1 - g0) * (t1 - t0))
        return float(t0)
    return None


def _fit_fcs_curve(tau: np.ndarray, g: np.ndarray, s_kappa: float, bunching_mdl: int) -> dict:
    """Fit 3D Gaussian diffusion + 0, 1, or 2 bunching components to G(tau)-1."""
    from scipy.optimize import curve_fit

    mask = (tau > 0) & np.isfinite(g) & (tau >= 1e-6)
    tau_fit = tau[mask]
    g_fit = g[mask]
    if tau_fit.size < 5:
        return {}

    s_val = max(0.5, float(s_kappa))
    s2 = s_val * s_val

    sel_amp = (tau >= 1e-5) & (tau <= 5e-5) & np.isfinite(g)
    amp = float(np.nanmedian(g[sel_amp])) if sel_amp.any() else (float(np.nanmax(g_fit)) if g_fit.size else 0.5)
    n0 = 1.0 / max(1e-4, amp)

    half_g = amp * 0.5
    idx = np.where(g_fit <= half_g)[0]
    tau_d0 = float(tau_fit[idx[0]]) if idx.size > 0 else 2e-4
    tau_d0 = np.clip(tau_d0, 1e-5, 0.1)

    try:
        if bunching_mdl == 0:
            def f0(t, N, tau_d):
                return (1.0 / N) * (1.0 / (1.0 + t / tau_d)) * (1.0 / np.sqrt(1.0 + t / (s2 * tau_d)))
            popt, _ = curve_fit(f0, tau_fit, g_fit, p0=[n0, tau_d0],
                                bounds=([1e-3, 1e-6], [1e6, 1.0]), maxfev=800)
            n_bright, tau_d = popt
            f_dark = 0.0
            b1 = t1 = b2 = t2 = 0.0
        elif bunching_mdl == 2:
            def f2(t, N, tau_d, b1, t1, b2, t2):
                diff = (1.0 / N) * (1.0 / (1.0 + t / tau_d)) * (1.0 / np.sqrt(1.0 + t / (s2 * tau_d)))
                bunch = (1.0 - b1 - b2) + b1 * np.exp(-t / t1) + b2 * np.exp(-t / t2)
                return diff * bunch
            popt, _ = curve_fit(f2, tau_fit, g_fit,
                                p0=[n0, tau_d0, 0.1, 3e-6, 0.05, 50e-6],
                                bounds=([1e-3, 1e-6, 0.0, 1e-7, 0.0, 1e-6],
                                        [1e6, 1.0, 0.5, 1e-4, 0.49, 1e-3]), maxfev=1000)
            n_bright, tau_d, b1, t1, b2, t2 = popt
            f_dark = min(0.95, b1 + b2)
        else:
            def f1(t, N, tau_d, b1, t1):
                diff = (1.0 / N) * (1.0 / (1.0 + t / tau_d)) * (1.0 / np.sqrt(1.0 + t / (s2 * tau_d)))
                bunch = (1.0 - b1) + b1 * np.exp(-t / t1)
                return diff * bunch
            popt, _ = curve_fit(f1, tau_fit, g_fit,
                                p0=[n0, tau_d0, 0.1, 3e-6],
                                bounds=([1e-3, 1e-6, 0.0, 1e-7],
                                        [1e6, 1.0, 0.95, 1e-4]), maxfev=800)
            n_bright, tau_d, b1, t1 = popt
            f_dark = min(0.95, b1)
            b2 = t2 = 0.0

        n_total = n_bright / max(1e-4, (1.0 - f_dark))
        tau_smooth = np.logspace(np.log10(max(1e-6, tau_fit[0])), np.log10(tau_fit[-1]), 80)
        diff_s = (1.0 / n_bright) * (1.0 / (1.0 + tau_smooth / tau_d)) * (1.0 / np.sqrt(1.0 + tau_smooth / (s2 * tau_d)))
        if bunching_mdl == 0:
            g_model = diff_s
        elif bunching_mdl == 2:
            g_model = diff_s * ((1.0 - b1 - b2) + b1 * np.exp(-tau_smooth / t1) + b2 * np.exp(-tau_smooth / t2))
        else:
            g_model = diff_s * ((1.0 - b1) + b1 * np.exp(-tau_smooth / t1))

        return {
            "success": True,
            "n_bright": float(n_bright),
            "n_total": float(n_total),
            "tau_d_s": float(tau_d),
            "f_dark": float(f_dark),
            "b1": float(b1), "t1": float(t1),
            "b2": float(b2), "t2": float(t2),
            "tau_smooth": tau_smooth,
            "g_model": g_model,
        }
    except Exception:
        return {}


def _plot_correlation(corr: dict, height: float, fit_tau: np.ndarray | None = None, fit_g: np.ndarray | None = None) -> None:
    """The live correlation curve G(tau) - 1 on a logarithmic lag axis with optional model fit overlay."""
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
        if fit_tau is not None and fit_g is not None and len(fit_tau) > 0:
            implot.plot_line(tr("fit (diffusion + bunching)"), fit_tau, fit_g)
        implot.end_plot()


def _histogram_display_grid(counts, scale: str, cap: float):
    """Return display-only values and upper scale in linear or log10(1+count)."""
    grid = np.maximum(np.asarray(counts, dtype=float), 0.0)
    limit = float(cap) if cap > 0 else max(1.0, float(grid.max(initial=0.0)))
    grid = np.minimum(grid, limit)
    if scale == "log":
        return np.log10(1.0 + grid), float(np.log10(1.0 + limit))
    return grid, limit


def _plot_histogram(hist: dict, height: float, view: tuple[float, float, float] = (0.0, 0.0, 0.0),
                    *, scale: str = "log", cap: float = 0.0, colormap: str = "Viridis") -> None:
    """One of the analyzer's histograms: 1-D as bars, 2-D as a heatmap with both marginals.

    *view* is the user's viewing range (x min, x max, y max; 0 = the data's full range)."""
    from emtk import implot

    counts = np.asarray(hist["counts"], dtype=float)
    xe = np.asarray(hist["x_edges"], dtype=float)
    xc = (xe[:-1] + xe[1:]) / 2
    x_lo, x_hi = _view_limit(view[0], view[1], float(xe[0]), float(xe[-1]))
    width = im.get_content_region_avail()[0]
    if "y" not in hist:
        if implot.begin_plot("##hist1d", (width, height), implot.FLAGS_NO_TITLE):
            implot.setup_axes(hist["x"], tr("bursts"))
            implot.setup_axis_limits(implot.AXIS_X1, x_lo, x_hi, implot.COND_ALWAYS)
            if view[2]:
                implot.setup_axis_limits(
                    implot.AXIS_Y1, 0.0, float(view[2]), implot.COND_ALWAYS)
            implot.plot_bars(f"##{hist['x']}", xc, counts, bar_size=float(xe[1] - xe[0]))
            implot.end_plot()
        return
    ye = np.asarray(hist["y_edges"], dtype=float)
    yc = (ye[:-1] + ye[1:]) / 2
    y_lo, y_hi = _view_limit(0.0, view[2], float(ye[0]), float(ye[-1]))
    side = max(80.0, width * 0.22)
    main = max(160.0, width - side - 12.0)
    marg_h = max(70.0, height * 0.28)
    if implot.begin_plot("##x_marginal", (main, marg_h), implot.FLAGS_NO_TITLE):
        implot.setup_axes(None, tr("bursts"))
        implot.setup_axis_limits(implot.AXIS_X1, x_lo, x_hi, implot.COND_ALWAYS)
        implot.plot_bars(f"##{hist['x']}", xc, counts.sum(axis=1), bar_size=float(xe[1] - xe[0]))
        implot.end_plot()
    if implot.begin_plot("##hist2d", (main, height - marg_h), implot.FLAGS_NO_TITLE):
        implot.setup_axes(hist["x"], hist["y"])
        implot.setup_axis_limits(implot.AXIS_X1, x_lo, x_hi, implot.COND_ALWAYS)
        implot.setup_axis_limits(implot.AXIS_Y1, y_lo, y_hi, implot.COND_ALWAYS)
        display, upper = _histogram_display_grid(counts, scale, cap)
        grid = np.ascontiguousarray(display.T[::-1])  # rows: y from top (high) down
        cmap = getattr(implot, "COLORMAP_" + colormap.upper(), implot.COLORMAP_VIRIDIS)
        implot.push_colormap(cmap)
        implot.plot_heatmap(
            "##counts",
            grid,
            grid.shape[0],
            grid.shape[1],
            0.0,
            upper,
            None,
            (float(xe[0]), float(ye[0])),
            (float(xe[-1]), float(ye[-1])),
        )
        implot.pop_colormap()
        implot.end_plot()
    im.same_line()
    if implot.begin_plot("##y_marginal", (side, height - marg_h), implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("bursts"), None)
        implot.setup_axis_limits(implot.AXIS_Y1, y_lo, y_hi, implot.COND_ALWAYS)
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
    (PIE: prompt/delayed x G|G/R|G), else per detector."""
    names = list((snap.get("decays") or snap.get("background_cps") or {}).keys())
    windowed = [n for n in names if " " in n]
    return windowed or names


def _detector_of_stream(name: str) -> str:
    """A stream's detector: the last word of a windowed stream ("prompt G|G" -> "G|G"),
    the name itself otherwise ("ch0") -- the grouping ``_shown_streams`` draws by."""
    return name.rsplit(" ", 1)[1] if " " in name else name


def detector_rates(snap: dict | None) -> list[dict]:
    """Per-detector count rates of a snapshot: ``khz`` now (the trace's last second) and
    ``mean_khz`` over the whole trace window. A detector's streams -- a windowed stream belongs
    to its detector -- are added up per bin."""
    trace = (snap or {}).get("trace") or {}
    counts = trace.get("counts") or {}
    width = float(trace.get("bin_width_s") or 0.0)
    if width <= 0.0 or not counts:
        return []
    groups: dict[str, list[np.ndarray]] = {}
    for name, stream in counts.items():
        groups.setdefault(_detector_of_stream(name), []).append(np.asarray(stream, dtype=float))
    now_bins = max(1, int(round(1.0 / width)))
    rows = []
    for name, arrays in groups.items():
        n = min(a.size for a in arrays)
        if n <= 0:
            continue  # nothing binned yet (the first frames of a run)
        total = np.zeros(n)
        for a in arrays:
            total += a[:n]
        rows.append({
            "name": name,
            "khz": float(total[-now_bins:].mean()) / width / 1e3,
            "mean_khz": float(total.mean()) / width / 1e3,
        })
    return rows


def overall_mean_khz(snap: dict | None) -> float | None:
    """The mean rate of all streams together over the trace window (kHz), or None without one."""
    trace = (snap or {}).get("trace") or {}
    counts = trace.get("counts") or {}
    width = float(trace.get("bin_width_s") or 0.0)
    if width <= 0.0 or not counts:
        return None
    n = min(np.asarray(a).size for a in counts.values())
    total = sum(float(np.asarray(a, dtype=float)[:n].sum()) for a in counts.values())
    return total / (n * width) / 1e3


def _rate_text(hz: float) -> str:
    """A count rate for the dock's big digits: the unit that keeps them readable."""
    hz = float(hz)
    a = abs(hz)
    if a >= 0.995e6:
        return f"{hz / 1e6:.2f} MHz"
    if a >= 0.995e3:
        return f"{hz / 1e3:.1f} kHz"
    return f"{hz:.0f} Hz"


def _rate_value(hz: float) -> None:
    """One count rate in large digits (the dock's point is reading it from the desk)."""
    im.push_font_scale(1.9)
    im.text(_rate_text(hz))
    im.pop_font_scale()


def _view_limit(lo: float, hi: float, data_lo: float, data_hi: float) -> tuple[float, float]:
    """The axis limits a user range asks for: 0 means auto (the data's extent)."""
    return (float(lo) or float(data_lo), float(hi) or float(data_hi))


def _plot_rates(snap: dict, exp: Experiment | None, size,
                view: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
    """The count rates per stream over the run (image mode and runs without a mirrored trace).

    *view* is the user's viewing range (x min/max in s, y max in kHz; 0 = auto)."""
    from emtk import implot

    trace = snap.get("trace") or {}
    if implot.begin_plot("##rates", size, implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("time (s)"), tr("count rate (kHz)"))
        width = float(trace.get("bin_width_s", 0.0))
        series = []
        t_max = 0.0
        for k, name in enumerate(_shown_streams(snap, exp)):
            counts = np.asarray((trace.get("counts") or {}).get(name, ()), dtype=float)
            if counts.size == 0 or width <= 0:
                continue
            t = (trace["first_bin"] + np.arange(counts.size)) * width
            t_max = max(t_max, float(t[-1]))
            series.append((name, t, counts / width / 1e3, _COLOURS[k % len(_COLOURS)]))
        if view[0] or view[1]:
            implot.setup_axis_limits(
                implot.AXIS_X1, float(view[0]) or 0.0,
                float(view[1]) or max(t_max, 1.0), implot.COND_ALWAYS
            )
        if view[2]:
            implot.setup_axis_limits(
                implot.AXIS_Y1, 0.0, float(view[2]), implot.COND_ALWAYS)
        for name, t, y, colour in series:
            implot.set_next_line_style(colour)
            implot.plot_line(name, t, y)
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
                 detected: dict | None = None,
                 view: tuple[float, float, float] = (0.0, 0.0, 0.0),
                 *, bursts_only: bool = False) -> None:
    """The live decays per detector over the micro-time channels, with the run's window edges
    and -- when they do not match -- the detected ones.

    The analyzer histograms the micro times in ``len(decay)`` bins over the device's *n_micro*
    channels, so a bin is ``n_micro / len(decay)`` channels wide: the x axis is in channels, the
    unit the windows are in, or a window edge lands that factor away from its pulse. *view* is
    the user's viewing range (x min/max in channels, y max in photons; 0 = auto).
    """
    from emtk import implot

    decays = snap.get("burst_decays" if bursts_only else "decays") or {}
    if implot.begin_plot("##decays", size, implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("micro-time channel"), tr("photons"))
        implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
        if view[0] or view[1]:
            implot.setup_axis_limits(
                implot.AXIS_X1, float(view[0]) or 0.0,
                float(view[1]) or float(n_micro or 1), implot.COND_ALWAYS
            )
        if view[2]:
            implot.setup_axis_limits(
                implot.AXIS_Y1, 0.5, float(view[2]), implot.COND_ALWAYS)
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


def _draw_qc(qc: dict | None, *, summary_only: bool = False, warnings_only: bool = False) -> None:
    """The quality checker's verdict: an overall light, then one line per check -- light, name,
    value; what it means and what to do are in the line's tooltip (and in the stored verdict)."""
    if warnings_only:
        if not qc or not qc.get('ready'):
            im.text_disabled(tr('Waiting for quality data'))
            im.set_item_tooltip((qc or {}).get('why',''))
            return
        warnings=[c for c in qc.get('checks',()) if c.get('light') in ('amber','red')]
        if not warnings:
            im.text_disabled(tr('No quality warnings'))
        for check in warnings:
            detail=str(check.get('detail',''))
            if check.get('action'):detail+='\n\n'+str(check['action'])
            _short_line(f"{check['name']}: {check.get('value','')}",detail,
                        _LIGHT_COLOURS[check['light']])
        return
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
    if summary_only:
        return
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
    ("laser", "Laser & Shutter", "settings"),
    ("analysis", "Analysis", "settings"),
    ("settings", "Settings", "main"),
    ("plot_hist", "Histogram", "main"),
    ("plot_correlation", "FCS Correlation", "main"),
    ("plot_polarization", "Polarization", "main"),
    ("plot_image", "Image", "main"),
    ("power_calibration", "Power calibration", "main"),
    ("plot_trace", "Trace", "main"),
    ("plot_decays", "Decays", "main"),
    ("rates", "Count rates", "main"),
    ("video", "Camera", "main"),
    ("quality", "Quality", "main"),
    ("setup_quality", "Setup quality", "main"),
    ("points", "Points", "main"),
)
#: Height of the run bar above the docks.
RUN_BAR_H = 30.0

_DOCK_ACCENTS = {
    'acquisition': _style.Accent('#235e85'),
    'laser': _style.Accent('#8a520a'),
    'shutters': _style.Accent('#8a520a'),
    'analysis': _style.Accent('#694892'),
    'settings': _style.Accent('#167a8c'),
    'phacq': _style.Accent('#167a8c'),
    'workspace': _style.Accent('#694892'),
    'plot_hist': _style.Accent('#694892'),
    'plot_correlation': _style.Accent('#694892'),
    'plot_polarization': _style.Accent('#694892'),
    'plot_trace': _style.Accent('#694892'),
    'plot_decays': _style.Accent('#694892'),
    'power_calibration': _style.Accent('#694892'),
    'rates': _style.Accent('#00626b'),
    'video': _style.Accent('#00626b'),
    'quality': _style.Accent('#1f5c46'),
    'setup_quality': _style.Accent('#1f5c46'),
    'points': _style.Accent('#694892'),
}


def _layout():
    from emtk.docking import Region, Split

    return Split("h", 0.30, Region("settings"), Region("main", workspace=True))


def _trace_overlap(donor, acceptor):
    """Coincident counts in a display bin; not a molecular FRET assignment."""
    return np.minimum(np.maximum(np.asarray(donor, dtype=float), 0),
                      np.maximum(np.asarray(acceptor, dtype=float), 0))


def _trace_y_limits(trace: dict) -> tuple[float, float]:
    """Scale from whole-run mean counts, not the largest transient burst.

    Twenty times the mean provides headroom for typical bursts; extreme bursts
    may clip. The floor keeps an empty or very dim run readable.
    """
    streams = trace.get("streams", ())
    positive = sum(max(0.0, float(s.get("run_mean_per_bin", 0.0)))
                   for s in streams if s.get("sign", 1) > 0)
    negative = sum(max(0.0, float(s.get("run_mean_per_bin", 0.0)))
                   for s in streams if s.get("sign", 1) < 0)
    return -max(5.0, 20.0 * negative), max(5.0, 20.0 * positive)


def _plot_mirrored_trace(trace: dict, size) -> None:
    """The running smFRET trace, mirrored: donor signals above the baseline, the acceptor's
    below (the classic burst view), the last *window* seconds.

    Overlap: bins where the donor and the FRET acceptor both counted are marked white on the
    baseline. Coincidence is a display cue -- it is not proof of FRET (two molecules in the
    focus, crosstalk and background coincide too).
    """
    from emtk import implot

    if implot.begin_plot("##mirrored_trace", size, implot.FLAGS_NO_TITLE):
        implot.setup_axes(tr("time (s)"), tr("photons per bin"))
        y_min, y_max = _trace_y_limits(trace)
        implot.setup_axis_limits(implot.AXIS_Y1, y_min, y_max, implot.COND_ALWAYS)
        t = np.asarray(trace["t"], dtype=float)
        implot.setup_axis_limits(
            implot.AXIS_X1, float(t[0]) - trace["bin_s"], float(t[-1]) + trace["bin_s"],
            implot.COND_ALWAYS,
        )
        # acceptor curves first (AA under DA), the donor last: each sign's main signal on top
        streams = trace["streams"]
        ordered = sorted(streams, key=lambda st: (st["sign"],))
        ordered = [st for st in reversed(ordered) if st["sign"] < 0] + [
            st for st in ordered if st["sign"] > 0
        ]
        for stream in ordered:
            # the peak of each pixel column, sign kept (acceptor streams point down)
            y = np.abs(np.asarray(stream["counts"], dtype=float))
            ts, ys = _to_pixels(t, y, size[0] / 2, "max")
            ys = ys * stream["sign"]
            implot.set_next_line_style(stream["colour"])
            implot.set_next_fill_style(stream["colour"], 0.35)
            implot.plot_shaded(tr(stream["name"]), ts, ys, yref=0.0)
            implot.set_next_line_style(stream["colour"])
            implot.plot_stairs(f"##{stream['name']}", ts, ys)
        # coincident counts of the FRET pair (donor over FRET acceptor, AA excepted): filled
        # white over the mirrored curves with the overlap's magnitude -- where both counted,
        # and how much. A display cue, not a FRET assignment.
        donors = [s for s in streams if s["sign"] > 0]
        acceptors = [s for s in streams if s["sign"] < 0 and not s["name"].startswith("AA")]
        if donors and acceptors:
            donor = sum((np.abs(np.asarray(s["counts"], float)) for s in donors),
                        np.zeros_like(t))
            acceptor = sum((np.abs(np.asarray(s["counts"], float)) for s in acceptors),
                           np.zeros_like(t))
            overlap = _trace_overlap(donor, acceptor)
            if (overlap > 0).any():
                ts, ys = _to_pixels(t, overlap, size[0] / 2, "max")
                implot.set_next_fill_style((1.0, 1.0, 1.0, 1.0), 1.0)
                implot.set_next_line_style((1.0, 1.0, 1.0, 1.0))
                implot.plot_shaded(tr("Coincident (not proof of FRET)"), ts, ys, yref=0.0)
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


from emtk.docking import DockManager, Region, Split


class RecordDockManager(DockManager):
    """The Record tool's dock manager, supporting aliases and unrestricted docking across all regions."""

    @staticmethod
    def _alias(key: str) -> str:
        if key == "shutters":
            return "laser"
        if key == "phacq":
            return "settings"
        return key

    def admits(self, key: str, region: str | None) -> bool:
        if region is None or region not in self.regions:
            return False
        return True

    def target_admits(self, key: str | None, target: str) -> bool:
        return True

    def in_workspace(self, key: str) -> bool:
        k = self._alias(key)
        win = self.windows.get(k)
        return bool(win and win.workspace and self.workspace is not None)

    def window(self, key: str):
        return super().window(self._alias(key))

    def minimize(self, key: str):
        return super().minimize(self._alias(key))

    def add_window(self, key: str, *args, **kwargs):
        return super().add_window(self._alias(key), *args, **kwargs)

    def remove_window(self, key: str) -> bool:
        return super().remove_window(self._alias(key))

    def is_shown(self, key: str) -> bool:
        return super().is_shown(self._alias(key))

    def is_visible(self, key: str) -> bool:
        return super().is_visible(self._alias(key))

    def hide(self, key: str):
        return super().hide(self._alias(key))

    def show(self, key: str):
        return super().show(self._alias(key))

    def focus(self, key: str):
        return super().focus(self._alias(key))

    def undock(self, key: str, box=None):
        return super().undock(self._alias(key), box=box)

    def region_of(self, key: str):
        return super().region_of(self._alias(key))


class RecordApp(ImApp):
    """The Record tool: settings, laser, analysis, quality and every plot in its own dock, with a
    run bar above them that always shows Start, Stop and Laser off."""

    #: Recording is a live view the user watches, not a wait: no busy overlay over it.
    busy_overlay = False

    window_title = "ChiSurf Record"

    def __init__(self, model: RecordModel | None = None) -> None:
        from emtk.docking import DockManager, Region, Split

        self.model = model or RecordModel()
        if not self.model.source_changed():
            self.model.status_detail = tr('Could not initialize the selected source. Disconnect existing instrument connections first.')
        from chisurf.plugins.core.acq.gui.setup_quality import SetupQualityModel
        self.setup_quality = SetupQualityModel(self.model)
        from chisurf.plugins.core.acq.gui.power_controls import SimplePowerPanel
        from chisurf.plugins.core.acq.gui.measurement_wizard import MeasurementWizard

        self.power_panel = SimplePowerPanel(self.model)
        self.power_form = FormState()
        self.power_form.custom["power_target_slider"] = self._draw_power_target_slider
        self.wizard = MeasurementWizard(self.model)
        from chisurf.plugins.core.acq.gui.phacq_settings import SettingsPanel, PhacqSettingsPanel
        self.settings_panel = SettingsPanel(self.model, self)
        self.phacq_settings = self.settings_panel
        from chisurf.plugins.core.acq.gui.video_panel import VideoPanel

        self.video = VideoPanel()
        if sys.platform.startswith("win"):
            self.video.address = "0"
            self.video.connect()
        else:
            # Do not probe an unspecified camera. Restored camera settings are
            # connected once on the next frame, after the saved address is adopted.
            self.video.address = ""
            self.video.status = "Camera unavailable: configure a source (right-click)."
        self._video_auto_connect_pending = False
        self.video.photon_context = lambda: str(self.model.saved_path or "") if self.model.running else ""
        self.video.output = str(self.model.output_dir / self.video.output)
        video_spec = json.loads((HERE / "video.view.json").read_text(encoding="utf-8"))
        #: The camera surface is uniform; detailed controls live in its context menu.
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
            ("live_correlation", self._draw_correlation_dock),
            ("live_polarization", self._draw_polarization_dock),
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
            ("live_rates", self._draw_rates_dock),
            ("laser_power", self._draw_laser_power),
            ("transfer_status", self._draw_transfer_status),
        ):
            self.form.custom[key] = draw
        #: the generated device / laser forms: their own form state, their spec per form
        self._sub_forms: dict[str, tuple[Any, dict, FormState]] = {}
        self.save_dialog = None
        self.save_window = None
        from chisurf.plugins.core.acq.gui.settings_file_dialog import SettingsFileDialog
        self.settings_open_dialog = SettingsFileDialog(self.model)
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
        self.docks = RecordDockManager(_layout(), name="record_docks")
        for key, title, region in DOCKS:
            is_ws = (region == "main")
            self.docks.add_window(
                key,
                tr(title),
                self._dock_drawer(key),
                dock=region,
                accent=_DOCK_ACCENTS.get(key, _DOCK_ACCENTS["analysis"]),
                header_tint=True,
                workspace=is_ws,
            )
        self.docks.tab_workspace()
        self._user_dock_overrides: dict[str, bool] = {}
        self._mode_shown = None
        self._sync_docks_to_mode(force=True)
        self._setup_quality_advanced = None
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
        out["live_correlation"] = "plot_correlation"
        out["live_polarization"] = "plot_polarization"
        out["live_image"] = "plot_image"
        out["point_rows"] = "points"
        out["Survey.fold"] = "points"
        return out

    def focus_dock(self, key: str) -> None:
        """Show the dock *key* and bring it in front of the tabs it shares its region with."""
        if key == "shutters":
            key = "laser"
        if key == "phacq":
            key = "settings"
        if key in ('setup_quality', 'settings') and not self.model.advanced:
            return
        self.docks.show(key)
        self.docks.focus(key)

    @property
    def item_rects(self) -> dict[str, tuple]:
        """Every control's rectangle of the last frame: the view form's and the generated
        sub-forms' (drivers' device, laser, shutter and scanner panels)."""
        if self.settings_open_dialog.open:
            return {}
        dialogs=getattr(self,'_power_change_dialogs',None)
        if dialogs is not None and dialogs.pending:
            return {'power_change.'+key:rect for key,rect in dialogs.pending[0].rects.items()}
        if self.wizard.window.open:
            return {**self.wizard.form.rects, **self.wizard.setup_form.rects}
        out = dict(self.form.rects)
        out.update(self.power_panel.form.rects)
        out.update(self.power_form.rects)
        out.update(self.wizard.setup_form.rects)
        for _form, _spec, sub in self._sub_forms.values():
            out.update(sub.rects)
        return out

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
            if dock in ("settings", "phacq"):
                if not self.model.advanced:
                    return
                self.settings_panel.draw(width=box[2])
                return
            if dock == "setup_quality":
                self._draw_setup_quality()
                return
            if dock == "power_calibration":
                im.text_disabled(tr("Power calibration"))
                self.power_panel.draw()
                return
            if dock == "plot_correlation":
                self._draw_correlation_dock(width=box[2])
                return
            if dock == "plot_polarization":
                self._draw_polarization_dock(width=box[2])
                return

            panels = self._panels(dock)
            single = len(panels) == 1 and dock.startswith(
                ("plot_", "quality", "video", "rates"))
            if single:
                draw_sections(panels[0]["sections"], self.model, self.form, titles=False)
            else:
                draw_sections(panels, self.model, self.form, titles=True)

        return draw

    def _draw_setup_quality(self) -> None:
        if not self.model.advanced:
            return
        qc = self.setup_quality
        if qc.simulated:
            im.text('SIMULATION ONLY')

        # Check setup quality bounds across days and report call for maintenance
        out_of_bounds, reason = qc.check_quality_bounds()
        if out_of_bounds:
            im.push_style_color(im.Col.TEXT, (0.95, 0.20, 0.15, 1.0))
            im.text(f"🔴 {tr('SETUP OUT OF QUALITY BOUNDS — CALL FOR MAINTENANCE')}")
            if reason:
                im.text_wrapped(reason)
            im.pop_style_color()
            im.separator()

        top = im.get_cursor_screen_pos()
        try:
            for row in qc.quality_rows():
                im.text(f"{row['dye']}  {row['metric']}: {row['value']}  ({row['status']})")
        except Exception as exc:
            im.text(f"Reference history unavailable: {exc}")
        bottom = im.get_cursor_screen_pos()
        self.form.rects['setup_quality_rows'] = (top[0], top[1], self._avail()[0], max(28.0, bottom[1] - top[1]))
        im.separator()

        im.text(tr('Calibration of setup (FCS & Dye Library)'))
        im.text_wrapped(tr('The saved timestamp is the entry time; the measurement time is unknown.'))

        # Action buttons
        if im.button(f"📥 {tr('Pull from live FCS')}"):
            live_fcs = getattr(self, '_latest_fcs_fit', None)
            if live_fcs:
                qc.pull_from_live_fcs(live_fcs)
        im.same_line()
        if im.button(f"📈 {tr('Graph setup quality')}"):
            self._show_quality_graph = not getattr(self, '_show_quality_graph', False)
        im.same_line()
        if im.button(f"💾 {tr('Save reference')}"):
            qc.save_reference()

        if getattr(self, '_show_quality_graph', False):
            from emtk import implot
            dates, cpm_vals, veff_vals, dyes = qc.history_graph_data()
            if dates:
                w_avail = self._avail()[0]
                if implot.begin_plot("##quality_history_plot", (w_avail, 140.0), implot.FLAGS_NO_TITLE):
                    implot.setup_axes(tr("record #"), tr("CPM (kHz)"))
                    xs = np.arange(len(cpm_vals), dtype=float)
                    implot.plot_line(tr("CPM bright (kHz)"), xs, np.asarray(cpm_vals, dtype=float))
                    implot.end_plot()
            else:
                im.text_disabled(tr("No historical records yet to graph."))

        # Form as an aligned ImGui table
        from chisurf.plugins.core.acq.gui.setup_quality import REFERENCE_DYES, compute_confocal_parameters
        if im.begin_table("##setup_cal_table", 2, im.TableFlags.BORDERS_INNER_H | im.TableFlags.ROW_BG):
            im.table_setup_column("Property", im.TableColumnFlags.WIDTH_FIXED, 130.0)
            im.table_setup_column("Value", im.TableColumnFlags.WIDTH_STRETCH)

            # Row 1: Dye choice
            im.table_next_row()
            im.table_next_column(); im.text(tr("Calibration dye"))
            im.table_next_column()
            dye_keys = [k for k, _ in REFERENCE_DYES]
            dye_lbls = [l for _, l in REFERENCE_DYES]
            curr_dye_idx = dye_keys.index(qc.dye) if qc.dye in dye_keys else 0
            im.set_next_item_width(160.0)
            ch_d, new_d = im.combo("##cal_dye_combo", curr_dye_idx, dye_lbls)
            if ch_d:
                qc.dye = dye_keys[new_d]

            # Row 2: Temperature & D(T)
            im.table_next_row()
            im.table_next_column(); im.text(tr("Temperature (°C)"))
            im.table_next_column()
            im.set_next_item_width(80.0)
            ch_t, new_t = im.input_float("##cal_temp", float(qc.temperature_c), 0, 0, "%.1f")
            if ch_t: qc.temperature_c = new_t

            tau_ms = float(qc.diffusion_ms) if qc.diffusion_ms else 0.0
            d_val, w0_nm, veff_fl = compute_confocal_parameters(qc.dye, qc.temperature_c, tau_ms, qc.kappa_s)

            im.table_next_row()
            im.table_next_column(); im.text(tr("Diffusion D(T)"))
            im.table_next_column()
            im.text(f"{d_val:.1f} µm²/s")

            # Row 3: Diffusion time tau_D
            im.table_next_row()
            im.table_next_column(); im.text(tr("Diffusion time τ_D"))
            im.table_next_column()
            im.set_next_item_width(100.0)
            _, qc.diffusion_ms = im.input_text("##cal_tau_d", str(qc.diffusion_ms))
            im.same_line(); im.text("ms")

            # Row 4: Structure parameter s (kappa)
            im.table_next_row()
            im.table_next_column(); im.text(tr("Aspect ratio s (κ)"))
            im.table_next_column()
            im.set_next_item_width(80.0)
            ch_k, new_k = im.input_float("##cal_kappa", float(qc.kappa_s), 0, 0, "%.1f")
            if ch_k and new_k > 0.5: qc.kappa_s = new_k

            # Row 5: Confocal waist w0
            im.table_next_row()
            im.table_next_column(); im.text(tr("Confocal waist ω₀"))
            im.table_next_column()
            w0_str = f"{w0_nm:.1f} nm" if math.isfinite(w0_nm) else "—"
            im.text(w0_str)

            # Row 6: Confocal volume V_eff
            im.table_next_row()
            im.table_next_column(); im.text(tr("Confocal volume V_eff"))
            im.table_next_column()
            veff_str = f"{veff_fl:.3f} fL" if math.isfinite(veff_fl) else "—"
            im.text(veff_str)

            # Row 7: CPM bright & CPM total
            im.table_next_row()
            im.table_next_column(); im.text(tr("CPM bright (kHz)"))
            im.table_next_column()
            im.set_next_item_width(100.0)
            _, qc.brightness_khz = im.input_text("##cal_cpm_bright", str(qc.brightness_khz))

            im.table_next_row()
            im.table_next_column(); im.text(tr("CPM total (kHz)"))
            im.table_next_column()
            im.set_next_item_width(100.0)
            _, qc.cpm_total_khz = im.input_text("##cal_cpm_total", str(qc.cpm_total_khz))

            # Row 8: Lifetime
            im.table_next_row()
            im.table_next_column(); im.text(tr("Lifetime (ns)"))
            im.table_next_column()
            im.set_next_item_width(100.0)
            _, qc.lifetime_ns = im.input_text("##cal_lifetime", str(qc.lifetime_ns))

            # Row 9: Laser & Power
            im.table_next_row()
            im.table_next_column(); im.text(tr("Laser (nm) & Power"))
            im.table_next_column()
            im.set_next_item_width(60.0)
            _, qc.laser_nm = im.input_text("##cal_laser_nm", str(qc.laser_nm))
            im.same_line(); im.text("nm  Pwr:")
            im.same_line(); im.set_next_item_width(60.0)
            _, qc.power_uw = im.input_text("##cal_pwr_uw", str(qc.power_uw))
            im.same_line(); im.text("µW")

            # Row 10: Optics & Detector
            im.table_next_row()
            im.table_next_column(); im.text(tr("Optics & Detector"))
            im.table_next_column()
            im.set_next_item_width(70.0)
            _, qc.optics = im.input_text("##cal_optics", str(qc.optics))
            im.same_line(); im.set_next_item_width(70.0)
            _, qc.detector = im.input_text("##cal_det", str(qc.detector))

            im.end_table()

        if qc.message:
            im.text_wrapped(qc.message)

    @staticmethod
    def _load_experiment_modes() -> dict:
        json_path = Path(__file__).parent / "experiment_modes.json"
        if json_path.is_file():
            try:
                return json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "point": {
                "title": "smFRET (point)",
                "default_docks": ["plot_hist", "plot_trace", "plot_decays", "video"],
                "focus_dock": "plot_hist"
            },
            "fcs": {
                "title": "FCS",
                "default_docks": ["plot_correlation", "plot_decays", "video"],
                "focus_dock": "plot_correlation"
            },
            "pol": {
                "title": "Polarization single-molecule",
                "default_docks": ["plot_polarization", "plot_decays", "plot_trace", "video"],
                "focus_dock": "plot_polarization"
            },
            "image": {
                "title": "Image scan",
                "default_docks": ["plot_image", "points", "plot_trace", "video"],
                "focus_dock": "plot_image"
            }
        }

    def _sync_docks_to_mode(self, force: bool = False) -> None:
        """Presets loaded from experiment_modes.json control default visible docks per mode."""
        is_inert = getattr(self, "_rendering_inert", False)
        current_state = (self.model.mode, self.model.ui_mode, is_inert)
        if current_state == getattr(self, "_mode_shown", None) and not force:
            return
        self._mode_shown = current_state
        ui_mode = "simple" if is_inert else self.model.ui_mode

        if ui_mode == "guided":
            for w in self.docks.windows.values():
                w.visible = False
            return

        modes = self._load_experiment_modes()
        preset = modes.get(self.model.mode) or modes.get("point") or {}
        defaults = set(preset.get("default_docks", []))
        defaults.add("video")

        expert_docks = {"analysis", "settings", "setup_quality", "power_calibration"}
        common_docks = {"acquisition", "laser", "quality", "rates"}

        for dock in self.docks.windows:
            if dock in self._user_dock_overrides:
                val = self._user_dock_overrides[dock]
            elif ui_mode == "simple" and dock in expert_docks:
                val = False
            elif dock in common_docks:
                val = True
            elif dock in defaults:
                val = True
            elif ui_mode == "advanced" and dock in expert_docks:
                val = True
            else:
                val = False
            if val:
                self.docks.show(dock)
            else:
                self.docks.hide(dock)

        focus = preset.get("focus_dock")
        if focus and self.docks.is_shown(focus):
            self.focus_dock(focus)

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
        self._user_dock_overrides.clear()
        self.docks.reset()
        self.docks.tab_workspace()
        self._mode_shown = None
        self._sync_docks_to_mode(force=True)

    def key(self, key, text="", modifiers=0):
        if self.docks.handle_key(key, modifiers):
            self.request_frame()
            return True
        return super().key(key, text, modifiers)

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
                ("start_pause", (tr("End pause") if self.model.session and getattr(self.model.session, "_pause_requested", None) and self.model.session._pause_requested.is_set() else tr("Pause analysis")) if self.model.running else f"▶ {tr('Start')}", "primary", tr("Start recording or mark an analysis pause. Raw photons continue; analysis remains incomplete until a new run.")),
                ("stop", f"⏹ {tr('Stop')}", "danger", tr("Stop measuring.")),
            ):
                enabled = model.enabled(action)
                if not enabled:
                    im.begin_disabled()
                if im.small_button(f"{label}##bar_{action}"):
                    getattr(model, action)()
                    self.tour.notify_used(action)
                self.form.rects[action] = im.get_current_context().get_item_rect()
                if not enabled:
                    im.end_disabled()
                im.set_item_tooltip(tip)
                im.same_line()
            snap = model.snapshot or {}
            # the recording's clock (photons received and written), not the live analysis': an
            # analysis that catches up after a hiccup must not make the run look stopped
            elapsed = float(snap.get("received_elapsed_s") or snap.get("elapsed_s", 0.0))
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
            if box[2] >= 850:
                im.same_line()
                im.text(f"|  {tr('Experiment')}:")
                im.same_line()
                mode_opts = model.mode_options()
                mode_keys = [k for k, _ in mode_opts]
                mode_labels = [lbl for _, lbl in mode_opts]
                curr_idx = mode_keys.index(model.mode) if model.mode in mode_keys else 0
                im.set_next_item_width(170.0)
                changed, new_idx = im.combo("##bar_mode", curr_idx, mode_labels)
                if changed and new_idx != curr_idx:
                    model.mode = mode_keys[new_idx]
                    model.mode_changed()
                    self._sync_docks_to_mode()
                self.form.rects["bar_mode"] = im.get_item_rect()
                im.set_item_tooltip(tr("Experiment type: smFRET (point bursts & E-S), FCS (correlation & diffusion), Polarization (single-molecule anisotropy & lifetime), or Image (fast-FLIM scan)."))

                im.same_line()
                im.text(f"|  {tr('Mode')}:")
                im.same_line()
                ui_opts = model.ui_mode_options()
                ui_keys = [k for k, _ in ui_opts]
                ui_labels = [lbl for _, lbl in ui_opts]
                curr_ui_idx = ui_keys.index(model.ui_mode) if model.ui_mode in ui_keys else 0
                im.set_next_item_width(105.0)
                changed_ui, new_ui_idx = im.combo("##bar_ui_mode", curr_ui_idx, ui_labels)
                if changed_ui and new_ui_idx != curr_ui_idx:
                    model.ui_mode = ui_keys[new_ui_idx]
                    model.ui_mode_changed()
                self.form.rects["bar_ui_mode"] = im.get_item_rect()
                im.set_item_tooltip(tr("User mode: Simple (routine controls), Advanced (full hardware & settings), Guided (workflow wizard)."))
            im.same_line()
            if im.small_button(f"📖 {tr('Guide')}"):
                self.tour.start()
            im.set_item_tooltip(tr("A guided tour: it points at each control in turn."))
            im.same_line()
            if im.small_button(f"❓ {tr('Help')}"):
                self.help_window.show()
            im.set_item_tooltip(tr("What every window and control does."))
            im.same_line()
            if im.small_button(tr("Reset layout")):
                self.reset_layout()
                self.tour.notify_used("reset_layout")
            self.form.rects["reset_layout"] = im.get_item_rect()
            im.set_item_tooltip(tr("Put every window back where the Record tool puts it."))
            im.same_line()
            if im.small_button(f"🪟 {tr('Docks ▾')}"):
                im.open_popup("##docks_selection_popup")
            self.form.rects["bar_docks"] = im.get_item_rect()
            im.set_item_tooltip(tr("Enable or disable docks in the current experiment mode."))
            if im.begin_popup("##docks_selection_popup"):
                im.text_disabled(tr("Visible docks"))
                im.separator()
                for key, title, region in DOCKS:
                    if key in ("acquisition", "laser", "analysis", "rates"):
                        continue
                    if region == "main":
                        continue
                    shown = self.docks.is_shown(key)
                    ch, val = im.checkbox(f"{tr(title)}##toggle_dock_{key}", shown)
                    if ch:
                        self._user_dock_overrides[key] = val
                        if val:
                            self.docks.show(key)
                            self.docks.focus(key)
                        else:
                            self.docks.hide(key)
                im.separator()
                im.text_disabled(tr("Workspace plots"))
                for key, title, region in DOCKS:
                    if region != "main":
                        continue
                    shown = self.docks.is_shown(key)
                    ch, val = im.checkbox(f"{tr(title)}##toggle_dock_{key}", shown)
                    if ch:
                        self._user_dock_overrides[key] = val
                        if val:
                            self.docks.show(key)
                            self.docks.focus(key)
                        else:
                            self.docks.hide(key)
                im.end_popup()
            if getattr(model, "overcount_alert", False) and not getattr(model, "advanced", False):
                im.same_line()
                im.push_style_color(im.Col.TEXT, (1.0, 0.25, 0.25, 1.0))
                im.text("⚠ >1 MHz/ch: Shutter closed")
                im.pop_style_color()
                im.same_line()
                if im.small_button("Override##bar_overcount_override"):
                    model.overcount_override = True
                    model.overcount_alert = False
                    model.set_shutter('Excitation', True)
                im.set_item_tooltip(tr("Count rate exceeded 1 MHz/channel. Excitation shutter was closed to protect detectors. Click to override protection and reopen excitation shutter."))
                self.form.rects["overcount_override"] = im.get_item_rect()

            im.same_line()
            im.set_cursor_pos_x(max(im.get_cursor_pos_x(), box[2] - 230.0))
            test_active = getattr(model, "test_mode", False)
            if test_active:
                im.push_style_color(im.Col.BUTTON, (0.85, 0.45, 0.1, 1.0))
                im.push_style_color(im.Col.BUTTON_HOVERED, (0.95, 0.55, 0.2, 1.0))
            if im.small_button(f"🧪 {'Test: ON' if test_active else 'Test mode'}##bar_test_mode"):
                model.test_mode = not test_active
            if test_active:
                im.pop_style_color(2)
            self.form.rects["test_mode"] = im.get_item_rect()
            im.set_item_tooltip(tr("Test mode: when ON, data is streamed and analyzed in real time, but NO files are written to disk."))

            im.same_line()
            if model.running:
                if getattr(model, "test_mode", False):
                    im.text_colored((1.0, 0.65, 0.1, 1.0), "● TEST")
                    im.set_item_tooltip(tr("Test acquisition in progress: live analysis active, disk writing disabled."))
                else:
                    im.text_colored((1.0, 0.25, 0.25, 1.0), "● REC")
                    im.set_item_tooltip(tr("Recording active: saving measurement data to disk.") + (f"\n{model.saved_path}" if model.saved_path else ""))
            else:
                im.text_colored((0.5, 0.5, 0.5, 1.0), "○ IDLE")
                im.set_item_tooltip(tr("Acquisition idle: no measurement in progress."))
            self.form.rects["acq_indicator"] = im.get_item_rect()
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
        # the generated form's controls are this window's controls (the drivers, tests and the
        # tour look them up on the app's form)
        self.form.rects.update(cached[2].rects)
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
        if not model.advanced:
            return
        self._draw_generated("laser_settings", model.laser_form, state, width,
                             tr("The simulated laser is set in the program below."))

    def _avail(self, minimum=(200.0, 120.0)) -> tuple[float, float]:
        w, h = im.get_content_region_avail()[:2]
        return max(minimum[0], w), max(minimum[1], h - 4.0)

    def _placeholder(self, state: FormState, key: str, text: str, width: float) -> None:
        top = im.get_cursor_screen_pos()
        im.text_disabled(text)
        labels = {
            'live_view': ('E', 'S'),
            'live_correlation': ('lag time τ (s)', 'G(τ) − 1'),
            'live_polarization': ('micro-time (ns)', 'anisotropy r(t)'),
            'live_trace': ('time (s)', 'count rate (kHz)'),
            'live_decays': ('micro-time channel', 'photons'),
            'live_image': ('x (pixel)', 'y (pixel)'),
        }
        axes = labels.get(key, ('', ''))
        avail = self._avail()
        # Draw placeholder rect outline and axis labels cheaply without full implot pipeline
        dl = im.get_window_draw_list()
        pos = im.get_cursor_screen_pos()
        box_w, box_h = avail[0], avail[1]
        dl.add_rect((pos[0], pos[1]), (pos[0] + box_w, pos[1] + box_h), (50, 50, 56, 120))
        if axes[0]:
            dl.add_text((pos[0] + box_w * 0.5 - 20, pos[1] + box_h - 18), (120, 120, 120, 180), tr(axes[0]))
        if axes[1]:
            dl.add_text((pos[0] + 6, pos[1] + 6), (120, 120, 120, 180), tr(axes[1]))
        im.dummy(box_w, box_h)
        bottom = im.get_cursor_screen_pos()
        state.rects[key] = (*top, width, max(28., bottom[1] - top[1]))

    def _draw_hist(self, section, model: RecordModel, state: FormState, width: float) -> None:
        if not self.docks.is_shown("plot_hist"):
            return
        snap = self.wizard.model.display_snapshot() if (model.ui_mode == "guided" and hasattr(self, "wizard")) else model.snapshot
        if snap is None or model.mode in ("image", "fcs", "pol"):
            self._placeholder(state, "live_view", tr("Start a run: the bursts build up here."), width)
            return
        top = im.get_cursor_screen_pos()
        if snap.get("live_analysis_dropped") or getattr(model.session, "_burst_overload", False):
            im.push_style_color(im.Col.TEXT, _LIGHT_COLOURS["amber"])
            im.text(f"⚠ {tr('Live burst analysis not possible for part of the run — it skipped photons and continues; raw photons are intact.')}")
            im.pop_style_color()
        _short_line(
            f"{tr('Bursts')}: {snap.get('bursts', 0):,} · {snap.get('burst_rate_hz', 0.0):.1f} Hz",
            tr("{photons:,} analyzed photons in {t:.1f} s").format(photons=snap.get("photons", 0),
                                                         t=snap.get("received_elapsed_s") or snap.get("elapsed_s", 0.0)),
        )
        hists = snap.get("histograms") or {}
        if hists and model.plot_choice not in hists:
            two_d = [n for n, h in hists.items() if "y" in h]
            model.plot_choice = (two_d or list(hists))[0]
        _w, h = self._avail()
        if hists:
            hist = hists[model.plot_choice]
            maps = ("Viridis", "Plasma", "Hot", "Cool", "Greys", "Jet", "Spectral")
            if "y" in hist:
                # cap widths explicitly: default combos consume the whole dock
                im.set_next_item_width(max(65.0, min(105.0, width * 0.23)))
                _, model.hist_scale = im.combo(tr("Intensity"), model.hist_scale,
                                               ("Linear", "Log counts"))
                im.same_line()
                im.set_next_item_width(max(65.0, min(105.0, width * 0.23)))
                _, model.hist_colormap = im.combo(tr("Map"), model.hist_colormap, maps)
                im.same_line()
                im.set_next_item_width(max(65.0, min(90.0, width * 0.19)))
                _, model.hist_count_cap = im.input_float(tr("Cap"),
                                                         model.hist_count_cap)
                im.set_item_tooltip(tr("Display count cap; zero uses the full range. Raw counts are unchanged."))
                model.hist_count_cap = max(0.0, model.hist_count_cap)
            _w, h = self._avail()
            _plot_histogram(
                hist, h, view=(model.hist_x_min, model.hist_x_max, model.hist_y_max),
                scale="log" if model.hist_scale else "linear",
                cap=model.hist_count_cap, colormap=maps[model.hist_colormap]
                if "y" in hist else "Viridis")
        else:
            im.text_wrapped(tr("This measurement type keeps no histogram."))
        bottom = im.get_cursor_screen_pos()
        state.rects["live_view"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def _draw_correlation_dock(self, section=None, model=None, state=None, width=None) -> None:
        if not self.docks.is_shown("plot_correlation"):
            return
        model = self.model
        snap = model.snapshot or {}
        w, h = self._avail()
        width = w if width is None else width
        top = im.get_cursor_screen_pos()
        im.text(tr("FCS Correlation"))

        # User setup: correlation channel choice, refresh rate, bunching model, structure parameter s (kappa)
        corr_opts = [
            ("all", tr("All (combined)")),
            ("ch0", tr("Auto Ch 0")),
            ("ch1", tr("Auto Ch 1")),
            ("cross_01", tr("Cross 0 × 1")),
        ]
        corr_keys = [k for k, _ in corr_opts]
        corr_lbls = [l for _, l in corr_opts]
        cur_key = getattr(self, '_fcs_corr_key', 'all')
        cur_idx = corr_keys.index(cur_key) if cur_key in corr_keys else 0

        im.set_next_item_width(120.0)
        ch_c, new_c = im.combo("##fcs_channel_select", cur_idx, corr_lbls)
        if ch_c and new_c != cur_idx:
            self._fcs_corr_key = corr_keys[new_c]
            cur_key = self._fcs_corr_key
        im.set_item_tooltip(tr("Select correlation function to display and fit"))

        im.same_line()
        rate_opts = [0.5, 1.0, 2.0, 5.0]
        rate_lbls = ["0.5 s", "1.0 s", "2.0 s", "5.0 s"]
        cur_rate = getattr(self, '_fcs_refresh_s', 1.0)
        cur_r_idx = rate_opts.index(cur_rate) if cur_rate in rate_opts else 1
        im.set_next_item_width(75.0)
        ch_r, new_r = im.combo("##fcs_refresh_select", cur_r_idx, rate_lbls)
        if ch_r and new_r != cur_r_idx:
            self._fcs_refresh_s = rate_opts[new_r]
        im.set_item_tooltip(tr("FCS analysis refresh rate"))

        im.same_line()
        bunch_opts = [0, 1, 2]
        bunch_lbls = ["0 bunch", "1 bunch", "2 bunch"]
        cur_b = getattr(self, '_fcs_bunching_mdl', 1)
        cur_b_idx = bunch_opts.index(cur_b) if cur_b in bunch_opts else 1
        im.set_next_item_width(85.0)
        ch_b, new_b = im.combo("##fcs_bunch_select", cur_b_idx, bunch_lbls)
        if ch_b and new_b != cur_b_idx:
            self._fcs_bunching_mdl = bunch_opts[new_b]
        im.set_item_tooltip(tr("Bunching model: 0 (pure diffusion), 1 (triplet), 2 (triplet + microsecond blink)"))

        im.same_line()
        im.set_next_item_width(55.0)
        cur_s = getattr(self, '_fcs_s_param', 5.0)
        ch_s, new_s = im.input_float("s (κ)##fcs_s", cur_s, 0.0, 0.0, "%.1f")
        if ch_s and new_s > 0.5:
            self._fcs_s_param = float(new_s)
        im.set_item_tooltip(tr("Confocal structure parameter s = z0 / w0 (aspect ratio kappa)"))

        # Extract correlation data for selected channel/correlation
        correlations = snap.get("correlations") or {}
        corr = correlations.get(cur_key) or snap.get("correlation") or {}
        tau = np.asarray(corr.get("tau_s", ()), dtype=float)
        g = np.asarray(corr.get("g", ()), dtype=float)
        corr_rate_hz = float(corr.get("count_rate_hz", snap.get("count_rate_hz", 0.0)))
        corr_rate_khz = corr_rate_hz / 1000.0

        # Automatic live curve fitting with rate throttling
        now = time.monotonic()
        last_fit_time = getattr(self, '_fcs_last_fit_time', 0.0)
        fit_res = getattr(self, '_fcs_cached_fit', None)
        if fit_res is None or (now - last_fit_time) >= getattr(self, '_fcs_refresh_s', 1.0):
            fit_res = _fit_fcs_curve(tau, g, getattr(self, '_fcs_s_param', 5.0), getattr(self, '_fcs_bunching_mdl', 1))
            self._fcs_cached_fit = fit_res
            self._fcs_last_fit_time = now

        if fit_res and fit_res.get("success"):
            n_bright = fit_res["n_bright"]
            n_total = fit_res["n_total"]
            tau_d_s = fit_res["tau_d_s"]
            fit_tau = fit_res.get("tau_smooth")
            fit_g = fit_res.get("g_model")
        else:
            amp = _amplitude(tau, g)
            n_bright = (1.0 / amp) if amp > 0 else float(snap.get("n_focus", float("nan")))
            n_total = n_bright
            tau_d_s = _estimate_diffusion_time_s(tau, g)
            fit_tau = fit_g = None

        cpm_bright = (corr_rate_khz / n_bright) if (np.isfinite(n_bright) and n_bright > 0) else (float(snap.get("brightness_hz", 0.0)) / 1000.0)
        cpm_total = (corr_rate_khz / n_total) if (np.isfinite(n_total) and n_total > 0) else cpm_bright

        self._latest_fcs_fit = {
            "tau_d_s": tau_d_s,
            "s": getattr(self, '_fcs_s_param', 5.0),
            "n_bright": n_bright,
            "n_total": n_total,
            "cpm_bright": cpm_bright,
            "cpm_total": cpm_total,
            "rate_khz": corr_rate_khz,
        }

        tau_d_str = "τ_D: —"
        if tau_d_s is not None and tau_d_s > 0:
            if tau_d_s < 1e-3:
                tau_d_str = f"τ_D ≈ {tau_d_s * 1e6:.1f} µs"
            else:
                tau_d_str = f"τ_D ≈ {tau_d_s * 1e3:.2f} ms"

        if snap.get("correlator_throttled") or getattr(model.session, "_correlator_throttled", False):
            im.push_style_color(im.Col.TEXT, _LIGHT_COLOURS["amber"])
            im.text(f"⚠ {tr('Live correlator throttled — analysis budget protected. Recorded photons are intact.')}")
            im.pop_style_color()

        n_str = f"N ≈ {n_bright:.2g}" if np.isfinite(n_bright) else "N: —"
        n_tot_str = f"N_total ≈ {n_total:.2g}" if np.isfinite(n_total) else "N_total: —"
        b_str = f"{cpm_bright:.1f} kHz/mol" if cpm_bright > 0 else "B: —"
        cpm_t_str = f"{cpm_total:.1f} kHz/mol" if cpm_total > 0 else "CPM_tot: —"
        r_str = f"{corr_rate_khz:.1f} kHz"
        s_str = f"s(κ) = {getattr(self, '_fcs_s_param', 5.0):.1f}"

        im.text(f"  {n_str}  ·  {n_tot_str}  ·  {b_str}  ·  CPM total: {cpm_t_str}  ·  {tau_d_str}  ·  {s_str}  ·  {r_str}")
        im.set_item_tooltip(
            tr("{photons:,} analyzed photons in {t:.1f} s\n"
               "N: bright molecules in observation volume\n"
               "N_total: bright + dark molecules (corrected for bunching fraction)\n"
               "CPM bright: count rate / N_bright (counts per bright molecule)\n"
               "CPM total: count rate / N_total (counts per total molecule)\n"
               "τ_D: translational diffusion time\n"
               "s (κ): structure parameter (z0 / w0)").format(
                photons=corr.get("photons", snap.get("photons", 0)),
                t=snap.get("elapsed_s", 0.0)
            )
        )

        rem_h = max(80.0, h - 75.0)
        keep = (tau > 0) & np.isfinite(g)
        if keep.any():
            _plot_correlation(corr, rem_h, fit_tau=fit_tau, fit_g=fit_g)
        else:
            from emtk import implot
            flags = (implot.FLAGS_NO_TITLE | implot.FLAGS_NO_INPUTS | implot.FLAGS_NO_MENUS |
                     implot.FLAGS_NO_BOX_SELECT | implot.FLAGS_NO_FRAME)
            if implot.begin_plot("##empty_correlation", (w, rem_h), flags):
                axis_flags = implot.AXIS_FLAGS_NO_GRID_LINES | implot.AXIS_FLAGS_NO_TICK_MARKS | implot.AXIS_FLAGS_NO_TICK_LABELS
                implot.setup_axes(tr("lag time τ (s)"), tr("G(τ) − 1"), axis_flags, axis_flags)
                implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
                implot.end_plot()
        bottom = im.get_cursor_screen_pos()
        self.form.rects["live_correlation"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def _draw_polarization_dock(self, section=None, model=None, state=None, width=None) -> None:
        if not self.docks.is_shown("plot_polarization"):
            return
        model = self.model
        snap = model.snapshot or {}
        w, h = self._avail()
        width = w if width is None else width
        top = im.get_cursor_screen_pos()
        im.text(tr("Polarization"))

        decays = snap.get("burst_decays" if model.decay_bursts_only else "decays") or {}
        detectors = [n for n in decays if " " not in n]

        par_key = str(model.pol_par_channel)
        perp_key = str(model.pol_perp_channel)
        if par_key not in decays and len(detectors) > 0:
            par_key = detectors[0]
        if perp_key not in decays and len(detectors) > 1:
            perp_key = detectors[1]

        decay_par = np.asarray(decays.get(par_key, ()), dtype=float)
        decay_perp = np.asarray(decays.get(perp_key, ()), dtype=float)

        i_par = float(np.sum(decay_par)) if decay_par.size > 0 else 0.0
        i_perp = float(np.sum(decay_perp)) if decay_perp.size > 0 else 0.0

        g = float(model.pol_g_factor)
        l1 = float(model.pol_l1)
        l2 = float(model.pol_l2)

        den_app = i_par + 2.0 * i_perp
        r_app = (i_par - i_perp) / den_app if den_app > 0 else float("nan")

        den_cor = (1.0 - 3.0 * l2) * i_par + (2.0 - 3.0 * l1) * g * i_perp
        r_cor = (i_par - g * i_perp) / den_cor if den_cor > 0 else float("nan")

        total_decay = (decay_par + decay_perp) if (decay_par.size > 0 and decay_par.size == decay_perp.size) else (decay_par if decay_par.size > 0 else decay_perp)
        res_ns = 0.016
        tau_life, life_detail = (None, "")
        if total_decay.size > 10 and np.sum(total_decay) > 50:
            from chisurf.plugins.core.acq.live.calibration.measurements import tail_lifetime_ns
            peak_idx = int(np.argmax(total_decay))
            start_ns = float((peak_idx + 3) * res_ns)
            stop_ns = float(min(total_decay.size - 1, peak_idx + 100) * res_ns)
            if stop_ns > start_ns:
                tau_life, life_detail = tail_lifetime_ns(total_decay, bin_ns=res_ns, start_ns=start_ns, stop_ns=stop_ns)

        r_str = f"r = {r_cor:.3f}" if np.isfinite(r_cor) else "r: —"
        r_app_str = f"r_app = {r_app:.3f}" if np.isfinite(r_app) else "r_app: —"
        tau_str = f"τ ≈ {tau_life:.2f} ns" if tau_life is not None else "τ: —"
        g_str = f"G = {g:.3f}"

        im.text(f"  {r_str}  ({r_app_str})  ·  {tau_str}  ·  {g_str}  ·  I_∥={i_par:.0f}, I_⊥={i_perp:.0f}")
        im.set_item_tooltip(
            tr("Steady-state anisotropy r (Ströhl et al. 2018, DOI 10.1088/2050-6120/aa872e)\n"
               "r = (I_par - G*I_perp) / ((1 - 3*l2)*I_par + (2 - 3*l1)*G*I_perp)\n"
               "Lifetime τ: Poisson log-linear tail fit ({detail})").format(detail=life_detail or "idle")
        )

        if im.tree_node_ex(tr("Calibration helper: G-factor & l1/l2 (Ströhl et al. 2018)##pol_helper"), im.TreeNodeFlags.DEFAULT_OPEN):
            im.text_wrapped(tr("Calibrate G from a rotating reference dye (e.g. Rhodamine 110 in water, assumed r = 0)."))
            im.set_next_item_width(80.0)
            _, model.pol_par_channel = im.input_int(tr("Parallel ch (∥)"), model.pol_par_channel)
            im.same_line()
            im.set_next_item_width(80.0)
            _, model.pol_perp_channel = im.input_int(tr("Perp ch (⊥)"), model.pol_perp_channel)
            im.set_item_tooltip(tr("Routing channel indices for parallel and perpendicular polarization detection."))

            _, model.pol_ref_r = im.input_float(tr("Assumed reference r"), model.pol_ref_r, step=0.01, fmt="%.3f")
            im.set_item_tooltip(tr("Assumed true anisotropy of reference dye (-0.5 < r < 1.0; 0 for fast rotation)."))

            _, model.pol_l1 = im.input_float("l1", model.pol_l1, step=0.01, fmt="%.3f")
            im.same_line()
            _, model.pol_l2 = im.input_float("l2", model.pol_l2, step=0.01, fmt="%.3f")
            im.set_item_tooltip(tr("High-NA objective mixing corrections (Ströhl et al. 2018 Eq. 1; default 0.0)."))

            can_calc = i_par > 0 and i_perp > 0
            if not can_calc:
                im.begin_disabled()
            if im.button(tr("Calculate G from live counts")):
                from chisurf.plugins.core.acq.live.calibration.measurements import g_factor
                val, detail = g_factor(i_par=i_par, i_perp=i_perp, r_assumed=model.pol_ref_r)
                if val is not None:
                    model.pol_g_factor = val
                    model.status_detail = tr("G-factor calibrated: {g:.3f}").format(g=val)
            if not can_calc:
                im.end_disabled()
                im.set_item_tooltip(tr("Acquire photons in parallel and perpendicular channels to calculate G."))
            im.same_line()
            _, model.pol_g_factor = im.input_float(tr("Active G"), model.pol_g_factor, step=0.01, fmt="%.3f")
            im.tree_pop()

        rem_h = max(80.0, h - 80.0)
        from emtk import implot
        from chisurf.core.fluorescence.anisotropy.rt import rt_curves

        has_data = decay_par.size > 0 and decay_perp.size > 0 and decay_par.size == decay_perp.size and (i_par + i_perp > 0)
        if has_data:
            t_axis = (np.arange(decay_par.size, dtype=float) + 0.5) * res_ns
            t_ret, r_unc, r_cor_t = rt_curves(t_axis, decay_par, decay_perp, g=g, l1=l1, l2=l2)
            if implot.begin_plot("##polarization_decay", (w, rem_h), implot.FLAGS_NO_TITLE):
                implot.setup_axes(tr("micro-time (ns)"), tr("anisotropy r(t)"))
                implot.setup_axis_limits(implot.AXIS_Y1, -0.2, 0.5, implot.COND_ONCE)
                if t_ret.size > 0 and np.isfinite(r_cor_t).any():
                    implot.plot_line(tr("r(t) corrected"), t_ret, r_cor_t)
                implot.end_plot()
        else:
            flags = (implot.FLAGS_NO_TITLE | implot.FLAGS_NO_INPUTS | implot.FLAGS_NO_MENUS |
                     implot.FLAGS_NO_BOX_SELECT | implot.FLAGS_NO_FRAME)
            if implot.begin_plot("##empty_polarization", (w, rem_h), flags):
                axis_flags = implot.AXIS_FLAGS_NO_GRID_LINES | implot.AXIS_FLAGS_NO_TICK_MARKS | implot.AXIS_FLAGS_NO_TICK_LABELS
                implot.setup_axes(tr("micro-time (ns)"), tr("anisotropy r(t)"), axis_flags, axis_flags)
                implot.setup_axis_limits(implot.AXIS_Y1, -0.2, 0.5, implot.COND_ALWAYS)
                implot.end_plot()
        bottom = im.get_cursor_screen_pos()
        self.form.rects["live_polarization"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def _draw_video_panel(self, section, model: RecordModel, state: FormState, width: float) -> None:
        top = im.get_cursor_screen_pos()
        self.video_form.rects.clear()
        draw_sections(self.video_sections_simple, self.video, self.video_form, titles=False)
        if im.begin_popup_context_window("##camera_settings"):
            draw_sections(self.video_sections, self.video, self.video_form, titles=False)
            im.end_popup()
        bottom = im.get_cursor_screen_pos()
        state.rects["video_panel"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def _draw_video_frame(self, section, model: RecordModel, state: FormState, width: float) -> None:
        from emtk import Texture

        frame = self.video.frame
        if frame is None:
            self._placeholder(state, "camera_frame", tr("Waiting for camera preview; right-click for settings."), width)
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
                tr("Donor: green, above the baseline; acceptor: red, below; white: coincident "
                   "counts (not proof of FRET)."),
                (0.7, 0.7, 0.7, 1.0),
            )
            _plot_mirrored_trace(trace, self._avail())
        else:
            _plot_rates(snap, exp, self._avail(),
                        view=(model.rates_x_min, model.rates_x_max, model.rates_y_max))
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
        _plot_decays(snap, exp, self._avail(), n_micro, detected,
                     view=(model.decays_x_min, model.decays_x_max, model.decays_y_max),
                     bursts_only=model.decay_bursts_only)
        bottom = im.get_cursor_screen_pos()
        state.rects["live_decays"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def _draw_quality(self, section, model: RecordModel, state: FormState, width: float) -> None:
        top = im.get_cursor_screen_pos()
        snap = model.snapshot or {}
        healthy = not snap.get("dropped") and not snap.get("source_error")
        if snap and (not healthy or model.advanced):
            _short_line(
                tr("● healthy") if healthy else tr("● data lost"),
                tr("{batches} batches, {dropped} dropped, {queued} buffered.").format(
                    batches=snap.get("batches", 0), dropped=snap.get("dropped", 0),
                    queued=snap.get("queued", 0)),
                _LIGHT_COLOURS["green" if healthy else "red"],
            )
            if snap.get("source_error"):
                im.set_item_tooltip(str(snap["source_error"]))
        _draw_qc(snap.get("qc"), summary_only=True, warnings_only=not model.advanced)
        bottom = im.get_cursor_screen_pos()
        state.rects["live_qc"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def _draw_rates_dock(self, section, model: RecordModel, state: FormState,
                         width: float) -> None:
        """Compact shared table: channel labels, aligned numeric rates, separate units."""
        from emtk.widgets.data_table import TableBinding, draw_table

        spec = {"type": "custom", "key": "data_table", "options": {
            "source": "count_rate_rows", "fit_rows": True,
            "activated_call": "align_count_rate",
            "height": 150, "selection_note": False,
            "columns": [
                {"key": "channel", "title": "Channel", "width": 120},
                {"key": "value", "title": "Rate", "format": "%.2f", "width": 95},
                {"key": "unit", "title": "Unit", "width": 55},
            ]}}
        binding = state.tables.get("count_rate_rows")
        if binding is None:
            binding = state.tables["count_rate_rows"] = TableBinding(spec, model)
        top = im.get_cursor_screen_pos()
        draw_table(binding, "count_rate_rows", width=width)
        bottom = im.get_cursor_screen_pos()
        state.rects["live_rates"] = (top[0], top[1], width, max(28.0, bottom[1]-top[1]))

    def _sync_alignment_display(self,box):
        if not getattr(self.model,'alignment_requested',False):
            return
        self.model.alignment_requested=False
        key='alignment_rate'
        if self.docks.window(key) is None:
            x,y,w,h=box
            self.docks.add_window(key,tr('Alignment count rate'),self._draw_alignment_display,
                box=(x+w*.1,y+h*.12,w*.8,h*.78),min_size=(400,240),visible=False,
                accent=_DOCK_ACCENTS['rates'])
        self.docks.show(key)
        self.docks.focus(key)

    def _draw_alignment_display(self,box):
        channel=getattr(self.model,'alignment_channel','')
        row=next((r for r in self.model.count_rate_rows() if r['channel']==channel),None)
        im.text(channel)
        text='—'
        if row is not None and isinstance(row.get('value'),(int,float)):
            hz=row['value']*{'MHz':1e6,'kHz':1e3,'Hz':1.}.get(row['unit'],1.)
            text=_rate_text(hz)
        im.text_disabled(tr('No current rate available') if text=='—' else tr('Alignment monitor · read only'))
        w,h=im.get_content_region_avail()[:2]
        tw,th=im.calc_text_size(text)
        scale=max(1.,min(max(1.,w-20)/max(1.,tw),max(1.,h*.68)/max(1.,th)))
        im.push_font_scale(scale)
        try:
            im.text(text)
            self.form.rects['alignment_rate_value']=im.get_item_rect()
        finally:im.pop_font_scale()

    def _draw_power_target_slider(self, section, model, state, width):
        from emtk import SliderFlags

        try:
            points = model.power_book._record(model.power_laser_name())
        except ValueError as exc:
            im.text_wrapped(tr("Calibrate this laser before setting µW: ") + str(exc))
            return
        enabled = model.enabled("power_target_uw")
        if not enabled: im.begin_disabled()
        changed, value = im.slider_float(
            tr("Target (µW)"), model.power_target_uw, points[0][1], points[-1][1],
            fmt="%.3g µW", flags=SliderFlags.ALWAYS_CLAMP)
        state.rects["power_target_uw"] = im.get_current_context().get_item_rect()
        if changed: model.power_target_uw = value
        im.set_item_tooltip(tr("Drag, or Ctrl-click to type a target in the measured range. Press Set µW to adjust the selected laser."))
        if not enabled: im.end_disabled()

    def _draw_laser_power(self, section, model: RecordModel, state: FormState,
                          width: float) -> None:
        """One drive slider per laser head: the program's intensity, edited in place."""
        top = im.get_cursor_screen_pos()
        from chisurf.plugins.core.acq.gui.laser_cards import draw_laser_cards
        draw_laser_cards(self, model, state, width)
        bottom = im.get_cursor_screen_pos()
        state.rects["laser_power"] = (top[0], top[1], width, max(20.0, bottom[1] - top[1]))

    def _draw_transfer_status(self, section, model: RecordModel, state: FormState,
                              width: float) -> None:
        """The archive transfer's state for this session's recordings."""
        top = im.get_cursor_screen_pos()
        _short_line(model.transfer_status,
                    tr("The registered backend copies the session's recordings to the archive; "
                       "this tool never moves or deletes anything."),
                    (0.7, 0.7, 0.7, 1.0))
        state.rects["transfer_status"] = (*top, width, 20.0)

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

    def _draw_inert_background(self,box):
        from emtk import frame,IO
        ctx=im.get_current_context()
        self._rendering_inert=True
        if hasattr(self,'_head_edits'):self._head_edits.clear()
        if not hasattr(self,'_wizard_background_storage'):self._wizard_background_storage={}
        with frame(ctx.p,box,io=IO(),storage=self._wizard_background_storage):
            im.begin_disabled()
            self._sync_docks_to_mode()
            self._run_bar(box)
            self.docks.draw((box[0],box[1]+RUN_BAR_H,box[2],max(100.,box[3]-RUN_BAR_H)))
            im.end_disabled()
        self._wizard_background_rects=dict(self.form.rects)
        self.form.rects.clear()
        self._rendering_inert=False
        self._sync_docks_to_mode(force=True)

    # -- one frame ---------------------------------------------------------------------------------
    def render(self) -> None:
        self.video.preview_visible = (self.model.ui_mode != "guided" and self.docks.is_shown("video"))
        if self._video_auto_connect_pending:
            self._video_auto_connect_pending = False
            self.video.connect()
        # One-time migration of only the old oversized rates split; keep tab placements.
        if not self.docks.extras.get('compact_rates_v1'):
            from emtk.docking import Region
            for name, split in self.docks.splits.items():
                if (split.axis == 'v' and isinstance(split.first, Region)
                        and split.first.name == 'rates' and isinstance(split.second, Region)
                        and split.second.name == 'side' and split.ratio > .30):
                    self.docks.set_ratio(name, .30)
            self.docks.extras['compact_rates_v1'] = True
        self.model.poll()
        self.model.refresh_shutter_form()
        self._persist_loaded_settings()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        if self.settings_open_dialog.open or getattr(self.model,'settings_file_requested',False):
            self._draw_inert_background(box)
            self.settings_open_dialog.draw(box)
            return
        dialogs=getattr(self,'_power_change_dialogs',None)
        if self.model.pending_power_change is not None or (dialogs is not None and dialogs.pending):
            self._draw_inert_background(box)
            if dialogs is None:
                from chisurf.plugins.core.acq.gui.power_controls import PowerChangeDialogs
                dialogs = self._power_change_dialogs = PowerChangeDialogs(self.model, width=650)
            if not dialogs.pending:
                def answered(yes):
                    if yes:
                        if getattr(dialogs, 'ignore_checked', False):
                            self.model.power_change_ignore = True
                        self.model.confirm_power_change()
                    else:
                        self.model.cancel_power_change()
                dialogs.confirm(tr('Change laser power?'), self.model.power_change_warning, on_answer=answered)
            dialogs.draw(box)
            return
        if self.model.ui_mode == "guided":
            if (
                getattr(self.wizard.window, "_backdrop_cache", None) is None
                or getattr(self.wizard.window, "_backdrop_frame", None) != box
            ):
                self._draw_inert_background(box)
            if not self.wizard.window.open and self.wizard.model._index == 0:
                self.wizard.model.load_protocol()
            self.wizard.form.rects.clear()
            self.wizard.window.show()
            self.wizard.draw(box)
            return  # no interactive controls are drawn behind the modal wizard
        advanced = bool(self.model.advanced)
        if advanced != self._setup_quality_advanced:
            if advanced:
                self.docks.show('setup_quality')
                self.docks.show('settings')
            else:
                self.docks.hide('setup_quality')
                self.docks.hide('settings')
            self._setup_quality_advanced = advanced
        if not advanced:
            self.docks.hide('setup_quality')
            self.docks.hide('settings')
        self._sync_docks_to_mode()
        self._sync_docks_to_video()
        self._follow_tour()
        self._run_bar(box)
        self._sync_alignment_display(box)
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
            "ui_mode",
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
            "stop_after",
            "operator_name",
            "project_name",
            "sample_name",
            "experiment_type",
            "dye_names",
            "laser_kind",
            "mode",
            "trace_window_s",
            "trace_bin_ms",
            "decay_bursts_only",
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
        if self.model.simulation_connected:
            saved['laser_kind'] = self.model._simulation_previous['laser_kind']
        saved["video"] = {k: getattr(self.video, k) for k in ("address", "output", "fps", "display_gain")}
        return saved

    def restore_settings(self, settings: dict[str, Any]) -> None:
        for key, value in (settings or {}).get("video", {}).items():
            if key in ("address", "output", "fps", "display_gain"):
                setattr(self.video, key, value)
        if (settings or {}).get("video", {}).get("address", "").strip():
            self._video_auto_connect_pending = True
        self.model.source_kind = (settings or {}).get('source_kind', self.model.source_kind)
        self.model.source_changed()
        if self.model.simulation_connected and 'laser_kind' in (settings or {}):
            self.model._simulation_previous['laser_kind'] = settings['laser_kind']
        for key, value in (settings or {}).items():
            if key == 'source_kind' or (key == 'laser_kind' and self.model.simulation_connected):
                continue
            if hasattr(self.model, key) and not key.startswith("_"):
                setattr(self.model, key, value)
        if "ui_mode" not in (settings or {}):
            self.model.ui_mode = "advanced" if self.model.advanced else "simple"
        self.model.ui_mode_changed()
        # The settings last used on the hardware are loaded again on start: with the device
        # attached, connect and fill the form (only for a device source; a simulation or a
        # detached device connects nothing and the operator applies them with Load).
        if (settings or {}).get("settings_address") and self.model.source_kind == "device":
            try:
                attached = bool(devices.attached_devices())
            except Exception:
                attached = False
            if attached:
                self.model.settings_chosen()
            else:
                self.model.settings_detail = tr("Choose Load to apply these settings to connected hardware.")

    def close(self) -> None:
        self.model.cancel_power_target()
        if self.wizard.window.open:
            self.wizard.model.abort()
        self.video.close()
        if self.model.transfer_hook is not None and self.model.recorded_paths:
            self.model.transfer_pending()  # the archive backend gets what was recorded
        self.model.close()


def make_app() -> RecordApp:
    """The acq plugin's window: the Record tool."""
    from chisurf.emtk.i18n import install

    install()
    return RecordApp()
