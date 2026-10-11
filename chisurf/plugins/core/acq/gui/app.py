"""Qt-free native acquisition UI backed by the production streaming pipeline."""

from __future__ import annotations

import copy
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.file_dialog import FileDialog
from emtk.flags import InputTextFlags
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.core.acq.gui.live_plots import LivePlots, stream_words
from chisurf.plugins.core.acq.gui.setup_models import (
    BH_PARAMETERS,
    BHSetupModel,
    BrickMicSetupModel,
    PicoQuantSetupModel,
    SimulationSetupModel,
)
from chisurf.plugins.core.acq.pipeline import (
    AcquisitionPipeline,
    PipelineConfig,
    record_type_for_device,
)
from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
    build_engine,
    generate_spc132_uint32,
)
from chisurf.plugins.emtk_layout import action_button

HERE = Path(__file__).parent
DEVICE_LABELS = {
    "SIMULATION": "Simulation",
    "BH_SPC": "Becker-Hickl",
    "PICOQUANT": "PicoQuant",
    "BRICKMIC": "BrickMic",
}


#: ``gui.acquisition.device_type`` as Setup -> Settings -> Acquisition stores it -> this tool's device key.
SETTINGS_DEVICE_TYPES = {
    "Simulation": "SIMULATION",
    "Becker-Hickl": "BH_SPC",
    "PicoQuant": "PICOQUANT",
    "BrickMic": "BRICKMIC",
}


def stored_acquisition_settings() -> dict[str, Any]:
    """The ``gui.acquisition`` section Setup -> Settings -> Acquisition writes (``{}`` when there is none)."""
    try:
        from chisurf.settings import gui as gui_settings

        stored = gui_settings.get("acquisition") or {}
    except Exception:  # noqa: BLE001 - a missing or unreadable settings file means "nothing configured"
        return {}
    return stored if isinstance(stored, dict) else {}


def _peak(values: Any) -> float:
    """Largest finite brightness in a (nested) ``q`` list; 0 when there is none."""
    flat = np.asarray(values, dtype=float).ravel() if values is not None else np.zeros(0)
    flat = flat[np.isfinite(flat)]
    return float(flat.max()) if flat.size else 0.0


def default_acquisition_output_path() -> str:
    """Return the configured standard output folder, or the working-path fallback.

    The Settings panel's *standard output folder* (``gui["acquisition"]["output_path"]``)
    wins; without one, ``<working path>/acquisition`` and finally
    ``~/chisurf/acquisition``.
    """
    from chisurf import settings

    configured = str(
        (getattr(settings, "gui", {}).get("acquisition", {}) or {}).get("output_path", "") or ""
    ).strip()
    if configured:
        return str(Path(configured).expanduser())
    working_path = getattr(settings, "working_path", "") or ""
    if working_path:
        return str(Path(working_path).expanduser() / "acquisition")
    return str(Path.home() / "chisurf" / "acquisition")


def configured_output_path() -> str:
    """Return the standard output folder only when the user configured one, else ``""``."""
    from chisurf import settings

    configured = str(
        (getattr(settings, "gui", {}).get("acquisition", {}) or {}).get("output_path", "") or ""
    ).strip()
    return str(Path(configured).expanduser()) if configured else ""


def _default_hardware_factory(device_type: str):
    """Load a Qt wrapper only after the operator explicitly initializes hardware."""
    from chisurf.plugins.core.acq.tcspc_devices.device_factory import TCSPCDevice

    return TCSPCDevice(device_type)


