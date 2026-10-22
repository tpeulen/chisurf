"""Example data for the region-MLE panel: the spot-finder demo field with known lifetimes.

The tool's *Load demo* already generates the spot-finder example (a field whose
regions have known lifetimes) and runs the standard detection, ready to fit.
``make_demo`` produces that field for scripts; *Load example* presses the tool's
own demo load on the worker.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.microscopy.spot_finder.demo import demo_folder as _source_folder
from chisurf.plugins.microscopy.spot_finder.demo import make_demo as _make_source_demo


def demo_folder() -> Path:
    """The settings-owned demonstration folder shared with the spot finder."""
    return _source_folder()


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the demo field (the spot finder's example, read in place)."""
    folder = demo_folder() if folder is None else Path(folder)
    return _make_source_demo(folder, overwrite=overwrite)


def load_into(app) -> Path:
    """The tool's own demo load: generate the field and detect its regions (worker)."""
    import time

    app.start_job("load_demo")
    deadline = 300.0
    while app.job.busy and deadline > 0:
        time.sleep(0.05)
        deadline -= 0.05
    return make_demo()
