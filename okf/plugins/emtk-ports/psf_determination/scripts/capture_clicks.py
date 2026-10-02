"""Real-input flow (pointer, wheel, keys, drop only), a screenshot after each step. Usage: <out_dir>. Temp HOME/settings."""
import test.gui.emtk_port_parity  # noqa (first: the stdlib "test" must not win)
import pathlib, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import chisurf.core.settings as st
tmp = pathlib.Path(tempfile.mkdtemp()); st.chisurf_settings_path = tmp / "settings"; (tmp / "settings").mkdir()
from make_data import write_stack
from chisurf.plugins.emtk_test_input import CTRL, Driver
from chisurf.plugins.microscopy.psf_determination.gui.app import make_app
out = pathlib.Path(sys.argv[1]).resolve(); tiff = write_stack(tmp / "data")
app = make_app(); ui = Driver(app); n = [0]
def settle():
    ui.draw(1)
    while app.job.busy: time.sleep(0.01); ui.draw(1)
    ui.draw(3)
def shot(name):
    n[0] += 1; ui.screenshot(out / f"click_{n[0]}_{name}.png"); ui.draw()
ui.draw(); shot("empty_window_actions_greyed")
ui.click_name("load_stack"); shot("Load_stack_dialog"); ui.click_text("Cancel")
ui.drop(tiff); settle(); shot("tiff_dropped_stack_loaded")
ui.type_into(app.forms["psf"].rects["pixel_size_nm"], "100"); ui.type_into(app.forms["psf"].rects["z_step_nm"], "300"); shot("calibration_typed")
ui.click_name("detect_beads"); settle(); shot("beads_detected")
app.canvas.z = 10; ui.draw(3); px, py = app.canvas.pick_pixels(60, 22); ui.click((px - 2, py - 2, 4, 4)); settle(); shot("clicked_a_bead_it_is_fitted")
ui.click_text("z profile"); shot("z_profile_tab")
ui.click_name("fit_all"); settle(); shot("fit_all_batch_results")
x, y, w, h = app.item_rects["stack"]; ui.wheel(x + w * .5, y + h * .5, -3.0); shot("wheel_zoom_over_the_image")
ui.click_text("magma"); shot("colormap_list_open"); ui.click_text("gray"); shot("gray_colormap")
ui.type_into(app.forms["beads"].rects["bead_index"], "2"); settle(); shot("bead_index_2_typed")
ui.click_name("help"); shot("Help_window"); ui.click_text("Close")
ui.click_name("guide"); shot("guide_started")
print(app.model.results_text[:80])
