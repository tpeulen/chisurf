"""Example data for the IRF estimator: a VV/VH decay whose tail is background.

``make_demo`` writes ``irf_demo_vvvh.dat`` — a seeded bi-exponential decay
(1.1 ns and 3.9 ns) with Poisson noise and a flat tail, in the VV/VH format the
tool reads. The estimator infers the instrument response from the rising edge;
the demo's known start (a Gaussian IRF of 0.18 ns FWHM at 0.4 ns) is the truth
the estimate is judged against.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

STEM = "irf_demo"
SEED = 5
#: The truth the estimate is judged against.
TRUE_IRF = {"center_ns": 0.4, "fwhm_ns": 0.18}
LIFETIMES_NS = (1.1, 3.9)
WEIGHTS = (0.7, 0.3)
N_BINS = 512
BIN_NS = 0.02


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the IRF estimator."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "irf_estimator"


def synthetic_decay() -> np.ndarray:
    """A bi-exponential decay convolved with the demo's Gaussian IRF, Poisson-noised."""
    t = np.arange(N_BINS) * BIN_NS
    sigma = TRUE_IRF["fwhm_ns"] / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    irf = np.exp(-0.5 * ((t - TRUE_IRF["center_ns"]) / sigma) ** 2)
    decay = sum(w * np.exp(-t / tau) for w, tau in zip(WEIGHTS, LIFETIMES_NS))
    convolved = np.convolve(np.asarray(decay), np.asarray(irf), mode="full")[:N_BINS]
    convolved = convolved / convolved.max() * 1e4
    rng = np.random.default_rng(SEED)
    return rng.poisson(np.maximum(convolved, 0.0) + 2.0).astype(float)


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the demo decay in the VV/VH format the tool reads."""
    from chisurf.core.fio.vv_vh import write_vv_vh

    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}_vvvh.dat"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        decay = synthetic_decay()
        write_vv_vh(
            path,
            vv=decay,
            vh=decay,
            metadata={"dt_ns": BIN_NS, "comment": "chisurf irf_estimator demo decay"},
        )
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"could not write the demo decay to {path}")
    return path


def load_into(model) -> Path:
    """Load the demo decay and estimate the IRF."""
    path = make_demo()
    model.load_file(str(path))
    model.estimate()
    return path
