"""Real-input click sequence on the populated BVA window (pointer / keys only), one PNG per step.

usage: capture_clicks.py <out_dir>   (run from the repo root, with the temp settings env of the brief)
"""
import pathlib, sys, tempfile, time

out = pathlib.Path(sys.argv[1])
from test.gui.emtk_port_parity import emtk_screenshot  # before the burst modules (another `test` package)
from emtk import keys
from emtk.testing import RecordingPainter
from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build
from chisurf.plugins.burst.burst_bva.gui.app import create_app

root = pathlib.Path(tempfile.mkdtemp())
folder = build(root / "measurement")
a = create_app()
a.model.auto_update = False
a.model.donor_channels_text, a.model.acceptor_channels_text = "0", "1"
SIZE = (1200, 800)


def draw(n=2):
    p = None
    for _ in range(n):
        p = RecordingPainter(); a.draw(p, 0, 0, *SIZE)
    return p


def click(rect, fx=.5, clicks=1):
    x, y, w, h = rect
    a.pointer_move(x + w * fx, y + h / 2); draw(1)
    a.press(x + w * fx, y + h / 2, clicks=clicks); draw(1); a.release(); draw(1)


def shot(name):
    draw(); emtk_screenshot(a, out / f"click_{name}.png", SIZE)
    draw(4)    # a pixel-painter frame measures text differently: let the layout settle again before the next input


def text(p, label):
    return [t[:4] for t in p.texts if t[5] == label][-1]


def settle():
    while a.controller.running:
        time.sleep(0.05); draw(1)
    draw(2)


# (a pixel-painter frame drawn before the first typed key made that typing miss its field: the sequence starts without one)
draw()
click(a.item_rects["folder_path"], fx=.3)
for ch in str(folder): a.key(ord(ch), ch); draw(1)
shot("1_typed_folder_path")
click(a.item_rects["run"]); shot("2_after_click_on_Run_computing"); settle(); shot("3_run_done")
x, y, w, h = a.item_rects["bins_x"]; cx, cy = x + w / 2, y + h / 2
a.pointer_move(cx, cy); draw(2); a.press(cx, cy); draw(1)
for s in range(1, 7): a.drag(cx - 6 * s, cy); draw(1)
a.release(); draw(2); shot("4_after_drag_on_Bins_X")
click(a.item_rects["show_static_line"]); shot("5_static_line_unchecked")
draw(); click(a.item_rects["Channel Definitions"]); draw()
click(a.item_rects["donor_microtime"], fx=.3)
a.key(0x41, "a", 0x04000000)
for ch in "10:20, 30:40": a.key(ord(ch), ch); draw(1)
shot("6_channel_tab_typed_microtime_gates")
draw(); click(a.item_rects["BVA Settings"]); draw(); click(a.item_rects["folder"]); shot("7_folder_dialog")
click(text(draw(), "Cancel")); draw(); click(a.item_rects["save_plot"]); shot("8_save_plot_dialog")
click(text(draw(), "Cancel")); draw(); click(a.item_rects["guide"]); click(text(draw(), "Next ►")); shot("9_guide_waiting_for_Folder")
click(text(draw(), "Close Tour")); draw(); click(a.item_rects["help"]); shot("10_help")
a.close()
print("done", a.model.status_text)
