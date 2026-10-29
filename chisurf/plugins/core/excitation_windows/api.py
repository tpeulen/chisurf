"""The plugin's JSON-in, JSON-out functions (RPC, CLI, scripts) over the Qt-free core.

>>> from chisurf.plugins.core.excitation_windows import api
>>> api.detect("measurement.ptu")["kind"]          # doctest: +SKIP
'pie'
>>> api.check("measurement.ptu", setup="mt200.setup.json")["status"]   # doctest: +SKIP
'warning'
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from chisurf.core.fluorescence.excitation import check_setup, detect_windows

__all__ = ["apply_to_setup", "check", "detect", "load_setup"]


def load_setup(setup: Mapping | str | Path | None) -> dict:
    """A setup given as a mapping, a JSON file, or a workspace ``setup`` address."""
    if setup is None or isinstance(setup, Mapping):
        return dict(setup or {})
    text = str(setup)
    if Path(text).is_file():
        data = json.loads(Path(text).read_text(encoding="utf-8"))
    else:
        from chisurf.plugins.tttr.workspace_io import read_setup

        return read_setup(text)
    named = data.get("setups") if isinstance(data, dict) else None
    if isinstance(data, dict) and "detectors" not in data and isinstance(named, dict) and named:
        data = next(iter(named.values()))
    return dict(data.get("data", data)) if isinstance(data, dict) else {}


def _path(measurement: Any) -> Any:
    if isinstance(measurement, (str, Path)):
        from chisurf.core.plugin.workspace_input import read_address

        return str(read_address(str(measurement)))
    return measurement


def detect(measurement: Any, setup: Mapping | str | None = None, kind: str = "auto") -> dict:
    """Detect the excitation scheme of *measurement* (path, workspace address or TTTR) and
    propose windows; the result as a dict (``kind``, ``windows``, ``windows_ns``, ``pulses``,
    ``message``, ...)."""
    return detect_windows(_path(measurement), setup=load_setup(setup), kind=kind).to_dict()


def check(measurement: Any, setup: Mapping | str | None) -> dict:
    """Check *setup*'s windows against *measurement*: ``status``, ``summary``, ``issues``,
    ``proposal`` (the windows to take, in the data's channels) and the detection."""
    return check_setup(load_setup(setup), _path(measurement)).to_dict()


def apply_to_setup(setup: Mapping, result: Mapping) -> dict:
    """*setup* with the windows of a :func:`detect` / :func:`check` result: the windows, the
    detector gates a check proposes, and the channel width they are in
    (``tttr_reading.micro_time_resolution``, ps). A ``single`` or
    ``unclear`` result changes nothing."""
    det = result.get("detection", result)
    windows = result.get("proposal") if "proposal" in result else det.get("windows")
    out = dict(setup)
    if not windows or det.get("kind") not in ("pie", "alex"):
        return out
    if det.get("domain") == "macro":
        out["alex_windows"] = {k: list(v) for k, v in windows.items()}
        out["alex_period_s"] = float(det["n_channels"]) * float(det["resolution_s"])
        return out
    out["windows"] = {k: list(v) for k, v in windows.items()}
    gates = result.get("proposal_gates") or {}
    if gates:
        detectors = {k: dict(v) for k, v in (out.get("detectors") or {}).items()}
        for name, ranges in gates.items():
            if name in detectors:
                detectors[name]["micro_time_ranges"] = [list(r) for r in ranges]
        out["detectors"] = detectors
    reading = dict(out.get("tttr_reading") or {})
    reading["micro_time_resolution"] = float(det["resolution_s"]) * 1e12
    out["tttr_reading"] = reading
    return out
