"""Populated captures: two fake open fits, model 1 and model 2 loaded from them, params = 1.

usage: capture_populated.py <out_dir> qt|emtk <prefix>   (run from the repo root; qt = the HEAD tool via qt_head)
"""
import pathlib, sys
from types import SimpleNamespace

out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]


def fit(name, chi2r, n_points, n_free):
    return SimpleNamespace(name=name, chi2r=chi2r, model=SimpleNamespace(n_points=n_points, n_free=n_free))


FITS = [fit("decay 1-exp", 1.31, 1024, 3), fit("decay 2-exp", 1.02, 1024, 5)]

if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("f_test")
    w = klass()
    w._load_fit(FITS[0], "model1"); w._load_fit(FITS[1], "model2"); w._load_fit(FITS[1], "chi2max")
    w.resize(900, 850); w.show()
    for _ in range(20):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot
    from chisurf.plugins.core.f_test.gui.app import FTestApp
    for size in [(1200, 800), (800, 600)]:
        a = FTestApp(fit_provider=lambda: FITS)
        if hasattr(a, "load_fit_into"):
            a.load_fit_into(0, "model1"); a.load_fit_into(1, "model2"); a.load_fit_into(1, "chi2max")
        else:  # the earlier app: combo selection + Load
            for i, t in ((0, 0), (1, 1), (1, 2)):
                a.fit_index, a.target_index = i, t; a.load_selected_fit()
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
