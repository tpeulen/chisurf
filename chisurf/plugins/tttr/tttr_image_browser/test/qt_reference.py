"""Drives the real Qt TTTR image browser on a folder and prints what it computed and did, as JSON on the last line.

Usage (a subprocess of the parity tests, offscreen, temporary settings): ``qt_reference.py <folder> <setup.json> <work_dir>``.
The folder holds ``Leica_SP8.ptu``, ``corrupt.ptu`` (empty) and ``sub/Leica_SP5.ptu``; ``<setup.json>`` is the detector setup
passed to the Qt workspace the way the setup page's *Use setup and continue* does.
"""

import hashlib
import json
import os
import pathlib
import shutil
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

folder, setup_file, work = (pathlib.Path(a) for a in sys.argv[1:4])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
QtCore.QSettings.setPath(
    QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, str(work / "qsettings")
)

from chisurf.gui import dialogs
from chisurf.plugins.tttr.tttr_image_browser.gui import tool as tool_mod

messages = []
dialogs.information = lambda parent, title, text, *a, **k: messages.append((title, text))
chosen = {"dir": ""}
QtWidgets.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: chosen["dir"])


def settle(n=40):
    for _ in range(n):
        app.processEvents()


def sha(a):
    return hashlib.sha1(np.ascontiguousarray(a).tobytes()).hexdigest()


w = tool_mod.TTTRImageBrowserTool()
w.resize(1200, 800)
w.show()
ws = w._workspace
setup = json.loads(setup_file.read_text())
ws.apply_setup_settings(setup)
out = {}

ws.model.open_folder(str(folder))
settle()
out["entries_flat"] = [(e["label"], e["badge"], e["rating"]) for e in ws.model.file_entries()]
out["info_flat"] = ws.model.info_html()
ws._on_subfolders_toggled(True)
settle()
out["entries_recursive"] = [(e["label"], e["badge"], e["rating"]) for e in ws.model.file_entries()]
ws._on_subfolders_toggled(False)
settle()

lst = ws._browser._list


def pick(name):
    for i in range(lst.count()):
        if name in lst.item(i).text():
            lst.setCurrentRow(i)
            settle(80)
            return
    raise KeyError(name)


def mosaic_of(name):
    ws.model.select_file(name)
    m = ws.model._mosaic()
    if m is None:
        return None
    return dict(
        shape=list(m["mosaic"].shape),
        cols=m["cols"],
        rows=m["rows"],
        labels=m["labels"],
        sum=int(m["mosaic"].sum()),
        max=int(m["mosaic"].max()),
        sha1=sha(m["mosaic"]),
        tile_labels=ws.model.image_labels(),
    )


sp8 = str(folder / "Leica_SP8.ptu")
out["mosaic_SP8"] = mosaic_of(sp8)
out["mosaic_corrupt"] = mosaic_of(str(folder / "corrupt.ptu"))
ws._on_subfolders_toggled(True)
settle()
out["mosaic_SP5"] = mosaic_of(str(folder / "sub" / "Leica_SP5.ptu"))
ws._on_subfolders_toggled(False)
settle()

canvas = ws._browser._canvas
out["colormaps"] = [canvas._combo.itemText(i) for i in range(canvas._combo.count())]
out["colormap_default"] = canvas._combo.currentText()
out["rating_filters"] = ws.model.rating_filter_options()

# rating and annotation through the widgets, then the file the Qt tool wrote
pick("Leica_SP8")
ws._browser._star_buttons[1].click()
ws._browser._note.setPlainText("good cell, bleached after frame 3")
settle()
out["meta"] = json.loads((folder / ".image_browser_meta.json").read_text())
out["entries_rated"] = [(e["label"], e["badge"], e["rating"]) for e in ws.model.file_entries()]
filt = {}
for text in ("All", "≥ 1★", "≥ 2★★", "≥ 3★★★", "Only 0★"):
    ws.model.set_rating_filter(text)
    filt[text] = [e["label"] for e in ws.model.file_entries()]
ws.model.set_rating_filter("All")
out["filters"] = filt

# exports (the destination dialogs are stubbed)
ws._on_subfolders_toggled(True)
settle()
lst.selectAll()
settle()
out["selected"] = [pathlib.Path(p).name for p in ws.model.selected_files]
copy_dir = work / "qt_copy"
copy_dir.mkdir()
chosen["dir"] = str(copy_dir)
ws._on_export()
out["copy"] = {
    p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in sorted(copy_dir.rglob("*.ptu"))
}
tiff_dir = work / "qt_tiff"
tiff_dir.mkdir()
chosen["dir"] = str(tiff_dir)
ws._on_save_tiff()
import tifffile

out["tiff"] = {
    p.name: [list(tifffile.imread(p).shape), int(tifffile.imread(p).sum())]
    for p in sorted(tiff_dir.iterdir())
}

# Next with a recording coordinator
calls = []


class Coord:
    def set_pipeline(self, **kw):
        calls.append(["set_pipeline", {k: pathlib.Path(v).name for k, v in kw.items()}])

    def goto_role(self, role):
        calls.append(["goto_role", role])

    def autorun_role(self, role):
        calls.append(["autorun_role", role])


w._coordinator = Coord()
ws.model.select_file(sp8)
del calls[:]
w._on_next_step()
out["next_calls"] = [list(c) for c in calls]

# caches
out["cache_dirs_before"] = sorted(
    str(p.relative_to(folder)) for p in folder.rglob(".tttr_image_cache")
)
ws._on_clear_caches()
out["cache_dirs_after"] = sorted(
    str(p.relative_to(folder)) for p in folder.rglob(".tttr_image_cache")
)
out["messages"] = messages

# a folder dropped on the workspace
ws.model.clear()
out["entries_after_clear"] = [e["label"] for e in ws.model.file_entries()]
md = QtCore.QMimeData()
md.setUrls([QtCore.QUrl.fromLocalFile(str(folder / "sub"))])
ws.dropEvent(
    QtGui.QDropEvent(
        QtCore.QPointF(5, 5), QtCore.Qt.CopyAction, md, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier
    )
)
out["drop_folder"] = [e["label"] for e in ws.model.file_entries()]

bar = w.findChildren(QtWidgets.QToolBar)[0]
out["toolbar"] = [a.text() for a in bar.actions() if a.text()]
print("JSON:" + json.dumps(out), flush=True)
os._exit(0)
