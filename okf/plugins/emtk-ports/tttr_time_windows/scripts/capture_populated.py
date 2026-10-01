"""Populated captures on test/data/clsm/Leica_SP5.ptu: preview, then Process with a 10 s window into a temp folder.

qt:   TTTRTimeWindowTool as committed (HEAD tool.py)
emtk: the current app (create_app)
"""
import sys, pathlib, tempfile, time
from test.gui.emtk_port_parity import emtk_screenshot
sys.path.insert(0, str(pathlib.Path(__file__).parent))
out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
ptu = pathlib.Path("test/data/clsm/Leica_SP5.ptu").resolve()
outdir = pathlib.Path(tempfile.mkdtemp()) / which
if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("tttr_time_windows", ())
    w = klass(); w.resize(1200, 800); w.show()
    w._file_paths = [ptu]; w._on_files_changed()
    for _ in range(30): app.processEvents()
    bars = w.findChildren(QtWidgets.QTabBar)
    def show(name):
        for bar in bars:
            for i in range(bar.count()):
                if name in bar.tabText(i):
                    bar.setCurrentIndex(i)
        for _ in range(15): app.processEvents()
    show("Preview"); w.grab().save(str(out / f"{prefix}_preview.png"))
    w.tws_spin.setValue(10000.0); w.output_edit.setText(str(outdir)); w._on_settings_changed()
    w._process_all()
    for _ in range(50): app.processEvents(); time.sleep(0.05)
    show("Summary"); w.grab().save(str(out / f"{prefix}_summary.png"))
    print("qt log:", w.status_log.toPlainText()[-400:] if hasattr(w, "status_log") else "")
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.tttr.tttr_time_windows.gui.controller import create_app
    a = create_app(); c = a.tool if hasattr(a, "tool") else a.controller
    c.add_paths([ptu])
    c.load_preview_for_index(0); c.job.future.result(timeout=120); c.job.poll()
    for size in [(1200, 800), (800, 600)]:
        for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_preview_{size[0]}x{size[1]}.png", size)
    c.time_window_ms = 10000.0; c.output_dir_text = str(outdir)
    c._process_all(); c.job.future.result(timeout=300); c.job.poll()
    for _ in range(3): a.draw(RecordingPainter(), 0, 0, 1200, 800)
    emtk_screenshot(a, out / f"{prefix}_processed_1200x800.png", (1200, 800))
    print("emtk log:", c._log_lines[-6:])
print("outputs:", sorted(p.name for p in outdir.rglob("*") if p.is_file())[:8], "n=", sum(1 for p in outdir.rglob("*") if p.is_file()))
import hashlib
for p in sorted(outdir.rglob("*")):
    if p.is_file():
        print("sha256", p.name, hashlib.sha256(p.read_bytes()).hexdigest()[:16], p.stat().st_size)
