"""Lazy exports for the Qt and EMTK plot settings surfaces."""

__all__ = ["PlotSettingsWidget"]


def __getattr__(name):
    if name == "PlotSettingsWidget":
        from .tool import PlotSettingsWidget

        return PlotSettingsWidget
    raise AttributeError(name)
