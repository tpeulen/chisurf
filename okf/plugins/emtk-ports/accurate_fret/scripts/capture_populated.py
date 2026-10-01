"""Populated captures on the plugin test suite's simulated bursts (n=100), no bootstrap.

qt:   the Qt tool as committed (HEAD tool.py + HEAD app.py + HEAD view_model.py)
emtk: the current emtk app (create_app)
"""
import sys, pathlib, tempfile, importlib.util
import numpy as np
from test.gui.emtk_port_parity import emtk_screenshot  # before the plugin tests shadow `test`
sys.path.insert(0, str(pathlib.Path(__file__).parent))
spec = importlib.util.spec_from_file_location("af_t", "chisurf/plugins/burst/accurate_fret/test/test_accurate_fret_plugin.py")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
dd, da, aa, tau = t._simulate(n=100)
npz = pathlib.Path(tempfile.mkdtemp()) / "bursts.npz"
np.savez(npz, **{"Green Count Rate (KHz)": dd, "Red Count Rate (KHz)": da, "S delayed yellow (kHz)": aa, "Tau (green)": tau})
if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("accurate_fret", ("app", "view_model"))
    w = klass(); w.resize(1200, 800); w.show()
    m = w.model; m.n_bootstrap = 0; m.donor_lifetime = t.TAU_D0
    m.set_filename(str(npz)); assert m.compute()
    w.app.sync_fields() if hasattr(w.app, "sync_fields") else None
    for _ in range(30): app.processEvents()
    w.host.update()
    for _ in range(10): app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("qt factors", {r.get("name", r.get("factor")): r.get("value") for r in m.factor_rows()})
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot
    from chisurf.plugins.burst.accurate_fret.gui.app import create_app
    for size in [(1200, 800), (800, 600)]:
        a = create_app(); a.model.n_bootstrap = 0; a.model.donor_lifetime = t.TAU_D0
        a.controller.load(str(npz)); a.controller._future.result(timeout=30); a.controller.poll()
        a.controller.run(); a.controller._future.result(timeout=60); a.controller.poll()
        for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        if size[0] == 1200:
            print("emtk factors", {r.get("name", r.get("factor")): r.get("value") for r in a.model.factor_rows()})
            for key in ("tau", "hist"):
                a.accurate_gui.docks.focus(key)
                for _ in range(2): a.draw(RecordingPainter(), 0, 0, *size)
                emtk_screenshot(a, out / f"{prefix}_{key}_{size[0]}x{size[1]}.png", size)
        a.close()
