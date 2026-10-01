"""Capture the legacy Qt plot settings tool in populated states (TEMPORARY settings).

Usage: CHISURF_SETTINGS_DIR=<tmp> MMFDB_SETTINGS_DIR=<tmp> MMFDB_DATABASE_PATH=<tmp>/m.db
python capture_qt_populated.py <out_dir>   (QT_QPA_PLATFORM=offscreen, PYTHONPATH with the repo and emtk)
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])
from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.core.plot_settings.gui.tool import PlotSettingsWidget  # noqa: E402
from chisurf.gui.widgets.collapsible_box import CollapsibleBox  # noqa: E402

w = PlotSettingsWidget()
w.resize(1200, 800)
w.show()


def pump(n=30):
    for _ in range(n):
        app.processEvents()


def grab(name, bottom=False):
    pump()
    if bottom:
        sb = w.findChild(QtWidgets.QScrollArea).verticalScrollBar()
        sb.setValue(sb.maximum())
        pump()
    w.grab().save(str(out / name))
    print("wrote", name)


pump()
boxes = w.findChildren(CollapsibleBox)
print([(b.title(), b.is_expanded()) for b in boxes])
grab("before_populated_default.png")
for b in boxes:
    b.set_expanded(True)
pump(60)
grab("before_populated_all_expanded.png")
grab("before_populated_all_expanded_bottom.png", bottom=True)
# a colour changed through the same path as the picker: preview must follow
btn = w._color_buttons["data"]
btn.color = "#22cc44"
btn.color_changed.emit("#22cc44")
w.line_width.setValue(4.0)
w.show_legend.setChecked(True)
grab("before_populated_colour_changed.png", bottom=True)
w._save_settings()
grab("before_populated_saved.png", bottom=True)
w._color_buttons["model"].color = "#00ffff"
w._color_buttons["model"].color_changed.emit("#00ffff")
w._load_settings()
grab("before_populated_reset.png", bottom=True)
