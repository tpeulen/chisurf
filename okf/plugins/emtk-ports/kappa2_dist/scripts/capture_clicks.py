"""A real click flow through the drawn app (simulated pointer and keys only), a screenshot after every step. Usage: <out_dir>."""
import os, pathlib, sys, tempfile
import numpy as np
from emtk import keys
from test.gui.emtk_port_parity import emtk_screenshot
import chisurf.plugins.calculator.kappa2_dist.tests.test_emtk_kappa2_dist_clicks as tk

out = pathlib.Path(sys.argv[1]).resolve(); size = tk.SIZE
os.chdir(tempfile.mkdtemp())          # the Save dialog starts in the working folder
np.random.seed(7)
app = tk.make_app()


def shot(name):
    tk.draw(app)
    emtk_screenshot(app, out / f"click_{name}_{size[0]}x{size[1]}.png", size)
    tk.draw(app)   # re-lay out with the recording painter's metrics before the next click uses the rects


shot("0_before_any_click")
tk.draw(app); tk.click(app, app.item_rects["model_type"]); shot("1_after_click_on_the_Model_combo")
painter = tk.draw(app, frames=1); x, y, w, h = tk.text_rect(painter, "Isotropic")
np.random.seed(7); app.press(x + w / 2, y + h / 2); tk.draw(app, frames=1); app.release(); tk.settle(app); shot("2_after_click_on_Isotropic_statistics_recomputed")
tk.draw(app); tk.click(app, app.item_rects["r_Dinf"], fx=0.3)
app.key(0x41, "a", 0x04000000)
for ch in "0.2": app.key(ord(ch), ch); tk.draw(app, frames=1)
shot("3_typed_0.2_in_r_D_inf_not_committed")
np.random.seed(7); app.key(keys.KEY_RETURN, "\r"); tk.settle(app); shot("4_after_Enter_distribution_and_statistics_follow")
for _ in range(3): tk.arrow(app, "n_bins", +1)
shot("5_after_three_clicks_on_the_Bins_up_arrow")
tk.draw(app); tk.click(app, app.item_rects["save"]); shot("6_after_click_on_Save_dialog_open")
tk.click(app, tk.text_rect(tk.draw(app), "kappa2.csv"), fx=0.3); app.key(0x41, "a", 0x04000000)
for ch in "my_k2": app.key(ord(ch), ch); tk.draw(app, frames=1)
shot("7_typed_my_k2_in_the_file_name_field")
tk.click(app, tk.text_rect(tk.draw(app), "Save")); shot("8_after_click_on_the_dialog_Save_status_line_says_where")
tk.press_text(app, "Help"); shot("9_after_click_on_Help")
print("files:", sorted(p.name for p in pathlib.Path.cwd().iterdir()), app.tool.status)
