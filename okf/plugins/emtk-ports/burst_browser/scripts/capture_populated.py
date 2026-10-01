"""Populated captures on the demo burst folder (300 bursts, 2 files), histogram of E.

usage: capture_populated.py <out_dir> qt|emtk <prefix>   (run from the repo root)
qt = the committed Qt widget: HEAD's package __init__ (BurstBrowserWidget) over HEAD's gui/app.py and view_model.py.
"""
import importlib.util, pathlib, subprocess, sys, tempfile, time

out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.burst.burst_browser.test.demo_folder import build

root = build(pathlib.Path(tempfile.mkdtemp()) / "measurement")
PKG = "chisurf.plugins.burst.burst_browser"
SRC = pathlib.Path("chisurf/plugins/burst/burst_browser")


def head_module(name, rel):
    src = subprocess.run(["git", "show", f"HEAD:{SRC / rel}"], capture_output=True, text=True, check=True).stdout
    tmp = pathlib.Path(tempfile.mkdtemp()) / pathlib.Path(rel).name
    tmp.write_text(src)
    spec = importlib.util.spec_from_file_location(name, tmp)
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str((SRC / rel).resolve())          # resources (help.md, guide.json) beside it
    mod.__package__ = name.rsplit(".", 1)[0] if not rel.endswith("__init__.py") else PKG
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import chisurf.plugins.burst.burst_browser.gui  # noqa: F401  (the package objects)
    head_module(f"{PKG}.view_model", "view_model.py")
    head_module(f"{PKG}.gui.app", "gui/app.py")
    widget_mod = head_module(f"{PKG}._head_widget", "__init__.py")
    w = widget_mod.BurstBrowserWidget()
    w.load_folder(root)
    w.model.hist_column = "E"; w.model.refresh()
    w.resize(1200, 800); w.show()
    for _ in range(30):
        app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.burst.burst_browser.gui.app import create_app
    for size in [(1200, 800), (800, 600)]:
        a = create_app()
        a.load_folder(root)
        ctrl = getattr(a, "controller", None)
        while ctrl is not None and ctrl.running:
            time.sleep(0.05); ctrl.poll()
        a.model.hist_column = "E"; a.model.refresh()
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        a.close()
