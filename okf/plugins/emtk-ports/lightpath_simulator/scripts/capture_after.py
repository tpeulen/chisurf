"""Populated captures of the emtk app, states reached by real pointer/key input. Usage: capture_after.py <out_dir> <prefix>."""
import pathlib, sys, tempfile, threading
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from test.gui import migration_parity as _mp  # noqa: F401
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import lp_env
from emtk import testing
from emtk.testing import PixelPainter
from chisurf.plugins.core.lightpath_simulator.gui.app import create_app
from chisurf.plugins.core.lightpath_simulator.tests.driving import LPDriver
from chisurf.plugins.core.lightpath_simulator.tests import test_emtk_lightpath_clicks as T

out = pathlib.Path(sys.argv[1]).resolve(); prefix = sys.argv[2]
work = pathlib.Path(tempfile.mkdtemp())
import os; os.chdir(work)
SIZES = ((1200, 800), (800, 600))
app = create_app(client=lp_env.in_process_client())
c = app.controller; c.auto_update = False
drv = LPDriver(app, SIZES[0])


def shot(name, sizes=SIZES):
    for size in sizes:
        if drv.size != size:
            app.graph_control.fit()  # the window was resized: the Fit button re-frames the graph
        drv.size = size
        for _ in range(3):
            p = PixelPainter(*size); app.draw(p, 0.0, 0.0, float(size[0]), float(size[1]))
        (out / f"{prefix}_{name}_{size[0]}x{size[1]}.png").write_bytes(testing.png_encode(p.width, p.height, p.px))
    drv.size = SIZES[0]


drv.settle(); drv.draw(3)
shot("empty")          # catalogue loaded, default path, nothing simulated yet
for n in c.document.nodes:
    if n.type == "detector": n.config["probe_id"] = lp_env.IDS["APD (flat QE)"]
drv.click("calculate"); drv.settle()
shot("populated")
for tab in ("Excitation", "Emission", "Detected", "Förster radius"):
    drv.click_text(tab); shot("tab_" + tab.split()[0], SIZES[:1])
drv.click_text("Signals")
# selected node: Delete Selected enabled
x, y, w, h = [t[:4] for t in drv.draw(2).texts if t[5] == "Förster Radius"][0]
T.press_on(drv, x + 20, y + 2); shot("selected_node", SIZES[:1])
# context menu
T.press_on(drv, x + 20, y + 2, 2); shot("context_menu_node", SIZES[:1])
drv.click_text("Duplicate")
gx, gy, gw, gh = app.item_rects["graph"]
T.press_on(drv, gx + 30, gy + 30, 2); shot("context_menu_canvas", SIZES[:1])
T.press_on(drv, gx + gw - 60, gy + 150)
# settings panels
drv.click_text("Backend"); drv.click_at(*T._centre(T.containing(drv, "Connections"))); drv.click_text("MMFDB", last=True)
shot("panels_open")
for label in ("Backend", "MMFDB"):
    pass
drv.click_text("Easy Mode"); shot("easy_mode")
drv.click_text("Optical Components")
# dialogs
drv.click("save_graph"); shot("save_dialog", SIZES[:1]); drv.click_text("Cancel")
drv.click("save_preset"); shot("preset_name_dialog", SIZES[:1]); drv.click_text("Cancel")
drv.click("save_mmfdb"); drv.click_text("OK"); drv.settle(); drv.draw(3); shot("saved_message", SIZES[:1]); drv.click_text("OK")
drv.click("load_mmfdb"); drv.settle(); drv.draw(3); shot("mmfdb_list", SIZES[:1]); drv.click_text("Cancel")
# load error
(work / "bad.json").write_text("{x"); drv.click("load_graph"); drv.click_text("bad.json"); drv.click_text("Open", last=True); drv.draw(3); shot("load_error", SIZES[:1]); drv.click_text("OK")
# running
gate = threading.Event(); real = c._backend
c._backend = lambda a, g=None, o=None: (gate.wait(20), real(a, g, o))[1]
drv.click("calculate"); shot("running_stop_visible", SIZES[:1]); gate.set(); drv.settle(); c._backend = real
# help and guide
drv.click("help"); shot("help", SIZES[:1]); drv.escape()
drv.click("guide"); shot("guide_step1", SIZES[:1]); drv.escape()
app.close()
print("ok")
