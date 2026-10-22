"""Example data for the maximum-entropy decay tool: a noisy bi-exponential decay.

``make_demo`` writes ``maxent_demo.dat`` — time/count pairs of a seeded
bi-exponential decay (1.0 ns and 4.5 ns, 2 % background, Poisson noise), the
two-column text the model's ``load_file`` reads. The MEM grid must put its mass
near the two lifetimes.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

STEM = "maxent_demo"
SEED = 9
#: The truth the reconstruction must find.
LIFETIMES_NS = (1.0, 4.5)
WEIGHTS = (0.6, 0.4)
N_BINS = 400
DT_NS = 0.05
BACKGROUND = 2.0


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the MEM tool."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "maxent_decay"


def synthetic_decay() -> tuple[np.ndarray, np.ndarray]:
    """Time axis and counts of the demo decay."""
    t = np.arange(N_BINS) * DT_NS
    decay = sum(w * np.exp(-t / tau) for w, tau in zip(WEIGHTS, LIFETIMES_NS))
    decay = decay / decay.max() * 5e3 + BACKGROUND
    rng = np.random.default_rng(SEED)
    return t, rng.poisson(decay).astype(float)


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the demo decay as two-column text."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.dat"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        t, counts = synthetic_decay()
        np.savetxt(path, np.column_stack([t, counts]), header="time_ns\tcounts")
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"could not write the demo decay to {path}")
    return path


def load_into(model) -> Path:
    """Load the demo decay and run the maximum-entropy reconstruction."""
    path = make_demo()
    model.load_file(str(path))
    model.run()
    return path
