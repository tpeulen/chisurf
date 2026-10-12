"""Settings ▸ Fonts: the faces, sizes and magnification of the ChiSurf window (emtk, Qt-free).

The form is ``fonts.view.json`` drawn by :func:`emtk.view_form.draw_sections` over
:class:`~.fonts_model.FontSettingsModel`; every change applies on the next frame (emtk
re-rasterises and relayouts) and is saved to ``gui.fonts``. Only the preview lines are
drawn here -- a sample in each role's own font, which a spec cannot express.
"""

from __future__ import annotations

import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.type_scale import math_args, text_style
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, window_size

from .fonts_model import FontSettingsModel

HERE = Path(__file__).parent
VIEW_JSON = HERE / "fonts.view.json"

#: Font role -> the type-scale role its preview line is set in.
_PREVIEW_STYLE = {"code": "code", "prose": "body", "heading": "h2", "caption": "caption"}


class FontSettingsApp(ImApp):
    """The Fonts panel of the Settings tool."""

    def __init__(self, model: FontSettingsModel | None = None) -> None:
        self.model = model or FontSettingsModel()
        self.spec = json.loads(VIEW_JSON.read_text(encoding="utf-8"))
        self.window_size = window_size(self.spec, (900, 760))
        self.form = FormState()
        self.form.custom["font_preview"] = self._draw_preview
        self.item_rects: dict[str, tuple] = {}
        #: ``{role: (text, width)}`` of the preview lines drawn on the last frame.
        self.previews: dict[str, tuple[str, float]] = {}
        self.help_window = EmTkHelpWindow(
            title="Fonts — Help", resource=HERE / "fonts_help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "fonts_guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        super().__init__(self.render)

    def render(self) -> None:
        """One frame: Help / Guide, the form, the help window and the tour."""
        vp = im.get_main_viewport()
        self.form.rects.clear()
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin("Fonts##fonts_settings", flags=im.WindowFlags.NO_RESIZE):
            if action_button("help"):
                self.help_window.show()
            self.item_rects["help"] = im.get_item_rect()
            im.same_line()
            if action_button("guide"):
                self.tour.start()
            self.item_rects["guide"] = im.get_item_rect()
            # A window does not scroll in emtk, a child does: the form scrolls in a short dock.
            avail_w, avail_h = im.get_content_region_avail()
            im.begin_child("##fonts_body", (float(avail_w), max(60.0, float(avail_h))))
            draw_sections(self.spec["sections"], self.model, self.form, titles=True)
            self.item_rects["fonts_body"] = im.end_child()
        im.end()
        box = (*vp.pos, *vp.size)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _draw_preview(
        self, section: dict, model: FontSettingsModel, state: FormState, width: float
    ) -> None:
        """A ``font_preview`` section: the sample line of role ``section["source"]`` in its font."""
        role = str(section.get("source", "ui"))
        text = model.preview_text(role)
        if role == "math":
            colour = im.get_style().color(im.Col.TEXT)
            im.math(text, colour=colour, **math_args("body"))
            drawn = im.get_item_rect()
        elif role == "ui":
            im.text_wrapped(text)
            drawn = im.get_item_rect()
        else:
            with text_style(_PREVIEW_STYLE[role]):
                im.text_wrapped(text)
                drawn = im.get_item_rect()
        description = section.get("description")
        if description:
            im.set_item_tooltip(str(description))
        key = f"preview.{role}"
        state.rects[key] = tuple(drawn)
        self.item_rects[key] = tuple(drawn)
        self.previews[role] = (text, float(drawn[2]) if drawn else 0.0)

    # -- persistence ------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        """Which sections are folded (the fonts themselves live in the settings file)."""
        return {"folds": dict(self.form.folds)}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        folds = settings.get("folds", {}) if isinstance(settings, dict) else {}
        if isinstance(folds, dict):
            self.form.folds.update({str(k): bool(v) for k, v in folds.items()})

    def close(self) -> None:
        """Nothing to release."""


def make_app() -> FontSettingsApp:
    """Build the Fonts panel (the Settings hub's ``fonts`` destination)."""
    return FontSettingsApp()


__all__ = ["FontSettingsApp", "make_app"]
