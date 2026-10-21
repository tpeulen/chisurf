"""Polarised reference decays with a known anisotropy, from the G-factor family's generator.

``make_demo(folder)`` reuses the ``vv_vh_g_factor`` demonstration generator
(:mod:`chisurf.plugins.vv_vh_g_factor.demo`) to write the same four stacked VV/VH
decays into this plugin's settings cache: a dye that depolarises within the pulse
(rho 0.2 ns), a slow protein (rho 16 ns) and two batch decays (8 ns and 30 ns).
Every decay has one 4 ns lifetime, r0 0.38, Gaussian pulse, mixing l1/l2, a
constant background and Poisson noise, so the anisotropy ``r(t) = r0 * exp(-t/rho)``
is known by construction. The example loads the slow protein decay; all four go to
the batch queue. Nothing here is a measurement; the files are byte-identical on
every run, and the JSON sidecar records ``DEMO`` while a checksum rejects partial
or modified cached data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from chisurf.plugins.vv_vh_g_factor import demo as gfactor_demo

STEM = "anisotropy_demo"
#: The file the Load-example action opens (the slow protein's decay).
PRIMARY = "slow"
#: The generator parameters this plugin's cache is bound to (the sibling's declared set).
DEMO: dict[str, Any] = {
    "version": 1,
    "generator": "chisurf.plugins.vv_vh_g_factor.demo",
    "seed": int(gfactor_demo.DEMO["seed"]),
    "primary": PRIMARY,
    "g_factor": float(gfactor_demo.DEMO["g_factor"]),
    "r0": float(gfactor_demo.DEMO["r0"]),
    "tau_ns": float(gfactor_demo.DEMO["tau_ns"]),
    "l1": float(gfactor_demo.DEMO.get("l1", 0.0)),
    "l2": float(gfactor_demo.DEMO.get("l2", 0.0)),
    "background_counts": float(gfactor_demo.DEMO["background_counts"]),
    "files": sorted(gfactor_demo.FILES.values()),
}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "vv_vh_anisotropy"


def paths(folder: Path | None = None) -> dict[str, Path]:
    """Return the four VV/VH file paths by key (``fast``, ``slow``, ``batch1``, ``batch2``)."""
    folder = demo_folder() if folder is None else Path(folder)
    return {key: folder / name for key, name in gfactor_demo.FILES.items()}


def _digest(folder: Path) -> str:
    """Return a checksum over the four reference files."""
    h = hashlib.sha256()
    for name in DEMO["files"]:
        h.update((folder / name).read_bytes())
    return h.hexdigest()


def _cache_is_good(folder: Path) -> bool:
    """Require matching parameters and intact files."""
    try:
        side = json.loads((folder / f"{STEM}.json").read_text(encoding="utf-8"))
        return side.get("demo") == DEMO and side.get("sha256") == _digest(folder)
    except (OSError, ValueError):
        return False


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the reference decays; return the primary file's path.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and checksum match.

    Returns
    -------
    pathlib.Path
        The primary (slow protein) VV/VH decay; the batch queue takes all four.
    """
    folder = demo_folder() if folder is None else Path(folder)
    if not overwrite and all(
        (folder / name).is_file() for name in DEMO["files"]
    ) and _cache_is_good(folder):
        return paths(folder)[PRIMARY]
    folder.mkdir(parents=True, exist_ok=True)
    gfactor_demo.make_demo(folder, overwrite=True)
    (folder / f"{STEM}.json").write_text(
        json.dumps(
            {
                "demo": DEMO,
                "sha256": _digest(folder),
                "truth": {
                    "g_factor": DEMO["g_factor"],
                    "r0": DEMO["r0"],
                    "primary": gfactor_demo.DEMO["decays"][1][0],
                    "primary_rho_ns": gfactor_demo.DEMO["decays"][1][1],
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return paths(folder)[PRIMARY]
