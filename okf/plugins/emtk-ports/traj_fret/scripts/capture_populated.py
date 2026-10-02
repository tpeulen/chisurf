"""Populated captures of Trajectory->FRET on the hgbp1 test trajectory (464 frames, 5235 atoms).

usage: capture_populated.py <out_dir> qt|emtk|emtk-states <prefix> [<qt_head dir>]   (run from the repo root)
Donor dipole atoms 1-20 (MET1 CA ... ), acceptor 3000-3010, dipoles on, stride 4, R0 52 A, tau0 4 ns, t-step 1 ns.
qt = the committed Qt tool (HEAD gui.py over HEAD sections.py / view_model.py); it has no topology row, so the
topology is set on its model directly (the gap guide 81 lists).
"""
import importlib, pathlib, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity  # noqa: E402,F401

out, which, prefix = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
DATA = pathlib.Path("test/data/atomic_coordinates/trajectory/hgbp1")
TRAJ, TOP = str(DATA / "hgbp1_transition.dcd"), str(DATA / "topol.pdb")
DONOR, ACCEPTOR = (1, 20), (3000, 3010)
work = pathlib.Path(tempfile.mkdtemp())


def settings(m):
    m.stride, m.forster_radius, m.tau0, m.t_step, m.dipoles = 4, 52.0, 4.0, 1.0, True


if which == "qt":
    from qtpy import QtWidgets
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    sys.path.insert(0, sys.argv[4])
    from qt_head import load_head_tool
    klass, _ = load_head_tool("traj_fret", ("view_model", "sections"))
    w = klass()
    m = w.model
    m.set_topology(TOP)
    m.set_trajectory(TRAJ)
    settings(m)
    m.atom_pair_section.set_donor(*DONOR)
    m.atom_pair_section.set_acceptor(*ACCEPTOR)
    w.auto_form.sync_fields()
    result = m.run_section.run(str(work / "fret.csv"))
    w.resize(1200, 800); w.show()
    for _ in range(30):
        qapp.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
    print("QT", result.shape, result[:2].round(3).tolist())
elif which == "emtk":
    from emtk.testing import RecordingPainter
    from test.gui.emtk_port_parity import emtk_screenshot, manifest_of
    module, attr = manifest_of("traj_fret")["entrypoints"]["emtk"].split(":")
    for size in [(1200, 800), (800, 600)]:
        a = getattr(importlib.import_module(module), attr)()
        m = a.model
        m.set_topology(TOP)
        m.set_trajectory(TRAJ)
        settings(m)
        m.donor, m.acceptor = DONOR, ACCEPTOR
        result = m.calc(str(work / "fret.csv"))
        for _ in range(3):
            a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
        print("EMTK", result.shape, result[:2].round(3).tolist())
        getattr(a, "close", lambda: None)()
