"""Example data for the 2D-FLCS tool: the parameters of its own simulated stream.

The tool generates its example itself (the *Sim* button: a two-state photon
stream with known kinetics). ``make_demo`` writes those parameters as a JSON
sidecar next to the settings; ``load_into`` presses Sim and then runs the
analysis, the two buttons a user would press.
"""

from __future__ import annotations

import json
from pathlib import Path

from chisurf.plugins.fcs.flc_2d.gui.model import FlcModel

STEM = "flc_2d_demo"
#: The demo simulates a short stream so the 2D correlation stays interactive.
SIM_TIME_S = 10.0


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the 2D-FLCS tool."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "flc_2d"


def _sim_parameters() -> dict:
    """The simulator parameters the demo runs with (the Sim defaults, slimmed)."""
    model = FlcModel()
    return {
        "k12": float(model.sim_k12),
        "k21": float(model.sim_k21),
        "irf_center_ns": float(model.irf_center_ns),
        "irf_fwhm_ns": float(model.irf_fwhm_ns),
        "irf_shape": float(model.irf_shape),
        "sim_time_s": SIM_TIME_S,
    }


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write (or reuse) the sidecar that states the simulated truth."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.json"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"sim": _sim_parameters()}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"could not write the demo sidecar to {path}")
    return path


def load_into(app) -> Path:
    """Simulate the example stream, then run the analysis (both on the tool's worker)."""
    path = make_demo()
    model = app.model
    import time

    def settle(deadline_s: float) -> None:
        """Wait for the worker, polling the job the way a drawn frame would."""
        end = time.monotonic() + deadline_s
        while app.job.busy and time.monotonic() < end:
            app.job.poll()
            time.sleep(0.05)
        app.job.poll()

    model.sim_time_s = SIM_TIME_S
    app.start_job("simulate")
    settle(300.0)
    app.start_job("run")
    settle(300.0)
    return path
