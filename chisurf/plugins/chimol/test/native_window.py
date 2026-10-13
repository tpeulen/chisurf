"""The toolkit-free chimol window the suite drives, in-process.

What this replaces
------------------
The suite used to build ``chimol.hosts.qt.window.MolViewPluginWindow`` -- a
``QMainWindow`` around a ``QWidget`` viewer -- and pump a ``QApplication``
between steps. That window is the legacy host: ChiSurf shows chimol through
:class:`chimol.hosts.native.app.ChimolApp` (an offscreen ``rendercanvas``
blitted onto an emtk surface by ``chisurf.plugins.chimol.app``), and the
browser and ``python -m chimol`` build the same thing. So the window a test
drives is that one: the same ``HeadlessViewer``, the same ``Cmd`` wired to the
in-viewport prompt, the same chrome, with no toolkit in the process.

Why in-process works now
------------------------
``ChimolApp`` builds a ``HeadlessViewer`` whatever was imported first (chimol
``36d8739``), so a test module here no longer needs the child process that
:mod:`.toolkit_free` uses for the "Qt must be unimportable" proofs.

Use
---
    from native_window import NativeWindow

    win = NativeWindow(size=(700, 500))
    win.load_structure_from_path(PDB_148L)
    win.do("bg_color white")
    win.pump()          # draw a frame
    win.close()
"""

from __future__ import annotations

import pathlib
import weakref

#: The repository root (``chisurf/plugins/chimol/test`` is four levels down).
ROOT = pathlib.Path(__file__).resolve().parents[4]

#: Owner's rendering test structures: T4 lysozyme for a protein, HIV reverse
#: transcriptase for protein plus nucleic acid.
PDB_DIR = ROOT / "test" / "data" / "atomic_coordinates" / "pdb_files"
PDB_148L = PDB_DIR / "148l.pdb"
PDB_1RTD = PDB_DIR / "1rtd.pdb"


#: Every live window, so :func:`process_events` can draw them all -- what a
#: test used to get from ``QApplication.processEvents``.
_LIVE: "weakref.WeakSet[NativeWindow]" = weakref.WeakSet()


def process_events(frames: int = 1) -> None:
    """Draw *frames* frames on every live window.

    The toolkit-free host has no event queue to drain: a command applies at
    once and a frame is drawn when asked for. So the one thing a pumped
    ``QApplication`` still did for a test -- render, so that what a frame
    computes (the scene, the chrome, the readouts) is current -- is this.
    """
    for window in list(_LIVE):
        window.pump(frames)


def native_viewer(size: tuple[int, int] = (900, 600), **viewer_options):
    """Return the viewer of a new :class:`NativeWindow`.

    For tests that only want a viewer with a renderer. The window stays alive
    as long as the viewer does (``viewer.native_window``).
    """
    if "renderer_factory" in viewer_options:
        # A test that brings its own backend (the scene-only sink, a stub)
        # wants the viewer on it, with no canvas of ours behind.
        from chimol.core.viewer import HeadlessViewer

        return HeadlessViewer(**viewer_options)
    window = NativeWindow(size=size, **viewer_options)
    window.viewer.native_window = window
    return window.viewer


class NativeWindow:
    """A ``ChimolApp`` with the handful of names the suite's tests use.

    Parameters
    ----------
    size : tuple of int, optional
        Canvas size in logical pixels.
    **viewer_options
        Passed through to the viewer (``scale_factor`` and the like).

    Attributes
    ----------
    app : chimol.hosts.native.app.ChimolApp
        The assembled application.
    viewer : chimol.core.viewer.HeadlessViewer
        The viewer.
    cmd : chimol.commands.Cmd
        The command layer, wired to the in-viewport prompt.
    host : chimol.hosts.base.ViewerHost
        The host services the commands reach (``load``, ``demo``, ...).
    """

    def __init__(self, size: tuple[int, int] = (900, 600), **viewer_options) -> None:
        from chimol.hosts.native.app import ChimolApp

        self.app = ChimolApp(size=size, backend="offscreen", **viewer_options)
        self.viewer = self.app.viewer
        self.cmd = self.app.cmd
        self.host = self.app.host
        self.renderer = self.app.renderer
        self.size = size
        self.messages: list[str] = []
        self.errors: list[str] = []
        _LIVE.add(self)

    # -- what the Qt window called these -------------------------------------

    def load_structure_from_path(self, path, *, name: str | None = None) -> str:
        """Load *path* as an object, through the host the commands use."""
        object_id = self.host.load_structure_from_path(pathlib.Path(path), name=name)
        self.pump()
        return object_id

    def run_demo(self, key: str) -> None:
        """Run the demo *key* through the host, as ``demo <key>`` does."""
        self.host.run_demo(key)
        self.pump()

    def run_script_text(self, text: str) -> None:
        """Run a command script line by line through the host."""
        self.host.run_script_text(text)
        self.pump()

    def set_object_visible(self, object_id: str, visible: bool) -> None:
        """Show or hide an object through the host (the object panel's eye)."""
        self.host.set_object_visible(object_id, visible)
        self.pump()

    def select_object(self, object_id) -> None:
        """Make *object_id* the active object through the host."""
        self.host.select_object(object_id)
        self.pump()

    def refresh_objects(self) -> None:
        """Rebuild the object list from the viewer."""
        self.app.sync_panel()

    def capture_messages(self) -> tuple[list[str], list[str]]:
        """Route the command layer's messages and errors into two lists.

        Returns
        -------
        tuple of list of str
            ``(messages, errors)``, filled as commands run.
        """
        self.cmd.set_message_callback(self.messages.append)
        self.cmd.set_error_callback(self.errors.append)
        return self.messages, self.errors

    def open_panel(self, key: str):
        """Open the in-viewport panel *key* and return it.

        Through the panel registry, the one way every host opens a panel
        (``density_panel on`` and its siblings end there). The Qt window kept a
        few panels' models as attributes of its own (``volume_panel``); here the
        panel holds its model, as on every other host.
        """
        self.cmd.panels.toggle(self.cmd, key, "on")
        self.pump()
        return self.viewer.gui.panels[key]

    def run_menu_command(self, line: str) -> None:
        """Run *line* the way a menu entry in the viewport does.

        Through the chrome's own ``run_command`` -- the callable every menu,
        object menu and toolbar button of the in-viewport chrome emits into --
        so an entry goes in whole, ``;`` and all.
        """
        self.renderer._internal_gui._run_command(line)
        self.pump()

    def do(self, line: str, frames: int = 1) -> None:
        """Run one command line and draw *frames* frames after it."""
        self.cmd.do(line)
        self.pump(frames)

    def pump(self, frames: int = 1):
        """Draw *frames* frames; return the last one (an RGBA array or ``None``)."""
        image = None
        for _ in range(max(0, int(frames))):
            image = self.app.draw_frame()
        return image

    def resize(self, width: int, height: int) -> None:
        """Resize the canvas, as a window resize would (``CanvasView.resize``)."""
        self.renderer.resize(int(width), int(height))
        self.size = (int(width), int(height))

    def grab(self):
        """Render one frame and return it as an ``(H, W, 4)`` uint8 array."""
        import numpy as np

        image = self.app.draw_frame()
        return None if image is None else np.asarray(image)

    def close(self) -> None:
        """Release the canvas."""
        try:
            self.app.close()
        except Exception:  # noqa: BLE001 - teardown of an offscreen canvas
            pass
