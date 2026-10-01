"""Populated captures: a seeded synthetic burst table (I_DD, I_DA, I_AA, Tau) shown in ndX.

qt:   build_ndxplorer_window (the Qt host), session_autosave=False, layout_store=None
emtk: gui.app.make_app
The table is test input, generated here; nothing in the app invents data.
"""
import sys, pathlib
import numpy as np
from test.gui.emtk_port_parity import emtk_screenshot
out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
rng = np.random.default_rng(7)
n = 4000
dd = rng.poisson(60, n).astype(float); da = rng.poisson(40, n).astype(float); aa = rng.poisson(50, n).astype(float)
tau = rng.normal(2.5, 0.3, n)
def source():
    from ndxplorer.core.data_source import DataSource
    return DataSource.from_columns({"I_DD": dd, "I_DA": da, "I_AA": aa, "Tau": tau})
if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window
    w = build_ndxplorer_window(data_source=source(), session_autosave=False, layout_store=None)
    w.resize(1200, 800); w.show()
    for _ in range(30): app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("qt rpc:", w.app.chisurf_rpc is not None, "autosave:", getattr(w.app, "session_autosave", None))
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.ndxplorer.gui import app as ndxapp
    import inspect
    kwargs = {"session_autosave": False} if "session_autosave" in inspect.signature(ndxapp.make_app).parameters else {}
    for size in [(1200, 800), (800, 600)]:
        a = ndxapp.make_app(**kwargs)
        a.model.set_source(source()); a.data_changed()
        for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("emtk rpc:", a.chisurf_rpc is not None, "autosave:", getattr(a, "session_autosave", None))
        a.close()
