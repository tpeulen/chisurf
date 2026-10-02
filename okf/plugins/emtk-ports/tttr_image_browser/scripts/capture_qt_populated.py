"""Populated captures of the Qt TTTR image browser on real CLSM files. Usage: capture_qt_populated.py <out_dir>

Everything on temporary settings (CHISURF_SETTINGS_DIR, MMFDB_*, QSettings redirected, HOME); the folder
holds copies of test/data/clsm/Leica_SP8.ptu and Leica_SP5.ptu (the latter in a subfolder), an empty
``corrupt.ptu`` and a ``notes.txt`` that is not a photon file.  File dialogs are stubbed (they would block
offscreen) and answer with folders in the temp area; the information dialog is recorded, never shown.

Writes before_populated_*.png, before_tab_*.png and qt_values.json (what the Qt window computed and did).
"""
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile

tmp = pathlib.Path(tempfile.mkdtemp(prefix="ib_qt_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m.sqlite")
os.environ["HOME"] = str(tmp / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

REPO = pathlib.Path(__file__).resolve().parents[5]
out = pathlib.Path(sys.argv[1])
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
QtCore.QSettings.setPath(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, str(tmp / "qsettings"))

imgs = tmp / "imgs"
(imgs / "sub").mkdir(parents=True)
shutil.copy(REPO / "test/data/clsm/Leica_SP8.ptu", imgs / "Leica_SP8.ptu")
shutil.copy(REPO / "test/data/clsm/Leica_SP5.ptu", imgs / "sub" / "Leica_SP5.ptu")
(imgs / "corrupt.ptu").write_bytes(b"")
(imgs / "notes.txt").write_text("not a photon file")

from chisurf.gui import dialogs
from chisurf.plugins.tttr.tttr_image_browser.gui import tool as tool_mod
from chisurf.plugins.tttr.tttr_image_browser.gui.view_model import ImageBrowserViewModel

SETUP = {
    "windows": {"all": [0, 4095]},
    "detectors": {
        "green": {"chs": [0, 1], "micro_time_ranges": [[0, 4095]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "red": {"chs": [2], "micro_time_ranges": [[0, 4095]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
    },
    "tttr_reading": {"file_type": "PTU", "macro_time_resolution": 50.0, "micro_time_resolution": 16.0,
                     "micro_time_binning": 1, "effective_micro_time_resolution": 16.0, "excitation_period": 50.0},
    "setup_name": "", "apply_lut": False, "polarization_resolved": True, "channel_luts": {}, "channel_shifts": {},
}
from chisurf.core.setup_channel_definition import ChannelDefinition

SETUP = ChannelDefinition(SETUP).get_settings()  # adds the window x detector cross product ("channels")

messages = []
dialogs.information = lambda parent, title, text, *a, **k: messages.append((title, text))
chosen_dir = {"value": ""}
QtWidgets.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: chosen_dir["value"])


def settle(n=30):
    for _ in range(n):
        app.processEvents()


w = tool_mod.TTTRImageBrowserTool()
w.resize(1200, 800)
w.show()
settle()
ws = w._workspace


def grab(name):
    settle()
    w.grab().save(str(out / f"{name}.png"))


def md5(path):
    return hashlib.md5(pathlib.Path(path).read_bytes()).hexdigest()


vals = {"fixture": sorted(str(p.relative_to(imgs)) for p in imgs.rglob("*") if p.is_file()), "messages": messages}

# 1. setup page with a real setup loaded into the wizard tables (the page the audit says the emtk app opens on)
ws.detector_page.load_data_into_tables(SETUP)
settle()
grab("before_populated_setup_page")
vals["setup_page_settings"] = ws.detector_page.get_settings()["tttr_reading"]

# 2. Use setup and continue -> browser page, no folder yet
ws.btn_continue.click()
settle()
ws.model.setup_settings = ws.detector_page.get_settings() | {"tttr_reading": SETUP["tttr_reading"]}
ws.model.setup_settings = SETUP
grab("before_populated_browser_empty")
vals["info_empty"] = ws.model.info_html()

# 3. open the folder (non recursive): the SP8 file and the empty corrupt.ptu; the txt is not listed
ws.model.open_folder(str(imgs))
settle()
browser = ws._browser
vals["entries_nonrecursive"] = ws.model.file_entries()
grab("before_populated_folder_opened")
vals["info_folder"] = ws.model.info_html()

# 4. select the SP8 file: its detector-window mosaic
lst = browser._list
row = [i for i in range(lst.count()) if "Leica_SP8" in lst.item(i).text()][0]
lst.setCurrentRow(row)
settle(60)
m = ws.model._mosaic()
vals["mosaic_SP8"] = dict(shape=list(m["mosaic"].shape), cols=m["cols"], rows=m["rows"], labels=m["labels"],
                          sum=int(m["mosaic"].sum()), max=int(m["mosaic"].max()), mean=float(m["mosaic"].mean()),
                          sha1=hashlib.sha1(np.ascontiguousarray(m["mosaic"]).tobytes()).hexdigest(),
                          tile_labels=ws.model.image_labels())
grab("before_populated_mosaic_SP8")
vals["info_selected"] = ws.model.info_html()

# 5. colormap combo of the image dock
canvas = browser._canvas
vals["colormaps"] = [canvas._combo.itemText(i) for i in range(canvas._combo.count())]
vals["colormap_default"] = canvas._combo.currentText()
canvas._combo.setCurrentText("viridis")
settle()
grab("before_populated_colormap_viridis")
vals["colormap_after"] = canvas._combo.currentText()
canvas._combo.setCurrentText("magma")
settle()

# 6. rating 2 stars, annotation; the file the Qt tool writes
browser._star_buttons[1].click()
settle()
browser._note.setPlainText("good cell, bleached after frame 3")
settle()
vals["rating_selected"] = ws.model.rating_of(ws.model.current_file)
vals["note_selected"] = ws.model.note_of(ws.model.current_file)
vals["meta_file"] = json.loads((imgs / ".image_browser_meta.json").read_text())
vals["entries_after_rating"] = ws.model.file_entries()
grab("before_populated_rated_annotated")

# 7. Subfolders (toolbar check box) -> recursive scan lists the SP5 file as sub/Leica_SP5.ptu
chk = [c for c in w.findChildren(QtWidgets.QCheckBox) if c.text() == "Subfolders"][0]
chk.setChecked(True)
settle(60)
vals["entries_recursive"] = ws.model.file_entries()
grab("before_populated_subfolders")

# 8. select the SP5 file (a second mosaic, three detector windows' worth of channels)
lst = browser._list
row = [i for i in range(lst.count()) if "Leica_SP5" in lst.item(i).text()][0]
lst.setCurrentRow(row)
settle(120)
m = ws.model._mosaic()
vals["mosaic_SP5"] = dict(shape=list(m["mosaic"].shape), cols=m["cols"], rows=m["rows"], labels=m["labels"],
                          sum=int(m["mosaic"].sum()), max=int(m["mosaic"].max()), mean=float(m["mosaic"].mean()),
                          sha1=hashlib.sha1(np.ascontiguousarray(m["mosaic"]).tobytes()).hexdigest(),
                          tile_labels=ws.model.image_labels())
grab("before_populated_mosaic_SP5")

# 9. the rating filter and the text filter
for text in ("≥ 2★★", "Only 0★", "≥ 1★", "≥ 3★★★", "All"):
    ws.model.set_rating_filter(text)
    ws.auto_form.refresh_plots()
    settle()
    vals[f"entries_filter[{text}]"] = [e["label"] for e in ws.model.file_entries()]
    if text in ("≥ 2★★", "Only 0★"):
        grab(f"before_populated_filter_{'ge2' if text.startswith('≥') else 'only0'}")
browser._filter_edit.setText("sp5")
settle()
vals["text_filter_sp5_visible"] = [lst.item(i).text() for i in range(lst.count()) if not lst.item(i).isHidden()]
grab("before_populated_text_filter")
browser._filter_edit.setText("")
settle()

# 10. multi-selection (ctrl-select two rows) and the exports
lst.selectAll()
settle()
vals["selected_files"] = [pathlib.Path(p).name for p in ws.model.selected_files]
grab("before_populated_multiselect")
dest = tmp / "export_copy"
dest.mkdir()
chosen_dir["value"] = str(dest)
ws._on_export()
vals["export_copy"] = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
vals["export_copy_md5_equal_source"] = {p.name: md5(p) == md5(imgs / p.name) for p in dest.glob("*.ptu") if (imgs / p.name).exists()}
tiff = tmp / "export_tiff"
tiff.mkdir()
chosen_dir["value"] = str(tiff)
ws._on_save_tiff()
vals["export_tiff"] = sorted(p.name for p in tiff.iterdir())
try:
    import tifffile

    vals["export_tiff_shapes"] = {p.name: list(tifffile.imread(p).shape) for p in sorted(tiff.iterdir())}
    vals["export_tiff_sums"] = {p.name: int(tifffile.imread(p).sum()) for p in sorted(tiff.iterdir())}
except Exception as exc:  # pragma: no cover
    vals["export_tiff_shapes"] = repr(exc)
before_docx = set(p.name for p in imgs.iterdir())
ws._on_export_docx()
vals["export_docx_new_files"] = sorted(set(p.name for p in imgs.iterdir()) - before_docx)
vals["export_docx_note"] = ("python-docx is not installed in this environment: the Qt DOCX export returns without "
                            "writing anything (workspace.Document is None)")
vals["messages_after_exports"] = list(messages)

# 11. Next -> Intensity with a recording stand-in for the imaging coordinator
calls = []


class Coord:
    def set_pipeline(self, **kw):
        calls.append(("set_pipeline", kw))

    def goto_role(self, role):
        calls.append(("goto_role", role))

    def autorun_role(self, role):
        calls.append(("autorun_role", role))


w._coordinator = Coord()
ws.model.select_file(str(imgs / "Leica_SP8.ptu"))
w._on_next_step()
vals["next_calls"] = [(a, (b if not isinstance(b, dict) else {k: pathlib.Path(v).name for k, v in b.items()})) for a, b in calls]

# 12. the corrupt file: no image can be reconstructed
ws.model.select_file(str(imgs / "corrupt.ptu"))
ws.auto_form.refresh_plots()
settle(40)
vals["corrupt_image_is_none"] = ws.model.current_image() is None
grab("before_populated_corrupt_file")

# 13. Caches: the on-disk caches are removed, a message is shown
vals["cache_dirs_before"] = sorted(str(p.relative_to(imgs)) for p in imgs.rglob(".tttr_image_cache"))
vals["cache_files_before"] = len(list(imgs.rglob(".tttr_image_cache/*.npz")))
ws._on_clear_caches()
vals["cache_dirs_after"] = sorted(str(p.relative_to(imgs)) for p in imgs.rglob(".tttr_image_cache"))
vals["messages_after_caches"] = list(messages)

# 14. a folder dropped on the workspace (dropEvent)
ws.model.clear()
settle()
vals["entries_after_clear"] = ws.model.file_entries()
grab("before_populated_cleared")
md = QtCore.QMimeData()
md.setUrls([QtCore.QUrl.fromLocalFile(str(imgs / "sub"))])
ev = QtGui.QDropEvent(QtCore.QPointF(10, 10), QtCore.Qt.CopyAction, md, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
ws.dropEvent(ev)
settle()
vals["drop_folder"] = [e["label"] for e in ws.model.file_entries()]
vals["drop_current_folder"] = pathlib.Path(ws.model.current_folder).name

# 15. Help dialog (QDialog.exec stubbed so it is grabbed instead of blocking)
shown = {}


def fake_exec(self):
    self.resize(760, 520)
    self.show()
    settle()
    self.grab().save(str(out / "before_populated_help.png"))
    shown["title"] = self.windowTitle()
    shown["text"] = self.findChild(QtWidgets.QPlainTextEdit).toPlainText()
    return 0


QtWidgets.QDialog.exec = fake_exec
w._show_help()
vals["help_title"] = shown.get("title")
vals["help_text"] = shown.get("text")

# 16. back to the setup page cannot be done from the page (no button in the Qt browser): record it
vals["qt_has_back_to_setup_button"] = any(b.text().lower().startswith("back") for b in ws.findChildren(QtWidgets.QPushButton))

# 17. toolbar action texts and tooltips
bar = w.findChildren(QtWidgets.QToolBar)[0]
vals["toolbar"] = [(a.text(), a.toolTip()) for a in bar.actions() if a.text()]

(out / "qt_values.json").write_text(json.dumps(vals, indent=2, default=str))
print("wrote", out / "qt_values.json")
os._exit(0)
