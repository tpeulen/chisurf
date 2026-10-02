"""Populated captures of the micro-time shifter on the demo file (detectors offset by 400 bins), auto-aligned.

usage: capture_populated.py <out_dir> qt|emtk <prefix> [<qt_head dir>]   (run from the repo root)
qt = the committed Qt tool (HEAD gui/tool.py via qt_head); emtk = the manifest's emtk entrypoint.
"""
import importlib, pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path.cwd()))
# Before the plugin import: it puts modules/ndxplorer on sys.path, whose own `test` package shadows the repo's.
import test.gui.emtk_port_parity  # noqa: E402,F401

out, which, prefix = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
from chisurf.plugins.tttr.tttr_microtime_shifter.tests.demo_data import build

path = build(pathlib.Path(tempfile.mkdtemp()) / "demo")

if which == "qt":
    from qtpy import QtWidgets
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("microtime_shifter", ())
    w = klass()
    w._file_model.files = [str(path)]
    w.file_list.refresh() if hasattr(w.file_list, "refresh") else None
    w._on_file_path(str(path))
    w.auto_align()
    w.resize(1200, 800); w.show()
    for _ in range(30):
        qapp.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", w._channel_shifts, w._trigger_level, w._trigger_pos)
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot, manifest_of
    module, attr = manifest_of("microtime_shifter")["entrypoints"]["emtk"].split(":")
    for size in [(1200, 800), (800, 600)]:
        a = getattr(importlib.import_module(module), attr)()
        a.load_files([path]) if hasattr(a, "load_files") else a.add_paths([str(path)])
        end = time.monotonic() + 60
        while (getattr(a, "job", None) and a.job.running) or not getattr(a, "n_mt", 0):
            assert time.monotonic() < end
            time.sleep(0.05); a.draw(RecordingPainter(), 0, 0, *size)
        a.auto_align()
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", a.channel_shifts, a.trigger_level, a.trigger_position)
        a.close()