class AcquisitionNativeModel:
    """Session state and explicit device lifecycle for the native acquisition UI."""

    def __init__(
        self,
        device_factory: Callable[[str], Any] | None = None,
        settings_path_provider: Callable[[str], str | Path | None] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        """Build an idle model without importing a device wrapper.

        *settings* is the ``gui.acquisition`` section (read from the user's settings when ``None``): its device
        type and simulator parameters -- what Setup -> Settings -> Acquisition edits -- are where the tool starts.
        """
        self.device_factory = device_factory or _default_hardware_factory
        self.settings_path_provider = settings_path_provider
        self.source = "simulation"
        self.hardware_contacted = False
        stored = stored_acquisition_settings() if settings is None else settings
        self.device_type = SETTINGS_DEVICE_TYPES.get(str(stored.get("device_type", "")), "SIMULATION")
        simulation = stored.get("simulation_params")
        #: The simulator parameters stored by Setup -> Settings -> Acquisition (``None``: built-in defaults).
        self.stored_simulation = copy.deepcopy(simulation) if isinstance(simulation, dict) else None
        self.time_limit_s, self.photon_limit = 900.0, 256
        self.channel_0, self.channel_1, self.channel_2, self.channel_3 = 8, 0, 9, 1
        # Prefilled from the Settings panel; empty (nothing written) until one is configured.
        self.output_folder = configured_output_path()
        self.brightness_khz, self.seed = 300.0, 12345
        if self.stored_simulation is not None:
            # The tool's Peak brightness / seed fields start at the stored values and scale / replace them.
            self.brightness_khz = _peak(self.stored_simulation.get("q")) or self.brightness_khz
            self.seed = int(self.stored_simulation.get("rmt1seed", self.seed))
        self.show_decay, self.show_correlation, self.show_count_rate = True, True, True
        self.show_macrotime, self.show_mcs = False, False
        self.status = "Ready: select a device and explicitly initialize it before Start."
        self.running = self.cancel_requested = self.initialized = False
        self.snapshot: dict[str, Any] | None = None
        self.live = LivePlots()
        #: The registered :class:`AcquisitionDataset` the fit window shows, if any.
        self.dataset: Any | None = None
        self.device: Any | None = None
        self.progress_percent = 0.0
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._cancel, self._thread = threading.Event(), None
        self._device_started = threading.Event()
        self._device_stop_sent = threading.Event()
        self._device_stop_lock = threading.Lock()
        self._file_request = ""
        self._device_setup_requested = False
        self.bh_simulation_mode = False
        self.advanced_settings_open = False
        self.advanced_settings_text = json.dumps(self.simulation_params(), indent=2, sort_keys=True)
        self._advanced_before_open = self.advanced_settings_text

    @property
    def channels(self) -> tuple[int, int, int, int]:
        """Return the legacy four-window routing order for :class:`PipelineConfig`."""
        return tuple(
            int(v) for v in (self.channel_0, self.channel_1, self.channel_2, self.channel_3)
        )

    def enabled(self, action: str) -> bool:
        """Return whether a user action is valid in the current lifecycle state."""
        if action in {"initialize_device", "start", "open_device_setup"}:
            return not self.running
        if action == "stop":
            return self.running
        if action in {
            "clear",
            "reset",
            "save_settings",
            "load_settings",
            "output_browse",
            "load_example",
        }:
            return not self.running
        return True

    def load_example(self) -> None:
        """Open the demo stream as a dataset with its Acquisition fit window (Load example)."""
        if self.running:
            return
        from chisurf.plugins.core.acq.dataset import open_demo

        try:
            if self.dataset is not None:
                self.dataset.close()
            self.dataset = open_demo()
            self.status = "Demo stream running: watch the Acquisition fit window."
        except Exception as exc:
            self.status = f"Could not open the demo fit window: {exc}"

    def open_device_setup(self) -> bool:
        """Request the selected device's native configuration card."""
        if self.running:
            self.status = "Device settings cannot be changed while an acquisition is running."
            return False
        self._device_setup_requested = True
        return True

    def simulation_params(self) -> dict[str, Any]:
        """Return the actual full simulator parameter dictionary used by the engine.

        Starts from the parameters stored in Setup -> Settings -> Acquisition (species, excitation mode,
        geometry, ...) when there are any; the tool's photon limit, seed and peak brightness are applied on top.
        """
        if self.stored_simulation is not None:
            return self.apply_tool_fields(copy.deepcopy(self.stored_simulation))
        return {
            "N_species": 1,
            "N_ph_max": max(1, int(self.photon_limit or 256)),
            "N_channels": 2,
            "M": [10.0],
            "D": [3.0],
            "q": [float(self.brightness_khz), float(self.brightness_khz) * 0.75],
            "q_bg": [0.001, 0.001],
            "k_rad": [0.0],
            "k_nrad": [0.0],
            "box_xy": 2.0,
            "box_z": 4.0,
            "focus_param": [0.3, 2.0],
            "dt": 0.01,
            "psf_type": "analytic_gaussian3d",
            "analytic_excitation": True,
            "rmt1seed": int(self.seed),
            "rmt2seed": int(self.seed) + 1,
            "N_tac_channels": 4096,
            "tac_dt": 0.004069,
            "decay_lifetimes": [[[1.0, 3.2]]],
        }

    def apply_tool_fields(self, params: dict[str, Any]) -> dict[str, Any]:
        """Write the tool's Photon limit, Deterministic seed and Peak brightness into simulator *params*.

        The brightness scales every ``q`` so that its largest entry is the peak brightness (the relative
        brightness of species and channels is kept). Returns *params*.
        """
        params["N_ph_max"] = max(1, int(self.photon_limit or params.get("N_ph_max", 1)))
        params["rmt1seed"], params["rmt2seed"] = int(self.seed), int(self.seed) + 1
        peak = _peak(params.get("q"))
        if peak > 0 and float(self.brightness_khz) > 0:
            scale = float(self.brightness_khz) / peak
            params["q"] = (np.asarray(params["q"], dtype=float) * scale).tolist()
        return params

    def _editor_params(self) -> dict[str, Any]:
        """Return advanced JSON when valid, otherwise the safe displayed defaults."""
        try:
            parsed = json.loads(self.advanced_settings_text)
        except json.JSONDecodeError:
            parsed = None
        return parsed if isinstance(parsed, dict) else self.simulation_params()

    def initialize_device(self) -> bool:
        """Create and initialize selected hardware only after the Initialize click."""
        if self.running:
            return False
        if self.device_type == "SIMULATION":
            self.initialized, self.source = True, "simulation"
            self.status = "Simulation initialized; no physical hardware was contacted."
            return True
        self.source, self.hardware_contacted = self.device_type, False
        try:
            self.device = self.device_factory(self.device_type)
        except Exception as exc:
            self.device = None
            self.status = f"{DEVICE_LABELS[self.device_type]} initialization failed: {exc}. No device was successfully made, so hardware was not contacted."
            return False
        try:
            self.initialized = bool(self.device.initialize())
        except Exception as exc:
            self.initialized = False
            self.status = f"{DEVICE_LABELS[self.device_type]} initialization failed: {exc}."
            return False
        self.hardware_contacted = True
        if not self.initialized:
            self.status = f"{DEVICE_LABELS[self.device_type]} initialization failed."
            return False
        try:
            active = (
                list(self.device.get_active_cards())
                if hasattr(self.device, "get_active_cards")
                else []
            )
        except Exception:
            active = []
        self.status = (
            f"{DEVICE_LABELS[self.device_type]} initialized ({len(active)} active device(s))."
        )
        return True

    def _pipeline(
        self, record_type: int, params: dict[str, Any] | None = None
    ) -> AcquisitionPipeline:
        """Create one production pipeline using native mappings and stop conditions."""
        tac = float((params or {}).get("tac_dt", 0.004069)) * 1e-9
        for i, channel in enumerate(self.channels):
            setattr(self.live, f"decay_ch{i}", channel)
        config = PipelineConfig(
            record_type=record_type,
            channels=self.channels,
            time_limit_s=max(0.0, float(self.time_limit_s)),
            photon_limit=max(0, int(self.photon_limit)),
            microtime_resolution_s=tac,
        )
        return AcquisitionPipeline(self.live.apply_to_config(config))

    def _configure_compatible_output(
        self, device: Any, params: dict[str, Any] | None = None
    ) -> None:
        """Pass output folders only to the simulation and BrickMic backends that support them."""
        path = str(self.output_folder).strip()
        if not path:
            return
        kind = getattr(device, "device_type", self.device_type)
        if kind == "SIMULATION" and device is not None and hasattr(device, "simulation_params"):
            device.simulation_params["spc_output_path"] = path
        elif kind == "BRICKMIC":
            target = getattr(device, "device", device)
            if hasattr(target, "spc_output_path"):
                target.spc_output_path = path
        elif params is not None:
            params["spc_output_path"] = path

    def start(self) -> bool:
        """Start an initialized device or simulator worker after validating stop conditions."""
        if self.running:
            return False
        if float(self.time_limit_s) <= 0 and int(self.photon_limit) <= 0:
            self.status = "Cannot start: set a positive time limit and/or photon limit."
            return False
        if self.device_type != "SIMULATION" and not self.initialized:
            self.status = "Cannot start: initialize the selected device first."
            return False
        self.running, self.cancel_requested, self.progress_percent = True, False, 0.0
        self._cancel.clear()
        self._device_started.clear()
        self._device_stop_sent.clear()
        if self.device_type == "SIMULATION":
            # The form's photon limit, seed and brightness reach the run (they were read once, at open, into
            # the advanced JSON, so editing them afterwards changed nothing).
            params = self.apply_tool_fields(self._editor_params())
            self._configure_compatible_output(None, params)
            self.status = (
                "Simulating encoded SPC records through AcquisitionPipeline; no hardware contacted."
            )
            target, args = self._run_simulation, (params,)
        else:
            self.status = (
                f"Streaming {DEVICE_LABELS[self.device_type]} FIFO through AcquisitionPipeline."
            )
            target, args = self._run_device, (self.device,)
        self._thread = threading.Thread(target=target, args=args, daemon=True)
        self._thread.start()
        return True

    def _stop_device_once(self, device: Any) -> Exception | None:
        """Send at most one physical stop command across UI and worker threads."""
        with self._device_stop_lock:
            if self._device_stop_sent.is_set():
                return None
            self._device_stop_sent.set()
        try:
            device.stop_measurement()
        except Exception as exc:  # a failed stop remains reportable, never retried blindly
            return exc
        return None

    def stop(self) -> bool:
        """Cancel a worker and interrupt its physical FIFO only when one is active."""
        if not self.running:
            self.status = "No simulator run or hardware acquisition is active."
            return False
        self.cancel_requested = True
        self._cancel.set()
        if (
            self.device_type != "SIMULATION"
            and self.device is not None
            and self._device_started.is_set()
        ):
            error = self._stop_device_once(self.device)
            if error is not None:
                self.status = f"Stop requested; device stop reported: {error}"
        self.status = "Stopping acquisition and flushing pipeline state."
        return True

    cancel = stop

    def _publish(self, pipeline: AcquisitionPipeline, cancelled: bool, source: str) -> None:
        """Flush pipeline state and send its real snapshot back to the render thread."""
        pipeline.flush()
        self._events.put(("result", (pipeline.snapshot(), cancelled, source)))

    def _run_simulation(self, params: dict[str, Any]) -> None:
        """Stream actual simulator words into the same production pipeline as hardware."""
        try:
            words = generate_spc132_uint32(params)
            pipeline = self._pipeline(PipelineConfig().record_type, params)
            stream_words(pipeline, words, self._events, every=8, cancel=self._cancel, pause_s=0.001)
            self._publish(pipeline, self._cancel.is_set(), "SIMULATION")
        except Exception as exc:
            self._events.put(("error", f"Simulation failed: {exc}; no hardware contacted."))

    def _run_device(self, device: Any) -> None:
        """Read fake or hardware FIFO words until stop, a limit, or FIFO exhaustion."""
        pipeline = self._pipeline(record_type_for_device(device))
        started, wall_start, empty = False, time.monotonic(), 0
        last_snapshot = wall_start
        try:
            if self._cancel.is_set():
                self._publish(pipeline, True, self.device_type)
                return
            self._configure_compatible_output(device)
            if not device.start_measurement():
                raise RuntimeError("device rejected start_measurement")
            started = True
            self._device_started.set()
            while not self._cancel.is_set() and not pipeline.stop_reason:
                if self.time_limit_s > 0 and time.monotonic() - wall_start >= self.time_limit_s:
                    pipeline.stop_reason = f"Time limit reached ({self.time_limit_s:.1f} s)"
                    break
                words = device.read_fifo(32768)
                if words is not None and len(words):
                    pipeline.push(np.asarray(words, dtype=np.uint32))
                    if time.monotonic() - last_snapshot >= 0.25:
                        last_snapshot = time.monotonic()
                        self._events.put(("snapshot", pipeline.snapshot()))
                    empty = 0
                else:
                    empty += 1
                    if empty >= 2:
                        break
                    time.sleep(0.001)
        except Exception as exc:
            self._events.put(("error", f"Hardware acquisition failed: {exc}"))
            return
        finally:
            if started:
                self._stop_device_once(device)
        self._publish(pipeline, self._cancel.is_set(), self.device_type)

    def poll(self) -> None:
        """Publish worker completion state without accessing device methods on the UI thread."""
        while True:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "snapshot":
                self.snapshot = payload
                self.live.set_snapshot(payload)
                if self.dataset is not None:
                    self.dataset.set_snapshot(payload)
                limit = int(self.photon_limit)
                if limit > 0:
                    self.progress_percent = min(99.0, 100.0 * payload["total_photons"] / limit)
                continue
            self.running, self.progress_percent = False, 100.0
            if kind == "result":
                self.snapshot, cancelled, source = payload
                self.live.set_snapshot(self.snapshot)
                if self.dataset is not None:
                    self.dataset.set_snapshot(self.snapshot)
                label = DEVICE_LABELS.get(source, str(source))
                self.status = f"{label} acquisition {'cancelled' if cancelled else 'complete'}: {int(self.snapshot['total_photons']):,} decoded photons."
            else:
                self.status = str(payload)

    def clear(self) -> None:
        """Clear only native result visibility, retaining selected device configuration."""
        if not self.running:
            self.snapshot, self.status = None, "Results cleared."
            self.live.clear()

    def reset(self) -> None:
        """Close any initialized session and restore defaults without constructing a device."""
        if not self.running:
            # Reset must not discard an initialized wrapper without closing it.
            # The next session is deliberately idle and requires a new explicit
            # initialization, rather than retaining a hardware handle invisibly.
            if self.device is not None:
                self.close()
            self.__init__(self.device_factory, self.settings_path_provider)
            self.status = "Settings restored to defaults; no new hardware was contacted."

    def open_advanced_settings(self) -> None:
        """Open the full actual simulation parameter dictionary for explicit editing."""
        self._advanced_before_open, self.advanced_settings_open = self.advanced_settings_text, True

    def apply_advanced_settings(self) -> bool:
        """Validate advanced JSON by constructing the actual simulator engine."""
        try:
            candidate = json.loads(self.advanced_settings_text)
            if not isinstance(candidate, dict):
                raise ValueError("simulation settings must be a JSON object")
            build_engine(candidate)
        except Exception as exc:
            self.status = f"Simulation settings rejected: {exc}"
            return False
        self.advanced_settings_text = json.dumps(candidate, indent=2, sort_keys=True)
        self.photon_limit = int(candidate.get("N_ph_max", self.photon_limit))
        self.seed = int(candidate.get("rmt1seed", self.seed))
        if _peak(candidate.get("q")) > 0:
            self.brightness_khz = _peak(candidate.get("q"))
        self.advanced_settings_open = False
        self.status = (
            "Simulation settings applied and validated by the configured simulator engine."
        )
        return True

    def cancel_advanced_settings(self) -> None:
        """Discard un-applied simulation JSON text."""
        self.advanced_settings_text, self.advanced_settings_open = self._advanced_before_open, False
        self.status = "Simulation settings edit cancelled."

    def settings_dict(self) -> dict[str, Any]:
        """Return the portable, no-device-action settings JSON contract."""
        return {
            "device_type": self.device_type,
            "time_limit_s": self.time_limit_s,
            "photon_limit": self.photon_limit,
            "channels": list(self.channels),
            "output_folder": self.output_folder,
            "brightness_khz": self.brightness_khz,
            "seed": self.seed,
            "show": {
                key: bool(getattr(self, key))
                for key in (
                    "show_decay",
                    "show_correlation",
                    "show_count_rate",
                    "show_macrotime",
                    "show_mcs",
                )
            },
            "simulation_params": self._editor_params(),
            "live_plots": self.live.export_settings(),
        }

    def apply_settings_dict(self, settings: dict[str, Any]) -> bool:
        """Validate and restore settings without automatically initializing a device."""
        try:
            device_type = str(settings["device_type"])
            channels = tuple(int(value) for value in settings["channels"])
            time_limit, photon_limit = (
                float(settings["time_limit_s"]),
                int(settings["photon_limit"]),
            )
            simulator = settings["simulation_params"]
            if (
                device_type not in DEVICE_LABELS
                or len(channels) != 4
                or any(not 0 <= value <= 4095 for value in channels)
            ):
                raise ValueError("invalid device type or routing channels")
            if time_limit < 0 or photon_limit < 0 or (time_limit <= 0 and photon_limit <= 0):
                raise ValueError("at least one stop condition must be positive")
            if not isinstance(simulator, dict):
                raise ValueError("simulation_params must be an object")
            build_engine(simulator)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.status = f"Settings load rejected: {exc}"
            return False
        self.device_type, self.time_limit_s, self.photon_limit = (
            device_type,
            time_limit,
            photon_limit,
        )
        self.channel_0, self.channel_1, self.channel_2, self.channel_3 = channels
        self.output_folder = str(settings.get("output_folder", ""))
        self.brightness_khz, self.seed = (
            float(settings.get("brightness_khz", self.brightness_khz)),
            int(settings.get("seed", self.seed)),
        )
        self.advanced_settings_text = json.dumps(simulator, indent=2, sort_keys=True)
        for key, value in settings.get("show", {}).items():
            if key.startswith("show_") and hasattr(self, key):
                setattr(self, key, bool(value))
        self.live.restore_settings(settings.get("live_plots", {}))
        self.status = "Settings loaded; initialize selected hardware explicitly before Start."
        return True

    def save_settings(self, path: str | Path | None = None) -> bool:
        """Save settings through an injected path seam or request the native file dialog."""
        target = path or (
            self.settings_path_provider("save") if self.settings_path_provider else None
        )
        if target is None:
            self._file_request = "save_settings"
            return True
        try:
            target = Path(target).with_suffix(".json")
            target.write_text(json.dumps(self.settings_dict(), indent=2), encoding="utf-8")
        except OSError as exc:
            self.status = f"Settings save failed: {exc}"
            return False
        self.status = f"Settings saved to {target}"
        return True

    def load_settings(self, path: str | Path | None = None) -> bool:
        """Load settings through an injected path seam or request the native file dialog."""
        target = path or (
            self.settings_path_provider("load") if self.settings_path_provider else None
        )
        if target is None:
            self._file_request = "load_settings"
            return True
        try:
            settings = json.loads(Path(target).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.status = f"Settings load rejected: {exc}"
            return False
        return self.apply_settings_dict(settings)

    def output_browse(self) -> None:
        """Request a native folder chooser without creating or writing to the selection."""
        self._file_request = "output_folder"

    def close(self) -> None:
        """Stop, bounded-join, flush, and close the selected session without hanging."""
        if self.running:
            self.stop()
            if self._thread is not None:
                self._thread.join(timeout=1.0)
            self.poll()
        if self.device is not None:
            try:
                self.device.close()
            except Exception as exc:
                self.status = f"Device close reported: {exc}"
            self.device, self.initialized = None, False


class AcquisitionApp(ImApp):
    """Render native acquisition controls, dialogs, guide, and real pipeline result tabs."""

    window_title = "ChiSurf Acquisition"

    def __init__(self, model: AcquisitionNativeModel | None = None) -> None:
        """Create a Qt-free native app around an injectable acquisition model."""
        self.model = model or AcquisitionNativeModel()
        self.sections = json.loads((HERE / "acq_emtk.view.json").read_text(encoding="utf-8"))[
            "sections"
        ]
        self.form, self.item_rects = FormState(), {}
        self.setup_buffers: dict[str, str] = {}
        self.form.custom["pipeline_results"] = self._draw_results
        for plot_key in (
            "live_decay",
            "live_correlation",
            "live_count_rate",
            "live_mcs",
            "live_macrotime",
        ):
            self.form.custom[plot_key] = lambda *a: self.model.live.draw_plot(*a)
        self.dialog, self.dialog_action = None, ""
        self.setup_open, self.setup_kind, self.setup_model = False, "", None
        self.setup_window = DialogWindow("Device Setup", size=(760, 560), key="acq_device_setup")
        self.file_window = DialogWindow(
            "Acquisition file chooser", size=(640, 460), key="acq_files"
        )
        self.help_window = EmTkHelpWindow(
            title="Acquisition help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self._last_fit_update = 0.0
        self._open_dataset()
        super().__init__(self.render, continuous=True)

    def _open_dataset(self) -> None:
        """Inside ChiSurf, open the demo stream's dataset and Acquisition fit window."""
        import chisurf as cs

        if getattr(cs, "cs", None) is not None:
            self.model.load_example()

    def _update_fits(self) -> None:
        """Pull the dataset's newest snapshot and redraw the fit windows that show it."""
        dataset = self.model.dataset
        if dataset is None:
            return
        changed = dataset.refresh()
        now = time.monotonic()
        if not changed or now - self._last_fit_update < 0.1:
            return
        self._last_fit_update = now
        dataset.update_fit()

    def _toolbar(self) -> None:
        """Draw the native Help and Guide buttons with useful tooltips."""
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if action_button("guide"):
            self.tour.start()
        self.item_rects["guide"] = im.get_item_rect()
        im.separator()

    def _open_file_dialog(self, action: str) -> None:
        """Open a native file or folder dialog requested by the model."""
        self.dialog_action = action
        if action == "output_folder":
            self.dialog = FileDialog("Choose acquisition output folder", mode="folder")
        else:
            self.dialog = FileDialog(
                action.replace("_", " ").title(),
                mode="save" if action == "save_settings" else "open",
                filters="JSON (*.json)",
                filename="acquisition_settings.json",
            )
        if action.startswith("bh_"):
            self.dialog = FileDialog(
                "Save BH settings" if action == "bh_save" else "Load BH settings",
                mode="save" if action == "bh_save" else "open",
                filters="JSON (*.json)",
                filename="bh_spc_settings.json",
            )
        self.file_window.title = self.dialog.title
        self.file_window.show()

    def _draw_file_dialog(self, box: tuple) -> None:
        """Route selected native dialog paths into the corresponding model operation."""
        if self.dialog is None:
            return
        close = self.file_window.begin(box)
        result = self.dialog.draw()
        if result:
            path = Path(result[0])
            if self.dialog_action == "save_settings":
                self.model.save_settings(path)
            elif self.dialog_action == "load_settings":
                self.model.load_settings(path)
            elif self.dialog_action == "bh_save":
                self.setup_model.save_json(path)
            elif self.dialog_action == "bh_load":
                self.setup_model.load_json(path)
            else:
                self.model.output_folder = str(path)
                self.model.status = (
                    "Output folder selected; it is passed only to compatible backends."
                )
            self.dialog = None
        elif result is False or close == "close":
            self.dialog = None
        self.file_window.end()

    def _open_device_setup(self) -> None:
        """Create a bounded Qt-free setup card for the currently selected source."""
        self.setup_kind = self.model.device_type
        if self.setup_kind == "BH_SPC":
            self.setup_model = BHSetupModel(self.model.device, self.model.bh_simulation_mode)
        elif self.setup_kind == "PICOQUANT":
            self.setup_model = PicoQuantSetupModel(self.model.device, self.model.photon_limit)
            self.setup_model.detect_status()
        elif self.setup_kind == "BRICKMIC":
            self.setup_model = BrickMicSetupModel(self.model.device)
        else:
            self.setup_kind = "SIMULATION"
            self.setup_model = SimulationSetupModel(self.model._editor_params())
        self.setup_open = True
        self.setup_window.title = f"{DEVICE_LABELS[self.setup_kind]} Device Setup"
        self.setup_window.show()

    def _close_device_setup(self) -> None:
        """Close a setup card without applying its editable state."""
        self.setup_open = False
        self.setup_window.hide()

    def _typed_field(
        self,
        key: str,
        text: str,
        minimum: float | None = None,
        maximum: float | None = None,
        integer: bool = True,
    ) -> float | int | None:
        """A keyboard-editable value field, as the main window's spin fields are.

        In-progress typing is kept in ``setup_buffers`` (as ``view_form``'s
        ``FormState.buffers`` does), so a frame never wipes the caret's text.
        A commit happens on Enter or click-away; it is parsed, clamped to
        *minimum*/*maximum* and returned; ``None`` when nothing committed.
        """
        flags = int(InputTextFlags.ENTER_RETURNS_TRUE) | int(InputTextFlags.AUTO_SELECT_ALL)
        shown = self.setup_buffers.get(key, text)
        entered, typed = im.input_text(f"##{key}", shown, "", flags)
        im.set_item_tooltip(
            (
                tr(
                    "Enter a whole-number acquisition setting. Press Enter or click elsewhere to commit; fractional entries are rounded and values are clamped to {minimum}–{maximum}."
                )
                if integer
                else tr(
                    "Enter a numeric acquisition setting. Press Enter or click elsewhere to commit; values are clamped to {minimum}–{maximum}."
                )
            ).format(minimum=minimum, maximum=maximum)
        )
        self.item_rects[key] = im.get_item_rect()
        if typed != shown:
            self.setup_buffers[key] = typed
        if entered:
            committed = self.setup_buffers.pop(key, typed)
            return self._parse_clamped(committed, minimum, maximum, integer)
        clicked_away = im.get_io().mouse_clicked[0] and not im.is_item_hovered()
        if key in self.setup_buffers and clicked_away:
            committed = self.setup_buffers.pop(key)
            return self._parse_clamped(committed, minimum, maximum, integer)
        return None

    @staticmethod
    def _parse_clamped(
        text: str, minimum: float | None, maximum: float | None, integer: bool
    ) -> float | int | None:
        """Parse committed field text; unparseable input commits nothing."""
        try:
            value = float(text)
        except ValueError:
            return None
        if integer:
            value = int(round(value))
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _draw_bh_setup(self) -> None:
        """Render all retained BH setup groups using stable native input IDs."""
        setup: BHSetupModel = self.setup_model
        if im.button(tr("Detect Cards") + "##bh_detect"):
            setup.detect_cards()
        im.set_item_tooltip(
            tr(
                "Discover BH modules through the supplied adapter using the selected simulation mode."
            )
        )
        self.item_rects["bh_detect"] = im.get_item_rect()
        im.same_line()
        changed, value = im.checkbox(
            tr("Simulation mode") + "##bh_simulation", setup.simulation_mode
        )
        im.set_item_tooltip(
            tr("Use simulated BH card detection; turn this off to request physical-card detection.")
        )
        if changed:
            setup.simulation_mode = value
        self.item_rects["bh_simulation"] = im.get_item_rect()
        im.text_wrapped(setup.status)
        for card in setup.cards:
            module = int(card["module_number"])
            active = module in setup.active_cards
            changed, selected = im.checkbox(
                f"Module {module}: {card.get('status', 'Unknown')}##bh_card_{module}", active
            )
            im.set_item_tooltip(
                tr("Include this BH module in the active-card selection written by Apply.")
            )
            if changed:
                setup.active_cards = [item for item in setup.active_cards if item != module]
                if selected:
                    setup.active_cards.append(module)
            self.item_rects[f"bh_card_{module}"] = im.get_item_rect()
        if im.begin_tab_bar("bh_setup_tabs"):
            for group in ("CFD", "Sync", "TAC", "Timing", "Mode"):
                if im.begin_tab_item(group):
                    for spec in (item for item in BH_PARAMETERS if item.group == group):
                        value = setup.values[spec.name]
                        im.text(spec.label)
                        im.same_line()
                        if spec.options:
                            keys = list(spec.options)
                            old = keys.index(int(value)) if int(value) in keys else 0
                            changed, index = im.combo(
                                f"##bh_{spec.name}", old, list(spec.options.values())
                            )
                            im.set_item_tooltip(
                                tr(
                                    "Select {parameter} from the supported hardware values. Apply writes this choice to the selected BH module."
                                ).format(parameter=tr(spec.label))
                            )
                            if changed:
                                setup.values[spec.name] = keys[index]
                        elif spec.integer:
                            committed = self._typed_field(
                                f"bh_{spec.name}",
                                str(int(value)),
                                minimum=float(spec.minimum),
                                maximum=float(spec.maximum),
                            )
                            if committed is not None:
                                setup.values[spec.name] = int(committed)
                        else:
                            committed = self._typed_field(
                                f"bh_{spec.name}",
                                format(value, "g"),
                                minimum=spec.minimum,
                                maximum=spec.maximum,
                                integer=False,
                            )
                            if committed is not None:
                                setup.values[spec.name] = float(committed)
                        self.item_rects[f"bh_{spec.name}"] = im.get_item_rect()
                    im.end_tab_item()
            im.end_tab_bar()
        if im.button(tr("Read values") + "##bh_read"):
            setup.read_parameters()
        im.set_item_tooltip(
            tr(
                "Read all retained BH parameter values from the detected module into these editable fields."
            )
        )
        self.item_rects["bh_read"] = im.get_item_rect()
        im.same_line()
        if im.button(tr("Save JSON") + "##bh_save"):
            self.model._file_request = "bh_save"
        im.set_item_tooltip(
            tr("Save editable BH parameter values to JSON without writing them to a device.")
        )
        self.item_rects["bh_save"] = im.get_item_rect()
        im.same_line()
        if im.button(tr("Load JSON") + "##bh_load"):
            self.model._file_request = "bh_load"
        im.set_item_tooltip(
            tr(
                "Load BH parameter values from JSON into these fields; press Apply to send them to the device."
            )
        )
        self.item_rects["bh_load"] = im.get_item_rect()
        im.same_line()
        if im.button(tr("Apply") + "##setup_apply"):
            if setup.apply():
                self.model.bh_simulation_mode = setup.simulation_mode
        im.set_item_tooltip(
            tr(
                "Write the active-card selection and validated BH parameters to the selected module."
            )
        )
        self.item_rects["setup_apply"] = im.get_item_rect()

    def _draw_picoquant_setup(self) -> None:
        """Render retained PicoQuant information and the global stop mapping."""
        setup: PicoQuantSetupModel = self.setup_model
        im.text_wrapped(
            tr(
                "PicoQuant devices are configured by snAPI, firmware, and INI files. This card does not claim a physical connection."
            )
        )
        im.text(f"Measurement mode (firmware): {setup.measurement_mode}")
        im.text(f"Reference source (firmware): {setup.reference_source}")
        im.text(tr("Maximum photons"))
        im.same_line()
        committed = self._typed_field(
            "pico_max_photons", str(int(setup.max_photons)), minimum=0.0, maximum=1_000_000_000.0
        )
        if committed is not None:
            setup.max_photons = int(committed)
        im.text_wrapped(setup.status)
        if im.button(tr("Refresh status") + "##pico_status"):
            setup.detect_status()
        im.set_item_tooltip(
            tr(
                "Query the initialized PicoQuant API for connected devices; an unavailable API does not imply a connection."
            )
        )
        self.item_rects["pico_status"] = im.get_item_rect()
        im.same_line()
        if im.button(tr("Apply") + "##setup_apply"):
            setup.apply(self.model)
        im.set_item_tooltip(
            tr(
                "Use the validated maximum-photon count as the acquisition stop limit; firmware settings remain unchanged."
            )
        )
        self.item_rects["setup_apply"] = im.get_item_rect()

    def _draw_brickmic_setup(self) -> None:
        """Render the retained BrickMic configuration fields with stable native IDs."""
        setup: BrickMicSetupModel = self.setup_model
        im.text_wrapped(
            tr(
                "BrickMic hardware acquisition and SPC output settings. "
                "Apply writes these values to the selected BrickMic backend."
            )
        )
        for key, label, minimum, maximum, step in BrickMicSetupModel.FIELDS:
            im.text(label)
            im.same_line()
            committed = self._typed_field(
                f"brickmic_{key}",
                str(int(setup.values[key])),
                minimum=float(minimum),
                maximum=float(maximum),
            )
            if committed is not None:
                setup.values[key] = int(committed)
        im.text(f"Channels (derived): {int(setup.values['channels'])}")
        im.text_wrapped(setup.status)
        if im.button(tr("Apply") + "##setup_apply"):
            setup.apply()
        im.set_item_tooltip(
            tr(
                "Write validated hardware acquisition and SPC output settings to the selected BrickMic backend."
            )
        )
        self.item_rects["setup_apply"] = im.get_item_rect()

    def _draw_simulation_setup(self) -> None:
        """Render the complete current simulator dictionary and production validation path."""
        setup: SimulationSetupModel = self.setup_model
        im.text_wrapped(
            tr(
                "All current simulation parameters are shown below. Apply validates this exact dictionary with the production simulator engine before use."
            )
        )
        changed, text = im.input_text_multiline("##simulation_setup_json", setup.text, (0.0, 350.0))
        if changed:
            setup.text = text
        self.item_rects["simulation_setup_json"] = im.get_item_rect()
        im.text_wrapped(setup.status)
        if im.button(tr("Apply") + "##setup_apply"):
            params = setup.apply()
            if params is not None:
                self.model.advanced_settings_text = setup.text
                self.model.photon_limit = int(params.get("N_ph_max", self.model.photon_limit))
                self.model.seed = int(params.get("rmt1seed", self.model.seed))
                target = self.model.device
                if target is not None and hasattr(target, "simulation_params"):
                    target.simulation_params.update(params)
        im.set_item_tooltip(
            tr(
                "Validate the complete configuration with the production simulator, then update acquisition limits and the selected simulator."
            )
        )
        self.item_rects["setup_apply"] = im.get_item_rect()

    def _draw_device_setup(self, box: tuple) -> None:
        """Draw the selected setup card as a bounded topmost native modal."""
        if not self.setup_open:
            return
        close = self.setup_window.begin(box)
        if self.setup_kind == "BH_SPC":
            self._draw_bh_setup()
        elif self.setup_kind == "PICOQUANT":
            self._draw_picoquant_setup()
        elif self.setup_kind == "BRICKMIC":
            self._draw_brickmic_setup()
        else:
            self._draw_simulation_setup()
        if im.button(tr("OK / close") + "##setup_ok"):
            self._close_device_setup()
        im.set_item_tooltip(
            tr(
                "Close device setup. Only settings already committed with Apply affect the device or acquisition."
            )
        )
        self.item_rects["setup_ok"] = im.get_item_rect()
        im.same_line()
        if (
            action_button(
                "cancel",
                id="setup_cancel",
                tooltip=tr(
                    "Close this card without applying pending device-setting edits; earlier Apply operations remain in effect."
                ),
            )
            or close == "close"
        ):
            self._close_device_setup()
        self.item_rects["setup_cancel"] = im.get_item_rect()
        self.setup_window.end()

    def _draw_advanced(self, box: tuple) -> None:
        """Render full simulator JSON with explicit Apply and Cancel lifecycle actions."""
        if not self.model.advanced_settings_open:
            return
        im.set_next_window_size((640.0, 520.0), im.Cond.FIRST_USE_EVER)
        if im.begin("Advanced simulation parameters", box):
            im.text_wrapped(
                tr(
                    "Apply constructs the actual simulator engine to validate this complete JSON dictionary."
                )
            )
            im.set_item_tooltip(tr("Full actual simulator configuration, not a decorative copy."))
            changed, text = im.input_text_multiline(
                "##advanced_json", self.model.advanced_settings_text, (0.0, 380.0)
            )
            if changed:
                self.model.advanced_settings_text = text
            im.set_item_tooltip(
                tr(
                    "Edit valid JSON only; Apply accepts it only if the simulator engine constructs."
                )
            )
            self.item_rects["advanced_json"] = im.get_item_rect()
            if im.button(tr("Apply advanced settings")):
                self.model.apply_advanced_settings()
            im.set_item_tooltip(
                tr("Validate the exact dictionary with the production simulator engine.")
            )
            self.item_rects["apply_advanced_settings"] = im.get_item_rect()
            im.same_line()
            if im.button(tr("Cancel advanced settings")):
                self.model.cancel_advanced_settings()
            im.set_item_tooltip(tr("Discard un-applied JSON edits."))
            self.item_rects["cancel_advanced_settings"] = im.get_item_rect()
        im.end()

    def _draw_results(
        self, section: dict[str, Any], model: AcquisitionNativeModel, state: FormState, width: float
    ) -> None:
        """Draw the overview line and the live plots from :class:`AcquisitionPipeline` snapshots."""
        top, snapshot = im.get_cursor_screen_pos(), model.snapshot
        live = model.live
        for tab, flag in (
            ("decay", model.show_decay),
            ("correlation", model.show_correlation),
            ("count_rate", model.show_count_rate),
            ("mcs", model.show_mcs),
            ("macrotime", model.show_macrotime),
        ):
            setattr(live, f"tab_{tab}", bool(flag))
        if snapshot is None:
            im.text_wrapped(
                tr(
                    "No result yet. Initialize a device or run the simulator, then Start acquisition."
                )
            )
            im.set_item_tooltip(str(section["description"]))
            state.rects["pipeline_results"] = (*top, width, 28.0)
            return
        im.text(
            f"{tr('Photons')}: {int(snapshot['total_photons']):,} | "
            f"{tr('Elapsed')}: {float(snapshot['elapsed_s']):.3f} s | "
            f"{float(snapshot['mean_count_rate_khz']):.1f} kHz | {model.progress_percent:.0f}%"
        )
        draw_sections(live.sections, live, state, titles=False)
        bottom = im.get_cursor_screen_pos()
        state.rects["pipeline_results"] = (top[0], top[1], width, max(28.0, bottom[1] - top[1]))

    def render(self) -> None:
        """Render one responsive frame and service model-requested native dialogs."""
        self.model.poll()
        self._update_fits()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        im.set_next_window_pos(vp.pos, im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin("ChiSurf Acquisition", box):
            self._toolbar()
            draw_sections(self.sections, self.model, self.form, titles=True)
        im.end()
        if self.model._file_request:
            action, self.model._file_request = self.model._file_request, ""
            self._open_file_dialog(action)
        self._draw_file_dialog(box)
        self._draw_advanced(box)
        if self.model._device_setup_requested:
            self.model._device_setup_requested = False
            self._open_device_setup()
        self._draw_device_setup(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def export_settings(self) -> dict[str, Any]:
        """Expose host persistence without persisting a hardware session."""
        return self.model.settings_dict()

    def restore_settings(self, settings: dict[str, Any]) -> None:
        """Restore validated host settings without implicit device initialization."""
        self.model.apply_settings_dict(settings)

    def close(self) -> None:
        """Close a session through the model's safe cancellation lifecycle."""
        if self.model.dataset is not None:
            self.model.dataset.close()
        self.model.close()


def make_app() -> AcquisitionApp:
    """Build the manifest's Qt-free native acquisition factory."""
    from chisurf.emtk.i18n import install

    install()
    return AcquisitionApp()
