"""The native hub in the Qt capture's scenarios: entries selected, a broken entry, no entries; both sizes. Usage: <out_dir>."""
import pathlib, sys
from emtk.testing import RecordingPainter
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.calculator.hub.core.registry import CalculatorEntry, default_calculators
from chisurf.plugins.calculator.hub.gui import app as hub
from chisurf.plugins.calculator.hub.gui.app import CalculatorHubApp, make_app

out = pathlib.Path(sys.argv[1])
for size in [(1200, 800), (800, 600)]:
    app = make_app()
    def shot(name, a=None):
        a = a or app
        for _ in range(3): a.draw(RecordingPainter(), 0, 0, *size)
        emtk_screenshot(a, out / f"after_populated_{name}_{size[0]}x{size[1]}.png", size)
    shot("fret_calculator")
    for id in ("kappa2_dist", "phasor", "f_test", "psf_calculator"):
        app.select(id); shot(id)
    if size[0] == 1200:
        app.select("rics_precision"); shot("rics_precision_long_description")
        hub.FACTORIES["broken"] = "chisurf.nowhere:Nothing"
        broken = CalculatorHubApp(entries=[CalculatorEntry(id="broken", label="Broken one", description="Cannot be built.", widget="x:y"), *default_calculators()[:1]])
        shot("broken_entry", broken)
        empty = CalculatorHubApp(entries=[]); shot("no_entries", empty)
        app.show_help(); shot("help"); app.help_window.hide(); app.tour.start(1); shot("guide_pick_one")
