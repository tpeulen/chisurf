"""The upgraded emtk app driven with simulated pointer and keys: a static line, a second state, the dynamic line, the lines
tab, Save CSV, Push, Help, Guide. Usage: <out_dir>. Writes click_*.png and after_populated_{1200x800,800x600}.png."""
import os, pathlib, sys, tempfile
from emtk import keys
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.fret_line.gui.app import FRETLineApp
from chisurf.plugins.fret_line.test.test_emtk_fret_line_clicks import edit_cell, pick, tab

out = pathlib.Path(sys.argv[1]).resolve(); n = [0]
os.chdir(tempfile.mkdtemp())


def shot(d, name, size=(1200, 800)):
    n[0] += 1; d.draw(3, size=size)
    emtk_screenshot(d.app, out / f"click_{n[0]}_{name}.png", size)


for size in ((1200, 800), (800, 600)):
    app = FRETLineApp(); d = Driver(app, size); d.draw(3); m = app.model
    if size == (1200, 800): shot(d, "start")
    tab(d, "Sweep"); d.type_into("minimum", "20"); d.type_into("maximum", "120")
    if size == (1200, 800): shot(d, "sweep_range_typed")
    d.click("add_line")
    if size == (1200, 800): shot(d, "static_line_added")
    tab(d, "Components"); d.click("add_component")
    edit_cell(d, "RDA0", "Value", "70")
    if size == (1200, 800): shot(d, "second_component_RDA0_typed_70")
    tab(d, "Sweep"); d.click("sweep_filter", fx=0.3); d.type_text("fraction · C0"); d.enter()
    d.type_into("minimum", "0"); d.type_into("maximum", "1")
    if size == (1200, 800): shot(d, "sweep_fraction_C0")
    d.click("add_line")
    emtk_screenshot(app, out / f"after_populated_{size[0]}x{size[1]}.png", size)
    if size == (1200, 800):
        tab(d, "FRET lines"); shot(d, "lines_tab")
        x, y, w, h = d.text_rect("Line 1", last=False); d.click_at(d.text_rect("Show")[0] + 8, y + h / 2); shot(d, "line_1_hidden_by_its_checkbox")
        d.click("show_all")
        d.click("save_csv"); shot(d, "save_csv_chooser")
        d.click(d.text_rect("Cancel")); d.click("push"); d.draw(3); shot(d, "push_notice")
        d.click(d.text_rect("OK")); d.draw(2)
        d.click_text("Help"); shot(d, "help_window"); d.click_text("Close Help", last=True)
        d.click_text("Guide"); shot(d, "guide_first_step"); app.tour.stop()
    app.close()
