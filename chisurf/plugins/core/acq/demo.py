"""A reproducible simulated photon stream for the acquisition plugin.

Two species diffuse through a confocal focus and are read out in two detection
channels: a low-FRET species (donor-dominated) and a high-FRET species with a
shortened donor lifetime, 20 s of measurement. The stream is written once as a
Becker & Hickl SPC-130 file (raw 32-bit words, no header) under the settings
directory; the JSON sidecar next to it holds the :data:`DEMO` settings as the
cache key, so a changed setting regenerates the file and an unchanged one reuses
it. :func:`words` reads it back for the streaming pipeline.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import numpy as np

#: The demo's ground truth, in one place so the help text and the tests agree.
DEMO = {
    "duration_s": 20.0,
    "dt_ms": 0.01,
    "n_channels": 2,
    "n_species": 2,
    "n_molecules": [6.0, 4.0],
    "diffusion": [0.4, 0.3],
    "brightness_khz": [[60.0, 20.0], [15.0, 55.0]],
    "lifetimes_ns": [3.4, 1.1],
    "background_khz": 0.0,
    "tac_channels": 4096,
    "tac_dt_ns": 0.004069,
    "seed": 11,
}

FILENAME = "demo.spc"


def demo_folder() -> pathlib.Path:
    """Return the plugin-owned demonstration cache in the settings directory."""
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "demos" / "acq"


def simulation_params(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map the demo settings onto the acquisition simulator's parameter dictionary.

    Parameters
    ----------
    cfg : dict, optional
        Settings; defaults to :data:`DEMO`.

    Returns
    -------
    dict
        Parameters accepted by
        :func:`~chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms.build_engine`.
    """
    cfg = {**DEMO, **(cfg or {})}
    q = [float(v) for row in cfg["brightness_khz"] for v in row]
    return {
        "N_species": int(cfg["n_species"]),
        "N_channels": int(cfg["n_channels"]),
        "M": [float(v) for v in cfg["n_molecules"]],
        "D": [float(v) for v in cfg["diffusion"]],
        "q": q,
        "q_bg": [float(cfg["background_khz"])] * int(cfg["n_channels"]),
        "k_rad": [0.0] * int(cfg["n_species"]) ** 2,
        "k_nrad": [0.0] * int(cfg["n_species"]) ** 2,
        "box_xy": 2.0,
        "box_z": 4.0,
        "focus_param": [0.3, 2.0],
        "dt": float(cfg["dt_ms"]),
        "psf_type": "analytic_gaussian3d",
        "analytic_excitation": True,
        "N_ph_max": 10**9,
        "max_windows": int(round(float(cfg["duration_s"]) * 1000.0 / float(cfg["dt_ms"]))),
        "rmt1seed": int(cfg["seed"]),
        "rmt2seed": int(cfg["seed"]) + 1,
        "N_tac_channels": int(cfg["tac_channels"]),
        "tac_dt": float(cfg["tac_dt_ns"]),
        "active_margin": 1.5,
        "per_molecule_skip": True,
        "decay_lifetimes": [[[1.0, float(t)]] for t in cfg["lifetimes_ns"]],
    }


def _fingerprint(cfg: dict[str, Any]) -> str:
    """Return a stable string identifying the settings a demo was made with."""
    return json.dumps(cfg, sort_keys=True)


def _sidecar(target: pathlib.Path) -> pathlib.Path:
    """Return the JSON sidecar belonging to *target*."""
    return target.with_suffix(".json")


def _cache_is_good(target: pathlib.Path, cfg: dict[str, Any]) -> bool:
    """Whether *target* exists, is complete and was made with *cfg*."""
    side = _sidecar(target)
    if not (target.is_file() and side.is_file()):
        return False
    try:
        stored = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (
        stored.get("fingerprint") == _fingerprint(cfg)
        and stored.get("n_bytes") == target.stat().st_size
    )


def make_demo(folder: str | pathlib.Path | None = None, *, overwrite: bool = False) -> pathlib.Path:
    """Simulate the demo stream and write it as an SPC-130 file.

    Parameters
    ----------
    folder : str or pathlib.Path, optional
        Cache directory; defaults to :func:`demo_folder`.
    overwrite : bool
        Regenerate even when a matching file is already there.

    Returns
    -------
    pathlib.Path
        The SPC file; its sidecar ``demo.json`` records :data:`DEMO` and the
        photon count.

    Raises
    ------
    RuntimeError
        If tttrlib was built without the photon simulator.
    """
    from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
        generate_spc132_uint32,
        tttrlib_available,
    )

    target = (pathlib.Path(folder) if folder is not None else demo_folder()) / FILENAME
    cfg = json.loads(json.dumps(DEMO))
    if not overwrite and _cache_is_good(target, cfg):
        return target
    if not tttrlib_available():
        raise RuntimeError("this tttrlib build has no photon simulator, so the demo cannot be made")
    target.parent.mkdir(parents=True, exist_ok=True)
    words = generate_spc132_uint32(simulation_params(cfg))
    staging = target.with_name(target.name + ".part")
    np.asarray(words, dtype="<u4").tofile(staging)
    staging.replace(target)
    # The sidecar is written last, so an interrupted run leaves a file with no
    # sidecar, which is treated as absent rather than reused.
    _sidecar(target).write_text(
        json.dumps(
            {
                "fingerprint": _fingerprint(cfg),
                "settings": cfg,
                "n_words": int(len(words)),
                "n_bytes": int(target.stat().st_size),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def words(path: str | pathlib.Path) -> np.ndarray:
    """Read the demo's raw SPC-130 words back as ``uint32``.

    Parameters
    ----------
    path : str or pathlib.Path
        File written by :func:`make_demo`.
    """
    return np.fromfile(path, dtype="<u4")
