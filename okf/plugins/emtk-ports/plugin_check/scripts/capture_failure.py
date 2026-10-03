"""A real failing check for the guide figure: a throw-away broken native factory is added to the real list and swept
for real (child process). Usage: <out_dir>."""
import os, pathlib, sys, tempfile, time
tmp = pathlib.Path(tempfile.mkdtemp()); (tmp / "broken_native.py").write_text("def make_app():\n    raise RuntimeError('boom: the factory could not build its window')\n")
os.environ["PYTHONPATH"] = str(tmp) + os.pathsep + os.environ.get("PYTHONPATH", "")
sys.path.insert(0, str(tmp))
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.core.plugin_check.gui.app import PluginCheckApp
from chisurf.plugins.core.plugin_check.gui.model import PluginCheckModel, discover
catalog, report = discover()
catalog = {"demo_broken": {"id": "demo_broken", "plugin_name": "Demo:Broken plugin", "version": "0.0", "source": "user",
                           "description": "A throw-away plugin whose native factory raises.", "entrypoints": {"emtk": "broken_native:make_app"}}, **catalog}
app = PluginCheckApp(PluginCheckModel(catalog, report)); app.model.delay = 0
d = Driver(app, (1200, 800)); d.draw(3)
d.click("test_safe")
while app.model.running: time.sleep(0.2); d.draw(1)
d.click_text("Demo:Broken plugin"); d.draw(3)
emtk_screenshot(app, pathlib.Path(sys.argv[1]) / "docs_failure_selected_1200x800.png", (1200, 800))
