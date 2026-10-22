"""Example data for the drift-correction tool: a bead stack with a known linear drift.

``make_demo`` writes ``drift_demo.tif``: Gaussian beads (see
:mod:`chisurf.plugins.microscopy.demo_stack`) that shift by ``(2, -1)`` px per
frame, seeded, so the measured shifts must be ``k * (2, -1)``. *Load example*
hands the stack to the model through ``open_path`` — the same path a dropped
file takes — which reads it and measures.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.microscopy import demo_stack

STEM = "drift_demo"
N_FRAMES = 6
#: The truth the tool must measure: the shift of frame *k* against frame 0.
TRUE_SHIFTS = [
    (k * demo_stack.DRIFT_STEP[0], k * demo_stack.DRIFT_STEP[1]) for k in range(N_FRAMES)
]


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the drift tool."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "img_drift"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the drifting bead stack."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.tif"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        demo_stack.write_tif(path, demo_stack.drift_stack(n_frames=N_FRAMES))
    return path


def load_into(app) -> Path:
    """Load the example and measure it (the model's own open-and-measure path)."""
    path = make_demo()
    app.model.open_path(str(path))
    return path
