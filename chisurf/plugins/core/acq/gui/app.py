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
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.core.acq.gui.live_plots import LivePlots, stream_words
from chisurf.plugins.core.acq.gui.setup_forms import SPECS as SETUP_SPECS
from chisurf.plugins.core.acq.gui.setup_forms import (
    BHSetupForm,
    BrickMicSetupForm,
    PicoQuantSetupForm,
)
from chisurf.plugins.core.acq.gui.setup_models import (
    BHSetupModel,
    BrickMicSetupModel,
    PicoQuantSetupModel,
)
from chisurf.plugins.core.acq.gui.sim_setup import SimulationSetupDialog
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
        from chisurf.core.settings import gui as gui_settings

        stored = gui_settings.get("acquisition") or {}
    except Exception:  # noqa: BLE001 - a missing or unreadable settings file means "nothing configured"
        return {}
    return stored if isinstance(stored, dict) else {}


def _peak(values: Any) -> float:
    """Largest finite brightness in a (nested) ``q`` list; 0 when there is none."""
    flat = np.asarray(values, dtype=float).ravel() if values is not None else np.zeros(0)
    flat = flat[np.isfinite(flat)]
    return float(flat.max()) if flat.size else 0.0


def _seed_offset(params: dict[str, Any]) -> int:
    """Distance of the emission seed from the diffusion seed in simulator *params* (1 when unset)."""
    try:
        return int(params.get("rmt2seed", int(params["rmt1seed"]) + 1)) - int(params["rmt1seed"])
    except (KeyError, TypeError, ValueError):
        return 1


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
        self.device_type = SETTINGS_DEVICE_TYPES.get(
            str(stored.get("device_type", "")), "SIMULATION"
        )
        simulation = stored.get("simulation_params")
        #: The simulator parameters stored by Setup -> Settings -> Acquisition (``None``: built-in defaults).
        self.stored_simulation = copy.deepcopy(simulation) if isinstance(simulation, dict) else None
        self.time_limit_s, self.photon_limit = 900.0, 256
        self.channel_0, self.channel_1, self.channel_2, self.channel_3 = 8, 0, 9, 1
        # Prefilled from the Settings panel; empty (nothing written) until one is configured.
        self.output_folder = configured_output_path()
        self.brightness_khz, self.seed = 300.0, 12345
        #: Emission seed minus diffusion seed: the seed field moves both, keeping their distance.
        self.seed_offset = 1
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
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._device_started = threading.Event()
        self._device_stop_sent = threading.Event()
        self._device_stop_lock = threading.Lock()
        self._file_request = ""
        self._device_setup_requested = False
        self._simulation_setup_requested = False
        self.bh_simulation_mode = False
        self.advanced_settings_open = False
        self.advanced_settings_text = json.dumps(self.simulation_params(), indent=2, sort_keys=True)
        self._advanced_before_open = self.advanced_settings_text

    @property
    def channels(self) -> tuple[int, int, int, int]:
        """Return the legacy four-window routing order for :class:`PipelineConfig`."""
        return (
            int(self.channel_0),
            int(self.channel_1),
            int(self.channel_2),
            int(self.channel_3),
        )

    def enabled(self, action: str) -> bool:
        """Return whether a user action is valid in the current lifecycle state."""
        if action in {"initialize_device", "start", "open_device_setup", "open_simulation_setup"}:
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
        params["rmt1seed"], params["rmt2seed"] = (
            int(self.seed),
            int(self.seed) + int(self.seed_offset),
        )
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
        target: Callable[..., None]
        args: tuple[Any, ...]
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
            type(self).__init__(self, self.device_factory, self.settings_path_provider)
            self.status = "Settings restored to defaults; no new hardware was contacted."

    def open_simulation_setup(self) -> bool:
        """Request the simulation setup dialog (species, brightness and kinetics grids)."""
        if self.running:
            self.status = "Simulation settings cannot be changed while an acquisition is running."
            return False
        self._simulation_setup_requested = True
        return True

    def apply_simulation_setup(self, params: dict[str, Any]) -> bool:
        """Apply the dialog's parameters: the full dictionary the next run simulates.

        The dictionary is merged over the current one (keys the dialog does not edit are kept) and
        validated by constructing the production engine, exactly like the advanced JSON.
        """
        before = self.advanced_settings_text
        self.advanced_settings_text = json.dumps(
            {**self._editor_params(), **params}, indent=2, sort_keys=True
        )
        if not self.apply_advanced_settings():
            self.advanced_settings_text = before
            return False
        self.status = "Simulation setup applied; the next run simulates these species and rates."
        return True

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
        self.seed_offset = _seed_offset(candidate)
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
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        #: The open device card's form binding, sections and form state (``setup_forms``, ``*_setup.view.json``).
        self._card_form: Any = None
        self._card_sections: list = []
        self.setup_form = FormState()
        self.form.custom["pipeline_results"] = self._draw_results
        for plot_key in (
            "live_decay",
            "live_correlation",
            "live_count_rate",
            "live_mcs",
            "live_macrotime",
        ):
            self.form.custom[plot_key] = lambda *a: self.model.live.draw_plot(*a)
        self.dialog: FileDialog | None = None
        self.dialog_action = ""
        self.setup_open, self.setup_kind = False, ""
        self.setup_model: BHSetupModel | PicoQuantSetupModel | BrickMicSetupModel | None = None
        #: The simulation setup dialog while one is open (its own windows; not a device card).
        self.sim_setup: SimulationSetupDialog | None = None
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
            dialog = FileDialog("Choose acquisition output folder", mode="folder")
        elif action.startswith("sim_setup_"):
            saving = action == "sim_setup_save"
            dialog = FileDialog(
                "Save simulation JSON" if saving else "Load simulation JSON",
                mode="save" if saving else "open",
                filters="JSON (*.json)",
                filename="simulation_config.json",
            )
        elif action.startswith("bh_"):
            dialog = FileDialog(
                "Save BH settings" if action == "bh_save" else "Load BH settings",
                mode="save" if action == "bh_save" else "open",
                filters="JSON (*.json)",
                filename="bh_spc_settings.json",
            )
        else:
            dialog = FileDialog(
                action.replace("_", " ").title(),
                mode="save" if action == "save_settings" else "open",
                filters="JSON (*.json)",
                filename="acquisition_settings.json",
            )
        self.dialog = dialog
        self.file_window.title = dialog.title
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
            elif self.dialog_action.startswith("sim_setup_"):
                if self.sim_setup is not None:
                    self.sim_setup.file_chosen(self.dialog_action[len("sim_setup_") :], path)
            elif self.dialog_action in ("bh_save", "bh_load"):
                # only the BH card offers these; a card closed meanwhile ignores the file
                if isinstance(self.setup_model, BHSetupModel):
                    if self.dialog_action == "bh_save":
                        self.setup_model.save_json(path)
                    else:
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
            picoquant = PicoQuantSetupModel(self.model.device, self.model.photon_limit)
            picoquant.detect_status()
            self.setup_model = picoquant
        elif self.setup_kind == "BRICKMIC":
            self.setup_model = BrickMicSetupModel(self.model.device)
        else:
            self._open_simulation_setup()
            return
        self.setup_open = True
        self.setup_window.title = f"{DEVICE_LABELS[self.setup_kind]} Device Setup"
        self.setup_window.show()

    def _open_simulation_setup(self) -> None:
        """Open the simulation setup dialog on the parameters the next run would use."""
        self.setup_kind = "SIMULATION"
        self.sim_setup = SimulationSetupDialog(
            self.model._editor_params(),
            on_apply=self.model.apply_simulation_setup,
            request_file=lambda kind: setattr(self.model, "_file_request", f"sim_setup_{kind}"),
        )
        self.sim_setup.show()

    def _close_device_setup(self) -> None:
        """Close a setup card without applying its editable state."""
        self.setup_open = False
        self.setup_window.hide()

    def _setup_form(self) -> Any:
        """The binding of the open card's ``view.json`` (:mod:`.setup_forms`), made once per opened card."""
        setup = self.setup_model
        if self._card_form is None or self._card_form.setup is not setup:
            if isinstance(setup, BHSetupModel):

                def applied(ok: bool) -> None:
                    if ok:
                        self.model.bh_simulation_mode = setup.simulation_mode

                self._card_form = BHSetupForm(
                    setup,
                    self._close_device_setup,
                    request_file=lambda kind: setattr(self.model, "_file_request", kind),
                    on_applied=applied,
                )
            elif isinstance(setup, PicoQuantSetupModel):
                self._card_form = PicoQuantSetupForm(setup, self._close_device_setup, self.model)
            else:
                self._card_form = BrickMicSetupForm(setup, self._close_device_setup)
            spec = SETUP_SPECS[type(setup)]
            self._card_sections = json.loads((HERE / spec).read_text(encoding="utf-8"))["sections"]
            self.setup_form = FormState()
        return self._card_form

    def _draw_device_setup(self, box: tuple) -> None:
        """Draw the selected setup card (its ``view.json``) as a bounded topmost native modal.

        The card's controls are remembered for the Driver and the tour as ``setup_<name>`` (``setup_apply``,
        ``setup_CFD_LIMIT_LOW``, ``setup_detect_cards``, ...).
        """
        if not self.setup_open:
            return
        close = self.setup_window.begin(box)
        form = self._setup_form()
        draw_sections(self._card_sections, form, self.setup_form)
        self.item_rects.update({f"setup_{k}": v for k, v in self.setup_form.rects.items()})
        if close == "close":
            self._close_device_setup()
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
        if self.model._simulation_setup_requested:
            self.model._simulation_setup_requested = False
            self._open_simulation_setup()
        if self.sim_setup is not None:
            self.sim_setup.draw(box)
            self.item_rects.update(self.sim_setup.rects)
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
