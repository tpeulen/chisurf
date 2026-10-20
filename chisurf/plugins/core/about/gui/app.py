"""About ChiSurf using the same identity content and logo as the Qt dialog."""

import json
from pathlib import Path

from emtk import clipboard, im
from emtk.app import ImApp
from emtk.keys import KEY_ESCAPE
from emtk.texture import Texture
from emtk.view_form import FormState, draw_sections

import chisurf
from chisurf.core.info import __license__, __version__
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import window_size

from .translations import install_translations, tr

HERE = Path(__file__).parent
#: ChiSurf's own licence line; ``{licence}`` is :data:`chisurf.core.info.__license__`.
LICENCE = "Licence: {licence} (documentation: CC BY-SA 4.0)"
#: The two companion libraries that do not share ChiSurf's MIT licence (see docs/licensing.md).
COMPANIONS = (
    "Companion libraries keep their own licences: tttrlib BSD-3-Clause, IMP.bff LGPL-2.1-or-later."
)


class AboutApp(ImApp):
    @property
    def window_title(self):
        """Localize the existing host title without altering its identity."""
        return tr("About ChiSurf")

    def __init__(self):
        """Bind declared actions and help to the existing application identity view."""
        install_translations()
        self.spec = json.loads((HERE / "about.view.json").read_text(encoding="utf-8"))
        self.window_size = window_size(self.spec, (380, 420))
        self.form = FormState()
        self.copy_status = ""
        self.help_window = EmTkHelpWindow(
            title=tr("About ChiSurf — Help"),
            resource=HERE / "help.md",
            owner=self,
        )
        self.tour = EmTkGuidedTour(
            HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda name: self.form.rects.get(name),
        )
        self._copy_step = next(
            step for step in self.tour.steps if step["target"]["name"] == "copy_details"
        )
        self._copy_instruction = self._copy_step["text"]
        self.form.on_used = self._used
        self.logo = None
        logo = Path(chisurf.__file__).parent / "gui/resources/icons/cs_logo.png"
        if logo.is_file():
            self.logo = Texture.from_file(logo)
        super().__init__(self.render)

    def _used(self, action):
        """A copy step requires successful delivery, not merely pressing its button."""
        if action != "copy_details":
            self.tour.notify_used(action)

    def enabled(self, action):
        """Let overlays own input while keeping their awaited real action reachable."""
        if self.close_requested or self.help_window.open:
            return False
        if self.tour.active:
            step = self.tour.steps[self.tour.step_idx]
            return self.tour.awaiting and action == self.tour._target_key(step.get("target"))
        return True

    def open_help(self):
        """Open the application-information reference."""
        if self.close_requested:
            return
        self.help_window.show()
        self.request_frame()

    def start_guide(self):
        """Start a tour without opening help, copying or closing on the user's behalf."""
        if self.close_requested:
            return
        self._copy_step["text"] = self._copy_instruction
        self.tour.start()
        self.request_frame()

    def details_text(self):
        """Return the displayed identity details without including user analysis data."""
        return "\n".join(
            (
                "ChiSurf",
                tr("Fluorescence Data Analysis"),
                tr("Version: {version}").format(version=__version__),
                tr("Development: Thomas-Otavio Peulen"),
                "thomas.peulen@tu-dortmund.de",
                tr("Repository: github.com/fluorescence-tools/chisurf"),
                tr(LICENCE).format(licence=__license__),
                tr(COMPANIONS),
            )
        )

    def copy_details(self):
        """Copy through the host-aware system clipboard and report its result."""
        if self.close_requested:
            return
        if clipboard.copy(self.details_text()):
            self.copy_status = "Application details copied."
            self._copy_step["text"] = self._copy_instruction
            self.tour.notify_used("copy_details")
        else:
            self.copy_status = (
                "Clipboard unavailable. Try another host or copy the displayed details."
            )
            self._copy_step["text"] = self.copy_status
        self.request_frame()

    @property
    def copy_status_text(self):
        """Translate the declared conditional status when the frame is drawn."""
        return tr(self.copy_status)

    def close_about(self):
        """Acknowledge the terminal tour action before requesting host closure."""
        self.tour.notify_used("close_about")
        self.tour.stop()
        self.help_window.hide()
        self.request_close()

    def key(self, key, text="", modifiers=0):
        """Close only the foremost help/tour overlay when Escape is pressed."""
        if key == KEY_ESCAPE and (self.help_window.open or self.tour.active):
            if self.help_window.open:
                self.help_window.hide()
            else:
                self.tour.stop()
            self.request_frame()
            return True
        return super().key(key, text, modifiers)

    def render(self):
        """Draw the identity content, declared actions and owned help overlays."""
        viewport = im.get_main_viewport()
        self.form.rects.clear()
        lines = getattr(self, "_button_lines", 1)
        im.begin("##about", (*viewport.pos, *viewport.size))
        if self.logo is not None:
            im.set_cursor_pos_x(max(8.0, (viewport.size[0] - 64) / 2))
            im.image(self.logo, (64, 64))
        im.push_font_scale(1.6)
        im.set_cursor_pos_x(max(8.0, (viewport.size[0] - im.calc_text_size(tr("ChiSurf"))[0]) / 2))
        im.text(tr("ChiSurf"))
        im.pop_font_scale()
        im.set_cursor_pos_x(8.0)
        im.text(tr("Fluorescence Data Analysis"))
        im.separator()
        im.text(tr("Version: {version}").format(version=__version__))
        im.text(tr("Development: Thomas-Otavio Peulen"))
        im.text(tr("thomas.peulen@tu-dortmund.de"))
        im.text_wrapped(tr("Repository: github.com/fluorescence-tools/chisurf"))
        im.text_wrapped(tr(LICENCE).format(licence=__license__))
        im.text_wrapped(tr(COMPANIONS))
        im.separator()
        section = self.spec["sections"][0]
        buttons = [
            {**button, "label": tr(button["label"]), "description": tr(button["description"])}
            for button in section["buttons"]
        ]
        if self.copy_status:
            for button in buttons:
                if button["action"] == "copy_details":
                    button["description"] += " " + tr(self.copy_status)
        x, y = im.get_cursor_screen_pos()
        row_height = im.get_frame_height() + 4
        # A narrow window or a long locale wraps the buttons onto further lines; the child must be as tall as the
        # lines the previous frame drew, or the wrapped buttons sit outside it and cannot be pressed.
        rows_height = row_height * lines
        height = (
            max(rows_height, viewport.size[1] - (y - viewport.pos[1]) - 8)
            if self.copy_status
            else rows_height
        )
        im.begin_child((x, y, max(viewport.size[0] - 16, 1), height), scrollable=False)
        try:
            draw_sections(
                [{**section, "buttons": buttons}, *self.spec["sections"][1:]],
                self,
                self.form,
                titles=False,
            )
        finally:
            im.end_child()
        im.set_cursor_screen_pos((x, y + rows_height + 4))
        im.end()
        drawn = len({round(rect[1]) for rect in self.form.rects.values()}) or 1
        if drawn != lines:
            self._button_lines = drawn
            self.request_frame()
        self.help_window.draw((*viewport.pos, *viewport.size))
        if not self.help_window.open:
            self.tour.draw(*viewport.size)


def make_app():
    """Build the native About window using the current application locale."""
    from chisurf.emtk.i18n import install

    install()
    return AboutApp()
