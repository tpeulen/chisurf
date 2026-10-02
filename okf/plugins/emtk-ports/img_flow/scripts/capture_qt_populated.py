"""Populated captures of the Qt flow tool: the built-in photon-stream demo (as the guide walks it) and a drifting TIFF with a known speed.
Usage: <out_dir>.

Everything on temporary settings (the demo is simulated into the temporary settings folder: about 20 s). Writes before_populated_*.png,
before_tab_*.png and qt_values.json (every number and message the Qt window showed), qt_flow.csv (what Export CSV wrote).
"""
import json, os, pathlib, sys, tempfile, time

tmp = pathlib.Path(tempfile.mkdtemp())
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m.sqlite")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from qtpy import QtCore, QtWidgets

out = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(out / "scripts"))
from make_data import TIMING, drifting_stack, expected_speed_um_s  # noqa: E402
from chisurf.core.fio.image import imwrite  # noqa: E402
from chisurf.plugins.microscopy.img_flow.gui import tool as tool_mod  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def settle(n=30):
    for _ in range(n):
        app.processEvents()


def wait():
    end = time.monotonic() + 300
    settle()
    while QtCore.QThreadPool.globalInstance().activeThreadCount() and time.monotonic() < end:
        app.processEvents(); time.sleep(0.05)
    settle(60)


w = tool_mod.ImgFlowTool()
w.resize(1200, 800)
w.show()
settle()
m = w.model


def grab(name):
    settle(); w.grab().save(str(out / f"{name}.png"))


def tab(text):
    for bar in w.findChildren(QtWidgets.QTabBar):
        for i in range(bar.count()):
            if bar.tabText(i) == text:
                bar.setCurrentIndex(i); settle(); return True
    return False


def state():
    d = {"status": w.statusBar().currentMessage(), "model_status": m.status, "filename": pathlib.Path(m.filename).name, "channel_names": m.channel_names,
         "method": m.method, "tile": m.tile, "n_lags": m.n_lags, "min_quality": m.min_quality, "summary_html": m.summary_html()}
    r = m.result
    if r is not None:
        s = r.summary(m.min_quality)
        d.update(summary={k: (None if not np.isfinite(v) else float(v)) for k, v in s.items()}, n_escaped=int(r.n_escaped), shape=list(np.asarray(r.vx).shape),
                 vx=np.nan_to_num(np.asarray(r.vx), nan=-999).tolist(), vy=np.nan_to_num(np.asarray(r.vy), nan=-999).tolist(),
                 quality=np.asarray(r.quality).tolist(), x=np.asarray(r.x).tolist(), y=np.asarray(r.y).tolist(), vectors=m.flow_vectors(), n_vectors=len(m.flow_vectors()),
                 extent=list(m.flow_extent()), vector_rows=m.vector_rows(),
                 profile=[{k: (v if k in ("name", "color") else [None if not np.isfinite(a) else float(a) for a in v]) for k, v in s2.items() if k in ("x", "y", "name")} for s2 in m.profile_series()],
                 diagnose=m.diagnose())
    return d


def run(**settings):
    for k, v in settings.items():
        setattr(m, k, v)
    w._refresh(); w.run_with_progress(); wait()


vals = {}
# 1. nothing loaded
w.run_with_progress(); wait(); grab("before_populated_empty_map_pressed"); vals["empty_map"] = state()
w._export_csv(); settle(); vals["empty_export"] = {"status": w.statusBar().currentMessage()}

# 2. the demo, as the guide walks it: Load demo, then Map flow
w.load_demo_with_progress(); wait(); vals["demo_loaded"] = state(); grab("before_populated_demo_loaded")
run(); vals["demo_mapped"] = state(); grab("before_populated_demo_mapped")

# 3. a TIFF flow stack with a known speed (+x, 0.5 px/frame)
tif = tmp / "flow.tif"
imwrite(tif, drifting_stack(0.5))
for k, v in TIMING.items():
    setattr(m, k, v)
m.tile, m.n_lags, m.min_quality = 16, 4, 0.5
m.set_filename(str(tif)); w._refresh(); settle(); vals["tiff_loaded"] = state(); grab("before_populated_tiff_loaded")
run(); vals["tiff_stics"] = state(); grab("before_populated_tiff_stics")
for t in ("Report", "Flow", "Flow field", "Profile and tiles", "Profile", "Tiles"):
    if tab(t):
        grab("before_tab_" + t.replace(" ", "_"))
tab("Profile and tiles"); tab("Profile"); grab("before_tab_Profile_selected")
vals["truth_um_s"] = expected_speed_um_s(0.5)
run(min_quality=0.99); vals["tiff_quality_099"] = state(); grab("before_populated_no_arrows")
run(min_quality=0.5, subtract_average="stack"); vals["tiff_subtract_stack"] = state()
run(subtract_average="frame", n_lags=30); vals["tiff_too_many_lags"] = state(); grab("before_populated_escaped")
run(n_lags=4, method="pcf", distance=4); vals["tiff_pcf"] = state(); grab("before_populated_pcf")
run(method="stics", tile=24, step=24, arrow_scale=2.0); vals["tiff_tile24_step24_scale2"] = state()
m.arrow_scale = 1.0; m.step = 0

# 4. export (dialog stubbed)
run(tile=16, step=0)
target = tmp / "flow_map.csv"
tool_mod.QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), ""))
w._export_csv(); settle()
vals["export"] = {"status": w.statusBar().currentMessage(), "csv": target.read_text()}
(out / "qt_flow.csv").write_text(target.read_text())

# 5. errors: corrupt, two frames, missing
(tmp / "bad.tif").write_bytes(b"not a tiff")
m.set_filename(str(tmp / "bad.tif")); vals["corrupt_loaded"] = state(); run(); vals["corrupt"] = state(); grab("before_populated_corrupt_file")
two = tmp / "two.tif"; imwrite(two, drifting_stack(0.5, n_frames=2))
m.set_filename(str(two)); vals["two_frames_loaded"] = state(); grab("before_populated_two_frames"); run(); vals["two_frames"] = state()
m.set_filename(str(tmp / "missing.tif")); vals["missing_loaded"] = state(); run(); vals["missing"] = state()
(out / "qt_values.json").write_text(json.dumps(vals, indent=1, default=str))
print(json.dumps({k: {x: y for x, y in v.items() if x in ("status", "model_status", "n_vectors", "n_escaped")} for k, v in vals.items() if isinstance(v, dict)}, default=str)[:3500])
