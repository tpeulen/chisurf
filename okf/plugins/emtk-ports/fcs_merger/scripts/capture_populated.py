"""Populated captures of the FCS curve merger on six real FCS repeats (make_chunks.py).

usage: capture_populated.py <out_dir> qt|qt-head|emtk|emtk-states <prefix> [<qt_head dir>]   (run from the repo root)
State: the chunk folder loaded, chunk 3 unticked, chunk 2 highlighted.
qt-head = the Qt page as committed before this upgrade (HEAD fcs_merger.py, via qt_head's module overlay);
qt = the working Qt page.
"""
import importlib, pathlib, subprocess, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path.cwd()))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import test.gui.emtk_port_parity  # noqa: E402,F401
from make_chunks import build  # noqa: E402

out, which, prefix = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
FOLDER = build(pathlib.Path(tempfile.mkdtemp()) / "BH_SPC132")

if which in ("qt", "qt-head"):
    from qtpy import QtCore, QtWidgets
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if which == "qt-head":
        sys.path.insert(0, sys.argv[4])
        from qt_head import _install
        page_src = "chisurf/gui/widgets/wizard/fcs_merger/fcs_merger.py"
        head = subprocess.run(["git", "show", f"HEAD:{page_src}"], capture_output=True, text=True, check=True).stdout
        import chisurf.gui.widgets.wizard.fcs_merger as package  # noqa: F401
        module = _install("chisurf.gui.widgets.wizard.fcs_merger.fcs_merger", head, page_src)
        package.WizardFcsMerger = module.WizardFcsMerger
        import chisurf.gui.widgets.wizard as wizard_package
        wizard_package.WizardFcsMerger = module.WizardFcsMerger
    from chisurf.plugins.fcs.fcs_merger.wizard import ChisurfWizard
    w = ChisurfWizard()
    p = w.page(w.pageIds()[0])
    p.lineEdit.setText(str(FOLDER))
    p.open_correlation_folder(FOLDER)
    p.tableWidget.item(2, 0).setCheckState(QtCore.Qt.Unchecked)
    p.tableWidget.setCurrentCell(1, 1)
    p.update_plots()
    w.resize(1200, 800); w.show()
    for _ in range(40):
        qapp.processEvents(); time.sleep(0.02)
    w.grab().save(str(out / f"{prefix}.png"))
    t = p.tableWidget
    print("QT", [[t.item(r, c).text() for c in range(1, 5)] for r in range(t.rowCount())][:2],
          p.mean_correlation["count_rate"], p.lineEdit_2.text())
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot, manifest_of
    module, attr = manifest_of("fcs_merger")["entrypoints"]["emtk"].split(":")
    for size in [(1200, 800), (800, 600)]:
        a = getattr(importlib.import_module(module), attr)()
        a.load_folder(FOLDER)
        a.job.future.result(timeout=60)
        a.job.poll()
        a.use = [i != 2 for i in range(len(a.use))]
        a.selected = 1
        for _ in range(4):
            a.draw(RecordingPainter(), 0, 0, *size)
        if which == "emtk-states" and hasattr(a, "tour"):
            a.tour.start(1)
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", a.mean_correlation["count_rate"], a.output)
        getattr(a, "close", lambda: None)()
