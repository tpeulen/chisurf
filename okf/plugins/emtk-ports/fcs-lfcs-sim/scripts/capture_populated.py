"""Populated captures: the default simulation (τ 1/4 ns, D 8/0.5 µm²/ms, k 0, 400k photons, seed 1) run once.

usage: capture_populated.py <out_dir> qt|emtk <prefix>   (run from the repo root)
"""
import pathlib, sys, time

out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
from test.gui.emtk_port_parity import emtk_screenshot

if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.fcs.fcs_lfcs_sim.gui.tool import LifetimeFcsSimWidget, _LfcsSimControls
    w = LifetimeFcsSimWidget()
    w.resize(1200, 800); w.show()
    for _ in range(10):
        app.processEvents()
    w.findChild(_LfcsSimControls)._on_click()          # the button's own slot: simulate, plot, status
    for _ in range(30):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.fcs.fcs_lfcs_sim.app import make_app
    a = make_app()
    if hasattr(a, "simulate"):
        a.simulate()
        while getattr(a, "running", False):
            time.sleep(0.1); a.draw(RecordingPainter(), 0, 0, 1200, 800)
    else:  # the earlier app ran inside its button
        a.model.run()
    for size in [(1200, 800), (800, 600)]:
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
