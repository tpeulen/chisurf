"""Qt baseline of the PSF calculator (the committed gui/tool.py), driven headlessly.

The Qt tool needs a 3-D volume renderer (`cp.VolumeView`) and the 'emtk' chiplot backend has none: constructing PSFCalculator raises
`NotImplementedError: the 'emtk' backend has no 3-D volume renderer`. So `cp.VolumeView` is replaced by a recording stub that receives exactly what the
Qt tool hands the renderer (the volume, the scale, the colormap, threshold and gamma, the polarization segments); the AutoForm parameter panels,
the toolbar, the export menu and the model run for real. NOT comparable: the rendered 3-D image itself. Usage: capture_qt_populated.py <out_dir>.
Hermetic: temp HOME, settings."""
import hashlib, json, os, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from test.gui import migration_parity as mp  # before anything can import the stdlib `test`
from test.gui.emtk_port_parity import normalize
tmp = pathlib.Path(tempfile.mkdtemp(prefix="psf_"))
os.environ.update(HOME=str(tmp / "home"), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "p.sqlite"), QT_QPA_PLATFORM="offscreen")
(tmp / "home").mkdir()
out = pathlib.Path(sys.argv[1]).resolve()
import numpy as np
from qtpy import QtCore, QtWidgets
import chisurf.gui.chiplot as cp


class StubVolumeView(QtWidgets.QLabel):
    calls = []

    def __init__(self, *a, **k):
        super().__init__("3-D volume view (not rendered here: the 'emtk' chiplot backend has no volume renderer)")
        self.setAlignment(QtCore.Qt.AlignCenter); self.setWordWrap(True)
        self.setStyleSheet("background: #202428; color: #9aa;")

    def set_scale(self, *a): StubVolumeView.calls.append(("scale", [float(x) for x in a]))
    def set_volume(self, volume, colormap=None, threshold=None, gamma=None):
        StubVolumeView.calls.append(("volume", list(np.asarray(volume).shape), hashlib.sha1(np.ascontiguousarray(volume, dtype=np.float32).tobytes()).hexdigest()[:12], colormap, threshold, gamma))
    def set_vectors(self, segments, color=None, width=None):
        StubVolumeView.calls.append(("vectors", None if segments is None else list(np.asarray(segments).shape)))


cp.VolumeView = StubVolumeView
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.calculator.psf_calculator.gui.tool import PSFCalculator
from chisurf.gui.autoform.sections.builtin import ChoiceWidget, ToggleWidget, ValueWidget

spin = lambda n=30: [app.processEvents() for _ in range(n)]


def wait_compute(w):
    for _ in range(600):
        spin(2)
        if not w.model.is_stale and w.model.volume is not None and not w._pool.activeThreadCount():
            break
        QtCore.QThread.msleep(20)
    spin(10)


w = PSFCalculator(); w.resize(1200, 800); w.show(); wait_compute(w); spin()
vals = {"scenarios": {}}


def record(name):
    m = w.model
    vals["scenarios"][name] = {
        "params": {k: getattr(m, k) for k in ("na", "n_immersion", "wavelength_nm", "model", "polarization", "angle_deg", "nxy", "nz", "pixel_size_nm", "z_step_nm", "quality", "threshold", "gamma", "colormap", "show_polarization")},
        "summary": m.summary_text(), "shape": list(m.volume.shape), "sum": float(m.volume.sum()), "max": float(m.volume.max()),
        "viewer_calls": [c for c in StubVolumeView.calls[-3:]]}
    w.grab().save(str(out / f"before_populated_{name}.png"))


record("default_vectorial_circular")
inv = mp.control_inventory(w); inv["entrypoint"] = "HEAD gui/tool.py (volume view stubbed)"; inv["size"] = [1200, 800]
inv["controls"] = sorted({normalize(c) for c in inv["controls"]} - {""})
(out / "before.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False)); w.grab().save(str(out / "before.png"))
editors = {vw._section.attr: vw.editor for vw in w.auto_form.findChildren(ValueWidget) if getattr(vw, "_section", None)}
combos = {cw._section.attr: cw for cw in w.auto_form.findChildren(ChoiceWidget) if getattr(cw, "_section", None)}
toggles = {tw._section.attr: tw.checkbox for tw in w.auto_form.findChildren(ToggleWidget) if getattr(tw, "_section", None)}
vals["controls"] = {"values": sorted(editors), "choices": sorted(combos), "toggles": sorted(toggles),
                    "choice_labels": {k: [v.combo.itemText(i) for i in range(v.combo.count())] if v.combo is not None else [b.text() for b in getattr(v, "_radios", [])] for k, v in combos.items()}}
w.model.model = "airy"; w.model.polarization = "linear"; w.model.angle_deg = 45.0; w.auto_form.sync_fields(); w.recompute(); wait_compute(w); record("airy_linear_45")
w.model.model = "gaussian"; w.auto_form.sync_fields(); w.recompute(); wait_compute(w); record("gaussian")
w.model.model = "vectorial"; w.model.polarization = "radial"; w.model.quality = "preview"; w.auto_form.sync_fields(); w.recompute(); wait_compute(w); record("vectorial_radial")
w.model.show_polarization = False; w.model.colormap = "viridis"; w.model.threshold = 0.1; w.model.gamma = 1.0; w.auto_form.sync_fields(); w.recompute(); wait_compute(w); record("display_viridis_no_vectors")
w.resize(800, 600); spin(); w.grab().save(str(out / "before_populated_800x600.png")); w.resize(1200, 800); spin()
# export through the menu path with the file dialog answered by the script
from chisurf.gui.widgets import general
written = {}
import chisurf.gui.widgets.general as G
for suffix, filt in ((".npy", "NumPy array (*.npy)"), (".tif", "TIFF stack (*.tif *.tiff)")):
    target = tmp / f"psf_export{suffix}"
    G.save_file = lambda description="", file_type="", _t=target: str(_t)
    w.export_volume(suffix, filt)
    written[suffix] = {"exists": target.exists(), "bytes": target.stat().st_size if target.exists() else 0}
vals["export"] = written
if (tmp / "psf_export.npy").exists():
    vals["export"]["npy_equals_volume"] = bool(np.array_equal(np.load(tmp / "psf_export.npy"), w.model.volume))
vals["toolbar"] = [a.text() for a in w.findChildren(QtWidgets.QToolBar)[0].actions() if a.text()]
(out / "qt_values.json").write_text(json.dumps(vals, indent=1, default=str))
w.close()
print("ok", len(vals["scenarios"]))
