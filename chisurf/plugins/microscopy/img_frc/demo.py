"""Example data for the FRC tool: one band-limited object, independent noise per frame.

``make_demo`` writes ``frc_demo.tif``: a stack whose object carries no detail
above the 0.15 cut-off, so the FRC crossing must sit near ``1 / 0.15`` px (see
:mod:`chisurf.plugins.microscopy.demo_stack`). *Load example* opens the stack
and measures, the way a dropped file is handled.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.microscopy import demo_stack

STEM = "frc_demo"
#: The spatial frequency the object is band-limited to (cycles/px).
CUTOFF = 0.15


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the FRC tool."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "img_frc"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the band-limited stack."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.tif"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        demo_stack.write_tif(path, demo_stack.frc_stack(cutoff=CUTOFF))
    return path


def load_into(app) -> Path:
    """Load the example, then measure (the Qt tool measured only on demand)."""
    import time

    path = make_demo()
    model = app.model
    model.open_path(str(path))
    while app.job.busy:  # the load runs on the worker; poll it like a drawn frame would
        app.job.poll()
        time.sleep(0.05)
    app.job.poll()
    model.measure()
    while app.job.busy:
        app.job.poll()
        time.sleep(0.05)
    app.job.poll()
    return path
