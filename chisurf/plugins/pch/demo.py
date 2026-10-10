"""A simulated photon stream of one diffusing species with a known brightness, so the PCH tool can teach itself.

``make_demo(folder)`` writes ``pch_demo.ptu``: molecules diffusing in three dimensions through a
Gaussian focus (``tttrlib`` photon simulator), detected on channel 0. The molecular brightness is
set by construction: a molecule at the centre of the focus emits ``q`` photons per millisecond, so
in a counting interval of ``bin_time_us`` it contributes :func:`expected_brightness` counts, the
quantity the fit calls epsilon. "Load example" therefore also sets the tool to channel 0 and that
bin time, which is short against the diffusion time so a molecule hardly moves within one bin.

The occupancy is not asserted from the box: the tool reports ``N`` in a reference volume whose
convention is the model's, so the test derives the expected ``N`` from the mean count rate
(``<k> = N * epsilon * g`` with ``g`` the model's own factor) instead of restating a geometry.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

STEM = "pch_demo"
#: The simulation, in one place so the help text, the guide and the tests agree.
DEMO: dict[str, Any] = {
    "version": 1,
    "seed": 20261010,
    "n_photons": 200_000,
    "brightness_per_ms": 150.0,
    "bin_time_us": 20.0,
    "diffusion_um2_ms": 0.05,
    "population": 6.0,
    "waist_um": 0.3,
    "axial_um": 0.9,
    "box_xy_um": 1.2,
    "box_z_um": 2.4,
    "macro_time_resolution_s": 1.0e-7,
}


def expected_brightness() -> float:
    """Return the true epsilon: photons per molecule per counting interval at the focus centre."""
    return DEMO["brightness_per_ms"] * DEMO["bin_time_us"] * 1e-3


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "pch"


def photon_times_ms() -> np.ndarray:
    """Simulate the stream and return the ascending arrival times (ms)."""
    from chisurf.core.fluorescence.simulation import build_engine, seeds

    c = DEMO
    dt = 0.005
    engine = build_engine(
        {
            "settings": {
                "dt": dt,
                "n_ph_max": int(c["n_photons"]),
                "n_channels": 1,
                "n_microtime_channels": 256,
                "microtime_resolution": 0.032,
                "laser_period": 256 * 0.032,
                "fast_grid_bbox": True,
                "active_margin": 1.0,
                **seeds(int(c["seed"])),
            },
            "box": {"xy": c["box_xy_um"], "z": c["box_z_um"]},
            "species": [
                {
                    "D": c["diffusion_um2_ms"],
                    "q": [c["brightness_per_ms"]],
                    "decay": {"lifetimes": [2.0]},
                }
            ],
            "k_rad": [0.0],
            "k_nrad": [0.0],
            "background": [0.0],
            "population": [c["population"]],
            "excitation": {
                "type": "gaussian3d",
                "w0": c["waist_um"],
                "z0": c["axial_um"],
                "extent_xy": c["box_xy_um"],
                "extent_z": c["box_z_um"],
                "spacing": 0.05,
            },
        }
    )
    engine.run()
    t = np.asarray(engine.macro_window()).astype(np.float64) * dt + np.asarray(engine.arrival_time())
    micro = np.asarray(engine.micro_time()).astype(np.uint16)
    order = np.argsort(t, kind="stable")
    return t[order], micro[order]


def _digest(path: Path) -> str:
    """Return the checksum of the stream file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cache_is_good(path: Path) -> bool:
    """Require matching parameters and an intact stream."""
    try:
        side = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        return side.get("demo") == DEMO and side.get("sha256") == _digest(path)
    except (OSError, ValueError):
        return False


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the simulated one-species photon stream.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and checksum match.

    Returns
    -------
    pathlib.Path
        The PTU file; its JSON sidecar holds the settings and the true brightness.
    """
    import tempfile

    import tttrlib

    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.ptu"
    if not overwrite and path.is_file() and _cache_is_good(path):
        return path
    folder.mkdir(parents=True, exist_ok=True)
    t_ms, micro = photon_times_ms()
    res = DEMO["macro_time_resolution_s"]
    ticks = np.maximum.accumulate(np.round(t_ms * 1e-3 / res).astype(np.uint64))
    stream = tttrlib.TTTR(
        ticks, micro, np.zeros(len(ticks), dtype=np.int8), np.zeros(len(ticks), dtype=np.int8)
    )
    header = stream.header
    header.set_macro_time_resolution(res)
    header.set_micro_time_resolution(0.032e-9)
    with tempfile.TemporaryDirectory(prefix="pch-demo-", dir=folder) as staging:
        staged = Path(staging) / path.name
        if not stream.write(str(staged), "PTU"):
            raise OSError(f"could not write the demo photon stream to {path}")
        staged.replace(path)
    path.with_suffix(".json").write_text(
        json.dumps(
            {
                "demo": DEMO,
                "sha256": _digest(path),
                "epsilon": expected_brightness(),
                "channels": "0",
                "bin_time_us": DEMO["bin_time_us"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path
