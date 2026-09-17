"""The Qt-free half of ChiSurf's console.

Everything needed to *run* Python interactively lives here: input
transformation, completeness detection, compilation, execution, output capture,
traceback formatting, magics, completion and history. Nothing in this package
imports Qt, which is what lets the whole interpreter be tested without a
``QApplication`` -- the thing the qtconsole-based console it replaces could
never do, because execution lived inside an in-process Jupyter kernel.

The Qt widget that draws it is :mod:`chisurf.gui.chinsole`. The seam between
them is five callbacks passed to :class:`~chisurf.core.console.shell.Shell`
(write, display, read_input, clear, edit_file); pass none of them and the shell
is a perfectly usable head-less REPL that writes to ``sys.stdout``.

See Also
--------
:mod:`chisurf.gui.chinsole` : the console widget.
"""

from __future__ import annotations

__all__ = [
    "Shell",
    "ExecutionResult",
    "MagicError",
    "MagicRegistry",
    "register_magic",
    "check_complete",
    "transform_cell",
]


def __getattr__(name: str):
    """Resolve the public names lazily.

    Keeps ``import chisurf.core.console.transform`` cheap for the pieces that
    do not need the whole shell.

    Parameters
    ----------
    name : str

    Returns
    -------
    object
    """
    if name in ("Shell", "ExecutionResult"):
        from chisurf.core.console import shell as _shell

        return getattr(_shell, name)
    if name in ("MagicError", "MagicRegistry", "register_magic"):
        from chisurf.core.console import magics as _magics

        return getattr(_magics, name)
    if name in ("check_complete", "transform_cell"):
        from chisurf.core.console import transform as _transform

        return getattr(_transform, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
