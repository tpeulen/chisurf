"""Populated captures of the Qt particle-tracking tool on its own simulated movie. Usage: <out_dir>.

Everything on temporary settings; the file scenario writes a TIFF of the simulated movie into a temp folder.
Writes before_populated_*.png, before_tab_*.png and qt_values.json (what the Qt window computed and showed).
"""
import json, os, pathlib, sys, tempfile, time

tmp = pathlib.Path(tempfile.mkdtemp())
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m.sqlite")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from qtpy import QtWidgets, QtCore

from chisurf.core.fluorescence.imaging import tracking as tk
from chisurf.plugins.microscopy.img_tracking.gui import tool as tool_mod

out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def settle(n=30):
    for _ in range(n):
        app.processEvents()


w = tool_mod.ImgTrackingTool()
w.resize(1200, 800)
w.show()
settle()


def grab(name):
    settle()
    w.grab().save(str(out / f"{name}.png"))


def tab(text):
    for bar in w.findChildren(QtWidgets.QTabBar):
        for i in range(bar.count()):
            if bar.tabText(i) == text:
                bar.setCurrentIndex(i)
                settle()
                return True
    return False


def run_and_wait():
    w.run_with_progress()
    end = time.monotonic() + 120
    while QtCore.QThreadPool.globalInstance().activeThreadCount() and time.monotonic() < end:
        app.processEvents(); time.sleep(0.02)
    settle(60)


def state():
    m = w.model
    r = m.result
    d = {"status": w.statusBar().currentMessage(), "results_text": m.results_text, "can_run": m.can_run()}
    if r is not None:
        d.update(n_detections=len(r.detections), n_tracks=len(r.tracks),
                 detections_per_frame=float(r.detections_per_frame), track_lengths=[int(v) for v in r.track_lengths()],
                 tracks_table=r.tracks_table()[:12], n_markers=len(m.detection_markers()),
                 n_track_series=len(m.track_series()), msd_series_names=[s["name"] for s in m.msd_series()],
                 length_series_len=len(m.length_series()), track_rows_head=m.track_rows()[:5])
        if r.fit is not None:
            f = r.fit
            d["fit"] = dict(D=float(f.diffusion_coefficient), D_err=float(f.diffusion_coefficient_error),
                            alpha=float(f.alpha), loc=float(f.localisation_error),
                            lags=[float(v) for v in f.lags], msd=[float(v) for v in f.msd])
    return d


vals = {}
# 1. empty: Track with nothing loaded (the status bar says why)
w.run_with_progress(); grab("before_populated_empty_track_pressed"); vals["empty_track"] = state()

# 2. the Simulate panel opened, a deliberately small simulation
for hdr in w.findChildren(QtWidgets.QWidget):
    pass
m = w.model
m.use_simulation = True; m.sim_n_frames = 40; m.sim_size = 160; m.sim_n_particles = 6
m.sim_diffusion = 0.5; m.sim_seed = 1; m.max_distance = 4.0; m.n_bootstrap = 50
w._refresh()
for btn in w.findChildren(QtWidgets.QPushButton):
    if "Simulate instead" in btn.text():
        btn.click(); settle()
grab("before_populated_simulate_panel")
run_and_wait()
vals["simulated"] = state()
grab("before_populated_simulated")
for name in ("Report", "Movie", "Trajectories", "MSD", "Track lengths", "Tracks"):
    if tab(name):
        grab(f"before_tab_{name.replace(' ', '_')}")
# the movie slider scrubbed to the middle
tab("Movie")
for s in w.findChildren(QtWidgets.QSlider):
    if s.maximum() > 5:
        s.setValue(s.maximum() // 2); settle()
        vals["movie_slider_max"] = s.maximum(); break
grab("before_tab_Movie_frame_mid")

# 3. fit alpha on
m.fit_alpha = True; w._refresh(); run_and_wait(); vals["fit_alpha"] = state(); tab("Report"); grab("before_populated_fit_alpha")
m.fit_alpha = False

# 4. a file: the same movie as a TIFF; a missing file; a corrupt file
import tifffile
frames, _ = tk.simulate_particle_movie(n_frames=40, shape=(160, 160), n_particles=6, diffusion_coefficient=0.5,
                                       sigma_psf=1.5, amplitude=250.0, background=10.0, seed=1)
tif = tmp / "movie.tif"; tifffile.imwrite(str(tif), frames.astype(np.float32))
m.use_simulation = False
m.set_filename(str(tif)); w._refresh(); grab("before_populated_file_loaded")
vals["file_loaded"] = state()
run_and_wait(); vals["file_tracked"] = state(); tab("Report"); grab("before_populated_file_tracked")
m.set_filename(str(tmp / "missing.tif")); m.filename = str(tmp / "missing.tif"); w._refresh()
w.run_with_progress(); grab("before_populated_missing_file"); vals["missing_file"] = state()
(tmp / "bad.tif").write_bytes(b"not a tiff")
m.set_filename(str(tmp / "bad.tif")); run_and_wait(); tab("Report"); grab("before_populated_corrupt_file"); vals["corrupt_file"] = state()

# 5. Export CSV (dialog stubbed) from the file run
m.set_filename(str(tif)); run_and_wait()
target = tmp / "tracks.csv"
tool_mod.QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), ""))
w._export_csv(); settle()
vals["export"] = {"status": w.statusBar().currentMessage(), "csv_head": target.read_text().splitlines()[:4] if target.exists() else None,
                  "default_name_hint": str(pathlib.Path(str(tif)).with_suffix(".tracks.csv").name)}
if target.exists():
    (out / "qt_exported.csv").write_text(target.read_text())
(out / "qt_values.json").write_text(json.dumps(vals, indent=1, default=str))
print(json.dumps({k: {a: b for a, b in v.items() if a in ("status", "n_tracks", "n_detections", "fit")} if isinstance(v, dict) else v for k, v in vals.items()}, default=str)[:3000])
