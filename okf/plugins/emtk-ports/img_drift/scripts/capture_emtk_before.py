"""The stream's thin emtk app (pre-upgrade/app.py.txt) on the drifting TIFF, as before_emtk_*.png; also records what its Reference / Boundary
mode choices do (the options it offered are not the core's). Usage: <out_dir>."""
import importlib.util, json, pathlib, sys, tempfile
from emtk.testing import PixelPainter, png_encode
out = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(out / "scripts"))
from make_data import drifting_stack
from chisurf.core.fio.image import imwrite
src = (out / "pre-upgrade" / "app.py.txt").read_text()
tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "old_drift_app.py").write_text(src.replace("from .gui.view_model", "from chisurf.plugins.microscopy.img_drift.gui.view_model").replace(
    "from .strings import install_translations, tr", "install_translations = lambda: None\ntr = lambda s: s"))
spec = importlib.util.spec_from_file_location("old_drift_app", tmp / "old_drift_app.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
tif = tmp / "drift.tif"; imwrite(tif, drifting_stack())
app = mod.make_app()
def shot(name, size):
    for _ in range(3):
        p = PixelPainter(*size); app.draw(p, 0, 0, *size)
    (out / name).write_bytes(png_encode(p.width, p.height, p.px))
shot("before_emtk_empty_1200x800.png", (1200, 800))
m = app.model
m.set_filename(str(tif)); m.compute()
shot("before_emtk_populated_1200x800.png", (1200, 800)); shot("before_emtk_populated_800x600.png", (800, 600))
found = {}
for attr, offered in (("reference", ["first", "mean", "middle"]), ("mode", ["wrap", "nearest", "reflect"])):
    for value in offered:
        m.reference, m.mode = "first", "wrap"
        setattr(m, attr, value)
        ok = m.compute()
        found[f"{attr}={value}"] = {"ok": ok, "status": m.status[:120]}
(out / "before_emtk_choices.json").write_text(json.dumps(found, indent=1))
print(json.dumps(found, indent=1))
