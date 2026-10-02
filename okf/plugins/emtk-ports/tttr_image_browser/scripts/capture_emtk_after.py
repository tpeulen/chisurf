"""The emtk app on the same real CLSM files in every state worth a screenshot, at 1200x800 and 800x600. Usage: <out_dir>.

Writes after_populated_<state>_<size>.png, click_*.png (real-input sequences), after.json (the union of the control
inventories of every state, every page and tab of the shared setup editor, the opened lists) and the numbers it printed.
Everything on temporary settings (CHISURF_SETTINGS_DIR, MMFDB_*, HOME); no network.
"""
import json, os, pathlib, shutil, sys, tempfile, time

tmp = pathlib.Path(tempfile.mkdtemp(prefix="ib_after_"))
os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"),
                  MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"), HOME=str(tmp / "home"))
from emtk.pil_painter import PilPainter
from emtk.testing import PixelPainter, RecordingPainter, png_encode

from test.gui.emtk_port_parity import emtk_inventory, qt_free
from chisurf.plugins.tttr.tttr_image_browser.test.conftest import two_detector_setup
from chisurf.plugins.tttr.tttr_image_browser.test.test_emtk_tttr_image_browser_clicks import BrowserDriver
from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app

REPO = pathlib.Path(__file__).resolve().parents[5]
out = pathlib.Path(sys.argv[1])
imgs = tmp / "work" / "imgs"
(imgs / "sub").mkdir(parents=True)
shutil.copy2(REPO / "test/data/clsm/Leica_SP8.ptu", imgs / "Leica_SP8.ptu")
shutil.copy2(REPO / "test/data/clsm/Leica_SP5.ptu", imgs / "sub" / "Leica_SP5.ptu")
(imgs / "corrupt.ptu").write_bytes(b"")
SP8 = str(imgs / "Leica_SP8.ptu")
SIZES = ((1200, 800), (800, 600))

union, interactive, missing = set(), [], set()


def inventory(app, size=(1200, 800)):
    inv = emtk_inventory(app, size)
    union.update(inv["controls"]); interactive.extend(inv["interactive"]); missing.update(inv["controls_without_tooltip"])


def shot(app, name, sizes=SIZES, inv=True):
    for size in sizes:
        app.pointer_move(-1.0, -1.0)
        for _ in range(3):
            p = PilPainter(*size)  # PixelPainter ignores the clip stack for images (gap_plot_image_clip.py)
            app.draw(p, 0, 0, *size)
        (out / f"{name}_{size[0]}x{size[1]}.png").write_bytes(png_encode(p.width, p.height, p.px))
        if inv:
            inventory(app, size)


app = make_app()
drv = BrowserDriver(app, (1200, 800))
drv.draw(3)
shot(app, "after_populated_empty")
# the setup page and every tab of the shared editor
drv.click("tab_setup"); drv.draw(3)
shot(app, "after_populated_setup_page")
for tab in ("Setups", "TTTR reading", "Detectors", "PIE windows", "TAC corrections", "Optical setup"):
    drv.click_text(tab); drv.draw(3)
    inventory(app)
    shot(app, f"after_populated_setup_{tab.replace(' ', '_')}", sizes=((1200, 800),), inv=False)
drv.click_text("TTTR reading"); drv.draw(3)
combo = [t for t in drv.draw(1).texts if t[5] == "auto"]
if combo:
    drv.click_at(combo[0][0] + 10, combo[0][1] + combo[0][3] / 2); drv.draw(3)
    inventory(app)
    shot(app, "after_populated_setup_format_list_open", sizes=((1200, 800),), inv=False)
    drv.escape()
drv.click_text("Setups"); drv.draw(3)
setup_combo = [t for t in drv.draw(1).texts if t[5] == "Unsaved"]
if setup_combo:
    drv.click_at(setup_combo[0][0] + 10, setup_combo[0][1] + setup_combo[0][3] / 2); drv.draw(3)
    inventory(app)
    drv.escape()
