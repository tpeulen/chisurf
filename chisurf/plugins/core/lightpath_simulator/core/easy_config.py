"""Easy-mode files of the Light Path Simulator: templates, presets, the last configuration, the FRET defaults.

The Easy Mode form (:class:`chisurf.emtk.optical_configuration.OpticalConfigurationWidget`) edits an
*easy-mode configuration* -- lasers, excitation dichroic, emission splitters, detectors, dyes, κ² and n --
that :func:`chisurf.core.optical_configuration.build_easy_graph` turns into a light-path graph. This module
holds what is read and written around that form:

- the packaged templates (one JSON file per instrument under ``templates/``);
- presets (a configuration or a graph saved as JSON);
- the last configuration simulated (``lightpath_easy_last.json`` in the settings folder), which the PDA
  models read as their default light path;
- κ² and the refractive index, persisted to the user's ``fret`` settings so the next form starts from them.

Paths are resolved under the settings folder (``CHISURF_SETTINGS_DIR`` redirects it, which keeps tests off
``~/.chisurf``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from chisurf.core.settings.path_utils import get_path

logger = logging.getLogger(__name__)


def last_config_path() -> Path:
    """Where the last simulated configuration is kept (read by ``chisurf.core.models.pda2c`` as its light path).

    Resolved at call time, so ``CHISURF_SETTINGS_DIR`` set after import (a test's temporary settings) is honoured.

    Returns
    -------
    pathlib.Path
    """
    return get_path("settings") / "settings" / "lightpath_easy_last.json"


#: Packaged instrument templates, one JSON file each (``{"name": ..., "config": {...}}``).
TEMPLATE_LIBRARY_DIR = Path(__file__).resolve().parents[1] / "templates"

#: κ² and n of a form that has no user setting yet.
FRET_DEFAULTS = {"kappa2": 0.6667, "n": 1.33}


def load_template_library(directory: str | Path = TEMPLATE_LIBRARY_DIR) -> list[dict]:
    """Load the packaged optical-path templates.

    Parameters
    ----------
    directory : str or pathlib.Path
        Folder with one JSON file per template.

    Returns
    -------
    list of dict
        Each template with its ``config`` object, ``id`` and ``name`` (both default to the file stem) and
        ``_path``. Files that are not JSON objects with a ``config`` object are skipped.
    """
    template_dir = Path(directory)
    if not template_dir.exists():
        return []
    valid = []
    for path in sorted(template_dir.glob("*.json")):
        try:
            template = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load lightpath template %s: %s", path, exc)
            continue
        if not isinstance(template, dict) or not isinstance(template.get("config"), dict):
            continue
        template.setdefault("id", path.stem)
        template.setdefault("name", path.stem)
        template["_path"] = str(path)
        valid.append(template)
    return valid


def save_easy_preset(config: dict, path: str | Path) -> None:
    """Write an easy-mode configuration (or a graph) to *path* as JSON.

    Parameters
    ----------
    config : dict
        The configuration.
    path : str or pathlib.Path
        Destination file.
    """
    Path(path).write_text(json.dumps(config, indent=2))


def load_easy_preset(path: str | Path) -> dict:
    """Read a preset written by :func:`save_easy_preset`.

    Parameters
    ----------
    path : str or pathlib.Path
        The JSON file.

    Returns
    -------
    dict
    """
    return json.loads(Path(path).read_text())


def save_last_config(config: dict) -> None:
    """Remember *config* as the last simulated configuration; a failure is logged, never raised.

    Parameters
    ----------
    config : dict
        The easy-mode configuration (keys starting with ``_`` other than ``_graph`` are dropped).
    """
    try:
        clean = {k: v for k, v in config.items() if not str(k).startswith("_") or k == "_graph"}
        path = last_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(clean, indent=2, default=str))
    except Exception as exc:  # noqa: BLE001 - a settings write must not break a simulation
        logger.warning("Failed to save last easy config: %s", exc)


def load_last_config() -> dict | None:
    """The configuration saved by :func:`save_last_config`, or ``None``.

    Returns
    -------
    dict or None
    """
    try:
        path = last_config_path()
        if path.exists():
            value = json.loads(path.read_text())
            return value if isinstance(value, dict) else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load last easy config: %s", exc)
    return None


def fret_setting(key: str) -> float:
    """κ² (``"kappa2"``) or the refractive index (``"n"``) from the user's ``fret`` settings.

    Parameters
    ----------
    key : str
        ``"kappa2"`` or ``"n"``.

    Returns
    -------
    float
    """
    from chisurf.core.settings import cs_settings

    try:
        return float(cs_settings.get("fret", {}).get(key, FRET_DEFAULTS[key]))
    except (TypeError, ValueError):
        return FRET_DEFAULTS[key]


def persist_fret_setting(key: str, value: float) -> None:
    """Store one ``fret`` setting in memory and in the user's ``settings_chisurf.yaml``.

    Parameters
    ----------
    key : str
        ``"kappa2"`` or ``"n"``.
    value : float
        The new value.
    """
    from chisurf.core.settings import cs_settings

    cs_settings.setdefault("fret", {})[key] = value
    try:
        import yaml

        settings_file = get_path("settings") / "settings_chisurf.yaml"
        try:
            data = yaml.safe_load(settings_file.read_text()) or {}
        except Exception:  # noqa: BLE001 - a missing or unreadable file starts empty
            data = {}
        data.setdefault("fret", {})[key] = float(value)
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(yaml.safe_dump(data, default_flow_style=False))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist fret setting %s: %s", key, exc)


__all__ = [
    "FRET_DEFAULTS",
    "TEMPLATE_LIBRARY_DIR",
    "fret_setting",
    "last_config_path",
    "load_easy_preset",
    "load_last_config",
    "load_template_library",
    "persist_fret_setting",
    "save_easy_preset",
    "save_last_config",
]
