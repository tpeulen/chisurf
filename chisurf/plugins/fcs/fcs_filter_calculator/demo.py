"""Example data for the filtered-FCS calculator: the synthetic two-component decay.

The tool's *Load example* is its own ``populate_example``: two synthetic lifetime
components (1.2 ns, 4.0 ns; weights 0.665 / 0.285) seen through per-detector
IRFs. ``make_demo`` writes that truth as a JSON sidecar, so the tests can assert
the fit recovers what the example was built from without restating the synthesis.
"""

from __future__ import annotations

import json
from pathlib import Path

STEM = "filter_demo"
#: The truth the example is built from (the same numbers populate_example uses).
TRUTH = {
    "lifetimes_ns": [1.2, 4.0],
    "component_weights": [0.665, 0.285],
    "n_bins": 256,
    "bin_width_ns": 0.05,
}


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the filter calculator."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "fcs_filter_calculator"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the sidecar that states the example's truth."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.json"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(TRUTH, indent=2, sort_keys=True), encoding="utf-8")
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"could not write the demo sidecar to {path}")
    return path


def load_into(app) -> Path:
    """The model ships populated; recompute so the filters are fresh evidence."""
    app.model.compute()
    return make_demo()
