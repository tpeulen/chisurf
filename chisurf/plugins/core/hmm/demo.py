"""Example data for the HMM tool: a binned trace that switches between two states.

``make_demo`` writes ``hmm_demo_trace.npy``: a seeded telegraph process — a slow
two-state chain observed as noisy intensities (0.30 and 0.70 with Gaussian
noise) — so the fit must find two states and put the means near the truth. The
trace is exactly what :func:`chisurf.plugins.core.hmm.cli.main.load_trace` reads.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

STEM = "hmm_demo_trace"
SEED = 11
N_BINS = 4000
#: The truth the fit must find.
STATE_MEANS = (0.30, 0.70)
SWITCH_PROBABILITY = 0.01
NOISE = 0.05


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the HMM tool."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "hmm"


def synthetic_trace(n_bins: int = N_BINS, seed: int = SEED) -> np.ndarray:
    """The two-state trace as an ``(n_bins, 1)`` array."""
    rng = np.random.default_rng(seed)
    states = np.empty(n_bins, dtype=int)
    states[0] = 0
    flips = rng.random(n_bins) < SWITCH_PROBABILITY
    for i in range(1, n_bins):
        states[i] = states[i - 1] ^ 1 if flips[i] else states[i - 1]
    means = np.asarray(STATE_MEANS)[states]
    return (means + NOISE * rng.standard_normal(n_bins))[:, None]


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the two-state trace."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.npy"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        np.save(path, synthetic_trace())
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"could not write the demo trace to {path}")
    return path


def load_into(model) -> Path:
    """Load the trace into the model and fit it."""
    path = make_demo()
    model.sel_files = [str(path)]
    model.load()
    model.run()
    return path
