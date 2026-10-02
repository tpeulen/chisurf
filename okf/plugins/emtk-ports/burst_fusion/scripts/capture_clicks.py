"""Real-input click sequence on the Burst Fusion window (pointer / keys only), one PNG per step.

usage: capture_clicks.py <out_dir>   (run from the repo root, with the temp settings env of the brief)
"""
import functools, json, pathlib, sys, tempfile, time

out = pathlib.Path(sys.argv[1])
from test.gui.emtk_port_parity import emtk_screenshot  # before the burst modules (another `test` package)
from emtk import clipboard, keys
from emtk.testing import RecordingPainter
from chisurf.plugins.burst.burst_fusion import demo
from chisurf.plugins.burst.burst_fusion.gui.app import create_app

root = pathlib.Path(tempfile.mkdtemp())
demo.create_demo = functools.partial(demo.create_demo, directory=root / "own")
a = create_app()
SIZE = (1200, 800)


def draw(n=2):
    p = None
    for _ in range(n):
        p = RecordingPainter(); a.draw(p, 0, 0, *SIZE)
    return p


def rect(name):
    return a.item_rects.get(name) or a.fusion_gui.form_state.rects[name]


def click(r, fx=.5, clicks=1):
    x, y, w, h = r
    a.pointer_move(x + w * fx, y + h / 2); draw(1)
    a.press(x + w * fx, y + h / 2, clicks=clicks); draw(1); a.release(); draw(1)


def text(label, last=True):
    return [t[:4] for t in draw().texts if t[5] == label][-1 if last else 0]


def settle():
    while a.controller.running:
        time.sleep(0.05); draw(1)
    draw(2)


def shot(name):
    draw(); emtk_screenshot(a, out / f"click_{name}.png", SIZE)
    draw(4)    # a pixel-painter frame measures text differently: let the layout settle before the next input


def type_into(name, s):
    draw(); click(rect(name), fx=.3); a.key(0x41, "a", 0x04000000)
    for ch in s: a.key(ord(ch), ch); draw(1)
    a.key(keys.KEY_RETURN, "\r"); draw(2)


draw()
click(rect("load_demo")); draw(2); shot("1_after_click_on_Demo_generating")
settle(); shot("2_demo_loaded")
click(rect("toolAction_refresh")); settle(); shot("3_after_click_on_Estimate")
type_into("threshold", "0.8"); shot("4_typed_threshold_0.8_estimate_invalidated")
click(rect("toolAction_refresh")); settle()
click(text("Photons")); shot("5_photons_tab")
click(text("All plots")); click(text("P(same molecule) estimate")); draw(); type_into("n_bins", "30"); shot("6_estimate_panel_open_lag_bins_30")
click(text("> Detector definitions")); shot("7_detector_definitions_open")
click(text("> Detector definitions", last=False) if False else text("v Detector definitions"))
click(text("Open burst folder")); shot("8_open_burst_folder_dialog")
click(text("Cancel")); click(text("Save settings")); shot("9_save_settings_dialog")
click(text("Cancel")); click(rect("guide")); shot("10_guide_step_0_waiting_for_Demo")
click(text("Close Tour")); click(rect("help")); shot("11_help")
a.close()
print("done", a.model.settings.threshold, a.model.settings.n_bins)
