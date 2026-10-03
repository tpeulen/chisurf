"""Populated Qt baseline of Traj Tools (offscreen): Align with the hgbp1 trajectory, then every other tab. Usage: <out dir>."""
import sys, pathlib
from qtpy import QtWidgets
from chisurf.plugins.traj.traj_tools.gui.tool import TrajectoryToolsTool
out = pathlib.Path(sys.argv[1]).resolve(); out.mkdir(parents=True, exist_ok=True)
base = pathlib.Path(__file__).resolve().parents[4] / "test/data/atomic_coordinates/trajectory/hgbp1"
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
w = TrajectoryToolsTool(); w.resize(1200, 800); w.show(); app.processEvents()
align = w._tools["Align"]
align.trajectory_filename = str(base / "hgbp1_transition.dcd")
for attr in ("topology_filename",):
    if hasattr(type(align), attr): setattr(align, attr, str(base / "topol.pdb"))
for i, name in enumerate(w._tools):
    w._select_tool(name); app.processEvents()
    w.grab().save(str(out / f"before_populated_{i+1}_{name.lower().replace(' ', '_')}.png"))
