"""A two-channel image with a known colocalization, so the tool can teach itself.

``make_demo(folder)`` writes ``coloc_demo.tif`` (channels A and B, ImageJ ``CYX`` hyperstack).
Channel A holds :data:`DEMO` ``n_shared`` equally bright, well separated flat discs; channel B holds
the same spots **plus** ``n_extra`` further ones that A does not have. Every spot of A therefore
has a partner in B but only ``n_shared / (n_shared + n_extra)`` of B's intensity sits on a spot of
A, so the answer is known by construction and is the asymmetric one the guide warns about:
Manders M1 (the share of A that overlaps B) is about 1, M2 (the share of B that overlaps A) about
``expected_m2()`` = 0.5, read with a threshold of :data:`DEMO` ``threshold`` photons between the
background and the discs (flat discs, so the answer does not depend on where exactly it sits). A single Pearson number cannot say which. Nothing here is a measurement.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

STEM = "coloc_demo"
#: The simulation, in one place so the help text, the guide and the tests agree.
DEMO: dict[str, Any] = {
    "version": 1,
    "seed": 20261010,
    "size": 128,
    "n_shared": 14,
    "n_extra": 14,
    "spot_radius_px": 3.5,
    "spot_amplitude": 100.0,
    "background": 0.1,
    "threshold": 30.0,
    "min_separation_px": 14.0,
    "pixel_size_um": 0.1,
}


def expected_m1() -> float:
    """Return the true share of channel A that overlaps channel B: every spot of A is in B."""
    return 1.0


def expected_m2() -> float:
    """Return the true share of channel B that overlaps channel A: ``n_shared / (n_shared + n_extra)``."""
    return DEMO["n_shared"] / (DEMO["n_shared"] + DEMO["n_extra"])


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "demos" / "img_coloc"


def spot_centres(rng: np.random.Generator) -> np.ndarray:
    """Draw ``n_shared + n_extra`` centres at least ``min_separation_px`` apart, away from the edge."""
    c = DEMO
    margin = 2.0 * c["spot_radius_px"]
    centres: list[np.ndarray] = []
    while len(centres) < c["n_shared"] + c["n_extra"]:
        candidate = rng.uniform(margin, c["size"] - margin, 2)
        if all(np.hypot(*(candidate - other)) >= c["min_separation_px"] for other in centres):
            centres.append(candidate)
    return np.asarray(centres)


def simulate() -> np.ndarray:
    """Return the ``(2, size, size)`` uint16 stack: channel A, channel B."""
    c = DEMO
    rng = np.random.default_rng(c["seed"])
    centres = spot_centres(rng)
    yy, xx = np.mgrid[0 : c["size"], 0 : c["size"]].astype(float)

    def spots(rows: np.ndarray) -> np.ndarray:
        out = np.zeros((c["size"], c["size"]))
        for cy, cx in rows:
            out += c["spot_amplitude"] * (
                (yy - cy) ** 2 + (xx - cx) ** 2 <= c["spot_radius_px"] ** 2
            )
        return out

    shared = c["n_shared"]
    a = spots(centres[:shared]) + c["background"]
    b = spots(centres) + c["background"]
    return np.stack([rng.poisson(a), rng.poisson(b)]).astype(np.uint16)


def _digest(path: Path) -> str:
    """Return the checksum of the image file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cache_is_good(path: Path) -> bool:
    """Require matching parameters and an intact image."""
    try:
        side = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        return side.get("demo") == DEMO and side.get("sha256") == _digest(path)
    except (OSError, ValueError):
        return False


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the two-channel image.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and checksum match.

    Returns
    -------
    pathlib.Path
        The TIFF; its JSON sidecar records the settings and the true Manders coefficients.
    """
    from chisurf.core.fio.image import imwrite

    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.tif"
    if not overwrite and path.is_file() and _cache_is_good(path):
        return path
    folder.mkdir(parents=True, exist_ok=True)
    pixel = DEMO["pixel_size_um"]
    imwrite(
        path,
        simulate(),
        axes="CYX",
        resolution=(1.0 / pixel, 1.0 / pixel),
        metadata={"unit": "um"},
    )
    path.with_suffix(".json").write_text(
        json.dumps(
            {
                "demo": DEMO,
                "sha256": _digest(path),
                "truth": {"manders_m1": expected_m1(), "manders_m2": expected_m2()},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path
