"""About ChiSurf using the same identity content and logo as the Qt dialog."""
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.texture import Texture

import chisurf
from chisurf.core.info import __version__


class AboutApp(ImApp):
    window_title = "About ChiSurf"
    window_size = (380, 420)

    def __init__(self):
        self.logo = None
        logo = Path(chisurf.__file__).parent / "gui/resources/icons/cs_logo.png"
        if logo.is_file():
            self.logo = Texture.from_file(logo)
        super().__init__(self.render)

    def render(self):
        viewport = im.get_main_viewport()
        im.begin("##about", (*viewport.pos, *viewport.size))
        if self.logo is not None:
            im.set_cursor_pos_x(max(8.0, (viewport.size[0] - 64) / 2))
            im.image(self.logo, (64, 64))
        im.push_font_scale(1.6)
        im.set_cursor_pos_x(max(8.0, (viewport.size[0] - im.calc_text_size("ChiSurf")[0]) / 2))
        im.text("ChiSurf")
        im.pop_font_scale()
        im.set_cursor_pos_x(8.0)
        im.text("Fluorescence Data Analysis")
        im.separator()
        im.text(f"Version: {__version__}")
        im.text("Development: Thomas-Otavio Peulen")
        im.text("thomas.peulen@tu-dortmund.de")
        im.text_wrapped("Repository: github.com/fluorescence-tools/chisurf")
        im.separator()
        if im.button("Close"):
            self.request_close()
        im.set_item_tooltip("Close the About ChiSurf window.")
        im.end()


def make_app():
    from chisurf.emtk.i18n import install

    install()
    return AboutApp()
