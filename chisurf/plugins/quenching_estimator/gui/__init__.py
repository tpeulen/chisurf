"""The surfaces of QuEst: the project form model, its view spec, the native emtk window and its Qt host.

``form_model.py`` is the Qt-free project model the window binds to; ``quest.view.json`` (and its ``de``/``fr``
translations) is generated from ``settings/parameter_catalog.json`` by ``generate_view_spec.py``. The native window
(``app.py``) is the QuEst card of Structure Tools plus site picking; ``tool.py`` hosts it in a ``ChisurfDockTool``.
Nothing here imports Qt at module scope: ``QuEstTool`` is resolved on first use (PEP 562).
"""

__all__ = ["QuEstTool"]


def __getattr__(name: str):
    """Load the Qt tool lazily: ``from ...gui import QuEstTool`` still works."""
    if name == "QuEstTool":
        from .tool import QuEstTool

        return QuEstTool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
