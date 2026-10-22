"""Example data for the tracking tool: a movie of particles with a known diffusion.

``make_demo`` writes ``tracking_demo.tif``: six particles diffusing with
``D = 0.5`` px²/frame, seeded (see
:mod:`chisurf.plugins.microscopy.demo_stack`), so the fit must return about that
coefficient and at least six tracks. *Load example* selects the movie; the
measurement runs as its own step, exactly as for a chosen file.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.microscopy import demo_stack

STEM = "tracking_demo"
#: The truth the fit must recover (px²/frame).
DIFFUSION = 0.5


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the tracking tool."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "img_tracking"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the diffusing-particle movie."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.tif"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        demo_stack.write_tif(path, demo_stack.tracking_stack(diffusion=DIFFUSION))
    return path


def load_into(app) -> Path:
    """Select the example movie, then track (the toolbar's own two steps)."""
    path = make_demo()
    app.model.open_path(str(path))
    app.model.track()
    return path
