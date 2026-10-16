"""Polarised reference decays with a known G, so the G-factor calculator can be learnt without user files.

``make_demo(folder)`` writes four stacked VV/VH files (:func:`chisurf.core.fio.write_vv_vh`, ``dt`` in the
header): ``gfactor_fast.dat`` (a dye that depolarises within the pulse, rho 0.2 ns), ``gfactor_slow.dat``
(a slow protein, rho 16 ns) and two batch decays (rho 8 ns and 30 ns). Every decay has one lifetime of
4 ns convolved with a Gaussian pulse at 5 ns, r0 0.38, no polarisation mixing (l1 = l2 = 0), a constant
background of 3 counts per bin in each channel, the VH channel detected with ``1 / G`` the efficiency of
VV, and Poisson noise. The answer is therefore known: tail matching on the fast reference must return
``G`` (1.2) and the slow reference a mixing estimate near zero. Nothing here is a measurement.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

STEM = "gfactor_demo"
FILES = {
    "fast": "gfactor_fast.dat",
    "slow": "gfactor_slow.dat",
    "batch1": "gfactor_batch1.dat",
    "batch2": "gfactor_batch2.dat",
}
#: The simulation, in one place so the help text, the guide and the tests agree.
DEMO: dict[str, Any] = {
    "version": 2,
    "seed": 5,
    "n_bins": 512,
    "dt_ns": 0.05,
    "g_factor": 1.2,
    "l1": 0.020,
    "l2": 0.045,
    "tau_ns": 4.0,
    "r0": 0.38,
    "irf_mean_ns": 5.0,
    "irf_sigma_ns": 0.1,
    "background_counts": 3.0,
    #: (key, rho in ns, scale)
    "decays": [
        ["fast", 0.2, 2000.0],
        ["slow", 16.0, 2000.0],
        ["batch1", 8.0, 1500.0],
        ["batch2", 30.0, 1500.0],
    ],
}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "demos" / "vv_vh_g_factor"


def simulate() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Return ``{key: (vv, vh)}`` for the fast, slow and two batch decays."""
    c = DEMO
    n, dt = int(c["n_bins"]), float(c["dt_ns"])
    rng = np.random.default_rng(c["seed"])
    t = np.arange(n) * dt
    irf = np.exp(-0.5 * ((t - c["irf_mean_ns"]) / c["irf_sigma_ns"]) ** 2)
    decay = np.exp(-t / c["tau_ns"])
    l1 = float(c.get("l1", 0.0))
    l2 = float(c.get("l2", 0.0))
    norm = max(1.0 - l1 - l2, 1e-6)
    out = {}
    for key, rho, scale in c["decays"]:
        # r(t) runs from the excitation, so the polarised decays are convolved, not r(t) applied
        # to the convolved intensity (which would start the rotation at the start of the TAC).
        r = c["r0"] * np.exp(-t / rho)
        i_par = np.convolve(irf, decay * (1 + 2 * r))[:n] * scale
        i_perp = np.convolve(irf, decay * (1 - r))[:n] * scale
        vv = ((1.0 - l1) * i_par + l1 * i_perp) / norm
        vh = (l2 * i_par + (1.0 - l2) * i_perp) / (norm * c["g_factor"])
        bg = c["background_counts"]
        out[key] = (rng.poisson(vv + bg).astype(float), rng.poisson(vh + bg).astype(float))
    return out


def _digest(folder: Path) -> str:
    """Return a checksum over the four files."""
    h = hashlib.sha256()
    for name in sorted(FILES.values()):
        h.update((folder / name).read_bytes())
    return h.hexdigest()


def _cache_is_good(folder: Path) -> bool:
    """Require matching parameters and intact files."""
    try:
        side = json.loads((folder / f"{STEM}.json").read_text(encoding="utf-8"))
        return side.get("demo") == DEMO and side.get("sha256") == _digest(folder)
    except (OSError, ValueError):
        return False


def paths(folder: Path | None = None) -> dict[str, Path]:
    """Return the four file paths by key (``fast``, ``slow``, ``batch1``, ``batch2``)."""
    folder = demo_folder() if folder is None else Path(folder)
    return {key: folder / name for key, name in FILES.items()}


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> dict[str, Path]:
    """Write or reuse the four reference files.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and checksum match.

    Returns
    -------
    dict
        The file paths by key (see :func:`paths`); the JSON sidecar beside them records the settings
        and the true G.
    """
    from chisurf.core.fio import write_vv_vh

    folder = demo_folder() if folder is None else Path(folder)
    files = paths(folder)
    if not overwrite and all(p.is_file() for p in files.values()) and _cache_is_good(folder):
        return files
    folder.mkdir(parents=True, exist_ok=True)
    for key, (vv, vh) in simulate().items():
        write_vv_vh(files[key], vv=vv, vh=vh, metadata={"dt": DEMO["dt_ns"]})
    (folder / f"{STEM}.json").write_text(
        json.dumps(
            {
                "demo": DEMO,
                "sha256": _digest(folder),
                "truth": {"g_factor": DEMO["g_factor"], "l1": DEMO.get("l1", 0.0), "l2": DEMO.get("l2", 0.0), "r0": DEMO["r0"]},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return files
