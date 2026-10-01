"""Populated captures: the plugin tests' synthetic peptide DCD, Radius of Gyration (weight 1) and Clash potential (0.5) added (H-Bond needs residue data the peptide lacks), processed.

qt:   PotentialEnergyWidget (AutoForm on calculate_potential.view.json); potentials added through the
      Qt-free model (the core classes the Qt editors subclass), Process run through the model
emtk: the emtk app; the same calls
Needs modules/imp-tricks/src on PYTHONPATH (IMP.cgmol).
"""
import sys, pathlib, tempfile
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.traj.potential_energy.test.test_view_model import _peptide_trajectory
from chisurf.plugins.traj.potential_energy.potential_specs import make_potential
out = pathlib.Path(sys.argv[1]); which = sys.argv[2]; prefix = sys.argv[3]
tmp = pathlib.Path(tempfile.mkdtemp()); dcd = tmp / "pep.dcd"; pdb = _peptide_trajectory(str(dcd))
def populate(model):
    model.set_trajectory(str(dcd)); model.set_topology(pdb)
    for name, weight in (("Radius of Gyration", 1.0), ("Clash potential", 0.5)):
        model.add_potential(make_potential(name, {}), weight, name=name)
    n = model.process(str(tmp / f"{which}.txt"))
    print(which, "frames", n, open(tmp / f"{which}.txt").read().splitlines()[:2])
if which == "qt":
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.traj.potential_energy.widget import PotentialEnergyWidget
    w = PotentialEnergyWidget(); w.resize(1200, 800); w.show(); app.processEvents()
    populate(w.model)
    for _ in range(10): app.processEvents()
    w.grab().save(str(out / f"{prefix}.png"))
else:
    from emtk.testing import RecordingPainter
    from chisurf.plugins.traj.potential_energy.app import make_app
    for size in [(1200, 800), (800, 600)]:
        a = make_app(); populate(a.model)
        for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"{prefix}_{size[0]}x{size[1]}.png", size)
