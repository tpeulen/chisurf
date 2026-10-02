"""Screenshots of the emtk PSF app. Usage: capture_emtk.py <out_dir> <prefix> (before_emtk | after). Hermetic."""
import os, pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
tmp = pathlib.Path(tempfile.mkdtemp(prefix="psf_"))
os.environ.update(HOME=str(tmp / "home"), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "p.sqlite"))
(tmp / "home").mkdir()
out = pathlib.Path(sys.argv[1]).resolve(); prefix = sys.argv[2]
from emtk import testing
from emtk.testing import PixelPainter
from chisurf.plugins.calculator.psf_calculator.gui.app import make_app

app = make_app()


def frame(size):
    p = PixelPainter(*size); app.draw(p, 0.0, 0.0, float(size[0]), float(size[1])); return p


end = time.monotonic() + 120
frame((1200, 800))
while (app.model.is_stale or app.busy) and time.monotonic() < end:
    time.sleep(0.05); frame((1200, 800))
for size in ((1200, 800), (800, 600)):
    for _ in range(2): p = frame(size)
    (out / f"{prefix}_populated_{size[0]}x{size[1]}.png").write_bytes(testing.png_encode(p.width, p.height, p.px))
print("ok", app.model.summary_text().replace("\n", " | "))
