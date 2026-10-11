"""Switch the owning ChiSurf host interface without creating another window."""

from chisurf.core.api.context import PluginContext
from chisurf.core.support.i18n import tr


def switch_interface(context: PluginContext) -> dict:
    """Toggle the supplied main window and report the actual resulting state."""
    window = context.main_window
    toggle = getattr(window, "toggle_ribbon_interface", None)
    if window is None or not callable(toggle):
        return {
            "ok": False,
            "available": False,
            "error": tr("Open Menu Switch from a ChiSurf main window to change its interface."),
        }
    before = getattr(window, "_ribbon_integration", None) is not None
    toggle(not before)
    enabled = getattr(window, "_ribbon_integration", None) is not None
    if enabled == before:
        return {
            "ok": False,
            "available": True,
            "error": tr("The ChiSurf interface did not change. Check the host log for details."),
        }
    return {"ok": True, "available": True, "ribbon_enabled": enabled}
