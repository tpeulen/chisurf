"""Capture populated native and genuine Qt anisotropy windows."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("native", "qt"))
    args = parser.parse_args()
    renders = Path(__file__).parent / "renders"
    renders.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        t = np.arange(100, dtype=float)
        vv = 1000 * np.exp(-t / 28) + 15
        vh = 480 * np.exp(-t / 30) + 8
        path = Path(directory) / "sample_vv_vh.dat"
        np.savetxt(path, np.r_[vv, vh])
        if args.mode == "qt":
            # The Qt reference was captured with the pyqtgraph backend forced on, so that no emtk
            # widget could hide in it. That backend is gone: the recorded reference stays in renders/.
            parser.error("the Qt reference needed the removed pyqtgraph backend; use 'native'")
        else:
            from emtk.pil_painter import PilPainter

            from chisurf.plugins.vv_vh_anisotropy.gui.app import create_app

            for width, height, label in ((1200, 800, "normal"), (800, 600, "narrow")):
                app = create_app()
                app.model.load(path)
                painter = PilPainter(width, height)
                app.draw(painter, 0, 0, width, height)
                painter.frame.save(renders / f"native-populated-{label}.png")


if __name__ == "__main__":
    main()
