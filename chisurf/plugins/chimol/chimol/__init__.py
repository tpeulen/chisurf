"""ChiMOL -- the molecular viewer.

Nothing is imported eagerly here, and that is deliberate. ``MolView`` pulls in
qtpy *and* ``chisurf``, so importing this package used to require a GUI toolkit
and most of the host application before a caller could reach
:mod:`chimol.renderer.pack` -- a module of numpy array normalisation with no
opinion about either. The engine (the renderer, the scene builders, the shaders,
the layout arithmetic) is meant to run wherever a GPU does, including where no
window system exists, and an eager import at the package root is enough on its
own to make that impossible.

So the names below resolve on first use, through :pep:`562`. ``import chimol``
costs nothing; ``chimol.MolView`` costs Qt, at the moment someone asks for a
window.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type checkers and IDEs only
    from .app import MolViewPluginWindow
    from .cmd import Cmd, cmd
    from .config import _DISPLAY_CONFIG, reload_display_config
    from .renderer.view import MolView

__all__ = [
    "MolView",
    "MolViewPluginWindow",
    "Cmd",
    "cmd",
    "_DISPLAY_CONFIG",
    "reload_display_config",
]

#: Where each public name lives. Kept as data rather than a chain of ``if``
#: statements so that :func:`__dir__` and the guard test can both read it.
_LAZY: dict[str, str] = {
    "MolView": ".renderer.view",
    "MolViewPluginWindow": ".app",
    "Cmd": ".cmd",
    "cmd": ".cmd",
    "_DISPLAY_CONFIG": ".config",
    "reload_display_config": ".config",
}


def __getattr__(name: str):
    """Resolve a public name on first access.

    Parameters
    ----------
    name : str
        The attribute being looked up.

    Returns
    -------
    object
        The requested object, also bound into the module namespace so the
        import happens once.

    Raises
    ------
    AttributeError
        If ``name`` is not one of :data:`__all__`.
    """
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """List the module's attributes, including the ones not yet imported."""
    return sorted({*globals(), *__all__})
