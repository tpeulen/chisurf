"""Chimol plugin -- molecular structure viewer for ChiSurf.

Importing this package costs **no GUI toolkit**. That is load-bearing rather
than tidy: ``python -m chisurf.plugins.chimol`` executes this file before it
executes ``__main__``, so an eager ``from ...app import MolViewPluginWindow``
here imported Qt before the Qt-free default entry point was ever reached. The
window resolves through a module-level ``__getattr__`` instead, which is the
same shape ``chimol/app/__init__.py`` and ``chimol/renderer/__init__.py`` use
and for the same reason.

The manifest, the display name and the version stay eager: the plugin loader
reads them, and none of them touches a toolkit.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from chisurf.core.plugin import load_manifest

if TYPE_CHECKING:  # pragma: no cover - for type checkers and IDEs only
    from chisurf.plugins.chimol.chimol.app import MolViewPluginWindow

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Structure:Structure:ChiMOL"

__version__ = "0.2.0"

__all__ = ["MolViewPluginWindow", "main", "name"]


def __getattr__(attribute: str):
    """Resolve the Qt main window on first access.

    Parameters
    ----------
    attribute : str
        The attribute being looked up.

    Returns
    -------
    object

    Raises
    ------
    AttributeError
        If *attribute* is not one this module provides.
    """
    if attribute == "MolViewPluginWindow":
        from chisurf.plugins.chimol.chimol.app import MolViewPluginWindow

        globals()["MolViewPluginWindow"] = MolViewPluginWindow
        return MolViewPluginWindow
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")


def __dir__() -> list[str]:
    """List the module's attributes, including the ones not yet imported."""
    return sorted({*globals(), *__all__})


def _create_window():
    """Build the Qt plugin window at a usable size.

    Returns
    -------
    chisurf.plugins.chimol.chimol.app.MolViewPluginWindow
    """
    from chisurf.plugins.chimol.chimol.app import MolViewPluginWindow

    win = MolViewPluginWindow()
    try:
        win.resize(1000, 700)
    except Exception:
        pass
    return win


def main() -> None:
    """Launch Chimol as a standalone **Qt** application.

    The Qt-free window is :func:`chisurf.plugins.chimol.chimol.host.run.run`,
    and it is what ``python -m chisurf.plugins.chimol`` opens; this is what
    ``--qt`` asks for.
    """
    from qtpy import QtWidgets
    app = QtWidgets.QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    win = _create_window()
    win.show()
    if owns_app:
        sys.exit(app.exec())


if __name__ == "__main__":
    main()


if __name__ == "plugin":
    win = _create_window()
    win.show()
