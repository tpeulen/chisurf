"""Capture the emtk plot settings app in populated states against TEMPORARY settings.

Usage: CHISURF_SETTINGS_DIR=<tmp> MMFDB_SETTINGS_DIR=<tmp> MMFDB_DATABASE_PATH=<tmp>/m.db
python capture_emtk_populated.py <out_dir>  (QT_QPA_PLATFORM=offscreen, PYTHONPATH with the repo and emtk).
The temporary folder must hold a copy of settings_chisurf.yaml (Save rewrites it).
"""
import pathlib
import sys

from emtk.testing import RecordingPainter

from test.gui.emtk_port_parity import build_emtk_app, emtk_screenshot

out = pathlib.Path(sys.argv[1])
SECTIONS = ("Rendering Backend", "Colors", "Appearance", "Node Graphs (Global View)",
            "Advanced: pyqtgraph Configuration")
app = build_emtk_app("plot_settings")


def shot(name, size):
    emtk_screenshot(app, out / name, size)
    print("wrote", name)


def click(name, size=(1200, 800)):
    def frames(n=2):
        for _ in range(n):
            app.draw(RecordingPainter(), 0, 0, *size)
    frames(3)
    r = app.form.rects[name]
    x, y = r[0] + r[2] / 2, r[1] + r[3] / 2
    app.hover(x, y); frames(1)
    app.press(x, y); frames(1)
    app.release(); frames(2)


shot("after_populated_default_1200x800.png", (1200, 800))
for t in SECTIONS:
    app.form.folds[t] = True
shot("after_populated_all_expanded_1200x800.png", (1200, 800))
shot("after_populated_all_expanded_800x600.png", (800, 600))
# the window is shorter than the five open sections: the form scrolls; a tall window shows them all
shot("after_populated_all_expanded_tall_1200x1500.png", (1200, 1500))
# a colour changed (what a pick commits), a wider line, legend on: the preview follows
app.model.color_data = "#22cc44"
app.model.color_model = "#00d5ff"
app.model.set_value("line_width", 4.0)
app.model.show_legend = True
app.model.label_axis = True
shot("after_populated_colour_changed_1200x800.png", (1200, 800))
shot("after_populated_colour_changed_800x600.png", (800, 600))
shot("after_populated_colour_changed_narrow_420x700.png", (420, 700))
# a light preview background
app.model.pg_background = "w"
shot("after_populated_light_preview_1200x800.png", (1200, 800))
app.model.pg_background = "k"
click("apply")
shot("after_populated_applied_1200x800.png", (1200, 800))
app.model.color_irf = "#ffcc00"
shot("after_populated_edit_after_apply_1200x800.png", (1200, 800))
click("save")
shot("after_populated_saved_1200x800.png", (1200, 800))
app.model.color_data = "#ff0000"
click("reset")
shot("after_populated_reset_1200x800.png", (1200, 800))
# the colour picker under a field
for t in SECTIONS:
    app.form.folds[t] = t in ("Rendering Backend", "Colors")
click("color_model.swatch")
shot("after_populated_picker_open_1200x800.png", (1200, 800))
