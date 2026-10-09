# GlobalView GUI layer; keep Qt hosts lazy for native factory imports.

__all__ = ["GraphWizard", "GlobalViewClient"]


def __getattr__(name):
    if name == "GraphWizard":
        from chisurf.plugins.core.globalview.gui.tool import GraphWizard

        return GraphWizard
    if name == "GlobalViewClient":
        from chisurf.plugins.core.globalview.gui.client import GlobalViewClient

        return GlobalViewClient
    raise AttributeError(name)
