"""The Record tool: measure, watch the burst histograms build up, keep the run in the project.

``record.view.json`` declares every control; :class:`RecordModel` is its model and owns the
:class:`~chisurf.plugins.core.acq.live.session.RecordSession` of a run. The analysis runs in the
session's worker thread; the window takes a snapshot of its accumulators about five times a second
and draws from that (:meth:`RecordApp._draw_live`), never from photons. The measurement type is
the Experiment setup's preset (single colour, two colour, PIE, µs-ALEX, MFD, three-colour PIE); the
histograms shown are the ones the analyzer keeps for it. The device session of
earlier versions stays reachable as *Device session…* (``app.AcquisitionApp``).

Devices are CMC's ``pqusb`` (PicoQuant over libusb). The simulator is a simulated MultiHarp
(``live.devices.PieSimDevice``), so a simulated run takes the hardware path from the FIFO on; without
pqusb the photon-level simulator stands in.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im
from emtk.app import ImApp
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.core.acq.live import devices
from chisurf.plugins.core.acq.live.analyzer import PRESETS
from chisurf.plugins.core.acq.live.session import RecordSession
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
#: How often the window takes a snapshot of the running analysis.
SNAPSHOT_INTERVAL_S = 0.2
_COLOURS = [
    (0.17, 0.63, 0.17, 1.0),
    (0.84, 0.15, 0.16, 1.0),
    (0.58, 0.40, 0.74, 1.0),
    (0.12, 0.47, 0.71, 1.0),
    (0.9, 0.6, 0.1, 1.0),
    (0.4, 0.4, 0.4, 1.0),
]


def _workspace(kind: str) -> list[Any]:
    try:
        from chisurf.core.api import dataset_objects

        return [d for d in dataset_objects() if str(getattr(d, "data_kind", "")) == kind]
    except Exception:  # noqa: BLE001 - no session (standalone): an empty workspace
        return []


class RecordModel:
    """The state behind ``record.view.json``.

    Parameters
    ----------
    output_dir : str or Path, optional
        Where recordings are written; the acquisition output folder by default.
    realtime : bool
        ``False`` lets simulated and replayed photons arrive as fast as they are made (tests).
    """

    def __init__(self, output_dir: str | Path | None = None, *, realtime: bool = True):
        from chisurf.plugins.core.acq.gui.app import default_acquisition_output_path

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
        self.min_photons = 30
        self.window_photons = 10
        self.window_time_ms = 1.0
        self.duration_s = 60.0
        self.run_name = ""
        self.status_text = tr("Ready. Press Load example, then Start.")
        self.session: RecordSession | None = None
        self.snapshot: dict[str, Any] | None = None
        self._last_snapshot = 0.0
        self._registered = False
        self._open_classic = False
        # -- the TCSPC device (pqusb) ----------------------------------------------------------
        self.device_index = "0"
        self.device = None
        self._found: list[str] = []
        self._found_at = -1e9
        self.device_text = tr("No device connected.")
        self._rates_at = 0.0
        self.sync_div = 1
        self.sync_level_mv = -50
        self.sync_edge = "0"
        self.sync_offset_ps = 0
        self.input_level_mv = -50
        self.input_edge = "0"
        self.donor_offset_ps = 0
        self.acceptor_offset_ps = 0
        self.binning = 0
        self.offset_ns = 0

    # -- options ---------------------------------------------------------------------------------
    def source_options(self) -> list:
        return [
            ("simulator", tr("Simulator (smFRET)")),
            ("replay", tr("Replay a photon stream")),
            (
                "device",
                tr("PicoQuant device (USB)")
                if devices.PQUSB
                else tr("PicoQuant device (pqusb not installed)"),
            ),
        ]

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

    def attached(self) -> list[str]:
        """The attached devices, enumerated at most every two seconds (not on every frame)."""
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
                    tr("No PicoQuant device found")
                    if devices.PQUSB
                    else tr("pqusb is not installed"),
                )
            ]
        return [(str(i), str(name)) for i, name in enumerate(found)]

    # -- the device --------------------------------------------------------------------------------
    def connect_device(self) -> bool:
        if self.device is not None or not devices.PQUSB:
            return False
        try:
            import pqusb

            dev = pqusb.open_device(int(self.device_index or 0))
            ident = dev.initialize(pqusb.MODE_T3, 0)
        except Exception as exc:  # noqa: BLE001 - busy, no permission, unsupported model
            self.device_text = tr("Cannot connect: {e}").format(e=exc)
            return False
        self.device = dev
        self.device_text = tr("{model} {serial}, {n} inputs, T3 mode.").format(
            model=ident.model, serial=ident.serial, n=getattr(dev, "nchan", "?")
        )
        self._update_rates(force=True)
        return True

    def disconnect_device(self) -> bool:
        if self.device is None or self.running:
            return False
        try:
            self.device.close()
        finally:
            self.device = None
            self.device_text = tr("No device connected.")
        return True

    def apply_device_settings(self, dev, exp: Experiment) -> None:
        """Send the TCSPC settings to *dev* (before a run)."""
        dev.set_sync_div(int(self.sync_div))
        dev.set_sync_edge_trg(int(self.sync_level_mv), int(self.sync_edge))
        dev.set_sync_channel_offset(int(self.sync_offset_ps))
        for ch in range(int(getattr(dev, "nchan", 0) or 0)):
            dev.set_input_edge_trg(ch, int(self.input_level_mv), int(self.input_edge))
        offsets = {}
        for role, ps in (("donor", self.donor_offset_ps), ("acceptor", self.acceptor_offset_ps)):
            chs = exp.channels(role)
            if chs:
                offsets[chs[0]] = ps
        for ch, ps in offsets.items():
            if 0 <= int(ch) < int(getattr(dev, "nchan", 0) or 0):
                dev.set_input_channel_offset(int(ch), int(ps))
        dev.set_binning(int(self.binning))
        dev.set_offset(int(self.offset_ns))

    def _update_rates(self, force: bool = False) -> None:
        """Count rates of the connected device while it does not measure (about once a second)."""
        if self.device is None or self.running:
            return
        now = time.monotonic()
        if not force and now - self._rates_at < 1.0:
            return
        self._rates_at = now
        try:
            sync, inputs = self.device.count_rates()
        except Exception as exc:  # noqa: BLE001 - shown, the device stays connected
            self.device_text = (
                self.device_text.split(" — ")[0] + " — " + tr("rates: {e}").format(e=exc)
            )
            return
        rates = ", ".join(f"{i + 1}: {r / 1e3:.1f} kHz" for i, r in enumerate(inputs))
        head = self.device_text.split(" — ")[0]
        self.device_text = f"{head} — " + tr("sync {sync:.2f} MHz; inputs {rates}").format(
            sync=sync / 1e6, rates=rates
        )

    def photon_options(self) -> list:
        rows = [
            (str(d.address), str(getattr(d, "name", "") or d.address))
            for d in _workspace("photons")
        ]
        return rows or [("", tr("No photon stream in the workspace"))]

    def setup_options(self) -> list:
        rows = [
            (str(d.address), str(getattr(d, "name", "") or d.address)) for d in _workspace("setup")
        ]
        return [
            (
                DEFAULT_SETUP,
                tr("Default for the type (channel 0 donor, 1 acceptor; PIE: half periods)"),
            )
        ] + rows

    # -- what the run uses -----------------------------------------------------------------------
    def make_source(self):
        if self.source_kind == "simulator":
            pops = (
                Population(self.sim_e_low, self.sim_s, self.sim_concentration),
                Population(self.sim_e_high, self.sim_s, self.sim_concentration),
            )
            if devices.PQUSB:
                import pqusb

                # A simulated MultiHarp: the run takes the hardware path from the FIFO on.
                dev = devices.PieSimDevice(
                    pops,
                    seed=int(self.sim_seed),
                    speed=float(self.speed) if self.realtime else 1000.0,
                    scheme=self.sim_scheme,
                )
                dev.initialize(pqusb.MODE_T3)
                self.apply_device_settings(dev, self.make_experiment(400))
                dev.set_sync_div(1)
                return devices.DeviceSource(dev)
            return SimulatedPieSource(
                pops,
                duration_s=None,
                seed=int(self.sim_seed),
                speed=float(self.speed),
                realtime=self.realtime,
                scheme=self.sim_scheme,
            )
        if self.source_kind == "replay":
            if not self.replay_address:
                raise SourceUnavailable(tr("Choose a photon stream of the workspace first."))
            return FileReplaySource(
                self.replay_address, speed=float(self.speed), realtime=self.realtime
            )
        if not devices.PQUSB:
            raise SourceUnavailable(
                tr("PicoQuant devices need pqusb (CMC), which is not installed.")
            )
        if self.device is None:
            raise SourceUnavailable(tr("Connect the device first."))
        return devices.DeviceSource(self.device)

    def _default_preset(self) -> str:
        if self.source_kind == "simulator":
            return self.sim_scheme
        return "pie"

    def make_experiment(self, n_micro: int) -> Experiment:
        """The setup (workspace row or the type's default) read with the chosen preset."""
        burst = BurstParameters(
            int(self.min_photons), int(self.window_photons), float(self.window_time_ms) / 1e3
        )
        if self.setup_address in ("", DEFAULT_SETUP):
            preset = self.preset if self.preset != AUTO_PRESET else self._default_preset()
            setup, name = default_setup(preset, n_micro), f"default {preset}"
        else:
            from chisurf.plugins.tttr.workspace_io import read_setup

            setup, name = read_setup(self.setup_address), Path(self.setup_address).name
            preset = self.preset if self.preset != AUTO_PRESET else infer_preset(setup)
        return Experiment(
            setup,
            preset,
            burst,
            name=name,
            alex_period_s=float(self.alex_period_us) * 1e-6 if preset == "alex" else None,
        )

    def setup_text(self) -> str:
        n_micro = 400 if self.session is None else self.session.source.info.n_micro
        try:
            exp = self.make_experiment(n_micro)
        except Exception as exc:  # noqa: BLE001 - shown, the run refuses to start
            return tr("The setup cannot be used: {e}").format(e=exc)
        return f"{tr(PRESET_LABELS[exp.preset])}: {exp.describe()}"

    def target_text(self) -> str:
        return tr(
            "Recorded to {folder}; enters the project as a photons dataset (linked or embedded as "
            "Read data › Add as says), its bursts as a run below it."
        ).format(folder=self.output_dir)

    # -- actions ---------------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.session is not None and self.session.running

    def enabled(self, action: str) -> bool:
        if action == "start":
            return not self.running and (self.source_kind != "device" or self.device is not None)
        if action == "connect_device":
            return devices.PQUSB and self.device is None and bool(self.attached())
        if action == "disconnect_device":
            return self.device is not None and not self.running
        if action == "stop":
            return self.running
        if action in ("load_example", "open_classic"):
            return not self.running
        return True

    def load_example(self) -> None:
        self.source_kind = "simulator"
        self.sim_e_low, self.sim_e_high, self.sim_s = 0.2, 0.8, 0.5
        self.sim_concentration = 1.0
        self.min_photons, self.window_photons, self.window_time_ms = 30, 10, 1.0
        self.setup_address = DEFAULT_SETUP
        self.sim_scheme, self.preset = "pie", AUTO_PRESET
        self.duration_s = 60.0
        self.status_text = tr(
            "Example ready: PIE, two populations, E 0.2 and 0.8, S 0.5. Press Start."
        )

    def start(self) -> bool:
        if self.running:
            return False
        try:
            if self.source_kind == "device" and self.device is not None:
                self.apply_device_settings(self.device, self.make_experiment(1))
            source = self.make_source()
            experiment = self.make_experiment(source.info.n_micro)
        except Exception as exc:  # noqa: BLE001 - the user picks something else
            self.status_text = str(exc)
            return False
        name = self.run_name.strip() or time.strftime("record_%Y%m%d_%H%M%S")
        self.session = RecordSession(
            source,
            experiment,
            duration_s=self.duration_s or None,
            ptu_path=self.output_dir / f"{name}.ptu",
            name=name,
        )
        try:
            self.session.start()
        except OSError as exc:
            self.status_text = str(exc)
            self.session = None
            return False
        self._registered = False
        self.snapshot = None
        self.plot_choice = ""
        self.status_text = tr("Recording {name} …").format(name=name)
        return True

    def stop(self) -> bool:
        if not self.running:
            return False
        self.session.stop()
        return True

    def open_classic(self) -> None:
        self._open_classic = True

    def poll(self, force: bool = False) -> None:
        """Take a snapshot at the display rate; register the run once it ended."""
        self._update_rates()
        session = self.session
        if session is None:
            return
        now = time.monotonic()
        if force or now - self._last_snapshot >= SNAPSHOT_INTERVAL_S:
            self.snapshot = session.snapshot()
            self._last_snapshot = now
        if not session.running and session.result is not None and not self._registered:
            self._registered = True
            self.snapshot = session.snapshot()
            result = session.result
            try:
                session.register()
                where = tr("in the workspace") if result.dataset_uid else tr("on disk")
            except Exception as exc:  # noqa: BLE001 - the file is written either way
                where = tr("on disk (not added to the workspace: {e})").format(e=exc)
            self.status_text = tr(
                "{reason}: {bursts} bursts in {photons} photons, {t:.1f} s — {file} {where}."
            ).format(
                reason=result.stop_reason.capitalize(),
                bursts=result.bursts,
                photons=result.photons,
                t=result.elapsed_s,
                file=result.ptu.name if result.ptu else "",
                where=where,
            )

    def close(self) -> None:
        if self.running:
            self.session.stop()
            self.session.wait(5.0)
        if self.device is not None:
            self.disconnect_device()


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


def _plot_decays(snap: dict, exp: Experiment | None, size) -> None:
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
            implot.set_next_line_style(_COLOURS[k % len(_COLOURS)])
            implot.plot_line(name, np.arange(y.size, dtype=float), np.maximum(y, 0.5))
        windows = (exp.setup.get("windows") or {}) if exp is not None else {}
        if windows:
            edges = sorted({float(v) for r in windows.values() for v in r})
            implot.plot_inf_lines(tr("windows"), np.asarray(edges, dtype=float))
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
    """The quality checker's verdict as traffic lights: overall, then one light per check."""
    if not qc or not qc.get("ready"):
        why = (qc or {}).get("why", "")
        im.text_colored(_LIGHT_COLOURS["grey"], "●")
        im.same_line()
        im.text_wrapped(tr("Quality: not enough data yet") + (f" ({why})" if why else ""))
        return
    level = qc["level"]
    im.text_colored(_LIGHT_COLOURS[level], "●")
    im.same_line()
    im.text(tr(_OVERALL[level]))
    for check in qc["checks"]:
        im.text_colored(_LIGHT_COLOURS.get(check["light"], _LIGHT_COLOURS["grey"]), "●")
        im.same_line()
        im.text_wrapped(f"{check['name']}: {check['value']}")
        im.set_item_tooltip(check["detail"])
        if check.get("action"):
            im.text_colored(_LIGHT_COLOURS.get(check["light"], _LIGHT_COLOURS["grey"]), "   →")
            im.same_line()
            im.text_wrapped(check["action"])


class RecordApp(ImApp):
    """The Record tool's window (``record.view.json`` plus the live plots)."""

    window_title = "ChiSurf Record"

    def __init__(self, model: RecordModel | None = None) -> None:
        self.model = model or RecordModel()
        self.sections = json.loads((HERE / "record.view.json").read_text(encoding="utf-8"))[
            "sections"
        ]
        self.form = FormState()
        self.form.custom["live_view"] = self._draw_live
        self.help_window = EmTkHelpWindow(
            title="Record help", resource=HERE / "record_help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "record_guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.classic = None
        super().__init__(self.render, continuous=True)

    def _toolbar(self) -> None:
        if im.small_button(f"📖 {tr('Guide')}"):
            self.tour.start()
        im.same_line()
        if im.small_button(f"❓ {tr('Help')}"):
            self.help_window.open()

    def _draw_live(self, section: dict, model: RecordModel, state: FormState, width: float) -> None:
        top = im.get_cursor_screen_pos()
        snap = model.snapshot
        if snap is None:
            im.text_wrapped(
                tr("Nothing measured yet. Start a run to see its bursts build up here.")
            )
            state.rects["live_view"] = (*top, width, 28.0)
            state.rects["live_qc"] = (*top, width, 28.0)
            return
        exp = model.session.experiment if model.session is not None else None
        im.text(
            f"{tr('Bursts')}: {snap['bursts']:,}   {tr('Burst rate')}: {snap['burst_rate_hz']:.1f} Hz   "
            f"{tr('Photons')}: {snap['photons']:,}   {tr('Measured')}: {snap['elapsed_s']:.1f} s"
        )
        bg = ", ".join(
            f"{name} {rate / 1e3:.2f}"
            for name, rate in snap["background_cps"].items()
            if name in _shown_streams(snap, exp)
        )
        im.text_disabled(
            tr(
                "Health: {batches} batches, {dropped} dropped, {queued} buffered; background (kHz) {bg}"
            ).format(batches=snap["batches"], dropped=snap["dropped"], queued=snap["queued"], bg=bg)
        )
        if snap.get("source_error"):
            im.text_colored((1.0, 0.45, 0.4, 1.0), str(snap["source_error"]))
        hists = snap.get("histograms") or {}
        if hists and model.plot_choice not in hists:
            two_d = [n for n, h in hists.items() if "y" in h]
            model.plot_choice = (two_d or list(hists))[0]
        avail_h = max(320.0, im.get_content_region_avail()[1] - 8.0)
        plot_w = max(320.0, width * 0.62)
        if im.begin_child("##hist_block", (plot_w, avail_h * 0.62), scrollable=False):
            if hists:
                _plot_histogram(hists[model.plot_choice], avail_h * 0.62 - 6.0)
            else:
                im.text_wrapped(tr("This measurement type keeps no histogram."))
        im.end_child()
        im.same_line()
        qc_top = im.get_cursor_screen_pos()
        qc_w = width - plot_w - 8.0
        if im.begin_child("##qc_block", (qc_w, avail_h * 0.62)):
            _draw_qc(snap.get("qc"))
        im.end_child()
        state.rects["live_qc"] = (qc_top[0], qc_top[1], qc_w, avail_h * 0.62)
        half = (width - 8.0) / 2
        _plot_rates(snap, exp, (half, avail_h * 0.34))
        im.same_line()
        _plot_decays(snap, exp, (half, avail_h * 0.34))
        bottom = im.get_cursor_screen_pos()
        state.rects["live_view"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def render(self) -> None:
        self.model.poll()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        if self.model._open_classic:
            if self.classic is None:
                from chisurf.plugins.core.acq.gui.app import AcquisitionApp

                self.classic = AcquisitionApp()
            self.classic.render()
            im.set_next_window_pos((vp.pos[0] + vp.size[0] - 190, vp.pos[1] + 4), im.Cond.ALWAYS)
            if im.begin(
                "##back_to_record",
                None,
                im.WindowFlags.NO_DECORATION | im.WindowFlags.ALWAYS_AUTO_RESIZE,
            ):
                if im.button(f"⏺ {tr('Back to Record')}"):
                    self.model._open_classic = False
            im.end()
            return
        self.form.rects.clear()
        im.set_next_window_pos(vp.pos, im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin("ChiSurf Record", box):
            self._toolbar()
            avail = im.get_content_region_avail()
            left = min(460.0, max(320.0, avail[0] * 0.34))
            if im.begin_child("##record_controls", (left, avail[1])):
                draw_sections(self.sections[:-1], self.model, self.form, titles=True)
            im.end_child()
            im.same_line()
            if im.begin_child("##record_live", (avail[0] - left - 8.0, avail[1])):
                draw_sections(self.sections[-1]["sections"], self.model, self.form, titles=False)
            im.end_child()
        im.end()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

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
            "min_photons",
            "window_photons",
            "window_time_ms",
            "duration_s",
        )
        return {k: getattr(self.model, k) for k in keys}

    def restore_settings(self, settings: dict[str, Any]) -> None:
        for key, value in (settings or {}).items():
            if hasattr(self.model, key) and not key.startswith("_"):
                setattr(self.model, key, value)

    def close(self) -> None:
        self.model.close()
        if self.classic is not None:
            self.classic.close()


def make_app() -> RecordApp:
    """The acq plugin's window: the Record tool."""
    from chisurf.emtk.i18n import install

    install()
    return RecordApp()
