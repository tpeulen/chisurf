"""Two fits of one simulated decay, so the F-test can teach itself.

``make_demo(folder)`` simulates a decay that is *truly* a two-exponential
(:data:`DEMO`), fits it with a one- and a two-exponential model by least squares, and
stores the two reduced chi-squares with their degrees of freedom in ``ftest_demo.json``.
The answer is known in advance: the extra component is real, so the F-test must
prefer the two-exponential model with a confidence near 1, and the fitted lifetimes
must lie close to the simulated ones. Nothing here is a measurement.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

STEM = "ftest_demo"
#: The simulation, in one place so the help text and the tests agree.
DEMO: dict[str, Any] = {
    "version": 1,
    "seed": 20261010,
    "n_points": 256,
    "t_max_ns": 25.0,
    "amplitudes": [1.0, 0.8],
    "lifetimes_ns": [0.8, 4.0],
    "noise": 0.01,
}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "f_test"


def simulate() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return time (ns), noisy decay and its constant standard deviation."""
    rng = np.random.default_rng(DEMO["seed"])
    t = np.linspace(0.0, DEMO["t_max_ns"], DEMO["n_points"])
    truth = sum(a * np.exp(-t / tau) for a, tau in zip(DEMO["amplitudes"], DEMO["lifetimes_ns"]))
    sigma = DEMO["noise"] * np.ones_like(t)
    return t, truth + rng.normal(0.0, sigma), sigma


def fit(n_components: int) -> dict[str, Any]:
    """Fit *n_components* exponentials; return reduced chi-square, dof and lifetimes."""
    from chisurf.core.math.numerics import least_squares

    t, y, sigma = simulate()

    def residuals(p):
        a, tau = p[:n_components], p[n_components:]
        return (sum(ai * np.exp(-t / ti) for ai, ti in zip(a, tau)) - y) / sigma

    start = np.concatenate([np.full(n_components, 1.0), np.geomspace(1.0, 5.0, n_components)])
    solution = least_squares(residuals, start, bounds=(1e-6, 1e3))
    n_free = 2 * n_components
    dof = len(t) - n_free
    order = np.argsort(solution.x[n_components:])
    return {
        "chi2r": float(np.sum(solution.fun**2) / dof),
        "n_points": int(len(t)),
        "n_free": n_free,
        "dof": int(dof),
        "lifetimes_ns": [float(solution.x[n_components:][i]) for i in order],
    }


def _digest(path: Path) -> str:
    """Return the checksum recorded beside *path*."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cache_is_good(path: Path) -> bool:
    """Require matching parameters and an intact data file."""
    try:
        side = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        return side == {"demo": DEMO, "sha256": _digest(path)}
    except (OSError, ValueError):
        return False


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the two-fit demo statistics.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and checksum match.

    Returns
    -------
    pathlib.Path
        The JSON file holding ``simple`` (one exponential) and ``complex`` (two) statistics.
    """
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.json"
    if not overwrite and _cache_is_good(path):
        return path
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"simple": fit(1), "complex": fit(2), "truth": DEMO}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    path.with_suffix(".meta.json").write_text(
        json.dumps({"demo": DEMO, "sha256": _digest(path)}, sort_keys=True), encoding="utf-8"
    )
    return path
