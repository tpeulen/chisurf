"""Qt-free setup contracts for native acquisition device configuration.

These models deliberately speak the existing wrapper APIs.  They are usable
with deterministic fakes; the acquisition app draws them as its Device Setup cards.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import build_engine

# Numeric values are the retained ``ParID`` values from the BH direct wrapper.
# Keeping this tiny immutable table here avoids importing its QObject-based
# wrapper merely to render a Qt-free factory.
BH_PARAMETER_IDS = {
    "CFD_LIMIT_LOW": 0,
    "CFD_LIMIT_HIGH": 1,
    "CFD_ZC_LEVEL": 2,
    "CFD_HOLDOFF": 3,
    "SYNC_ZC_LEVEL": 4,
    "SYNC_FREQ_DIV": 5,
    "SYNC_HOLDOFF": 6,
    "SYNC_THRESHOLD": 7,
    "TAC_RANGE": 8,
    "TAC_GAIN": 9,
    "TAC_OFFSET": 10,
    "TAC_LIMIT_LOW": 11,
    "TAC_LIMIT_HIGH": 12,
    "ADC_RESOLUTION": 13,
    "COLLECT_TIME": 15,
    "DISPLAY_TIME": 16,
    "REPEAT_TIME": 17,
    "STOP_ON_TIME": 18,
    "STOP_ON_OVFL": 19,
    "ROUTING_MODE": 25,
    "TAC_ENABLE_HOLD": 26,
    "MODE": 27,
    "RATE_COUNT_TIME": 40,
    "MACRO_TIME_CLK": 41,
}


@dataclass(frozen=True)
class BHParameterSpec:
    """One retained BH dialog parameter and its native editor metadata."""

    name: str
    label: str
    group: str
    minimum: float
    maximum: float
    integer: bool = False
    options: dict[int, str] | None = None


BH_PARAMETERS = (
    BHParameterSpec("CFD_LIMIT_LOW", "CFD Limit Low (mV)", "CFD", -1000, 1000),
    BHParameterSpec("CFD_LIMIT_HIGH", "CFD Limit High (mV)", "CFD", -1000, 1000),
    BHParameterSpec("CFD_ZC_LEVEL", "CFD Zero Cross Level (mV)", "CFD", -100, 100),
    BHParameterSpec("CFD_HOLDOFF", "CFD Holdoff (ns)", "CFD", 0, 100),
    BHParameterSpec("SYNC_ZC_LEVEL", "Sync Zero Cross Level (mV)", "Sync", -100, 100),
    BHParameterSpec("SYNC_FREQ_DIV", "Sync Frequency Divider", "Sync", 1, 16, True),
    BHParameterSpec("SYNC_HOLDOFF", "Sync Holdoff (ns)", "Sync", 0, 100),
    BHParameterSpec("SYNC_THRESHOLD", "Sync Threshold (mV)", "Sync", -1000, 1000),
    BHParameterSpec("TAC_RANGE", "TAC Range (ns)", "TAC", 0, 1000),
    BHParameterSpec("TAC_GAIN", "TAC Gain", "TAC", 1, 8, True, {1: "1", 2: "2", 4: "4", 8: "8"}),
    BHParameterSpec("TAC_OFFSET", "TAC Offset (%)", "TAC", 0, 100),
    BHParameterSpec("TAC_LIMIT_LOW", "TAC Limit Low (%)", "TAC", 0, 100),
    BHParameterSpec("TAC_LIMIT_HIGH", "TAC Limit High (%)", "TAC", 0, 100),
    BHParameterSpec("TAC_ENABLE_HOLD", "TAC Enable Hold (ns)", "TAC", 0, 100),
    BHParameterSpec("COLLECT_TIME", "Collection Time (s)", "Timing", 0.001, 1000),
    BHParameterSpec("DISPLAY_TIME", "Display Time (s)", "Timing", 0.001, 1000),
    BHParameterSpec("REPEAT_TIME", "Repeat Time (s)", "Timing", 0.001, 1000),
    BHParameterSpec("STOP_ON_TIME", "Stop on Time", "Timing", 0, 1, True, {0: "No", 1: "Yes"}),
    BHParameterSpec("STOP_ON_OVFL", "Stop on Overflow", "Timing", 0, 1, True, {0: "No", 1: "Yes"}),
    BHParameterSpec("RATE_COUNT_TIME", "Rate Count Time (s)", "Timing", 0.001, 10),
    BHParameterSpec(
        "MACRO_TIME_CLK",
        "Macro Time Clock",
        "Timing",
        0,
        7,
        True,
        {
            0: "25 ns",
            1: "50 ns",
            2: "100 ns",
            3: "200 ns",
            4: "400 ns",
            5: "800 ns",
            6: "1.6 µs",
            7: "3.2 µs",
        },
    ),
    BHParameterSpec(
        "MODE", "Mode", "Mode", 0, 3, True, {0: "Histogramming", 1: "FIFO", 2: "Scan", 3: "Imaging"}
    ),
    BHParameterSpec(
        "ROUTING_MODE", "Routing Mode", "Mode", 0, 2, True, {0: "Off", 1: "4 Bits", 2: "16 Bits"}
    ),
    BHParameterSpec(
        "ADC_RESOLUTION",
        "ADC Resolution",
        "Mode",
        6,
        16,
        True,
        {6: "6 Bits", 8: "8 Bits", 10: "10 Bits", 12: "12 Bits", 14: "14 Bits", 16: "16 Bits"},
    ),
)


class BHSetupModel:
    """Qt-free model retaining the BH direct-wrapper parameter contract."""

    def __init__(self, device: Any, simulation_mode: bool = False) -> None:
        self.device = getattr(device, "device", device)
        self.simulation_mode = bool(simulation_mode)
        self.cards: list[dict[str, Any]] = []
        self.active_cards: list[int] = []
        self.values: dict[str, float | int] = {spec.name: 0 for spec in BH_PARAMETERS}
        self.module_number = 0
        self.status = "Read values before applying changes."

    def detect_cards(self) -> bool:
        """Detect cards through the legacy adapter without inferring a connection."""
        try:
            self.cards = list(self.device.detect_cards(simulation=self.simulation_mode))
            self.active_cards = [int(c["module_number"]) for c in self.cards if c.get("active")]
            if self.active_cards:
                self.module_number = self.active_cards[0]
            self.status = f"Detected {len(self.cards)} module(s) via the supplied BH adapter."
            return True
        except Exception as exc:
            self.cards = []
            self.status = f"Card detection failed: {exc}"
            return False

    def read_parameters(self) -> bool:
        """Read all retained dialog parameters using ``get_parameter``."""
        try:
            for spec in BH_PARAMETERS:
                value = self.device.get_parameter(self.module_number, BH_PARAMETER_IDS[spec.name])
                self.values[spec.name] = int(value) if spec.integer else float(value)
        except Exception as exc:
            self.status = f"Read values failed: {exc}"
            return False
        self.status = f"Read {len(BH_PARAMETERS)} parameters from module {self.module_number}."
        return True

    def apply(self) -> bool:
        """Write selected cards and every retained parameter through the direct contract."""
        try:
            self.device.set_active_cards(list(self.active_cards))
            for spec in BH_PARAMETERS:
                value = self.values[spec.name]
                if not spec.minimum <= float(value) <= spec.maximum:
                    raise ValueError(f"{spec.label} is outside its retained bounds")
                if spec.options and int(value) not in spec.options:
                    raise ValueError(f"{spec.label} is not a supported option")
                self.device.set_parameter(self.module_number, BH_PARAMETER_IDS[spec.name], value)
        except Exception as exc:
            self.status = f"Apply failed: {exc}"
            return False
        self.status = f"Applied {len(BH_PARAMETERS)} parameters to module {self.module_number}."
        return True

    def save_json(self, path: str | Path) -> bool:
        """Save editable BH values only; saving never writes a device."""
        try:
            Path(path).with_suffix(".json").write_text(
                json.dumps(self.values, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            self.status = f"Save failed: {exc}"
            return False
        self.status = f"Saved BH settings to {Path(path).with_suffix('.json')}"
        return True

    def load_json(self, path: str | Path) -> bool:
        """Load editable values without applying them to a device."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            for spec in BH_PARAMETERS:
                if spec.name in data:
                    self.values[spec.name] = (
                        int(data[spec.name]) if spec.integer else float(data[spec.name])
                    )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.status = f"Load failed: {exc}"
            return False
        self.status = "Loaded BH settings; Apply writes them to the selected module."
        return True


