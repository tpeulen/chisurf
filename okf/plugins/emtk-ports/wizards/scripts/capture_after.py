"""Populated screenshots of the native Wizards hub at both sizes: each wizard, Help, a tour card. Usage: <out dir> [docs figure path]."""
import pathlib, sys, tempfile, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.core.wizards.gui.app import WizardHubApp
from chisurf.plugins.core.batch_analysis.test.fakes import FakeSession
from chisurf.plugins.emtk_test_input import Driver
out = pathlib.Path(sys.argv[1]).resolve()
for size in ((1200, 800), (800, 600)):
    s = f"{size[0]}x{size[1]}"
    app = WizardHubApp(); d = Driver(app, size); d.draw(3)
    d.screenshot(out / f"after_populated_1_anisotropy_{s}.png")
    d.click_name("entry:batch_analysis")
    b = app.children["batch_analysis"]; b.model.session = FakeSession(); b.model.reload_datasets(); b.model.reload_fits()
    b.model.set_dataset_use(b.model.dataset_rows()[0], "use", True); b.model.go_to(1)
    d.screenshot(out / f"after_populated_2_batch_analysis_{s}.png")
    d.click_name("help"); d.screenshot(out / f"after_help_{s}.png"); d.escape()
    d.click_name("guide"); d.screenshot(out / f"after_tour_{s}.png")
