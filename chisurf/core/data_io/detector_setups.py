from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

from chisurf.core.settings.path_utils import get_path

logger = logging.getLogger(__name__)

DETECTOR_SETUPS_FILE = get_path('settings') / 'detector_setups.json'


def load_detector_setups(
    file_path: str | pathlib.Path | None = None,
) -> dict[str, Any]:
    """Load detector setups from the canonical JSON file.

    Returns ``{"setups": {...}, "last_used": str}``.

    This is the Qt-free variant used by the headless server.  It does not
    attempt MMFDB migration and does not show a warning dialog when the file
    is missing — it simply returns an empty dict.
    """
    path = pathlib.Path(file_path) if file_path is not None else DETECTOR_SETUPS_FILE
    if not path.exists():
        logger.debug("Detector setups file not found: %s", path)
        return {"setups": {}}
    try:
        with open(path) as f:
            data: dict[str, Any] = json.load(f)
        setups = data.get("setups") or {}
        last_used = data.get("last_used") or ""
        return {"setups": setups, "last_used": last_used}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load detector setups from %s: %s", path, exc)
        return {"setups": {}}


def save_detector_setups(
    setups_data: dict[str, Any],
    file_path: str | pathlib.Path | None = None,
    is_public: bool | None = None,
) -> None:
    """Save detector setups to the canonical JSON file.

    Parameters
    ----------
    setups_data : dict
        Must contain a ``"setups"`` key mapping name -> settings dict.
    file_path : str or Path, optional
        Override the default file path.
    is_public : bool, optional
        Ignored in the headless JSON-only variant (only relevant for MMFDB).
    """
    path = pathlib.Path(file_path) if file_path is not None else DETECTOR_SETUPS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "setups": setups_data.get("setups") or {},
    }
    last_used = setups_data.get("last_used")
    if last_used:
        payload["last_used"] = last_used
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def setup_lut_open_kwargs(setup: dict[str, Any] | None) -> dict[str, Any]:
    """Return the ``open_tttr`` LUT/shift keyword arguments for a setup dict.

    The single adapter every setup-consuming reader uses to become LUT-aware:
    a plugin that has resolved its selected setup calls
    ``open_tttr(path, routine, **setup_lut_open_kwargs(setup))`` (or forwards the
    result to a reader). Returns ``{"channel_luts": {}, "channel_shifts": {},
    "apply_lut": False}`` for a missing/empty setup, so the open falls back to
    raw reading.

    Parameters
    ----------
    setup : dict or None
        A detector-setup dict (as stored under ``setups[name]``) carrying the
        inline ``channel_luts`` / ``channel_shifts`` / ``apply_lut`` keys.

    Returns
    -------
    dict
        ``{"channel_luts": {int: list}, "channel_shifts": {int: int},
        "apply_lut": bool}``.
    """
    if not isinstance(setup, dict):
        return {"channel_luts": {}, "channel_shifts": {}, "apply_lut": False}
    luts_raw = setup.get("channel_luts") or {}
    shifts_raw = setup.get("channel_shifts") or {}
    channel_luts: dict[int, Any] = {}
    for k, v in luts_raw.items():
        try:
            channel_luts[int(k)] = v
        except (TypeError, ValueError):
            continue
    channel_shifts: dict[int, int] = {}
    for k, v in shifts_raw.items():
        try:
            channel_shifts[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return {
        "channel_luts": channel_luts,
        "channel_shifts": channel_shifts,
        "apply_lut": bool(setup.get("apply_lut", False)),
    }
