"""A correlation curve whose answer is known, for the shell's *Demo* button and its tests.

One freely diffusing species in a 3D Gaussian focus, written in the Seidel
(Kristine) ``.cor`` layout the *Seidel Kristine* reader of the FCS experiment
reads: lag time in ms, G(τ), the count rate column (zero) and the standard
deviation of G(τ). The noise is drawn with a fixed seed, so the file is the
same on every machine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

#: The true values the demo curve is made with.
N_MOLECULES = 2.0
TAU_DIFFUSION_MS = 0.5
ASPECT_RATIO = 4.0
OFFSET = 1.0
NOISE_SD = 0.004
SEED = 20261011
#: What the demo is and how it was made; the shell's Read data dock reads the first three.
DEMO: dict[str, Any] = {
    "experiment": "FCS",
    "reader": "Seidel Kristine",
    "model": "FCS (general: diffusion + bunching/anticorr)",
    "n": N_MOLECULES,
    "tau_diffusion_ms": TAU_DIFFUSION_MS,
    "aspect_ratio": ASPECT_RATIO,
    "offset": OFFSET,
    "noise_sd": NOISE_SD,
    "seed": SEED,
}
STEM = "fcs_demo"


def demo_folder() -> Path:
    """Return the settings-owned folder the demo is written to."""
    from chisurf.core.settings import get_path

    return Path(get_path("settings")) / "demos" / "fcs"


def demo_curve() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(tau_ms, g, sd)``: the noisy demo correlation curve.

    G(τ) = offset + 1/N · (1 + τ/τ_D)⁻¹ · (1 + τ/(s² τ_D))^(-1/2), with additive
    Gaussian noise of standard deviation ``noise_sd``.
    """
    tau = np.logspace(-4, 3, 160)
    td, s2 = TAU_DIFFUSION_MS, ASPECT_RATIO**2
    g = OFFSET + (1.0 / N_MOLECULES) / (1.0 + tau / td) / np.sqrt(1.0 + tau / (s2 * td))
    rng = np.random.default_rng(SEED)
    sd = np.full_like(tau, NOISE_SD)
    return tau, g + rng.normal(0.0, NOISE_SD, tau.size), sd


def make_demo(folder: Path | str | None = None) -> Path:
    """Write the demo ``.cor`` file and return its path.

    Parameters
    ----------
    folder : path, optional
        Directory to write into; :func:`demo_folder` by default.

    Returns
    -------
    pathlib.Path
        The written file, readable by the *Seidel Kristine* FCS reader.
    """
    folder = demo_folder() if folder is None else Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    tau, g, sd = demo_curve()
    path = folder / f"{STEM}.cor"
    table = np.column_stack([tau, g, np.zeros_like(tau), sd])
    np.savetxt(path, table, fmt="%.10f", delimiter="\t")
    return path
