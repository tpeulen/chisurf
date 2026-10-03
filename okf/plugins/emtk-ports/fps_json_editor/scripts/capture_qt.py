"""Populated captures of the Qt standalone FpsJsonEditorTool (the baseline). usage: capture_qt.py <out_dir>"""
import json, os, pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fixtures  # noqa: E402

out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
work = pathlib.Path(tempfile.mkdtemp())
os.environ.update(CHISURF_SETTINGS_DIR=str(work / "s"), MMFDB_SETTINGS_DIR=str(work / "m"),
                  MMFDB_DATABASE_PATH=str(work / "m.sqlite"), HOME=str(work))
from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.modelling.fps_json_editor.gui.tool import FpsJsonEditorTool  # noqa: E402


def pump(n=30, dt=0.02):
    for _ in range(n):
        app.processEvents(); time.sleep(dt)


tool = FpsJsonEditorTool(); tool.resize(1200, 800); tool.show(); pump()
ed = tool.editor
tool.grab().save(str(out / "before_populated_empty.png"))
fps, pdbs = fixtures.make(work)
ed.onLoadJSON(str(fps)); pump(60)
for tab, name in ((0, "positions"), (1, "distances"), (2, "flexfit"), (3, "json"), (4, "3d")):
    ed.dock_area.setCurrentIndex(tab); pump(20)
    tool.grab().save(str(out / f"before_populated_{name}.png")); print("saved", name)
print("positions", len(ed.positions), "distances", len(ed.distances), "score sets", list(ed.score_sets))
json.dump({"positions": ed.positions, "distances": ed.distances, "score_sets": ed.score_sets,
           "extra": ed.extra_sections}, open(out / "qt_fps_values.json", "w"), indent=1, sort_keys=True, default=str)
