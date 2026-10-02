"""Captures of the emtk PSF app, states reached with real pointer and key input. Usage: capture_after.py <out_dir> <prefix>. Hermetic."""
import os, pathlib, sys, tempfile, threading
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
tmp = pathlib.Path(tempfile.mkdtemp(prefix="psf_"))
os.environ.update(HOME=str(tmp / "home"), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "p.sqlite"))
out = pathlib.Path(sys.argv[1]).resolve(); prefix = sys.argv[2]
(tmp / "home").mkdir(); os.chdir(tmp)
from emtk import testing
from emtk.testing import PixelPainter
from chisurf.plugins.calculator.psf_calculator.core import PSFModel
from chisurf.plugins.calculator.psf_calculator.gui.app import make_app
from chisurf.plugins.calculator.psf_calculator.tests.driving import PSFDriver
from chisurf.plugins.calculator.psf_calculator.tests import test_emtk_psf_clicks as T

SIZES = ((1200, 800), (800, 600))
app = make_app(); drv = PSFDriver(app, SIZES[0])


def shot(name, sizes=SIZES):
    for size in sizes:
        drv.size = size
        for _ in range(3):
            p = PixelPainter(*size); app.draw(p, 0.0, 0.0, float(size[0]), float(size[1]))
        (out / f"{prefix}_{name}_{size[0]}x{size[1]}.png").write_bytes(testing.png_encode(p.width, p.height, p.px))
    drv.size = SIZES[0]


app.model.nxy, app.model.nz = 48, 21
drv.settle(); shot("populated")                         # the Qt defaults: vectorial, circular, NA 1.4, preview
T.pick(drv, "model", "Airy (scalar, 2-D)"); drv.settle(); shot("airy_polarization_greyed", SIZES[:1])
T.pick(drv, "model", "Vectorial (Richards-Wolf)"); T.pick(drv, "polarization", "Linear at angle"); drv.type_into("angle_deg", "45"); drv.settle(); shot("linear_45", SIZES[:1])
T.pick(drv, "slice_plane", "XZ"); shot("slice_xz")
T.pick(drv, "quality", "Full"); drv.settle(); shot("full_quality", SIZES[:1])
T.pick(drv, "colormap", "viridis"); drv.type_into("threshold", "0.1"); shot("display_viridis", SIZES[:1])
drv.click("export_npy"); shot("export_dialog", SIZES[:1])
name = "psf_vectorial_NA1.4_n1.518_520nm_linear.npy"; drv.click_text(name); drv.select_all(); drv.type_text("my_psf"); drv.click_text("Save", last=True); shot("exported", SIZES[:1])
gate = threading.Event(); real = PSFModel.compute
PSFModel.compute = lambda self: (gate.wait(30), real(self))[1]
drv.type_into("na", "1.2")
for _ in range(80):
    if app.busy: break
    drv.draw(1)
shot("computing", SIZES[:1]); gate.set(); PSFModel.compute = real; drv.settle()
def boom(self): raise RuntimeError("no optics today")
PSFModel.compute = boom; drv.type_into("na", "1.3"); drv.settle(); shot("error", SIZES[:1]); PSFModel.compute = real; drv.type_into("na", "1.4"); drv.settle()
drv.click("guide"); drv.click_text("Next ►"); shot("guide_na_step", SIZES[:1]); drv.escape()
drv.click("help"); shot("help", SIZES[:1]); drv.escape()
app.close(); print("ok")
