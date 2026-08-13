"""ChiMol package entry point.

Three run modes, of which the **default needs no GUI toolkit**::

    python -m chisurf.plugins.chimol.chimol             # Qt-free desktop window
    python -m chisurf.plugins.chimol.chimol --qt        # the Qt plugin window
    python -m chisurf.plugins.chimol.chimol cli ...     # headless ptpython REPL

The default opens chimol's own window on a ``rendercanvas`` surface and drives
the same viewer and the same command layer the Qt window does; ``--qt`` is the
option, not the assumption. See :mod:`chimol.host.run`.
"""

from __future__ import annotations

import os
import sys


def _dispatch(argv: list[str] | None = None) -> int:
    """Route the command line to one of the three run modes.

    Parameters
    ----------
    argv : list of str, optional
        Arguments after the program name; ``sys.argv[1:]`` by default.

    Returns
    -------
    int
        A process exit code.
    """
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0].lower() == "cli":
        # Strip the "cli" subcommand so argparse in cli.main() sees clean args
        sys.argv = [sys.argv[0] + " cli"] + args[1:]
        from .cli import main as cli_main

        cli_main()
        return 0

    if "--qt" in args:
        from .. import main as gui_main

        gui_main()
        return 0

    # Choose the toolkit-free host *before* importing anything that can reach
    # `renderer.view`, because `class MolView(WidgetBase)` binds its base at
    # class-definition time -- a choice made after that import is made too late.
    #
    # This has to be a choice rather than a fallback. chimol runs as a plugin
    # inside a PyQt application, so Qt imports perfectly well here; picking the
    # base class from mere importability made `MolView` a `QWidget` even on this
    # path, and building a widget with no `QApplication` aborts the process
    # ("QWidget: Must construct a QApplication before a QWidget", SIGABRT)
    # before a single frame is drawn. `setdefault`, not assignment, so an
    # explicit `CHIMOL_TOOLKIT` from the environment still wins.
    os.environ.setdefault("CHIMOL_TOOLKIT", "none")

    from .host.run import main as run_main

    return run_main(args)


if __name__ == "__main__":
    raise SystemExit(_dispatch())