class PicoQuantSetupModel:
    """PicoQuant's intentionally small retained configuration contract."""

    def __init__(self, device: Any, photon_limit: int) -> None:
        self.device = device
        requested = int(photon_limit or 0)
        self.max_photons = requested if 1000 <= requested <= 10_000_000 else 100_000
        self.measurement_mode = "T3 Mode (Time-resolved)"
        self.reference_source = "Internal"
        self.status = "No physical PicoQuant status was queried."

    def detect_status(self) -> None:
        """Query a supplied API when available, without fabricating a connection result."""
        api = getattr(self.device, "api", None) if self.device is not None else None
        if api is None:
            self.status = (
                "No initialized PicoQuant API was supplied; no physical device status was checked."
            )
            return
        try:
            devices = list(api.detect_devices())
        except Exception as exc:
            self.status = f"PicoQuant status query failed: {exc}"
            return
        if not devices:
            self.status = "No PicoQuant devices detected."
            return
        lines = [f"PicoQuant API reports {len(devices)} device(s):"]
        for dev in devices:
            info = dev if isinstance(dev, dict) else {}
            lines.append(
                f"Device: {info.get('device_id', 'Unknown')}  Status: {info.get('status', 'Unknown')}"
            )
        self.status = "\n".join(lines)

    def apply(self, acquisition: Any) -> bool:
        """Map the retained maximum-photons setting to the native global stop limit."""
        if not 1000 <= int(self.max_photons) <= 10_000_000:
            self.status = "Maximum photons must be between 1,000 and 10,000,000."
            return False
        acquisition.photon_limit = int(self.max_photons)
        self.status = "Applied maximum photons to the native global photon stop condition."
        return True


