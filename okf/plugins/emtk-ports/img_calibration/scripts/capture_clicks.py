"""The calibration app driven with simulated pointer and keys on real photons (the micro-time shifter's demo SPC).
Usage: <out_dir>. Writes click_*.png and refreshes after_populated_*.png."""
import os, pathlib, sys, tempfile
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.microscopy.img_calibration.test.test_emtk_calibration_clicks import CalDriver
from chisurf.plugins.microscopy.img_calibration.test.test_emtk_calibration_parity import SETUP, _loaded
from chisurf.plugins.tttr.tttr_microtime_shifter.tests.demo_data import build


def main():
    out = pathlib.Path(sys.argv[1]).resolve(); n = [0]
    spc = str(build(pathlib.Path(tempfile.mkdtemp()) / "demo")); os.chdir(pathlib.Path(spc).parent)

    def shot(d, name, size=(1200, 800)):
        n[0] += 1; d.draw(3, size=size)
        emtk_screenshot(d.app, out / f"click_{n[0]}_{name}.png", size)

    for size in ((1200, 800), (800, 600)):
        app = _loaded(spc); d = CalDriver(app, size); d.settle()
        emtk_screenshot(app, out / f"after_populated_{size[0]}x{size[1]}.png", size)
        if size == (1200, 800):
            shot(d, "populated_start")
            d.type_into("sel_conv_start", "130"); d.type_into("sel_bg_vv", "2.5"); shot(d, "conv_start_130_background_vv_2.5_typed")
            d.click(d.rect("add_irf")); d.draw(3); shot(d, "irf_files_chooser")
            d.click(d.text_rect("Cancel")); d.click(d.text_rect("Apply →")); shot(d, "apply_pressed")
            d.click(d.rect("help")); shot(d, "help_window"); d.click_text("Close Help", last=True)
            d.click(d.rect("guide")); shot(d, "guide_first_step"); app.tour.stop()
        app.close()


if __name__ == "__main__":
    main()
