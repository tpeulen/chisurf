"""Populated captures of the Qt FRC tool on a Poisson TIFF stack, a second stack, and the real photon stream. Usage: <out_dir>.

Everything on temporary settings. Writes before_populated_*.png, before_tab_*.png and qt_values.json (every number and message the Qt window
showed: curves, resolutions, table rows, the exported CSV).
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
from make_data import noisy_stack  # noqa: E402
from chisurf.core.fio.image import imwrite  # noqa: E402
from chisurf.plugins.microscopy.img_frc.gui import tool as tool_mod  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[5]
HT3 = REPO / "test/data/clsm/PQ_Olympus_MFIS.ht3"
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def settle(n=30):
    for _ in range(n):
        app.processEvents()


def wait():
    end = time.monotonic() + 120
    settle()
    while QtCore.QThreadPool.globalInstance().activeThreadCount() and time.monotonic() < end:
        app.processEvents(); time.sleep(0.02)
    settle(60)


w = tool_mod.ImgFrcTool()
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


def measure():
    w.run_with_progress(); wait()


def state():
    d = {"status": w.statusBar().currentMessage(), "model_status": m.status, "channel_names": m.channel_names, "channel": m.channel,
         "split": m.split, "criterion": m.criterion, "pixel_size_nm": m.pixel_size_nm, "summary": m.summary_html()}
    r = m.result
    if r is not None:
        d.update(resolution=None if not np.isfinite(r.resolution) else float(r.resolution), crossing=None if not np.isfinite(r.crossing) else float(r.crossing),
                 crossed=bool(r.crossed), unit=r.unit, criterion_used=r.criterion, kind=r.kind, n_frames=r.n_frames, source=pathlib.Path(r.source).name,
                 frequency=[float(v) for v in r.frequency], correlation=[float(v) for v in np.nan_to_num(r.correlation)],
                 threshold=[float(v) for v in r.threshold], counts=[int(v) for v in r.counts],
                 ring_rows=m.ring_rows(), series_names=[s["name"] for s in m.frc_series()],
                 half_1_sum=float(np.asarray(m.half_1_image()).sum()), half_2_sum=float(np.asarray(m.half_2_image()).sum()),
                 half_shape=list(np.asarray(m.half_1_image()).shape))
    return d


vals = {}
# 1. nothing loaded
measure(); grab("before_populated_empty_measure_pressed"); vals["empty_measure"] = state()
w._export_csv(); settle(); vals["empty_export"] = {"status": w.statusBar().currentMessage()}

# 2. a Poisson stack, even / odd frames
a, b = tmp / "a.tif", tmp / "b.tif"
imwrite(a, noisy_stack(seed=0)); imwrite(b, noisy_stack(seed=1))
m.set_filename(str(a)); w._refresh(); settle(); vals["tiff_loaded"] = state(); grab("before_populated_tiff_loaded")
measure(); vals["tiff_even_odd"] = state(); grab("before_populated_tiff_even_odd")
for t in ("FRC", "Diagnostics", "Halves", "Rings", "Half 1", "Half 2"):
    if tab(t):
        grab("before_tab_" + t.replace(" ", "_"))
tab("FRC")

# 3. other splits, criteria and calibration
m.pixel_size_nm = 25.0; measure(); vals["tiff_25nm"] = state(); grab("before_populated_tiff_25nm")
for crit in ("half_bit", "two_sigma"):
    m.criterion = crit; measure(); vals["criterion_" + crit] = state()
m.criterion = "fixed_1/7"; m.split = "halves"; measure(); vals["tiff_halves"] = state()
m.split = "two_files"; m.second_filename = ""; measure(); vals["two_files_without_second"] = state(); grab("before_populated_two_files_without_second")
m.set_second_filename(str(b)); measure(); vals["two_files"] = state(); grab("before_populated_two_files")
m.split = "channels"; measure(); vals["channels_on_one_channel_tiff"] = state()
m.split = "even_odd"; m.bin_width = 0.02; m.smooth = 5; measure(); vals["tiff_binwidth_smooth"] = state()
m.bin_width = 0.0; m.smooth = 3
m.axis_order = "channels"; m.set_filename(str(a)); measure(); vals["tiff_axis_channels"] = state(); grab("before_populated_axis_channels")
m.axis_order = "frames"; m.set_filename(str(a)); m.split = "channels"; m.channel_2 = "ch1"; measure(); vals["tiff_axis_frames_channel_split"] = state()
m.axis_order = "auto"; m.split = "even_odd"; m.second_filename = ""; m.channel_2 = ""; m.set_filename(str(a))

# 4. exports
target = tmp / "frc.csv"
tool_mod.QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), ""))
measure(); w._export_csv(); settle()
vals["export"] = {"status": w.statusBar().currentMessage(), "csv": target.read_text()}
(out / "qt_frc.csv").write_text(target.read_text())

# 5. the real photon stream: even / odd frames and a two-channel split
m.set_filename(str(HT3)); measure(); vals["photon_even_odd"] = state(); grab("before_populated_photon_even_odd")
m.split = "channels"; m.channel = "ch0"; m.channel_2 = "ch1"; measure(); vals["photon_channels"] = state(); grab("before_populated_photon_channels")

# 6. errors
(tmp / "bad.tif").write_bytes(b"not a tiff")
m.split = "even_odd"; m.channel = 0; m.set_filename(str(tmp / "bad.tif")); measure(); vals["corrupt"] = state(); grab("before_populated_corrupt_file")
one = tmp / "one.tif"; imwrite(one, np.ones((32, 32), dtype=np.float32))
m.set_filename(str(one)); measure(); vals["one_frame"] = state(); grab("before_populated_one_frame")
m.set_filename(str(tmp / "missing.tif")); measure(); vals["missing"] = state()
(out / "qt_values.json").write_text(json.dumps(vals, indent=1, default=str))
print(json.dumps({k: {x: y for x, y in v.items() if x in ("status", "model_status", "resolution", "unit", "crossed")} for k, v in vals.items()}, default=str)[:3500])
