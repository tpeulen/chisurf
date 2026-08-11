"""Rendering: the scene, the shaders, the camera and the backends that drive them.

``MolView`` resolves lazily, for the reason given in :mod:`chimol`: it is a Qt
widget, and eagerly importing it here made every module in this package require
a window system. That included :mod:`~chimol.renderer.depth_cue` and
:mod:`~chimol.renderer.lighting`, which are a handful of floats each.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checkers and IDEs only
    from .view import MolView

__all__ = [
    "MolView",
]


def __getattr__(name: str):
    """Resolve :class:`~chimol.renderer.view.MolView` on first access.

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
    if name == "MolView":
        from .view import MolView

        globals()["MolView"] = MolView
        return MolView
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List the module's attributes, including the ones not yet imported."""
    return sorted({*globals(), *__all__})
