"""Native Wizards hub: the list of wizards on the left, the chosen wizard built lazily and embedded on the right.

The catalogue is Qt-free data (:mod:`..core.registry`); each entry names the wizard's own native app (``emtk``). The hub is the
shared :class:`~chisurf.plugins.calculator.hub.gui.app.CalculatorHubApp` (child lifetime, pointer / wheel / key / drop
forwarding, arrow keys on the list, settings of the children); only the window, the catalogue and the texts are the wizards'.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from emtk import im

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.calculator.hub.gui.app import CalculatorHubApp

from ..core.registry import default_wizards
from .strings import install_translations, tr

install_translations()

HERE = Path(__file__).parent
_LIST_MAX_W = 190.0
_LIST_MIN_W = 120.0
_HEADER_H = 70.0


class WizardHubApp(CalculatorHubApp):
    """Two panels: the wizard list, and the chosen wizard under its description."""

    window_title = "ChiSurf Wizards"

    def __init__(self, entries=None):
        super().__init__(entries=default_wizards() if entries is None else entries)
        self.help_window = EmTkHelpWindow(
            title="Wizards - Help",
            resource=HERE / "help.md",
            owner=self,
            on_start_guide=self.start_guide,
            size=(700.0, 480.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda name: self.item_rects.get(name),
            owner=self,
            wait_for_controls=True,
        )

    # -- children: the entry names its own factory ----------------------------------------------------------------- #
    def select(self, id):
        """Select a wizard, building its app on first use; returns the app (``None`` when it could not be built)."""
        entry = next((e for e in self.entries if e.id == id), None)
        if entry is None:
            raise ValueError("Unknown wizard: " + id)
        self.selected = id
        self.error = ""
        if id not in self.children:
            try:
                if not entry.emtk:
                    raise RuntimeError(
                        "it has no native window yet; the Qt wizard remains available"
                    )
                module, attr = entry.emtk.split(":")
                child = getattr(importlib.import_module(module), attr)()
                setter = getattr(child, "set_frame_request_callback", None)
                if callable(setter):
                    setter(self.request_frame)
                self.children[id] = child
                saved = self._pending_settings.pop(id, None)
                if saved is not None and callable(getattr(child, "restore_settings", None)):
                    child.restore_settings(saved)
            except Exception as exc:  # noqa: BLE001 - shown in the header, as the Qt hub showed it in the page
                self.error = f"Could not load '{entry.label}': {exc}"
        return self.children.get(id)

    def restore_settings(self, settings):
        """Restore the selection and the wizards' own settings; an unknown wizard or malformed entry is ignored."""
        if not isinstance(settings, dict):
            return
        known = {e.id for e in self.entries}
        saved = settings.get("children")
        if isinstance(saved, dict):
            for id, value in saved.items():
                if id not in known or not isinstance(value, dict):
                    continue
                child = self.children.get(id)
                if child is not None and callable(getattr(child, "restore_settings", None)):
                    child.restore_settings(value)
                else:
                    self._pending_settings[id] = value
        if settings.get("selected") in known:
            self.select(settings["selected"])

    # -- frame ----------------------------------------------------------------------------------------------------- #
    def render(self):
        width, height = im.get_main_viewport().size
        # Wide enough for the longest label behind its icon, and no wider: the wizard gets the rest.
        fit = (
            max((im.calc_text_size(e.label)[0] for e in self.entries), default=0.0)
            + im.selectable_icon_width()
            + 3.0 * im.get_style().frame_padding[0]
        )
        left = min(_LIST_MAX_W, max(_LIST_MIN_W, width * 0.15, fit))
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((left, height), im.Cond.ALWAYS)
        if im.begin(tr("Wizards"), flags=im.WindowFlags.NO_RESIZE):
            first = last = None
            for entry in self.entries:
                if im.selectable(entry.label, self.selected == entry.id, icon=entry.icon):
                    self.select(entry.id)
                    self.tour.notify_used("wizards_list")
                im.set_item_tooltip(entry.description)
                rect = im.get_item_rect()
                first, last = first or rect, rect
                self.item_rects["entry:" + entry.id] = rect
            if first is not None:
                self.item_rects["wizards_list"] = (
                    first[0],
                    first[1],
                    first[2],
                    last[1] + last[3] - first[1],
                )
            im.separator()
            if im.button(tr("Guide")):
                self.start_guide()
            im.set_item_tooltip(tr("A short walk through the hub."))
            self.item_rects["guide"] = im.get_item_rect()
            im.same_line()
            if im.button(tr("Help")):
                self.show_help()
            im.set_item_tooltip(tr("What the hub is and how the embedded wizards are used."))
            self.item_rects["help"] = im.get_item_rect()
        im.end()
        entry = next((e for e in self.entries if e.id == self.selected), None)
        hint = tr("Select a wizard on the left to get started.")
        wrap = max(width - left - 16.0, 50.0)
        shown = [entry.label if entry else "", entry.description if entry else hint, self.error]
        header_h = max(
            _HEADER_H, 10.0 + sum(im.calc_text_size(t, wrap_width=wrap)[1] for t in shown if t)
        )
        im.set_next_window_pos((left, 0), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, header_h), im.Cond.ALWAYS)
        if im.begin(
            "Wizard description", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        ):
            if entry:
                im.text_unformatted(entry.label)
                im.text_wrapped(entry.description)
            else:
                im.text_wrapped(hint)
            if self.error:
                im.text_wrapped(self.error)
            self.item_rects["description"] = im.get_item_rect()
        im.end()
        self.child_box = (left, header_h, max(1.0, width - left), max(1.0, height - header_h))
        if self.child is not None:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        self.help_window.draw((0.0, 0.0, width, height))
        self.tour.draw(width, height)


def make_app():
    """Build the hub (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return WizardHubApp()


__all__ = ["WizardHubApp", "make_app"]
