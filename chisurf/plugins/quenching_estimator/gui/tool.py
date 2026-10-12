"""QuEst as a dockable ChiSurf tool: the Qt host of the native emtk window.

The window itself is :func:`.app.make_app` -- the QuEst card of Structure Tools
plus attachment-site picking -- drawn by emtk. This class only *hosts* it, the
way ``lightpath_simulator`` hosts its emtk app: a ``ChisurfDockTool`` gives it
the docking, geometry persistence and status bar the host integrates. The
PyQt form this tool used to embed (``TransientDecayGenerator`` of the former
standalone QuEst package) is gone with that package.

Nothing heavy is imported at module scope: ChiSurf's discovery imports every
plugin at startup, and the engine (``core/``) reaches IMP.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.gui.widgets.tools import ChisurfDockTool

_MANIFEST_PATH = Path(__file__).parents[1] / "manifest.json"


def _display_name() -> str:
    try:
        from chisurf.core.plugin import load_manifest

        manifest = load_manifest(_MANIFEST_PATH)
        if manifest is not None:
            return manifest.display_name
    except Exception:  # noqa: BLE001 - a title is not worth failing the tool over
        pass
    return "QuEst"


class QuEstTool(ChisurfDockTool):
    """Dockable window hosting the native QuEst window."""

    tool_settings_name = "QuEstTool"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle(_display_name())

        from emtk.qt_host import ControlHost

        from .app import make_app

        self.quest_app = make_app()
        self.host = ControlHost(self.quest_app, background=(30, 32, 38))
        self.setCentralWidget(self.host)
        self.resize(1200, 760)
        try:
            self.restore_window_geometry()
        except Exception:  # noqa: BLE001 - a tool that cannot restore its geometry should still open
            pass


#: The old name, kept because ChiSurf's legacy AST discovery references it.
QuEstWindow = QuEstTool