class BrickMicSetupModel:
    """BrickMic configuration contract of the Device Setup card.

    Reads/writes six backend attributes: ``channels``, ``start_ctr``, ``end_ctr``,
    ``acquisition_rate``, ``buffer_size`` and ``N_ph_per_file``.  Channel count is kept consistent
    with the counter window (``end - start + 1``).
    """

    FIELDS = (
        # key, label, minimum, maximum, step
        ("start_ctr", "Start counter index", 0, 31, 1),
        ("end_ctr", "End counter index", 0, 31, 1),
        ("acquisition_rate", "Acquisition rate (Hz)", 1_000, 5_000_000, 100_000),
        ("buffer_size", "Buffer size / channel", 10_000, 20_000_000, 100_000),
        ("N_ph_per_file", "Photons per .spc file", 1_000, 1_000_000_000, 10_000),
    )

    def __init__(self, device: Any) -> None:
        self.device = getattr(device, "device", device)
        defaults = {
            "channels": 2,
            "start_ctr": 0,
            "end_ctr": 1,
            "acquisition_rate": 1_000_000.0,
            "buffer_size": 2_000_000,
            "N_ph_per_file": 100_000,
        }
        self.values: dict[str, int | float] = {}
        for key, default in defaults.items():
            try:
                self.values[key] = type(default)(getattr(self.device, key))
            except Exception:
                self.values[key] = default
        self.status = "Edit values, then Apply to write them to the BrickMic backend."

    def apply(self) -> bool:
        """Write every value, keeping channels consistent with the counter window."""
        brick = self.device
        if brick is None:
            self.status = "No BrickMic backend was supplied; nothing was written."
            return False
        try:
            start = int(self.values["start_ctr"])
            end = max(int(self.values["end_ctr"]), start)
            self.values["start_ctr"], self.values["end_ctr"] = start, end
            self.values["channels"] = max(1, end - start + 1)
            for key, value in self.values.items():
                if hasattr(brick, key):
                    setattr(brick, key, value)
        except Exception as exc:
            self.status = f"BrickMic apply failed: {exc}"
            return False
        self.status = (
            f"Applied BrickMic settings: channels={self.values['channels']}, "
            f"rate={self.values['acquisition_rate']:.0f} Hz."
        )
        return True


class SimulationSetupModel:
    """Full simulator dictionary editor validated by the production engine."""

    def __init__(self, parameters: dict[str, Any]) -> None:
        self.before = json.dumps(parameters, indent=2, sort_keys=True)
        self.text = self.before
        self.status = (
            "Full current simulator parameter dictionary; Apply validates the production engine."
        )

    def apply(self) -> dict[str, Any] | None:
        """Parse and validate complete current settings with ``build_engine``."""
        try:
            params = json.loads(self.text)
            if not isinstance(params, dict):
                raise ValueError("simulation settings must be a JSON object")
            build_engine(params)
        except Exception as exc:
            self.status = f"Simulation settings rejected: {exc}"
            return None
        self.text = json.dumps(params, indent=2, sort_keys=True)
        self.status = "Simulation settings validated by the production simulator engine."
        return params
