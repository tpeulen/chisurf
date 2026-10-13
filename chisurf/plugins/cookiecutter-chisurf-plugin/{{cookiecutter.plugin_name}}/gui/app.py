"""{{ cookiecutter.plugin_display_name }}: the emtk window, drawn from ``{{ cookiecutter.plugin_name }}.view.json``.

The window is declared, not coded. Every control is a section of the view spec bound to
:class:`~.view_model.{{ cookiecutter.class_prefix }}ViewModel`: a ``value`` section edits an attribute, a
``button_row`` calls a method, an ``info`` section shows what a method returns. Add controls by
adding sections; write draw code only for what a spec cannot express (a plot, an image).

The ``?`` (``help.md``) and **Guide** (``guide.json``) buttons are the spec's first button row.
Both shells open this app through the manifest's ``emtk`` entry; the ``--qt`` window hosts it.
No Qt is imported here or anywhere in the plugin.
"""

from __future__ import annotations

import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import window_size

from .view_model import {{ cookiecutter.class_prefix }}ViewModel

HERE = Path(__file__).parent
SPEC = HERE / "{{ cookiecutter.plugin_name }}.view.json"


class {{ cookiecutter.class_prefix }}App(ImApp):
    """The {{ cookiecutter.plugin_display_name }} window.

    Parameters
    ----------
    model : {{ cookiecutter.class_prefix }}ViewModel, optional
        The window's state; tests pass one with a fake client.
    """

    window_title = "{{ cookiecutter.plugin_display_name }}"

    def __init__(self, model: {{ cookiecutter.class_prefix }}ViewModel | None = None) -> None:
        self.model = model or {{ cookiecutter.class_prefix }}ViewModel()
        spec = json.loads(SPEC.read_text(encoding="utf-8"))
        self.sections = spec["sections"]
        self.window_size = window_size(spec, (900, 600))
        #: The tour points at the controls the form remembers (``attr`` and button ``action`` names).
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.form.rects.get(key),
        )
        self.form = FormState(on_used=self.tour.notify_used)
        self.help_window = EmTkHelpWindow(
            title="{{ cookiecutter.plugin_display_name }} - Help",
            resource=HERE / "help.md",
            owner=self,
            on_start_guide=self.tour.start,
        )
        self.model.on_help = self.help_window.show
        self.model.on_guide = self.tour.start
        super().__init__(gui=self.render, continuous=False)

    def render(self) -> None:
        """One frame: the declared form fills the window; help and tour draw over it."""
        vp = im.get_main_viewport()
        im.set_next_window_pos(vp.pos, im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin(
            "##{{ cookiecutter.plugin_name }}",
            flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE,
        ):
            draw_sections(self.sections, self.model, self.form)
        im.end()
        self.help_window.draw((*vp.pos, *vp.size))
        self.tour.draw(*vp.size)

    def export_settings(self) -> dict:
        """What the window remembers between sessions (the manifest's ``statefulness``)."""
        return self.model.export_settings()

    def restore_settings(self, state: dict) -> None:
        """Restore :meth:`export_settings`; an unusable value is ignored."""
        self.model.restore_settings(state or {})


def make_app(**kwargs) -> {{ cookiecutter.class_prefix }}App:
    """The factory named by the manifest's ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return {{ cookiecutter.class_prefix }}App()


__all__ = ["{{ cookiecutter.class_prefix }}App", "make_app"]
