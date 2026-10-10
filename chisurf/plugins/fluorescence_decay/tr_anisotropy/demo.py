"""A polarization-resolved decay with a known lifetime and rotational correlation time, so the wizard can teach itself.

``make_demo(folder)`` writes four two-column text files (time in ns, counts): ``anis_irf_vv.dat`` and
``anis_irf_vh.dat`` (the instrument response on each polarization) and ``anis_decay_vv.dat`` and
``anis_decay_vh.dat``. The decays come from the fit stack's own forward model
(:func:`chisurf.core.experiments.tcspc.simulator.simulate_decay_channels`) with one lifetime
``tau_ns`` and one rotation ``rho_ns`` of amplitude ``r0``, no correction factors (``g = 1``,
``l1 = l2 = 0``), convolved with the Gaussian response and Poisson sampled. The answer is
therefore known: the linked global fit must return ``tau_ns``, ``rho_ns`` and ``r0``. Nothing here
is a measurement.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

STEM = "anis_demo"
FILES = {
    "irf_vv": "anis_irf_vv.dat",
    "irf_vh": "anis_irf_vh.dat",
    "data_vv": "anis_decay_vv.dat",
    "data_vh": "anis_decay_vh.dat",
}
#: The simulation, in one place so the help text, the guide and the tests agree.
DEMO: dict[str, Any] = {
    "version": 1,
    "seed": 20261010,
    "n_tac": 800,
    "dt_ns": 0.05,
    "rep_rate_mhz": 25.0,
    "tau_ns": 4.0,
    "rho_ns": 2.0,
    "r0": 0.38,
    "peak_counts": 30000.0,
    "irf_mean_ns": 2.0,
    "irf_sigma_ns": 0.12,
    "irf_peak_counts": 20000.0,
    "irf_background_counts": 4.0,
}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "demos" / "tr_anisotropy"


def simulate() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Return ``{key: (time_ns, counts)}`` for the two IRFs and the two decays."""
    from chisurf.core.experiments.tcspc.simulator import simulate_decay_channels

    c = DEMO
    n, dt = c["n_tac"], c["dt_ns"]
    x, vv, vh = simulate_decay_channels(
        [1.0, c["tau_ns"]],
        [c["r0"], c["rho_ns"]],
        n_tac=n,
        dt=dt,
        p0=c["peak_counts"],
        irf_mean=c["irf_mean_ns"],
        irf_sigma=c["irf_sigma_ns"],
        seed=c["seed"],
    )
    rng = np.random.default_rng(c["seed"] + 1)
    prompt = c["irf_peak_counts"] * np.exp(-0.5 * ((x - c["irf_mean_ns"]) / c["irf_sigma_ns"]) ** 2)
    bg = c["irf_background_counts"]
    return {
        "irf_vv": (x, rng.poisson(prompt + bg).astype(float)),
        "irf_vh": (x, rng.poisson(0.8 * prompt + bg).astype(float)),
        "data_vv": (x, vv),
        "data_vh": (x, vh),
    }


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
    """Return the four file paths by key (``irf_vv``, ``irf_vh``, ``data_vv``, ``data_vh``)."""
    folder = demo_folder() if folder is None else Path(folder)
    return {key: folder / name for key, name in FILES.items()}


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the four files.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and checksum match.

    Returns
    -------
    pathlib.Path
        The decay VV file; the other three (:func:`paths`) sit beside it and the JSON sidecar
        records the settings and the true parameters.
    """
    folder = demo_folder() if folder is None else Path(folder)
    files = paths(folder)
    if not overwrite and all(p.is_file() for p in files.values()) and _cache_is_good(folder):
        return files["data_vv"]
    folder.mkdir(parents=True, exist_ok=True)
    for key, (x, y) in simulate().items():
        np.savetxt(files[key], np.column_stack((x, y)), header="time_ns counts", fmt="%.6g")
    (folder / f"{STEM}.json").write_text(
        json.dumps(
            {
                "demo": DEMO,
                "sha256": _digest(folder),
                "truth": {k: DEMO[k] for k in ("tau_ns", "rho_ns", "r0")},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return files["data_vv"]
