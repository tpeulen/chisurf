"""Burst background plugin: the native emtk app is :mod:`.gui.app`."""

icon = "🌑"
name = "Spectroscopy:Single-Molecule:Burst Background Estimation"
cli_entrypoint = "burst-background=chisurf.plugins.burst.burst_background.cli:cli"
__all__ = ["BackgroundViewModel", "name"]


def __getattr__(name):
    if name == "BackgroundViewModel":
        from .view_model import BackgroundViewModel

        return BackgroundViewModel
    raise AttributeError(name)
