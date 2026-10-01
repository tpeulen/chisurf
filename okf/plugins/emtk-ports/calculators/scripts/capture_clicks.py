"""A real click flow through the drawn hub (simulated pointer and keys only), a screenshot after every step. Usage: <out_dir>."""
import pathlib, sys
import numpy as np
from emtk import keys
from test.gui.emtk_port_parity import emtk_screenshot
import chisurf.plugins.calculator.hub.test.test_emtk_hub_parity as tk

out = pathlib.Path(sys.argv[1]).resolve(); size = tk.SIZE
np.random.seed(7)
app = tk.make_app()


def shot(name):
    tk.draw(app)
    emtk_screenshot(app, out / f"click_{name}_{size[0]}x{size[1]}.png", size)
    tk.draw(app)   # re-lay out with the recording painter's metrics before the next click uses the rects


shot("0_before_any_click_FRET_calculator_selected")
tk.click_entry(app, "kappa2_dist"); shot("1_after_click_on_the_kappa2_entry")
app.key(keys.KEY_DOWN, ""); tk.draw(app, frames=2); shot("2_after_the_Down_key_f_test_selected")
tk.click_entry(app, "kappa2_dist"); tk.draw(app); child = app.child
np.random.seed(7)
tk.type_into_child(app, child.item_rects["r_Dinf"], "0.2"); shot("3_typed_0.2_into_r_D_inf_of_the_embedded_calculator")
tk.click_entry(app, "fret_calculator"); shot("4_after_click_on_the_FRET_entry_again")
tk.type_into_child(app, app.child.active.form.rects["R"], "58"); shot("5_typed_58_into_Distance_DA")
tk.click_entry(app, "kappa2_dist"); shot("6_back_on_kappa2_its_r_D_inf_is_still_0.2")
tk.draw(app); tk.click(app, app.item_rects["guide"]); shot("7_after_click_on_Guide")
app.tour.stop(); tk.click(app, app.item_rects["help"]); shot("8_after_click_on_Help")
print(app.export_settings())
