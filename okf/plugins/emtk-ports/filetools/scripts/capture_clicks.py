"""The File tools hub driven with simulated pointer and keys on the REAL native children. Usage: <out_dir>.
Writes click_*.png and refreshes after_populated_*.png."""
import pathlib, sys
from emtk import keys
from test.gui.emtk_port_parity import emtk_screenshot
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from chisurf.plugins.tttr.filetools.gui.app import FileToolsApp


class HubDriver(Driver):
    def rect(self, name):
        self.draw(1)
        return tuple(self.app.item_rects[name])


def main():
    out = pathlib.Path(sys.argv[1]).resolve(); n = [0]

    def shot(d, name, size=(1200, 800)):
        n[0] += 1; d.draw(3, size=size)
        emtk_screenshot(d.app, out / f"click_{n[0]}_{name}.png", size)

    for size in ((1200, 800), (800, 600)):
        app = FileToolsApp(); d = HubDriver(app, size); d.draw(3)
        if size == (1200, 800): shot(d, "start_split_convert")
        for role in ("tttr_to_pto", "pto_inspector", "tttr_header_edit", "tttr_time_windows", "bid_to_analysis"):
            d.click(d.rect("nav_" + role)); d.draw(3)
            if size == (1200, 800): shot(d, "clicked_" + role)
        emtk_screenshot(app, out / f"after_populated_{size[0]}x{size[1]}.png", size)
        if size == (1200, 800):
            d.type_into("search", "header", enter=False); shot(d, "filter_header_typed")
            d.select_all(); d.key(keys.KEY_BACKSPACE)
            d.click_text("Help"); shot(d, "help_window"); d.click_text("Close Help", last=True)
            d.click_text("Guide"); shot(d, "guide_first_step"); app.tour.stop()
        app.close()


if __name__ == "__main__":
    main()
