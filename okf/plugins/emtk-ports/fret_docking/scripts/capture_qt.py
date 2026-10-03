"""Populated captures of the Qt standalone tools of fret_docking: FretDockingTool (docking) and FRETPairSelectionWindow.

usage: capture_qt.py <out_dir> <docking|pairs> (repo root, offscreen, temporary settings, no network)
"""
import json, os, pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fixtures  # noqa: E402

out, which = pathlib.Path(sys.argv[1]), sys.argv[2]
out.mkdir(parents=True, exist_ok=True)
work = pathlib.Path(tempfile.mkdtemp())
os.environ.update(CHISURF_SETTINGS_DIR=str(work / "s"), MMFDB_SETTINGS_DIR=str(work / "m"),
                  MMFDB_DATABASE_PATH=str(work / "m.sqlite"), HOME=str(work))
from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def pump(n=30, dt=0.02):
    for _ in range(n):
        app.processEvents(); time.sleep(dt)


def grab(w, name):
    pump(20)
    w.grab().save(str(out / f"{name}.png"))
    print("saved", name)


if which == "docking":
    from chisurf.plugins.modelling.fret.gui.dock_tool import FretDockingTool
    tool = FretDockingTool(); tool.resize(1200, 800); tool.show(); pump()
    grab(tool, "before_populated_empty")
    fps, pdbs = fixtures.make(work)
    tool._set_pdb_list([str(p) for p in pdbs])
    m = tool._model
    m.fps_json, m.output_dir, m.n_frames, m.n_repeats = str(fps), str(work / "dock_out"), 60, 1
    tool._form.sync_fields(); grab(tool, "before_populated_inputs")
    tool._on_run()
    end = time.monotonic() + 180
    while tool._thread is not None and tool._thread.isRunning() and time.monotonic() < end:
        pump(5)
    pump(40)
    rows = [[tool._table.item(r, c).text() for c in range(5)] for r in range(tool._table.rowCount())]
    print("status", m.status, rows)
    json.dump({"rows": rows, "status": m.status}, open(out / "qt_dock_values.json", "w"), indent=1)
    grab(tool, "before_populated_results")
    tool._dock_area.setCurrentIndex(1); grab(tool, "before_populated_score")
    tool._dock_area.setCurrentIndex(2); grab(tool, "before_populated_structure")
else:
    from chisurf.plugins.modelling.fret.gui.pair_selection_wizard import FRETPairSelectionWindow
    from chisurf.core.structure import trajectory_data as md
    data = pathlib.Path("test/data/atomic_coordinates/trajectory/hgbp1")
    full = md.load(str(data / "hgbp1_transition.dcd"), top=str(data / "topol.pdb"))
    full[:int(os.environ.get("FRAMES", 8))].save_dcd(str(work / "small.dcd"))
    w = FRETPairSelectionWindow(); w.resize(1100, 700); w.show(); pump()
    grab(w, "before_populated_pairs_empty")
    w.traj_edit.setText(str(work / "small.dcd")); w.top_edit.setText(str(data / "topol.pdb"))
    w.chain_edit.setText(os.environ.get("CHAIN", "A")); w.residues_edit.setText(os.environ.get("RES", "35-50,85-95,115-120"))
    w.max_pairs_spin.setValue(5)
    grab(w, "before_populated_pairs_inputs")
    from chisurf.gui import dialogs
    dialogs.error = lambda parent, title, text: print("ERROR DIALOG", title, text)
    dialogs.warning = lambda parent, title, text: print("WARNING DIALOG", title, text)
    w._run(); pump(20)
    rows = [[w.table.item(r, c).text() for c in range(3)] for r in range(w.table.rowCount())]
    print("rows", rows)
    json.dump({"rows": rows, "pair_names": list(w._last_pair_names)[:5]}, open(out / "qt_pairs_values.json", "w"), indent=1)
    grab(w, "before_populated_pairs_results")
