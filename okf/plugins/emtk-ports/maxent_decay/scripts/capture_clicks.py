"""Real-input flow (pointer, wheel, keys, drop only), a screenshot after each step. Usage: <out_dir>. Temp HOME/settings."""
import test.gui.emtk_port_parity  # noqa (first: the stdlib "test" must not win)
import pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np
import chisurf.core.settings as st
tmp = pathlib.Path(tempfile.mkdtemp()); st.chisurf_settings_path = tmp / "settings"; (tmp / "settings").mkdir()
from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.fluorescence_decay.maxent_decay.gui.app import make_app
from chisurf.plugins.fluorescence_decay.maxent_decay.test.test_solver_contract import _problem
out = pathlib.Path(sys.argv[1]).resolve()
y, lamp, dt, t = _problem(n=256)
np.savetxt(tmp / "two_lifetimes.dat", np.column_stack((t, y))); np.savetxt(tmp / "irf.dat", np.column_stack((t, lamp)))
app = make_app(); ui = Driver(app); n = [0]
def settle():
    ui.draw(1)
    while app.jobs.process is not None: time.sleep(0.02); ui.draw(1)
    ui.draw(3)
def shot(name):
    n[0] += 1; ui.screenshot(out / f"click_{n[0]}_{name}.png"); ui.draw()
ui.draw(); shot("empty_window_actions_greyed")
app.last_dir = str(tmp); ui.click_text("Load decay"); shot("Load_decay_dialog")
ui.click_text("two_lifetimes.dat"); ui.click_text("Open"); shot("decay_loaded")
ui.click_text("IRF file"); ui.click_text("irf.dat"); ui.click_text("Open"); shot("IRF_loaded")
app.model.settings.tau_bins = 48; app.model.settings.tau_max = 8.0
ui.click_text("Run MEM"); shot("run_started"); settle(); shot("run_finished_distribution_and_residuals")
ui.type_into(app.forms["mode"].rects["nu"], "0.02"); shot("typed_nu_0.02")
ui.click_name("lcurve"); settle(); shot("L-curve_done_nu_set_to_the_corner")
ui.draw(3); pts = app.plot_info["lcurve"]; ui.click((pts[4][0] - 3, pts[4][1] - 3, 6, 6)); shot("clicked_an_L-curve_point")
ui.draw(3); (x, y0) = app.plot_info["decay"]["left"]; ui.drag((x, y0), (x + 70, y0)); shot("dragged_the_fit_range_box")
info = app.plot_info["decay"]; ui.wheel(info["pos"][0] + info["size"][0] * .5, info["pos"][1] + info["size"][1] * .5, -3.0); shot("wheel_zoom_over_the_decay_plot")
ui.click(app.forms["mode"].rects["mode"]); shot("Mode_list_open"); ui.click_text("FRET"); shot("FRET_mode_distance_grid_donor_missing")
ui.click_text("JSON"); shot("JSON_preferences_editor"); ui.click_text("Close settings")
ui.click_text("Help"); shot("Help_window"); ui.click_text("Close")
ui.click_text("Guide"); shot("guide_started")
print(app.model.status)
