"""Native EMTK Wizards hub over the Qt-free wizard registry."""
from __future__ import annotations

import importlib

from emtk import im
from emtk.app import ImApp

from ..core.registry import default_wizards
from .strings import install_translations, tr

install_translations()


class WizardHubApp(ImApp):
    def __init__(self):
        self.entries = default_wizards()
        self.selected = self.entries[0].id if self.entries else ""
        self.children = {}
        self._painter = None
        super().__init__(self.render)

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        try:
            super().draw(painter, x, y, w, h)
        finally:
            self._painter = None

    def render(self):
        im.begin(tr("Wizards"), (0, 0, *im.get_main_viewport().size))
        im.heading(tr("Available wizards"), level=2)
        for entry in self.entries:
            label = f"{entry.icon}  {entry.label}" if entry.icon else entry.label
            if im.selectable(label, self.selected == entry.id):
                self.selected = entry.id
            im.set_item_tooltip(tr(entry.description))
        im.separator()
        current = next((entry for entry in self.entries if entry.id == self.selected), None)
        if current is None:
            im.text_wrapped(tr("No wizard selected."))
        else:
            im.heading(tr(current.label), level=2)
            im.text_wrapped(tr(current.description))
            factory = getattr(current, "emtk", None)
            if factory:
                child = self.children.get(current.id)
                if child is None:
                    module, attribute = factory.split(":", 1)
                    child = getattr(importlib.import_module(module), attribute)()
                    self.children[current.id] = child
                if self._painter is not None:
                    viewport = im.get_main_viewport().size
                    self.draw_child(self._painter, child, 0, 150, viewport[0], max(1.0, viewport[1] - 150.0))
                else:
                    im.text_disabled(tr("Native wizard loaded; render host unavailable."))
            else:
                im.text_disabled(tr("Native wizard surface pending; the Qt workflow remains available."))
        im.end()

    def export_settings(self):
        return {"selected": self.selected}

    def restore_settings(self, settings):
        self.selected = str(settings.get("selected", self.selected))

    def close(self):
        for child in self.children.values():
            close = getattr(child, "close", None)
            if callable(close):
                close()
        self.children.clear()


def make_app():
    return WizardHubApp()
