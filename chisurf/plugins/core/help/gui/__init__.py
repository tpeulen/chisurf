"""Help plugin GUI layer."""

from chisurf.plugins.core.help.gui.help_app import HelpApp, HelpGui, HelpModel, make_help_app

__all__ = ["HelpEmtkTool", "HelpApp", "HelpGui", "HelpModel", "make_help_app"]


def __getattr__(name):
    """Load the optional Qt hosting adapter only when explicitly requested."""
    if name == "HelpEmtkTool":
        from . import tool

        return getattr(tool, name)
    raise AttributeError(name)
