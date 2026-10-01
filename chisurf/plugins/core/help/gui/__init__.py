"""Help plugin GUI layer."""

from chisurf.plugins.core.help.gui.help_app import HelpApp, HelpGui, HelpModel, make_help_app

__all__ = ["HelpEmtkTool", "HelpWidget", "HelpApp", "HelpGui", "HelpModel", "make_help_app"]

def __getattr__(name):
    """Load optional Qt hosting adapters only when explicitly requested."""
    if name in ['HelpEmtkTool', 'HelpWidget']:
        from . import tool

        return getattr(tool, name)
    raise AttributeError(name)
