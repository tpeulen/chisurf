"""Populated captures: the Qt widget (example project computed) and the committed emtk app.  usage: capture_before.py <out_dir> qt|emtk"""
import pathlib, sys, time
out = pathlib.Path(sys.argv[1]); which = sys.argv[2]
if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.fcs.fcs_filter_calculator.gui_parts.main_window import FcsFilterCalculatorWidget
    w = FcsFilterCalculatorWidget()
    w.resize(1500, 900); w.show()
    for _ in range(80):
        app.processEvents(); time.sleep(0.03)
    w.grab().save(str(out / "before_populated.png"))
    print("qt ok")
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot
    from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import create_app
    for size in [(1200, 800), (800, 600)]:
        a = create_app()
        end = time.monotonic() + 60
        while time.monotonic() < end:
            a.draw(RecordingPainter(), 0, 0, *size)
            if not a.job.running: break
            time.sleep(0.05)
        for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"before_emtk_populated_{size[0]}x{size[1]}.png", size)
