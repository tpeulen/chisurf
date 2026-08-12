"""The application layer: the Qt main window, its panels, and what they share.

``MolViewPluginWindow`` resolves lazily, for the reason given in
:mod:`chimol.renderer`: it is a ``QMainWindow``, and eagerly importing it here
made *every* module in this package require a window system. That included
:mod:`~chimol.app.picking` -- a projection and an ``argmin`` -- which the
viewer imports for every click, so a host with no toolkit could not select an
atom because of an import three levels above the code doing the work.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checkers and IDEs only
    from .molview_main_window import MolViewPluginWindow

__all__ = [
    "MolViewPluginWindow",
]


def __getattr__(name: str):
    """Resolve :class:`~chimol.app.molview_main_window.MolViewPluginWindow`.

    Parameters
    ----------
    name : str
        The attribute being looked up.

    Returns
    -------
    object

    Raises
    ------
    AttributeError
        If ``name`` is not in :data:`__all__`.
    """
    if name == "MolViewPluginWindow":
        from .molview_main_window import MolViewPluginWindow

        globals()["MolViewPluginWindow"] = MolViewPluginWindow
        return MolViewPluginWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List the module's attributes, including the ones not yet imported."""
    return sorted({*globals(), *__all__})
