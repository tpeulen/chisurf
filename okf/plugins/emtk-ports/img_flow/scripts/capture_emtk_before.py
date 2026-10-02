"""The stream's thin emtk app (pre-upgrade/app.py.txt) on the drifting TIFF, as before_emtk_*.png. Usage: <out_dir>."""
import importlib.util, pathlib, sys, tempfile
from emtk.testing import PixelPainter, png_encode
out = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(out / "scripts"))
from make_data import TIMING, drifting_stack
from chisurf.core.fio.image import imwrite
src = (out / "pre-upgrade" / "app.py.txt").read_text()
tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "old_flow_app.py").write_text(src.replace("from .gui.view_model", "from chisurf.plugins.microscopy.img_flow.gui.view_model").replace(
    "from .strings import install_translations, tr", "install_translations = lambda: None\ntr = lambda s: s"))
spec = importlib.util.spec_from_file_location("old_flow_app", tmp / "old_flow_app.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
tif = tmp / "flow.tif"; imwrite(tif, drifting_stack(0.5))
app = mod.make_app()
def shot(name, size):
    for _ in range(3):
        p = PixelPainter(*size); app.draw(p, 0, 0, *size)
    (out / name).write_bytes(png_encode(p.width, p.height, p.px))
shot("before_emtk_empty_1200x800.png", (1200, 800))
m = app.model
for k, v in TIMING.items():
    setattr(m, k, v)
m.tile, m.n_lags = 16, 4
m.set_filename(str(tif)); ok = m.compute()
app.message = m.status
shot("before_emtk_populated_1200x800.png", (1200, 800)); shot("before_emtk_populated_800x600.png", (800, 600))
print(ok, m.status)
