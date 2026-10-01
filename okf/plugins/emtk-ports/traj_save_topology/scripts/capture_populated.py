"""Populated captures of a trajectory tool on the hgbp1 test trajectory (464 frames, 5235 atoms).

usage: capture_populated.py <tool> <out_dir> qt|emtk <prefix> [<qt_head dir>]   (run from the repo root)
qt = the committed Qt widget (HEAD widget.py over HEAD sections.py / view_model.py, via qt_head);
emtk = the app the manifest's emtk entrypoint builds. The tool is driven into the state its own
action leaves: both files chosen, the action run once (writing into a scratch folder), the log full.
"""
import importlib, json, pathlib, sys, tempfile

tool, out, which, prefix = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3], sys.argv[4]
DATA = pathlib.Path("test/data/atomic_coordinates/trajectory/hgbp1")
TRAJ, TOP = str(DATA / "hgbp1_transition.dcd"), str(DATA / "topol.pdb")
scratch = pathlib.Path(tempfile.mkdtemp())

# per tool: the populate step on the view model, and the action that writes a file
POPULATE = {
    "traj_save_topology": lambda m: (m.set_trajectory(TRAJ), m.set_topology(TOP),
                                     m.save_topology(str(scratch / "topology.pdb"))),
}


def populate(model):
    POPULATE[tool](model)


if which == "qt":
    from qtpy import QtWidgets
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[5])
    from qt_head import load_head_tool
    klass, _ = load_head_tool(tool, ("view_model", "sections"))
    w = klass()
    populate(w.model)
    w.auto_form.sync_fields(); w.auto_form.refresh_plots()
    w.resize(1200, 800); w.show()
    for _ in range(30):
        qapp.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", json.dumps(w.model._log[-3:]))
else:
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot, manifest_of
    module, attr = manifest_of(tool)["entrypoints"]["emtk"].split(":")
    for size in [(1200, 800), (800, 600)]:
        a = getattr(importlib.import_module(module), attr)()
        populate(a.model)
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", json.dumps(a.model.log_text()[-3:]))
        getattr(a, "close", lambda: None)()
