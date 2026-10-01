"""Capture actual populated Qt and native LUT tools for parity review."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SPC = ROOT / "test/data/tttr/BH/132/BH_SPC132.spc"


def capture_qt():
    from qtpy.QtWidgets import QApplication

    from chisurf.plugins.tttr.tttr_lut_tools.gui.tool import TTRLutToolsWidget

    app = QApplication.instance() or QApplication([])
    widget = TTRLutToolsWidget()
    widget.resize(1200, 900)
    widget.tac_panel.model.load_files([str(SPC)])
    widget._bridge_compute_to_assign()
    widget.settings_panel._load_tttr_paths([str(SPC)])
    widget.settings_panel.chk_show_lut.setChecked(True)
    widget.show()
    folder = ROOT / "okf/plugins/emtk-references"
    folder.mkdir(parents=True, exist_ok=True)
    for index, name in ((0, "compute"), (1, "settings")):
        widget.dock_area.setCurrentIndex(index)
        for _ in range(10):
            app.processEvents()
        widget.grab().save(str(folder / f"tttr_lut_tools_{name}.png"))
    widget.close()


def capture_native():
    from emtk.pil_painter import PilPainter

    from chisurf.plugins.tttr.tttr_lut_tools.gui.app import LutToolsApp

    app = LutToolsApp()
    app.model.load_compute([SPC])
    app.model.bridge()
    app.model.load_preview([SPC])
    app.model.show_lut = True
    folder = ROOT / "okf/plugins/emtk-native"
    folder.mkdir(parents=True, exist_ok=True)
    for index, name in ((0, "compute"), (1, "settings")):
        app.stage = index
        for _ in range(3):
            painter = PilPainter(1200, 900)
            app.draw(painter, 0, 0, 1200, 900)
        painter.frame.save(folder / f"tttr_lut_tools_{name}.png")
    app.close()


if __name__ == "__main__":
    capture_qt() if "qt" in sys.argv else capture_native()
