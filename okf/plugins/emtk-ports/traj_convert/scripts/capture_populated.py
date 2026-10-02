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
# (traj_join: hgbp1 then hgbp1 reversed, in time, chunk 100 -- the chunk the join interleaved on)
POPULATE = {
    "traj_save_topology": lambda m: (m.set_trajectory(TRAJ), m.set_topology(TOP),
                                     m.save_topology(str(scratch / "topology.pdb"))),
    "traj_align": lambda m: (m.set_trajectory(TRAJ), m.set_topology(TOP), setattr(m, "atom_selection", "0, 1, 2, 3"),
                             setattr(m, "stride", 4), m.save_aligned(str(scratch / "aligned.dcd"))),
    "traj_rotate_translate": lambda m: (m.set_trajectory(TRAJ), m.set_topology(TOP),
                                        m.set_rotation_matrix([[0, -1, 0], [1, 0, 0], [0, 0, 1]]),
                                        m.set_translation_vector([10, 0, 0]), setattr(m, "stride", 4),
                                        m.save_rotated_translated(str(scratch / "moved.dcd"))),
    "traj_remove_clashes": lambda m: (m.set_trajectory(TRAJ), m.set_topology(TOP), setattr(m, "atom_selection", "name CA"),
                                      setattr(m, "stride", 4), setattr(m, "min_distance", 3.5),
                                      m.save_clash_free(str(scratch / "clash_free.dcd"))),
    "traj_join": lambda m: (m.set_trajectory_1(TRAJ), m.set_trajectory_2(TRAJ), m.set_topology(TOP),
                            setattr(m, "reverse_traj_2", True), setattr(m, "chunk_size", 100),
                            m.save_joined(str(scratch / "joined.dcd"))),
    # frames 10..50 at stride 10, to one DCD: the old reader treated the last frame as exclusive
    "traj_convert": lambda m: (m.set_topology(TOP), m.set_trajectory(TRAJ), m.set_target_directory(str(scratch)),
                               setattr(m, "first_frame", 10), setattr(m, "last_frame", 50), setattr(m, "stride", 10),
                               setattr(m, "filename", "frames"), m.convert()),
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
elif which == "emtk":
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

if which == "emtk-states":
    # the save dialog over the loaded tool, and the guide's first waiting step
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot, manifest_of
    module, attr = manifest_of(tool)["entrypoints"]["emtk"].split(":")
    a = getattr(importlib.import_module(module), attr)()
    populate(a.model)
    a.begin_save()
    a.draw(RecordingPainter(), 0, 0, 1200, 800)
    emtk_screenshot(a, out / f"{prefix}_dialog_1200x800.png", (1200, 800))
    a.dialog = None
    step = next(i for i, s in enumerate(a.tour.steps) if s.get("await"))
    a.tour.start(step)
    for _ in range(2):
        a.draw(RecordingPainter(), 0, 0, 800, 600)
    emtk_screenshot(a, out / f"{prefix}_guide_800x600.png", (800, 600))
    a.close()
