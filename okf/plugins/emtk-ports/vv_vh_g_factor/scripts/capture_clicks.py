"""Real-input flow (pointer, wheel, keys, drop only), a screenshot after each step. Usage: <out_dir>. Temp settings only."""
import test.gui.emtk_port_parity  # noqa (first: the stdlib "test" must not win)
import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import chisurf.core.settings as settings
from make_data import make_data
from chisurf.plugins.emtk_test_input import CTRL, Driver
from chisurf.plugins.vv_vh_g_factor.gui.app import create_app
out = pathlib.Path(sys.argv[1]).resolve(); tmp = pathlib.Path(tempfile.mkdtemp())
settings.chisurf_settings_path = tmp / "settings"; (tmp / "settings").mkdir()
files = make_data(tmp / "data"); app = create_app(); ui = Driver(app); n = [0]
def settle():
    import time
    ui.draw(1)
    while app.job.running: time.sleep(0.01); ui.draw(1)
    ui.draw(3)
def shot(name):
    n[0] += 1; ui.screenshot(out / f"click_{n[0]}_{name}.png"); ui.draw()
ui.draw(); shot("empty_window")
app.last_dir = str(tmp / "data"); ui.click_name("load_fast"); shot("Fast_reference_dialog")
ui.click_text("fast.dat"); ui.click_text("Open"); settle(); shot("fast_loaded_G_calculated")
app.model.fp_dt_ns = 0.05; ui.click_name("load_slow"); ui.click_text("slow.dat"); ui.click_text("Open"); settle(); shot("slow_loaded_mixing_estimate")
ui.click_name("background"); settle(); shot("background_correction_on")
ui.type_into(ui.rect("tail_start"), "300"); settle(); shot("typed_300_in_Tail_start")
ui.draw(3); (x1, y1) = app.plot_info["tail"][1]; ui.drag((x1, y1), (x1 - 50, y1)); settle(); shot("dragged_the_yellow_stop_line")
(px, py), (sx, sy) = app.plot_info["pos"], app.plot_info["size"]; ui.wheel(px + sx * .5, py + sy * .5, -3.0); shot("wheel_zoom_over_the_decay_plot")
ui.click_name("manual_g"); settle(); ui.type_into(ui.rect("g_override"), "1.3"); settle(); shot("manual_G_1.3")
ui.click_text("Batch anisotropy"); ui.click_name("add"); shot("Batch_add_files_dialog")
ui.click_text("batch1.dat"); ui.click_text("batch2.dat"); ui.click_text("Open"); settle(); ui.click_name("run"); settle(); shot("batch_run_results")
ui.click_text("G-factor and mixing"); ui.click_name("help"); shot("Help_window"); ui.click_text("Close")
ui.click_name("guide"); shot("guide_started")
print(app.model.message)
