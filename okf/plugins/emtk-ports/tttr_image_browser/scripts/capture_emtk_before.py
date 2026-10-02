"""The stream's emtk app (the committed state, pre-upgrade/) on the same real files, as before_emtk_*.png. Usage: <out_dir>.

Everything on temporary settings. Pages: Detector setup (the page it opens on), Image browser empty, Image browser with
the folder open and Leica_SP8.ptu selected.
"""
import os, pathlib, shutil, sys, tempfile, time

tmp = pathlib.Path(tempfile.mkdtemp(prefix="ib_old_"))
os.environ.update(CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"),
                  MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"), HOME=str(tmp / "home"))
from emtk.testing import PixelPainter, png_encode

REPO = pathlib.Path(__file__).resolve().parents[5]
out = pathlib.Path(sys.argv[1])
imgs = tmp / "imgs"
(imgs / "sub").mkdir(parents=True)
shutil.copy(REPO / "test/data/clsm/Leica_SP8.ptu", imgs / "Leica_SP8.ptu")
shutil.copy(REPO / "test/data/clsm/Leica_SP5.ptu", imgs / "sub" / "Leica_SP5.ptu")
(imgs / "corrupt.ptu").write_bytes(b"")

from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app
app = make_app()


def shot(name, size, frames=3):
    for _ in range(frames):
        p = PixelPainter(*size)
        app.draw(p, 0, 0, *size)
    (out / name).write_bytes(png_encode(p.width, p.height, p.px))


def settle():
    end = time.monotonic() + 120
    while app.job.busy and time.monotonic() < end:
        time.sleep(0.05)
        app.draw(PixelPainter(600, 400), 0, 0, 600, 400)


shot("before_emtk_setup_page_1200x800.png", (1200, 800))
shot("before_emtk_setup_page_800x600.png", (800, 600))
app.open_folder(str(imgs))
settle()
shot("before_emtk_browser_folder_1200x800.png", (1200, 800))
app.select(str(imgs / "Leica_SP8.ptu"))
settle()
shot("before_emtk_browser_mosaic_1200x800.png", (1200, 800))
shot("before_emtk_browser_mosaic_800x600.png", (800, 600))
print("ok")
os._exit(0)
