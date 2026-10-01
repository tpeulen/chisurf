"""A real click flow through the drawn app (simulated pointer and keys only), a screenshot after every step. Usage: <out_dir>."""
import os, pathlib, sys, tempfile
from emtk import keys
from test.gui.emtk_port_parity import emtk_screenshot
import chisurf.plugins.burst.accurate_fret.test.test_emtk_accurate_fret_clicks as tk
from chisurf.plugins.burst.accurate_fret.test.test_emtk_accurate_fret_parity import _bursts
from chisurf.plugins.burst.accurate_fret.test.test_accurate_fret_plugin import TAU_D0

out = pathlib.Path(sys.argv[1]).resolve(); size = tk.SIZE
work = pathlib.Path(tempfile.mkdtemp()); os.chdir(work)
bursts = _bursts(work)
app = tk.create_app(); app.model.n_bootstrap = 0; app.model.donor_lifetime = TAU_D0


def shot(name):
    tk.draw(app)
    emtk_screenshot(app, out / f"click_{name}_{size[0]}x{size[1]}.png", size)
    tk.draw(app)   # re-lay out with the recording painter's metrics before the next click uses the rects


tk.draw(app, frames=3); shot("0_before_any_click_empty")
tk.click(app, tk.rect_of(app, "filename")); shot("1_after_click_on_Open_burst_table_dialog")
tk.click(app, tk.text_rect(tk.draw(app), bursts.name)); shot("2_after_click_on_the_file_entry")
tk.click(app, tk.text_rect(tk.draw(app), "Open")); tk.wait(app); shot("3_after_click_on_Open_table_loaded_channels_mapped")
tk.click(app, tk.rect_of(app, "Calibrate")); tk.wait(app); shot("4_after_click_on_Calibrate")
tk.click(app, tk.rect_of(app, "Populations")); shot("5_after_click_on_the_Populations_tab")
tk.fold(app, "Channels"); tk.fold(app, "Photophysics"); shot("6_after_click_on_the_Photophysics_header")
tk.type_into(app, "forster_radius", "55"); shot("7_typed_55_into_Forster_R0_Enter")
tk.fold(app, "Photophysics"); tk.fold(app, "Data, session and catalogue actions"); tk.press_text(app, "Export per-burst CSV"); shot("8_after_click_on_Export_per_burst_CSV_dialog")
tk.click(app, tk.text_rect(tk.draw(app), "Cancel")); tk.click(app, tk.rect_of(app, "help")); shot("9_after_Cancel_and_click_on_Help")
print(app.controller.status, app.model.forster_radius)
