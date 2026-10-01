"""Populated captures with the test suite's three-fit session (c + a x^2, `a` linked)."""
import sys, pathlib, importlib.util
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
spec = importlib.util.spec_from_file_location("gv_tests", "chisurf/plugins/core/globalview/tests/test_model.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
model, fits, mutator = t._session(3)
if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.core.globalview.gui.tool import GraphWizard
    w = GraphWizard(fit_list=fits, remember_layout=False)
    w.resize(1200, 800); w.show()
    for _ in range(20): app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
else:
    from chisurf.plugins.core.globalview.gui import app as gvapp
    for size in [(1200, 800), (800, 600)]:
        model, fits, mutator = t._session(3)
        import inspect
        if "model" in inspect.signature(gvapp.make_app).parameters:
            a = gvapp.make_app(model=model, remember_layout=False)
        else:  # the earlier factory: build the surface around the session model the same way
            from chisurf.plugins.core.globalview.gui.surface import GlobalViewSurface
            model.rebuild(force=True); a = GlobalViewSurface(model)
        for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
