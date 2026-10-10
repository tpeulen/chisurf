"""Burst browser: the native emtk app is :mod:`.gui.app`."""

icon = "📇"
name = "Spectroscopy:Single-Molecule:Burst Browser"
__all__ = ["BurstBrowserViewModel", "name"]


def __getattr__(name):
    if name == "BurstBrowserViewModel":
        from .view_model import BurstBrowserViewModel

        return BurstBrowserViewModel
    raise AttributeError(name)
