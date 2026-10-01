"""After-captures of the host services: the save dialog and a warning, on the three-fit session."""
import sys, pathlib, importlib.util
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
spec = importlib.util.spec_from_file_location("gv_tests", "chisurf/plugins/core/globalview/tests/test_model.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
from chisurf.plugins.core.globalview.gui.app import make_app
out = pathlib.Path(sys.argv[1])
model, fits, mutator = t._session(3)
a = make_app(model=model, remember_layout=False)
for _ in range(2): a.draw(RecordingPainter(), 0, 0, 1200, 800)
a.model.save_network()
for _ in range(2): a.draw(RecordingPainter(), 0, 0, 1200, 800)
emtk_screenshot(a, out / "after_populated_save_dialog_1200x800.png", (1200, 800))
a.dialog = None
a.model.link_selected()          # nothing selected: the model says so in the status line
a.model._warn("Cannot link", "The link was refused: it would make a cycle.")
for _ in range(2): a.draw(RecordingPainter(), 0, 0, 800, 600)
emtk_screenshot(a, out / "after_populated_warning_800x600.png", (800, 600))
