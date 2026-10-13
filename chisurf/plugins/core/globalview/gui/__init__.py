"""GlobalView GUI layer: the native emtk app (:func:`.app.make_app`) and its client."""

__all__ = ["GlobalViewClient"]


def __getattr__(name):
    if name == "GlobalViewClient":
        from chisurf.plugins.core.globalview.gui.client import GlobalViewClient

        return GlobalViewClient
    raise AttributeError(name)
