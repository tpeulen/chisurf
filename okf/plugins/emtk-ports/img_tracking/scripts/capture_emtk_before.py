"""The stream's thin emtk app (pre-upgrade/app.py.txt) in its empty and simulated states, as before_emtk_*.png. Usage: <out_dir>.

The old module is loaded from the committed copy; it needs the plugin's view model only.
"""
import importlib.util, pathlib, sys, tempfile
import numpy as np
from emtk.testing import PixelPainter, png_encode
out = pathlib.Path(sys.argv[1])
src = (out / "pre-upgrade" / "app.py.txt").read_text()
tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "old_tracking_app.py").write_text(src.replace("from .gui.view_model", "from chisurf.plugins.microscopy.img_tracking.gui.view_model").replace(
    "from .strings import install_translations, tr", "install_translations = lambda: None\ntr = lambda s: s"))
spec = importlib.util.spec_from_file_location("old_tracking_app", tmp / "old_tracking_app.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
app = mod.make_app()
def shot(name, size):
    for _ in range(3):
        p = PixelPainter(*size); app.draw(p, 0, 0, *size)
    (out / name).write_bytes(png_encode(p.width, p.height, p.px))
shot("before_emtk_empty_1200x800.png", (1200, 800))
m = app.model
m.use_simulation = True; m.sim_n_frames = 40; m.sim_size = 160; m.sim_n_particles = 6; m.sim_diffusion = 0.5; m.sim_seed = 1
m.max_distance = 4.0; m.n_bootstrap = 50
m.compute()
shot("before_emtk_populated_1200x800.png", (1200, 800))
shot("before_emtk_populated_800x600.png", (800, 600))
