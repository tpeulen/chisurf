"""Native EMTK menu/ribbon switch."""

from __future__ import annotations

from emtk import im
from emtk.app import ImApp


class MenuSwitchApp(ImApp):
    def __init__(self, main_window=None) -> None:
        self.main_window = main_window
        self.status = "Ready to switch the ChiSurf interface."
        super().__init__(self.render)

    def _resolve_window(self):
        # A standalone native factory has no Qt main-window object. The host
        # may inject one when embedding this control; never import ChiSurf's
        # Qt application just to probe for it during native startup.
        return self.main_window

    def render(self) -> None:
        im.begin("Menu Switch", (0, 0, *im.get_main_viewport().size))
        im.heading("Menu Switch", level=2)
        im.text_wrapped("Switch between the traditional menu bar and the ribbon interface.")
        if im.button("🔄 Switch interface"):
            im.set_item_tooltip("Toggle the ChiSurf ribbon/menu interface and keep the preference.")
            window = self._resolve_window()
            toggle = getattr(window, "toggle_ribbon_interface", None)
            if callable(toggle):
                enabled = getattr(window, "_ribbon_integration", None) is None
                toggle(bool(enabled))
                self.status = "Switched to ribbon interface." if enabled else "Switched to normal menu interface."
            else:
                self.status = "The ChiSurf main window is not available yet."
        else:
            im.set_item_tooltip("Toggle the ChiSurf ribbon/menu interface and keep the preference.")
        im.text_wrapped(self.status)
        im.end()


def make_app() -> MenuSwitchApp:
    from chisurf.emtk.i18n import install
    install()
    return MenuSwitchApp()