# use the two-detector setup: the editor takes it, the browser follows
app.apply_setup_settings(two_detector_setup())
drv.click("tab_browser"); drv.draw(3)

# folder opened by the chooser (real input), nothing selected
app.model.folder = str(imgs.parent)
drv.click("choose_folder"); drv.draw(3)
shot(app, "after_populated_folder_dialog", sizes=((1200, 800),))
drv.click_text("[imgs]"); drv.click_text("Choose", last=True); drv.settle()
shot(app, "after_populated_folder_opened")

# a file picked: the two-tile mosaic
drv.click_text("Leica_SP8.ptu"); drv.settle()
shot(app, "after_populated_mosaic_SP8")
drv.click("current_rating.2"); drv.draw(2)
box = drv.rect("annotation"); drv.click_at(box[0] + 20, box[1] + 15); drv.type_text("good cell, bleached after frame 3"); drv.draw(2)
shot(app, "after_populated_rated_annotated")
drv.click("recursive"); drv.settle()
shot(app, "after_populated_subfolders")
# multiple selection
drv.click("multi_select"); drv.click("select_all_files"); drv.settle()
shot(app, "after_populated_multiselect")
drv.click("multi_select"); drv.settle()
# rating filter and colormap lists open
drv.click("rating_filter"); drv.draw(3)
shot(app, "after_populated_rating_filter_open", sizes=((1200, 800),))
drv.escape()
drv.click("colormap"); drv.draw(3)
shot(app, "after_populated_colormap_open", sizes=((1200, 800),))
drv.click_text("viridis", last=True); drv.draw(3)
shot(app, "after_populated_viridis")
drv.click("colormap"); drv.draw(2); drv.click_text("magma", last=True); drv.draw(2)
# zoomed and panned, manual levels
x, y, w, h = app.item_rects["image"]
for _ in range(6):
    drv.wheel(x + w * 0.3, y + h * 0.4, 1)
drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.4, y + h * 0.45))
shot(app, "after_populated_zoomed")
drv.click("reset_view"); drv.draw(2)
drv.click("auto_levels"); drv.type_into("level_low", "20"); drv.type_into("level_high", "120"); drv.draw(2)
shot(app, "after_populated_manual_levels")
drv.click("auto_levels"); drv.draw(2)
# a file without an image
drv.click_text("corrupt.ptu"); drv.settle()
shot(app, "after_populated_corrupt_file")
# the text filter
drv.click_text("Leica_SP8.ptu"); drv.settle()
f = [t for t in drv.draw(1).texts if t[5] == "filter"][0]
drv.click_at(f[0] + 20, f[1] + f[3] / 2); drv.type_text("sp5"); drv.draw(2)
shot(app, "after_populated_text_filter")
# docx dialog, help, tour card
drv.click("export_docx"); drv.draw(3)
shot(app, "after_populated_docx_dialog", sizes=((1200, 800),))
drv.click_text("Cancel", last=True); drv.draw(2)
drv.click("show_help"); drv.draw(3)
shot(app, "after_populated_help", sizes=((1200, 800),))
drv.click_text("Close"); drv.draw(2)
drv.click("start_guide"); drv.draw(3)
for i in range(3):
    drv.click_text("Next ►", last=True); drv.draw(2)
shot(app, "after_populated_guide_step", sizes=((1200, 800), (800, 600)))
app.tour.stop()
shot(app, "after_populated_narrow_500x500", sizes=((500, 500),), inv=False)
inventory(app)
(out / "after.json").write_text(json.dumps({"size": [1200, 800], "controls": sorted(union), "interactive": interactive,
                                            "controls_without_tooltip": sorted(missing),
                                            "qt_free": qt_free("tttr_image_browser")}, indent=2, ensure_ascii=False))
print(len(union), "controls;", len(missing), "without tooltip", flush=True)
os._exit(0)
