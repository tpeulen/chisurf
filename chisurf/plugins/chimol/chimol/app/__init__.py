"""The ChiSurf/Qt integration layer: the main window, its panels, their glue.

Everything here needs a window system, and that is now the *definition* of the
package rather than an accident of where a file was first written. It used to
hold engine code too -- picking, the command dispatcher and its history, the
demo catalogue, the CLI -- none of which touches Qt, and which the engine
therefore had to reach *up* into this package to use: the command language
imported ``app`` to find a demo, the viewer imported ``app`` to resolve a
click. Those have moved to where they belong (:mod:`chimol.renderer.picking`,
:mod:`chimol.cmd.dispatch`, :mod:`chimol.demos`, :mod:`chimol.cli`), and the
dependency now runs one way: this layer imports the engine, never the reverse.

The CLI took a detour worth recording: it is toolkit-free but built its
prompt on ``chisurf.core.console``, so moving it merely swapped a Qt
dependency for a ChiSurf one -- which the seam test caught. The fix was not
to leave it here but to make the routing *attachable*: :mod:`chimol.repl`
owns the protocol, ChiSurf's console is attached when it is importable, and
chimol carries the same rule for when it is not.

``MolViewPluginWindow`` still resolves lazily, for the reason given in
:mod:`chimol.renderer` -- it is a ``QMainWindow``, and importing it eagerly
here made every module in the package require a window system.
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
