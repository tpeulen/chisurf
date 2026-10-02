"""Populated captures of the Qt Structure Tools hub (the baseline): FPS JSON editor, docking, QuEst.

usage: capture_qt.py <out_dir> <fps|docking|quest> (run from the repo root, offscreen, temporary settings)
The Qt widgets are built in-process; nothing is saved to the user's settings (the hub has no settings key; the
tools' close handlers never run). QuEst runs a few thousand photons only.
"""
import json, os, pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fixtures  # noqa: E402

out, which = pathlib.Path(sys.argv[1]), sys.argv[2]
work = pathlib.Path(tempfile.mkdtemp())
from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.modelling.structure_tools.gui.tool import StructureToolsTool  # noqa: E402


def pump(n=30, dt=0.02):
    for _ in range(n):
        app.processEvents(); time.sleep(dt)


hub = StructureToolsTool()
hub.resize(1200, 800); hub.show(); pump()


def grab(name):
    pump(20)
    hub.grab().save(str(out / f"{name}.png"))
    print("saved", name)


if which == "fps":
    from chisurf.plugins.modelling.fps_json_editor.gui.editor import FpsJsonEditor
    hub.show_panel_by_role("fps_json_editor"); pump()
    ed = hub.panels[0]["instance"].findChild(FpsJsonEditor)
    fps, pdbs = fixtures.make(work)
    ed.onLoadJSON(str(fps)); pump(60)
    for tab, name in ((0, "positions"), (1, "distances"), (2, "flexfit"), (3, "json"), (4, "3d")):
        ed.dock_area.setCurrentIndex(tab)
        grab(f"before_populated_fps_{name}")
    ed.dock_area.setCurrentIndex(0)
    print("positions", len(ed.positions), "distances", len(ed.distances), "score sets", list(ed.score_sets))
    json.dump({"positions": ed.positions, "distances": ed.distances, "score_sets": ed.score_sets,
               "extra": ed.extra_sections}, open(out / "qt_fps_values.json", "w"), indent=1, sort_keys=True, default=str)
elif which == "docking":
    hub.show_panel_by_role("docking"); pump()
    from chisurf.plugins.modelling.fret.gui.dock_tool import FretDockingTool
    tool = hub.panels[1]["instance"].findChild(FretDockingTool)
    fps, pdbs = fixtures.make(work)
    tool._set_pdb_list([str(p) for p in pdbs])
    m = tool._model
    m.fps_json, m.output_dir, m.n_frames, m.n_repeats = str(fps), str(work / "dock_out"), 60, 1
    tool._form.sync_fields(); grab("before_populated_docking_inputs")
    tool._on_run()
    end = time.monotonic() + 180
    while tool._thread is not None and tool._thread.isRunning() and time.monotonic() < end:
        pump(5)
    pump(40)
    print("status", m.status, "rows", tool._table.rowCount(),
          [[tool._table.item(r, c).text() for c in range(5)] for r in range(tool._table.rowCount())])
    grab("before_populated_docking_results")
    tool._dock_area.setCurrentIndex(1); grab("before_populated_docking_score")
    tool._dock_area.setCurrentIndex(2); grab("before_populated_docking_structure")
else:
    # QuEst: the Qt panel cannot be built where IMP.bff.quenching is missing (this machine's arm64 env has an IMP.bff
    # without it): the hub shows its error panel, which is the baseline. Where it can be built the populated tabs follow.
    hub.show_panel_by_role("quest"); pump()
    grab("before_populated_quest_panel")
    try:
        from quest.gui import TransientDecayGenerator
    except Exception as exc:
        print("quest gui unavailable:", exc); raise SystemExit
    dg = next(q for q in hub.panels if q.get("role") == "quest")["instance"].findChild(TransientDecayGenerator)
    if dg is None:
        print("QuEst panel did not build (see the grab)"); raise SystemExit
    pdb = pathlib.Path("test/data/atomic_coordinates/pdb_files/148l.pdb").resolve()
    dg.model.pdb = str(pdb); dg.model.auto_attach_to_structure()
    dg.model.n_photons = 20000
    dg.refresh(); grab("before_populated_quest_inputs")
    dg.update_all(); pump(40)
    print("status", dg.model.status)
    for tab, name in ((0, "plots"), (1, "structure"), (2, "quenching"), (3, "json")):
        dg.tabs.setCurrentIndex(tab); grab(f"before_populated_quest_{name}")
