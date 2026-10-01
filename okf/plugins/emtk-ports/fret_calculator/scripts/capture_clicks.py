"""A real click flow through the drawn app (simulated pointer and keys only), a screenshot after every step. Usage: <out_dir>."""
import pathlib, sys
from emtk import keys
from test.gui.emtk_port_parity import emtk_screenshot
import chisurf.plugins.calculator.fret_calculator.tests.test_emtk_fret_calculator_clicks as tk

out = pathlib.Path(sys.argv[1]); size = tk.SIZE
app = tk.make_app()


def shot(name):
    tk.draw(app)
    emtk_screenshot(app, out / f"click_{name}_{size[0]}x{size[1]}.png", size)
    tk.draw(app)   # the screenshot lays out with the pixel painter's font metrics: re-lay out before the next click uses the rects


shot("0_before_any_click")
tk.draw(app); tk.click(app, app.active.form.rects["R"], fx=0.3)
app.key(0x41, "a", 0x04000000)
for ch in "58": app.key(ord(ch), ch); tk.draw(app, frames=1)
shot("1_typed_58_in_Distance_DA_not_committed")
app.key(keys.KEY_RETURN, "\r"); tk.draw(app, frames=2)
shot("2_after_Enter_efficiency_lifetime_rate_follow")
tk.click(app, app.active.form.rects["use_chi"]); shot("3_after_click_on_chi_distribution")
tk.click(app, app.item_rects["tab_homofret"]); shot("4_after_click_on_the_HomoFRET_tab")
tk.spin(app, "R_DA", +1); tk.spin(app, "R_DA", +1); shot("5_after_two_clicks_on_the_R_DA_up_arrow")
tk.press_text(app, "Help"); shot("6_after_click_on_Help")
tk.click(app, tk.text_rect(tk.draw(app), "Close Help")); tk.press_text(app, "Guide"); shot("7_after_click_on_Guide")
print("model:", app.export_settings())
