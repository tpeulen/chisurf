"""Real-input click sequence on the photon-by-photon kinetics window (pointer / keys only), one PNG per step.

usage: capture_clicks.py <out_dir>   (run from the repo root, with the temp settings env of the brief)
"""
import pathlib, sys, tempfile, time

out = pathlib.Path(sys.argv[1])
from test.gui.emtk_port_parity import emtk_screenshot  # before the burst modules (another `test` package)
from emtk import keys
from emtk.testing import RecordingPainter
from chisurf.plugins.burst.burst_gs.gui.app import create_app

a = create_app()
SIZE = (1200, 800)
root = pathlib.Path(tempfile.mkdtemp())
(root / "m1.bur").write_text("First Photon\tLast Photon\n")


def draw(n=2):
    p = None
    for _ in range(n):
        p = RecordingPainter(); a.draw(p, 0, 0, *SIZE)
    return p


def rect(name):
    return a.item_rects.get(name) or a.gs_gui.form_state.rects[name]


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
click(rect("use_simulation")); shot("1_after_click_on_Use_Simulation_Mode")
type_into("sim_k_forward", "4000"); type_into("sim_n_bursts", "60"); type_into("sim_photons_per_burst", "100"); type_into("max_iterations", "300")
shot("2_typed_simulation_fields")
click(text("▶ Fit Kinetics")); draw(3); shot("3_after_click_on_Fit_running")
settle(); shot("4_fit_done_tables_and_rates_plot")
click(text("FRET states")); shot("5_fret_states_tab")
click(text("Kinetics dynamics")); type_into("n_states", "3"); click(text("▶ Fit Kinetics")); settle(); shot("6_three_states_fitted")
click(rect("scan_transition_time")); type_into("transit_points", "8"); click(text("▶ Fit Kinetics")); settle(); shot("7_transition_time_scan")
click(text("💾 Export CSV")); shot("8_export_dialog")
click(text("Cancel")); click(text("Open BUR files")); shot("9_open_bur_files_dialog")
click(text("Cancel")); a.files_dropped([str(root / "m1.bur")]); draw(3); click(rect("use_simulation")); shot("10_dropped_table_listed_data_panel")
click(rect("guide")); click(text("Next ►")); shot("11_guide_waiting_for_Simulate")
a.key(keys.KEY_ESCAPE, ""); draw(2); click(rect("help")); shot("12_help")
a.close()
print("done", a.controller.status)
