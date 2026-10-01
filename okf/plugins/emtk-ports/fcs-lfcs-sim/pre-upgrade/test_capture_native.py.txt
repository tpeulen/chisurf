"""Capture populated native LFCS views at normal and narrow sizes."""

from pathlib import Path

import numpy as np
from emtk.native import NativeHost
from PIL import Image

from ..app import LifetimeFcsSimApp


def _datasets():
    x = np.asarray([1e-3, 1e-2, 1e-1, 1.0])
    return [
        {"x": x, "y": np.asarray([2.0, 1.6, 1.2, 1.0]), "name": "τ=1 ns"},
        {"x": x, "y": np.asarray([2.4, 1.8, 1.25, 1.0]), "name": "τ=4 ns"},
        {"x": x, "y": np.asarray([1.7, 1.4, 1.15, 1.0]), "name": "cross"},
    ]


def main() -> None:
    out = Path(__file__).parent / "renders"
    out.mkdir(exist_ok=True)
    for size, name in [((980, 700), "native-normal"), ((800, 600), "native-narrow")]:
        app = LifetimeFcsSimApp()
        app.model.datasets = _datasets()
        app.message = "Simulation complete: 3 curves; condition number 2.4."
        host = NativeHost(app, size=size, backend="offscreen")
        Image.fromarray(np.asarray(host.draw_frame())).save(out / f"{name}.png")
        host.close()


if __name__ == "__main__":
    main()

