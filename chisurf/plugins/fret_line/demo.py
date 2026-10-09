"""Declared illustrative dye-pair inputs and their reproducible FRET line."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

DEMO = {
    "version": 1,
    "model": "FRET: FD (Gaussian)",
    "donor_lifetime_ns": 4.0,
    "forster_radius_angstrom": 52.0,
    "distance_min_angstrom": 20.0,
    "distance_max_angstrom": 120.0,
    "points": 100,
    "qualification": "Illustrative physical inputs, not a named vendor dye calibration.",
}


def pair_inputs() -> tuple[float, float]:
    """Read the two declared physical inputs with their numeric contract."""
    tau = DEMO["donor_lifetime_ns"]
    radius = DEMO["forster_radius_angstrom"]
    if not isinstance(tau, (int, float)) or not isinstance(radius, (int, float)):
        raise ValueError("The illustrative pair must declare numeric physical inputs.")
    return float(tau), float(radius)


def demo_folder() -> Path:
    """Return the settings-owned cache for the illustrative pair."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "fret_line"


def configure_example(model) -> None:
    """Replace the mixture with declared inputs, leaving Compute to the user."""
    model.close()
    model.components.clear()
    model.lines.clear()
    model._line_seq = 0
    model.component_index = 0
    model.add_component()
    model.dye_pair = "illustrative"
    model.pair_tau = DEMO["donor_lifetime_ns"]
    model.pair_r0 = DEMO["forster_radius_angstrom"]
    model.apply_dye_pair()
    model.minimum = DEMO["distance_min_angstrom"]
    model.maximum = DEMO["distance_max_angstrom"]
    model.n_points = DEMO["points"]
    model.log_scale = False
    model._sweep_filter = ""
    model._select_default_sweep()
    model.line_index = -1
    model.dialog_title = model.dialog_text = model.request = ""


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the actual model-computed example with its cache receipt."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / "illustrative_fret_line.csv"
    sidecar = folder / "illustrative_fret_line.json"
    if not overwrite and path.is_file() and sidecar.is_file():
        try:
            receipt = json.loads(sidecar.read_text())
            if (isinstance(receipt, dict) and receipt.get("parameters") == DEMO
                    and receipt.get("sha256") == hashlib.sha256(path.read_bytes()).hexdigest()):
                return path
        except (OSError, ValueError):
            pass
    from .gui.model import FretLineModel

    folder.mkdir(parents=True, exist_ok=True)
    model = FretLineModel()
    try:
        configure_example(model)
        if model.add_line() is None:
            raise RuntimeError(model.message)
        model.write_csv(path)
    finally:
        model.close()
    sidecar.write_text(json.dumps({"parameters": DEMO,
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
                                 indent=2) + "\n")
    return path
