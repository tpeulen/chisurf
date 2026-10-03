"""Populated emtk captures of the ALEX Creator: python capture_emtk.py <outdir> <prefix> (temp HOME/settings)."""
import os, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, os.getcwd())
import test.gui  # the repo's test package, not the stdlib one
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
tmp = Path(tempfile.mkdtemp(prefix="alexemtk_"))
os.environ.update(HOME=str(tmp), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"),
                  MMFDB_DATABASE_PATH=str(tmp / "m.sqlite"))
sys.path.insert(0, os.getcwd())
import tttrlib
from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.tttr.ptu_alex_creator.gui.app import AlexApp
out, prefix = Path(sys.argv[1]), sys.argv[2]
src = tmp / "source.ptu"
tttrlib.TTTR("test/data/clsm/Leica_SP5.ptu")[:5000].write(str(src))
second = tmp / "second.ptu"; second.write_bytes(src.read_bytes())
app = AlexApp(tmp / "prefs.json")
d = Driver(app)
app.model.alex_period = 4000; app.model.period_shift = 23
app.load(src)
t = time.monotonic()
while app.job.running and time.monotonic() - t < 30: time.sleep(0.01); d.draw(1)
app.add_paths([src, second]); app.model.batch_output_folder = str(tmp / "out")
for size in ((1200, 800), (800, 600)):
    d.resize(size); d.screenshot(out / f"{prefix}_{size[0]}x{size[1]}.png")
app.close()
