"""Populated Qt baseline of the Batch-Analysis wizard: every step with datasets, files, a fit and results (offscreen).

Run: QT_QPA_PLATFORM=offscreen PYTHONPATH=. HOME=<tmp> python okf/plugins/emtk-ports/batch_analysis/scripts/qt_populated.py <out dir>
"""
import os, sys, tempfile, pathlib, json
from qtpy import QtWidgets, QtCore

from chisurf.plugins.core.batch_analysis.core import runner
from chisurf.plugins.core.batch_analysis.gui import view_model as vm_mod
from chisurf.plugins.core.batch_analysis.gui.tool import BatchProcessingWizard
from chisurf.plugins.core.batch_analysis.test.fakes import FakeSession

out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
session = FakeSession()
vm_mod.BatchViewModel._fit_client = lambda self: session.client
vm_mod.BatchViewModel.imported_datasets = lambda self: list(session.datasets)
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
w = BatchProcessingWizard()
w.resize(1200, 800)
m = w.model
tmp = pathlib.Path(tempfile.mkdtemp())
files = []
for n in ("run_01.sm", "run_02.sm"):
    (tmp / n).write_text("x"); files.append(str(tmp / n))
m.files = files
m.selected_dataset_indices = [0, 2]
m.selected_fit_name = "Template fit"
m.save_path = str(tmp / "results.csv")
items = m.build_items()
m._results = runner.run_batch(0, items, fit_client=session.client, dispatch=lambda name, payload: session.dispatch(name, payload),
                              imported_datasets=session.datasets)
m._status_html = "<p style='color:#2e7d32'><b>Done.</b></p><pre>CSV: %s</pre>" % m.save_path
w.show(); app.processEvents()
form = w.assistant.auto_form
form.sync_fields() if hasattr(form, "sync_fields") else None
wiz = form.findChildren(QtWidgets.QWidget)
nav = None
for lst in form.findChildren(QtWidgets.QListWidget):
    if lst.count() == 5 and nav is None:
        nav = lst
names = ["welcome", "loaded_data", "files_fit", "run", "results"]
for i, name in enumerate(names):
    if nav is not None:
        nav.setCurrentRow(i)
    app.processEvents(); m.notify("refresh"); app.processEvents()
    w.grab().save(str(out / f"before_populated_{i + 1}_{name}.png"))
print("nav", nav is not None)
