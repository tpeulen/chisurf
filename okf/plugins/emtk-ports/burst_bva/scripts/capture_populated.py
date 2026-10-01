"""Populated captures on the 2CDE demo burst folder (60 bursts, static and dynamic), BVA computed.

usage: capture_populated.py <out_dir> qt|emtk <prefix>   (run from the repo root)
qt = the Qt tool as the stream left it (working-tree gui/tool.py, which drops file_type before compute_bva):
HEAD's tool passed it on and its run raised TypeError, so HEAD has no populated Qt state to capture.
"""
import pathlib, sys, tempfile, time

out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
from test.gui.emtk_port_parity import emtk_screenshot  # before the burst modules (another `test` package)
from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build

folder = build(pathlib.Path(tempfile.mkdtemp()) / "measurement")


class _Task:
    def set_range(self, *a): pass
    def set_text(self, *a): pass
    def progress_window(self, *a):
        return type("P", (), {"set_value": lambda self, v: None, "set_maximum": lambda self, v: None})()


if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.burst.burst_bva.gui.tool import BVATool
    w = BVATool()
    w.model.auto_update = False
    w.model.donor_channels_text, w.model.acceptor_channels_text = "0", "1"
    w.model.set_folder(folder)
    s = w.model.bva_settings()
    w._analysis_done(w._analysis_worker(s, True, w.analysis_fingerprint(s), w.input_files(), w.fingerprint_params(s), _Task()))
    w.resize(1200, 800); w.show()
    for _ in range(30):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", w.model.status_text)
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.burst.burst_bva.gui.app import create_app
    for size in [(1200, 800), (800, 600)]:
        a = create_app()
        a.model.auto_update = False
        a.model.donor_channels_text, a.model.acceptor_channels_text = "0", "1"
        a.model.set_folder(folder)
        a.controller.run()
        while a.model.is_running:
            time.sleep(0.05); a.draw(RecordingPainter(), 0, 0, *size)
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", a.model.status_text)
        a.close()
