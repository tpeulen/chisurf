"""Captures of the File tools hub with the TTTR header panel open on a photon file (the shifter demo SPC).

usage: capture_populated.py <out_dir> qt|emtk|emtk-states <prefix> [<qt_head dir>]   (run from the repo root)
qt = the committed Qt hub (HEAD gui/tool.py via qt_head); emtk = the manifest's emtk entrypoint.
"""
import importlib, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity  # noqa: E402,F401

out, which, prefix = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
import tempfile
from chisurf.plugins.tttr.tttr_microtime_shifter.tests.demo_data import build    # a valid SPC photon file

PTU = str(build(pathlib.Path(tempfile.mkdtemp()) / "demo"))
HEADER = "TTTR header"

if which == "qt":
    from qtpy import QtWidgets
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("filetools", ())
    w = klass()
    names = [p.name if hasattr(p, "name") else p["name"] for p in getattr(w, "_panels", [])] or None
    w.resize(1200, 800); w.show()
    for _ in range(30):
        qapp.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", names)
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot, manifest_of
    module, attr = manifest_of("filetools")["entrypoints"]["emtk"].split(":")
    for size in [(1200, 800), (800, 600)]:
        a = getattr(importlib.import_module(module), attr)()
        a.select("tttr_header_edit")
        a.draw(RecordingPainter(), 0, 0, *size)
        a.files_dropped([PTU])
        for _ in range(6):
            a.draw(RecordingPainter(), 0, 0, *size); time.sleep(0.2)
        if which == "emtk-states":
            a.tour.start(1)
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", a.selected, sorted(a.errors))
        a.close()
