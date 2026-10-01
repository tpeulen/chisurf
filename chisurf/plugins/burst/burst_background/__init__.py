"""Burst background plugin with lazy compatibility Qt entrypoint."""

icon = "🌑"
name = "Spectroscopy:Single-Molecule:Burst Background Estimation"
cli_entrypoint = "burst-background=chisurf.plugins.burst.burst_background.cli:cli"
__all__ = ["BurstBackgroundEstimator", "BackgroundViewModel", "name"]


def __getattr__(name):
    if name == "BurstBackgroundEstimator":
        from .gui.tool import BurstBackgroundEstimator

        return BurstBackgroundEstimator
    if name == "BackgroundViewModel":
        from .view_model import BackgroundViewModel

        return BackgroundViewModel
    raise AttributeError(name)
