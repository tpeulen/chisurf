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

import logging
import pathlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from chisurf.core.plugin import load_manifest

if TYPE_CHECKING:  # pragma: no cover - for type checkers and IDEs only
    from chimol.app import MolViewPluginWindow

def _place_chimol_settings_beside_chisurf_s() -> None:
    """Tell chimol to keep its settings where ChiSurf keeps everything else.

    chimol resolves its own settings directory and defaults to ``~/.chimol``,
    because it is packaged to run with no ChiSurf on the path. Inside ChiSurf
    that default is wrong: the plugin and the application should share one
    directory, so a user has one place to look and the standalone and plugin
    runs see the same configuration.

    Injected rather than asked for. chimol used to import
    ``chisurf.core.settings`` itself inside a ``try`` -- which worked, and put
    the dependency in the wrong direction and out of sight: nothing on this
    side said the plugin owned that decision. Here it is a single call at the
    only moment the answer is both known and correct, and chimol names nobody.

    A failure is not fatal. chimol falls back to its own directory, which is a
    working viewer whose settings live somewhere unexpected -- much better than
    a plugin that will not load because a settings path could not be resolved.
    """
    try:
        import chisurf.core.settings as _cs_settings

        from chimol.settings_dir import set_settings_dir

        set_settings_dir(_cs_settings.get_path("settings"))

        # The demo scripts say ``load 148l.pdb`` and expect the host to know
        # where sample structures live. Standalone chimol degrades to "no
        # samples"; inside ChiSurf the checkout's test data is the sample
        # store, and it is injected here for the same reason the settings
        # directory is: the host is the only side that knows the answer.
        from chimol.demos.catalog import set_data_dirs

        _samples = (
            pathlib.Path(__file__).resolve().parents[3]
            / "test" / "data" / "atomic_coordinates"
        )
        set_data_dirs(
            _samples / "pdb_files",
            _samples / "trajectory" / "hgbp1",
        )
    except Exception:  # noqa: BLE001 - a partial install, or a settings backend that moved
        logging.getLogger(__name__).debug(
            "chimol keeps its own settings directory; ChiSurf's was not resolvable",
            exc_info=True,
        )


_place_chimol_settings_beside_chisurf_s()

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
        from chimol.app import MolViewPluginWindow

        globals()["MolViewPluginWindow"] = MolViewPluginWindow
        return MolViewPluginWindow
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")


def __dir__() -> list[str]:
    """List the module's attributes, including the ones not yet imported."""
    return sorted({*globals(), *__all__})


def _open_fps_editor(window, payload: dict) -> None:
    """Open the FPS JSON Editor on ``payload``, reusing an open instance.

    The end of the ``load <file>.fps.json`` wiring: chimol's command layer
    labels the structure and then offers the document to the host through the
    ``on_open_fps_editor`` window hook (the same host-hook shape ``load`` uses
    for ``on_open_structure``), and this is what the hook runs. chiMOL stays
    editor-agnostic -- it names no editor -- and ChiSurf answers with the
    plugin that owns fps.json editing.

    Parameters
    ----------
    window : chimol.app.MolViewPluginWindow
        The window the hook was called on; the editor is kept alive on it.
    payload : dict
        The fps.json document, as :attr:`FpsJsonEditor.fps_json_payload` takes.
    """
    from chisurf.plugins.modelling.fps_json_editor.gui.tool import FpsJsonEditorTool

    tool = getattr(window, "_fps_json_editor", None)
    if tool is None:
        tool = FpsJsonEditorTool()
        # Held on the chimol window, or Qt collects the editor the moment the
        # command returns -- the same reason the plugin launcher keeps its
        # windows on the main window.
        window._fps_json_editor = tool
    tool.editor.fps_json_payload = dict(payload)
    tool.show()
    tool.raise_()
    tool.activateWindow()


def _create_window():
    """Build the Qt plugin window at a usable size.

    Returns
    -------
    chimol.app.MolViewPluginWindow
    """
    from chimol.app import MolViewPluginWindow

    win = MolViewPluginWindow()
    try:
        win.resize(1000, 700)
    except Exception:
        pass
    # The host half of ``load <file>.fps.json``: chimol's command layer calls
    # this when a labelling document is loaded, and this side opens the
    # editor that owns fps.json.
    win.on_open_fps_editor = lambda payload: _open_fps_editor(win, payload)
    return win


def main() -> None:
    """Launch Chimol as a standalone **Qt** application.

    The Qt-free window is :func:`chimol.host.run.run`,
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
