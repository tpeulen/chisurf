"""Populated captures of the IRF & BG calibration on real photons.

usage: capture_populated.py <out_dir> qt|emtk|emtk-states <prefix> [<qt_head dir>]   (run from the repo root)
Source and IRF: the micro-time shifter's demo SPC (two detectors offset by 400 bins); one imaging detector "green"
with channel 0 parallel and channel 8 perpendicular; conv 500-3000, IRF 550-700, background region 0-400.
qt = the committed Qt tool (HEAD gui/tool.py over HEAD gui/view_model.py via qt_head).
"""
import importlib, pathlib, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity  # noqa: E402,F401

out, which, prefix = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
from chisurf.plugins.tttr.tttr_microtime_shifter.tests.demo_data import build

SPC = str(build(pathlib.Path(tempfile.mkdtemp()) / "demo"))
SETUP = {"detectors": {"green": {"chs": [0, 8], "ch_p": [0], "ch_s": [8]}}}


def populate(model):
    model.apply_setup_settings(SETUP)
    model.apply_pipeline_context({"source": SPC})
    model.sel_irf_files = [SPC]
    model.ensure_histograms()
    model.set_conv_range(500, 3000)
    model.set_irf_range(550, 700)
    model.set_bg_range(0, 400)


if which == "qt":
    from qtpy import QtWidgets
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("img_calibration", ("view_model",))
    w = klass()
    populate(w.model)
    w.auto_form.sync_fields(); w.auto_form.refresh_plots()
    w.resize(1200, 800); w.show()
    for _ in range(40):
        qapp.processEvents(); time.sleep(0.02)
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", w.model.sel_bg_vv, w.model.sel_bg_vh, w.model.decay_data()["n"])
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot, manifest_of
    module, attr = manifest_of("img_calibration")["entrypoints"]["emtk"].split(":")
    for size in [(1200, 800), (800, 600)]:
        a = getattr(importlib.import_module(module), attr)()
        populate(a.model)
        for _ in range(4):
            a.draw(RecordingPainter(), 0, 0, *size)
        if which == "emtk-states" and hasattr(a, "tour"):
            a.tour.start(1)
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", a.model.sel_bg_vv, a.model.sel_bg_vh)
        getattr(a, "close", lambda: None)()
