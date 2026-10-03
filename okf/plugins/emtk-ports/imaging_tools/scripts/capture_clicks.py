"""The upgraded hub driven with simulated pointer and keys on the REAL native children (temp settings/HOME).
Usage: <out_dir>. Writes click_*.png and after_populated_{1200x800,800x600}.png."""
import pathlib, shutil, sys, tempfile
from emtk import keys
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.microscopy.imaging_tools.gui.app import ImagingToolsApp


class HubDriver(Driver):
    def rect(self, name):
        self.draw(1)
        return tuple(self.app.item_rects[name])


out = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else pathlib.Path('.'); n = [0]


def shot(d, name, size=(1200, 800)):
    n[0] += 1; d.draw(3, size=size)
    emtk_screenshot(d.app, out / f"click_{n[0]}_{name}.png", size)


def main():
    scan = pathlib.Path(tempfile.mkdtemp()) / "Leica_SP8.ptu"
    shutil.copy2(pathlib.Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP8.ptu", scan)  # a copy: the run writes beside it
    for size in ((1200, 800), (800, 600)):
        app = ImagingToolsApp(); d = HubDriver(app, size); d.draw(3)
        if size == (1200, 800): shot(d, "start_browser")
        d.click(d.rect("entry:setup")); d.draw(3)
        if size == (1200, 800): shot(d, "setup_clicked")
        d.click("next"); d.click("next"); d.click("next")
        if size == (1200, 800): shot(d, "next_three_times_flow")
        d.click(d.rect("entry:pixel_intensity")); d.draw(3)
        app.set_pipeline(source=str(scan), hdf5=str(scan.with_suffix(".imaging.h5")))
        emtk_screenshot(app, out / f"after_populated_{size[0]}x{size[1]}.png", size)
        if size == (1200, 800):
            shot(d, "intensity_with_source_banner")
            d.type_into("search", "phasor", enter=False); shot(d, "search_phasor_typed")
            d.select_all(); d.key(keys.KEY_BACKSPACE)
            d.click_text("Run all"); shot(d, "run_all_pressed")
            d.click_text("Help"); shot(d, "help_window"); d.click_text("Close Help", last=True)
            d.click_text("Guide"); shot(d, "guide_first_step"); app.tour.stop()
        app.close()


if __name__ == "__main__":
    main()
