"""Real-input click sequence on the Burst IRF & Background window (pointer / keys only), one PNG per step.

usage: capture_clicks.py <out_dir>   (run from the repo root, with the temp settings env of the brief)
"""
import pathlib, sys, tempfile, time

out = pathlib.Path(sys.argv[1])
from test.gui.emtk_port_parity import emtk_screenshot  # before the burst modules (another `test` package)
from emtk import keys
from emtk.testing import RecordingPainter
from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app
from chisurf.plugins.burst.burst_irf_bg.test.demo_data import build

root = pathlib.Path(tempfile.mkdtemp())
path = build(root / "measurement")
a = create_app()
SIZE = (1200, 800)


def draw(n=2):
    p = None
    for _ in range(n):
        p = RecordingPainter(); a.draw(p, 0, 0, *SIZE)
    return p


def rect(name):
    return a.item_rects.get(name) or a.irf_gui.form_state.rects[name]


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
click(text("Open TTTR files")); shot("1_open_tttr_files_dialog")
click(text("Cancel")); a.files_dropped([str(path)]); draw(3); shot("2_dropped_measurement_listed")
type_into("baseline_quantile", "0.3"); type_into("time_window_ms", "2"); shot("3_typed_baseline_quantile_and_time_window")
draw(); click(rect("irf_bg_run")); draw(3); shot("4_after_click_on_Compute")
settle(); shot("5_computed_irf_plot_and_table")
click(text("Backgr" if False else "Background (kHz)")); shot("6_table_sorted_by_background")
draw(); click(text("Channel definition", last=False)); shot("7_channel_definition_window")
click(text("Setups")); click(text("Detectors")); shot("8_channel_editor_detectors")
click(text("IRF parameters")); draw(); click(rect("send_to_mle")); shot("9_send_to_mle_without_a_workflow")
draw(); click(text("Export MLE patterns")); shot("10_export_patterns_dialog")
click(text("Cancel")); draw(); click(rect("guide")); click(text("Next ►")); shot("11_guide_step_2")
click(text("Close Tour")); draw(); click(rect("help")); shot("12_help")
a.close()
print("done", a.controller.status)
