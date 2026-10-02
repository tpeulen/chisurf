"""Capture the one-page emtk editor (Setup: Channel Definition) in the states the report discusses, then compose the
Qt-versus-emtk side-by-side images.

Usage: python capture_emtk.py <out_dir>   (repository root, QT_QPA_PLATFORM=offscreen, PYTHONPATH with the repository
and emtk; run capture_qt.py first for the side-by-sides). Settings, setups file and MMFDB are temporary.

Writes emtk_{1200x800,800x600,720x700,520x760,360x760}.png (populated: BH SPC-132 read, LUT box open, PIE Windows
folded, as the Qt capture), the windows of the page (plot, PIE open, LUT tools, shift adjuster, optical setup, help,
the Save prompt, a cell being typed into) and side_by_side_<size>.png (Qt left, emtk right).
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

out = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp(prefix="ce_emtk_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m" / "db.sqlite")
(tmp / "s").mkdir()
(tmp / "m").mkdir()
work = tmp / "work"
work.mkdir()
sample = work / "BH_SPC132.spc"
shutil.copy("test/data/tttr/BH/132/BH_SPC132.spc", sample)

from PIL import Image  # noqa: E402

from test.gui.emtk_port_parity import emtk_screenshot  # noqa: E402  (before anything shadows `test`)

from chisurf.plugins.core.setup_channel_definition.gui.app import make_app  # noqa: E402
from chisurf.plugins.core.setup_channel_definition.test import driver  # noqa: E402
from chisurf.plugins.tttr.tttr_count_rate_analysis.tests.pointer import Pointer  # noqa: E402

app = make_app(file_path=str(tmp / "setups.json"))
page = app.page
SIZES = [(1200, 800), (800, 600), (720, 700), (520, 760), (360, 760)]


def shot(name, size=(1200, 800)):
    app.pointer_move(-20.0, -20.0)  # no hover tooltip in the picture
    driver.settle(app, size, 3)
    path = out / f"{name}.png"
    emtk_screenshot(app, path, size)
    print("wrote", path.name)


driver.settle(app)
driver.populate(app, sample)
for size in SIZES:
    shot(f"emtk_{size[0]}x{size[1]}", size)

# the windows and states of the page
ui = Pointer(app, (1200.0, 800.0))
page.open_sections["windows"] = True
shot("emtk_pie_open_1200x800")
page.open_sections["windows"] = False
page.preview_window.show()
shot("emtk_plot_1200x800")
page.preview_window.hide()
page.lut_window.show()
shot("emtk_lut_tools_1200x800")
page.lut_window.hide()
page.open_shift_adjuster()
shot("emtk_shift_adjuster_1200x800")
page.shift_window.hide()
page.optical_window.show()
shot("emtk_optical_setup_1200x800")
page.optical_window.hide()
page.help_window.show()
shot("emtk_help_1200x800")
page.help_window.hide()
app.toolbar.request_save()
shot("emtk_prompt_save_1200x800")
app.toolbar.cancel()
driver.settle(app)
# a cell being typed into: double-click the ranges of "green", type, do not commit yet
from emtk.keys import KEY_BACKSPACE  # noqa: E402

ui = Pointer(app, (1200.0, 800.0))
control = page._detector_table.control
index = next(i for i, r in enumerate(control.records) if r["id"] == "green")
bx, by, bw, bh = control._body_box
x = control._header_box[0]
for column, width in zip(control._shown, control._widths):
    if column.key == "ranges":
        point = (x + width / 2, by + (control.order().index(index) - control.bar.top + 0.5) * control._row_h)
    x += width
ui.double_click(point)
for _ in range(12):
    ui.key(KEY_BACKSPACE)
ui.type("20:10")
shot("emtk_cell_editing_1200x800")
ui.enter()
shot("emtk_cell_committed_1200x800")

# the prompts of the Setup row, at both sizes (a dialog keeps the position it was first drawn at: smaller first)
page.model.data["detectors"]["green"]["micro_time_ranges"] = [[0, 4095]]
page.reset_views()
app.toolbar.save("Lab setup A")
app.toolbar.save("Lab setup B")
app.toolbar.select("Lab setup B")
for kind, start in (("save", app.toolbar.request_save), ("rename", app.toolbar.request_rename), ("delete", app.toolbar.request_delete)):
    start()
    for size in ((800, 600), (1200, 800)):
        shot(f"emtk_prompt_{kind}_{size[0]}x{size[1]}", size)
    app.toolbar.cancel()
    driver.settle(app)
app.toolbar.request_rename()
app.toolbar.name_text = "Lab setup A"
app.toolbar.confirm()
shot("emtk_prompt_overwrite_1200x800")
app.toolbar.cancel()
app.toolbar.select("")
app.toolbar.request_rename()  # nothing selected: the status line says so
shot("emtk_no_selection_1200x800")

# side by side: Qt left, emtk right
for size in ("1200x800", "800x600", "720x700"):
    qt_path, mine = out / f"qt_{size}.png", out / f"emtk_{size}.png"
    if not qt_path.exists():
        continue
    left, right = Image.open(qt_path).convert("RGB"), Image.open(mine).convert("RGB")
    height = max(left.height, right.height)
    both = Image.new("RGB", (left.width + right.width + 8, height), (255, 0, 255))
    both.paste(left, (0, 0))
    both.paste(right, (left.width + 8, 0))
    both.save(out / f"side_by_side_{size}.png")
    print("wrote", f"side_by_side_{size}.png")
