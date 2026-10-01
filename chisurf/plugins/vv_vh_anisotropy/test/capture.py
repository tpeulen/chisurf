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
            os.environ["CHISURF_PLOT_BACKEND"] = "pyqtgraph"
            from qtpy.QtWidgets import QApplication, QWidget

            from chisurf.gui import chiplot
            from chisurf.plugins.vv_vh_anisotropy.qt_tool import VvVhAnisotropyCalculator

            app = QApplication.instance() or QApplication([])
            chiplot.set_backend("pyqtgraph")
            widget = VvVhAnisotropyCalculator()
            widget.load_vv_vh_file(path)
            widget.resize(1200, 800)
            widget.show()
            for _ in range(20):
                app.processEvents()
            children = [type(w).__module__ for w in widget.findChildren(QWidget)]
            assert not any("emtk" in module.lower() for module in children)
            assert widget.grab().save(str(renders / "qt-populated-1200x800.png"))
            widget.close()
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
