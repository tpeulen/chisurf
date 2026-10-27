"""Where acquisition output goes, and what Setup -> Settings -> Acquisition stored.

Qt-free helpers shared by the Record tool and the settings panel: the ``gui.acquisition``
section of the user's settings and the standard output folder derived from it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def stored_acquisition_settings() -> dict[str, Any]:
    """Return the ``gui.acquisition`` settings section.

    Returns
    -------
    dict
        What Setup -> Settings -> Acquisition wrote; ``{}`` when there is none or the
        settings cannot be read.
    """
    try:
        from chisurf.core.settings import gui as gui_settings

        stored = gui_settings.get("acquisition") or {}
    except Exception:  # noqa: BLE001 - a missing or unreadable settings file means "nothing configured"
        return {}
    return stored if isinstance(stored, dict) else {}


def _configured() -> str:
    """Return the raw configured output folder text (``""`` when unset)."""
    from chisurf import settings

    return str(
        (getattr(settings, "gui", {}).get("acquisition", {}) or {}).get("output_path", "") or ""
    ).strip()


def default_acquisition_output_path() -> str:
    """Return the configured standard output folder, or the working-path fallback.

    Returns
    -------
    str
        The Settings panel's *standard output folder* (``gui["acquisition"]["output_path"]``)
        when set; otherwise ``<working path>/acquisition`` and finally
        ``~/chisurf/acquisition``.
    """
    from chisurf import settings

    configured = _configured()
    if configured:
        return str(Path(configured).expanduser())
    working_path = getattr(settings, "working_path", "") or ""
    if working_path:
        return str(Path(working_path).expanduser() / "acquisition")
    return str(Path.home() / "chisurf" / "acquisition")


def configured_output_path() -> str:
    """Return the standard output folder only when the user configured one.

    Returns
    -------
    str
        The expanded configured folder, or ``""`` when none is configured.
    """
    configured = _configured()
    return str(Path(configured).expanduser()) if configured else ""
