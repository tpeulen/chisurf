"""QuEst as a dockable ChiSurf tool.

# What changed, and why it is not cosmetic

The previous plugin was a `QMainWindow` used as a central widget, with a
hand-built `File` menu and `menu_hidden = True` — a window pretending to be
embedded. `ChisurfDockTool` is what the host actually integrates: docks,
drag-and-drop of paths, geometry persistence, and the tool status bar that
plugin messages appear in.

**The import of `quest` is inside `__init__`, not at module scope.** ChiSurf's
discovery imports every plugin at startup; the old file did
`from quest.gui import TransientDecayGenerator` at the top, so simply launching
ChiSurf pulled in QuEst, IMP and numba whether or not anyone opened this tool —
and a broken QuEst install became a broken ChiSurf startup.
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
    except Exception:
        pass
    return "QuEst"


class QuEstTool(ChisurfDockTool):
    """Dockable window hosting QuEst's AutoForm."""

    tool_settings_name = "QuEstTool"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle(_display_name())

        # Imported here, not at module scope: see the module docstring.
        from quest.gui import TransientDecayGenerator

        self.dg = TransientDecayGenerator()
        self.setCentralWidget(self.dg)
        self._init_actions()
        self.resize(1200, 760)
        try:
            self.restore_window_geometry()
        except Exception:
            # A tool that cannot restore its geometry should still open.
            pass

    #: Actions the embedded form does **not** already expose in its own footer.
    #:
    #: The form's footer carries Simulate, Load project and Save project. A
    #: first draft of this toolbar repeated the last two — found by rendering
    #: the widget and looking at it, not by any assertion, which is why
    #: okf/workflows/testing.md says to do that.
    TOOLBAR_ACTIONS = (("Load PDB…", "onLoadPDB"),)

    def _init_actions(self) -> None:
        """File actions, as a toolbar rather than a menu bar.

        A docked tool has no menu bar of its own; the host owns that. The
        previous plugin built its own `File` menu, which is one of the things
        that made it a window pretending to be embedded.
        """
        toolbar = self.addToolBar("QuEst")
        toolbar.setObjectName("quenching_estimator_toolbar")

        for label, slot in self.TOOLBAR_ACTIONS:
            handler = getattr(self.dg, slot, None)
            if handler is None:
                continue
            action = toolbar.addAction(label)
            action.triggered.connect(handler)
        self.ensure_help_toolbar(toolbar=toolbar, title="QuEst — help")


#: The old name. Kept because ChiSurf's legacy AST discovery and the plugin's
#: own test both reference it; it is the same widget.
QuEstWindow = QuEstTool
