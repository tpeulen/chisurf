"""Layout fixes with a measurable before: the file list at 800x600 with fixed column widths (before) and fitted columns (after).
Usage: <out_dir>. Real files (the SP8 file and the SP5 file in a subfolder), temporary settings."""
import copy, os, pathlib, shutil, sys, tempfile
tmp = pathlib.Path(tempfile.mkdtemp(prefix="ib_lay_"))
os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"), HOME=str(tmp / "home"))
from emtk.pil_painter import PilPainter
from emtk.testing import png_encode
from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app
REPO = pathlib.Path(__file__).resolve().parents[5]; out = pathlib.Path(sys.argv[1])
imgs = tmp / "imgs"; (imgs / "sub").mkdir(parents=True)
shutil.copy2(REPO / "test/data/clsm/Leica_SP8.ptu", imgs / "Leica_SP8.ptu"); shutil.copy2(REPO / "test/data/clsm/Leica_SP5.ptu", imgs / "sub" / "Leica_SP5.ptu")
(imgs / "corrupt.ptu").write_bytes(b"")
def shoot(app, name):
    app.model.recursive = True; app.model.open_folder(str(imgs))
    for _ in range(4):
        p = PilPainter(800, 600); app.draw(p, 0, 0, 800, 600)
    (out / name).write_bytes(png_encode(p.width, p.height, p.px))
after = make_app(); shoot(after, "after_file_columns_800x600.png")
before = make_app()
table = [s for s in before.panels["files"]["sections"] if s.get("key") == "data_table"][0]
table["options"]["fit_columns"] = False
for column, width in zip(table["options"]["columns"], (150, 78, 60)):
    column["width"] = width
shoot(before, "before_file_columns_800x600.png")

# the rating-filter list: labels equal to the Qt strings ("\u2265 1\u2605": the star is drawn over the digit) against labels with a gap
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
def list_open(app, name):
    drv = Driver(app, (1200, 800)); drv.draw(4)
    drv.click("rating_filter"); drv.draw(3)
    app.pointer_move(-1.0, -1.0)
    for _ in range(3):
        p = PilPainter(1200, 800); app.draw(p, 0, 0, 1200, 800)
    (out / name).write_bytes(png_encode(p.width, p.height, p.px))
app = make_app()
choice = [x for x in app.panels["files"]["sections"] if x.get("attr") == "rating_filter"]
choice = choice[0] if choice else [y for g in app.panels["files"]["sections"] for y in g.get("sections", []) if y.get("attr") == "rating_filter"][0]
choice["labels"] = list(choice["options"])
list_open(app, "before_rating_filter_labels_1200x800.png")
list_open(make_app(), "after_rating_filter_labels_1200x800.png")
os._exit(0)
