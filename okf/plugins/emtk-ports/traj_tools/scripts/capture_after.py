"""Populated screenshots of the native Traj Tools at both sizes: Align with a dropped trajectory, FRET, Help, a tour card. Usage: <out dir>."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.traj.traj_tools.app import TrajectoryToolsHubApp
from chisurf.plugins.emtk_test_input import Driver
out = pathlib.Path(sys.argv[1]).resolve()
dcd = pathlib.Path(__file__).resolve().parents[5] / "test/data/atomic_coordinates/trajectory/hgbp1/hgbp1_transition.dcd"
for size in ((1200, 800), (800, 600)):
    s = f"{size[0]}x{size[1]}"
    app = TrajectoryToolsHubApp(); d = Driver(app, size); d.draw(3)
    d.drop(str(dcd)); d.screenshot(out / f"after_populated_1_align_{s}.png")
    d.click_name("entry:FRET"); d.screenshot(out / f"after_populated_2_fret_{s}.png")
    d.click_name("help"); d.screenshot(out / f"after_help_{s}.png"); d.escape()
    d.click_name("guide"); d.screenshot(out / f"after_tour_{s}.png")
