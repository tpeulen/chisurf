"""Burst browser with lazy legacy Qt exports."""

icon = "📇"
name = "Spectroscopy:Single-Molecule:Burst Browser"
__all__ = ["BurstBrowserWidget", "BurstBrowserViewModel", "name"]


def __getattr__(name):
    if name == "BurstBrowserWidget":
        from .gui.tool import BurstBrowserWidget

        return BurstBrowserWidget
    if name == "BurstBrowserViewModel":
        from .view_model import BurstBrowserViewModel

        return BurstBrowserViewModel
    raise AttributeError(name)
