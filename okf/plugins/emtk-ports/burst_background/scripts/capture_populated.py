"""Populated captures: the demo measurement (2 kHz green / 1 kHz red background + bursts) estimated.

usage: capture_populated.py <out_dir> qt|emtk <prefix>   (run from the repo root)
qt = the committed Qt widget: HEAD's package __init__ (BurstBackgroundEstimator) over HEAD's gui/app.py and view_model.py.
"""
import importlib.util, pathlib, subprocess, sys, tempfile, time

out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.burst.burst_background.test.demo_data import build

path = build(pathlib.Path(tempfile.mkdtemp()) / "measurement")
PKG = "chisurf.plugins.burst.burst_background"
SRC = pathlib.Path("chisurf/plugins/burst/burst_background")


def head_module(name, rel):
    src = subprocess.run(["git", "show", f"HEAD:{SRC / rel}"], capture_output=True, text=True, check=True).stdout
    tmp = pathlib.Path(tempfile.mkdtemp()) / pathlib.Path(rel).name
    tmp.write_text(src)
    spec = importlib.util.spec_from_file_location(name, tmp)
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str((SRC / rel).resolve())
    mod.__package__ = PKG if rel.endswith("__init__.py") else name.rsplit(".", 1)[0]
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import chisurf.plugins.burst.burst_background.gui  # noqa: F401
    head_module(f"{PKG}.view_model", "view_model.py")
    head_module(f"{PKG}.gui.app", "gui/app.py")
    w = head_module(f"{PKG}._head_widget", "__init__.py").BurstBackgroundEstimator()
    w._add_tttr_files([str(path)])
    w._estimate()
    w.resize(1200, 800); w.show()
    for _ in range(30):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", w.model.backgrounds, w.model.status)
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.burst.burst_background.gui.app import create_app
    for size in [(1200, 800), (800, 600)]:
        a = create_app()
        a.controller.add_files([path])
        a.controller.run()
        while a.controller.running:
            time.sleep(0.05); a.draw(RecordingPainter(), 0, 0, *size)
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", a.model.backgrounds, a.controller.status)
        a.close()
