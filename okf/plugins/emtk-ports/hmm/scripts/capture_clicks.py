"""Real-input flow (pointer, wheel, keys, drop only), a screenshot after each step. Usage: <out_dir>. Temp HOME/settings."""
import test.gui.emtk_port_parity  # noqa (first: the stdlib "test" must not win)
import pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np
import chisurf.core.settings as st
tmp = pathlib.Path(tempfile.mkdtemp()); st.chisurf_settings_path = tmp / "settings"; (tmp / "settings").mkdir()
from make_data import write_trace
from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.core.hmm.gui.app import make_app
out = pathlib.Path(sys.argv[1]).resolve(); trace = write_trace(tmp / "data", "trace.csv")
app = make_app(); ui = Driver(app); n = [0]
def settle():
    ui.draw(1)
    while app.job.busy: time.sleep(0.01); ui.draw(1)
    ui.draw(3)
def shot(name):
    n[0] += 1; ui.screenshot(out / f"click_{n[0]}_{name}.png"); ui.draw()
ui.draw(); shot("empty_window_fit_greyed")
ui.click_name("add_files"); shot("Add_files_dialog")
ui.cancel = ui.click_text("Cancel")
ui.drop(trace); shot("file_dropped_on_the_window")
ui.type_into(app.forms["model"].rects["n_states"], "3"); ui.type_into(app.forms["model"].rects["time_step"], "0.001"); shot("typed_3_states_and_a_bin_width")
ui.click_name("request_run"); shot("fit_started"); settle(); shot("fit_done_tables_and_histogram")
ui.click_text("Dwell times"); shot("Dwell_times_tab")
ui.click_text("> State scan range"); ui.type_into(app.forms["scan"].rects["max_states"], "5"); ui.click_name("request_scan"); settle(); ui.click_text("Scan", last=False); shot("State_scan_BIC_minimum_at_3")
ui.click(app.forms["model"].rects["covariance_type"]); shot("Covariance_list_open"); ui.click_text("diag"); shot("diag_chosen")
d = app.plot_info["trace"]; px, py = d["pos"]; sx, sy = d["size"]; ui.wheel(px + sx * .5, py + sy * .5, -3.0); shot("wheel_zoom_over_the_trace")
ui.click_name("demo"); shot("Demo_trace_loaded")
ui.click_name("help"); shot("Help_window"); ui.click_text("Close")
ui.click_name("guide"); shot("guide_started")
print(app.model.status)
