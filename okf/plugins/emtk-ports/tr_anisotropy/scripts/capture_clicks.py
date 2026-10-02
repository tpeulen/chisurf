"""A real-input flow through the drawn app (pointer, wheel, keys, drop only), a screenshot after each step. Usage: <out_dir>. Temp settings only."""
import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import test.gui.emtk_port_parity  # noqa: F401 (before chisurf: the stdlib "test" must not win)
import chisurf, chisurf.core.settings as settings
from make_data import make_data
from emtk import keys
from chisurf.plugins.emtk_test_input import Driver
from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.app import make_app

out = pathlib.Path(sys.argv[1]).resolve()
tmp = pathlib.Path(tempfile.mkdtemp()); settings.chisurf_settings_path = tmp / "settings"; (tmp / "settings").mkdir()
chisurf.fits, chisurf.imported_datasets = [], []
files = make_data(tmp / "data")
app = make_app(); ui = Driver(app); n = [0]
def shot(name):
    n[0] += 1; ui.screenshot(out / f"click_{n[0]}_{name}.png"); ui.draw()

ui.draw(); ui.click_name("Data"); shot("Data_step_opened_by_clicking_its_entry")
ui.type_into_name("irf_vv_path", files["irf_vv"]); shot("typed_the_IRF_VV_path_found")
app.last_dir = str(tmp / "data")
ui.click([t[:4] for t in ui.draw().texts if t[5] == "Browse"][1]); shot("Browse_of_IRF_VH_dialog_open")
ui.click_text("irf_vh.txt"); ui.click_text("Open"); shot("irf_vh_chosen_in_the_dialog")
ui.drop(files["data_vv"], files["data_vh"]); shot("two_files_dropped_on_the_window")
ui.click_text("Next"); ui.click_text("Load / reload data"); shot("Normalize_IRF_after_Load")
ui.draw(3); info = app.plot_info; (x1, y1) = info["ub"]
ui.drag((x1, y1), (x1 - 120, y1)); shot("dragged_the_right_edge_of_the_background_box")
ui.type_into_name("region_lb", "40"); shot("typed_40_in_Background_from")
(px, py), (sx, sy) = info["pos"], info["size"]
ui.wheel(px + sx * 0.3, py + sy * 0.5, -3.0); shot("wheel_zoom_over_the_plot")
ui.click_text("Next"); ui.type_into_name("g_factor", "1.05"); shot("Corrections_g_typed_1.05")
ui.click_text("Next")
ui.click(ui.text_rect(ui.draw(), "1.8", last=False), clicks=2)
for _ in range(12): app.key(keys.KEY_BACKSPACE, ""); ui.draw(1)
ui.type("2.5"); shot("lifetime_cell_open_for_typing")
ui.enter(); shot("cell_committed")
ui.type_into(app.forms["rotation"].rects["new_value"], "3"); ui.click(app.forms["rotation"].rects["add"]); shot("rotation_component_added")
ui.click_text("Save spectra"); shot("Save_spectra_dialog_no_stored_file_in_the_temp_settings")
ui.click_text("Save"); shot("spectra_saved")
ui.click_text("Next"); ui.click_text("Create fits"); shot("Finish_after_Create_fits")
ui.click_text("Help"); shot("Help_window"); ui.click_text("Close")
ui.click_text("Guide"); shot("guide_started")
print(app.model.status)
