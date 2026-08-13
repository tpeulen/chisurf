"""Inspection commands: ``memory`` and ``editor``.

Two things the viewer could not answer about itself from inside itself.

``memory`` -- *where did it go?* A scene is vertex buffers, instance buffers, a
chrome texture and a glyph atlas, and the difference between a 16 ms frame and
a 60 ms one is usually how many of those exist and how large they are. Until
now that was answerable only by adding a print statement and re-running, and
for a device buffer not even then. The command reports both totals and the
biggest blocks, and can open a hex view on any of them.

``editor`` -- *a script, in the application it scripts.* chimol has a command
language and a prompt, and no way to write more than one line of it. The
command opens the ported code editor on a file, with the language guessed from
the extension and the **chimol** language -- built from the live command
registry, so every command the session knows colours as a keyword -- used for a
``.cmd``/``.pml`` script.

Both work headless: they return their result object and print their report, and
only open a window when asked to and when there is a display to open it on.
"""

from __future__ import annotations

from pathlib import Path

from .base import BaseCmd
from .registry import command

#: File extension -> the name of the language to colour it as. ``.pml`` is
#: PyMOL's script extension and chimol reads PyMOL scripts, so it gets chimol's
#: own language rather than nothing.
_BY_SUFFIX = {
    ".py": "Python",
    ".pyw": "Python",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cc": "C++",
    ".glsl": "GLSL",
    ".vert": "GLSL",
    ".frag": "GLSL",
    ".wgsl": "GLSL",
    ".lua": "Lua",
    ".json": "JSON",
    ".md": "Markdown",
    ".sql": "SQL",
    ".cmd": "chimol",
    ".pml": "chimol",
    ".chimol": "chimol",
}


class InspectMixin(BaseCmd):
    """Look at what the viewer is holding, and edit what it runs."""

    @command("memory", aliases=("mem",))
    def memory(self, block: str = "", top: int = 12, window: bool = False):
        """Report the memory the running viewer holds, in RAM and on the device.

        Parameters
        ----------
        block : str, optional
            Show a hex view of the first block whose name contains this. Empty
            lists the blocks instead.
        top : int, optional
            How many blocks to list.
        window : bool, optional
            Open the hex view in its own window. Requires a display; without
            one the dump is written to the log instead, which is what makes
            this usable over the headless server.

        Returns
        -------
        MemoryReport
            So a script can assert on it -- ``cmd.memory().vram_bytes`` is a
            regression test for a leak, and printing is not.

        Notes
        -----
        The totals say "found", not "total". The probe walks the live object
        graph rather than a registry of allocations, so it reports what is
        reachable from the viewer -- see
        :mod:`chimol.renderer.memory_probe` for why that is the honest design
        and what it can miss.
        """
        from ..renderer import memory_probe

        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return None
        found = memory_probe.report(viewer, getattr(viewer, "device", None))
        self._emit_message(found.summary())

        if not str(block).strip():
            for one in found.largest(int(top)):
                self._emit_message(
                    f"  {one.kind:4}  {_human(one.size()):>9}  {one.name}"
                    + (f"  [{one.detail}]" if one.detail else "")
                )
            return found

        wanted = str(block).strip().lower()
        source = next(
            (one for one in found.sources if wanted in one.name.lower()), None
        )
        if source is None:
            self._emit_error(f"no memory block matching {block!r}")
            return found
        if window:
            self._open_memory_window(source)
        else:
            self._emit_message(_hex_dump(source))
        return found

    @command("editor", aliases=("edit_file",))
    def editor(self, filename: str = "", language: str = "", window: bool = True):
        """Open the code editor on a file.

        Parameters
        ----------
        filename : str, optional
            The file. It need not exist -- an editor on a new path is how a
            script gets written.
        language : str, optional
            Override the language guessed from the extension.
        window : bool, optional
            Open a window. False builds the editor and returns it, which is
            what a test does.

        Returns
        -------
        TextEditor
            The editor, so a caller can read ``.text`` back.
        """
        from ..cmtk import text_editor as te

        path = Path(str(filename)).expanduser() if str(filename).strip() else None
        text = ""
        if path is not None and path.is_file():
            text = path.read_text(errors="replace")

        name = str(language).strip() or _BY_SUFFIX.get(
            path.suffix.lower() if path else "", "chimol"
        )
        chosen = None
        if name.lower() == "chimol":
            # Built from the live registry, so a command added to a mixin
            # colours as a keyword without anybody editing a word list -- the
            # failure mode every hand-maintained highlighter has.
            chosen = te.Language.chimol(self.command_names())
        else:
            for known, one in te.shipped_languages().items():
                if known.lower() == name.lower():
                    chosen = one
                    break
        editor = te.TextEditor(text, chosen)
        if window:
            self._open_editor_window(editor, path)
        return editor

    # -- helpers -------------------------------------------------------- #
    def _open_memory_window(self, source) -> None:
        """Open a hex view on one block, if there is a display."""
        from ..cmtk import memory_editor as me

        editor = me.MemoryEditor(source, read_only=True)
        self._open_control_window(editor, f"Memory — {source.name}", 720, 420)

    def _open_editor_window(self, editor, path) -> None:
        """Open the code editor, if there is a display."""
        title = f"Editor — {path}" if path is not None else "Editor"
        self._open_control_window(editor, title, 820, 560)

    def _open_control_window(self, control, title: str, width: int, height: int) -> None:
        """Host a painter-level control in its own top-level window.

        A window rather than a dock in the main window: a dock has to be
        registered, persisted in the saved layout, and given a place in the
        View menu, and none of that is what somebody typing ``memory foo, 1``
        at the prompt is asking for. The control is the same object either way,
        so promoting one of these to a dock later costs nothing.
        """
        try:
            from qtpy import QtWidgets

            from ..cmtk.qt_host import ControlHost
        except ImportError:
            self._emit_error("no Qt binding; use the text form instead")
            return
        if QtWidgets.QApplication.instance() is None:
            self._emit_error("no running application; use the text form instead")
            return
        host = ControlHost(control, parent=None)
        host.setWindowTitle(title)
        host.resize(int(width), int(height))
        host.show()
        # Held on the command object, because a top-level widget with no parent
        # and no reference is garbage-collected and vanishes on the next frame
        # -- the classic Qt-from-Python disappearing-window bug.
        windows = getattr(self, "_inspect_windows", None)
        if windows is None:
            windows = []
            self._inspect_windows = windows
        windows.append(host)


def _human(count: int) -> str:
    """Bytes as a short human-readable string."""
    size = float(count)
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"


def _hex_dump(source, rows: int = 16, columns: int = 16) -> str:
    """A few rows of *source* as text, for a log that has no pixels."""
    lines = []
    for row in range(rows):
        offset = row * columns
        if offset >= source.size():
            break
        chunk = source.read(offset, columns)
        if not chunk:
            break
        hexed = " ".join(f"{one:02X}" for one in chunk)
        shown = "".join(chr(one) if 32 <= one < 127 else "." for one in chunk)
        lines.append(f"  {offset:08X}  {hexed:<{columns * 3}} {shown}")
    if source.size() > rows * columns:
        lines.append(f"  ... {_human(source.size())} total")
    return "\n".join(lines)


class DebugMixin(BaseCmd):
    """The dbg window, and the nerd-mode switch it carries."""

    @command("dbg", aliases=("dbg_panel", "debug_window"))
    def dbg(self, action: str = "toggle") -> None:
        """Show, hide or toggle the dbg window (``dbg on``).

        What **Help → dbg** opens: five tabs -- what the last frame cost, every
        panel the viewer has, the shipped demos, the ported widgets running
        live, and the WGSL the renderer is actually using. One window rather
        than five scattered entries, and it **stays open**, because every
        action taken in it is one you want to take again.

        Parameters
        ----------
        action : str, optional
            ``toggle`` (the default), ``on``/``show``, or ``off``/``hide``.
        """
        _window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        gui = getattr(getattr(viewer, "_renderer", None), "_internal_gui", None)
        if gui is None:
            self._emit_error("dbg: this renderer draws no chrome")
            return

        from ..renderer.dbg_window import DbgWindow

        wanted = str(action).strip().lower() or "toggle"
        existing = gui.window(DbgWindow.KEY)
        if wanted in ("off", "hide", "0", "false"):
            if existing is not None:
                existing.visible = False
            viewer._update_view()
            return

        if existing is None:
            stats = getattr(getattr(viewer, "_renderer", None), "_gpu", None)
            panel = DbgWindow(self.do, getattr(stats, "stats", None))
            # Kept on the viewer so it outlives this call: the window holds a
            # bound method and nothing else keeps the panel alive.
            viewer._dbg_controls = panel
            existing = gui.add_window(panel.window())
        elif wanted == "toggle" and existing.visible:
            existing.visible = False
            viewer._update_view()
            return

        existing.visible = True
        gui.raise_window(DbgWindow.KEY)
        gui.layout(gui._width, gui._height)
        viewer._update_view()

    @command("nerd_mode", aliases=("nerd",))
    def nerd_mode(self, state: str = "") -> None:
        """Show or hide the frame instrumentation (``nerd on``).

        The block in the top-left of the backdrop: frame rate and where the
        frame's milliseconds went, how many draw calls and instances were
        submitted, how many quads the chrome cost, which pipelines ran, the
        ambient-occlusion strengths, and what the machine is.

        It answers one question -- *why is this frame slow* -- and it answers
        it in the place the question is asked, over the scene being driven,
        rather than in a window that would have to be dragged out of the way of
        the thing being measured.

        With no argument this **toggles**, which is what a checkbox needs.

        Parameters
        ----------
        state : str, optional
            ``on``/``1``/``true`` or ``off``/``0``/``false``. Empty toggles.

        Notes
        -----
        The counters are off until this is on, so nothing is paid for an
        instrument nobody is reading -- and the readout is re-published a few
        times a second rather than every frame, because it is drawn as chrome
        and chrome that changes every frame is rebuilt every frame. An
        instrument that costs a rebuild per frame reports the cost of switching
        it on.
        """
        from ..config import _DISPLAY_CONFIG, save_user_display_config  # noqa: PLC0415

        layout = _DISPLAY_CONFIG.setdefault("layout", {})
        current = bool(layout.get("nerd", False))
        text = str(state or "").strip().lower()
        if not text:
            wanted = not current
        elif text in ("on", "1", "true", "yes"):
            wanted = True
        elif text in ("off", "0", "false", "no"):
            wanted = False
        else:
            self._emit_error("Usage: nerd [on|off]")
            return

        layout["nerd"] = wanted
        try:
            save_user_display_config()
        except Exception:  # noqa: BLE001 - an unwritable settings dir
            pass
        _window, viewer = self._require_window_and_viewer()
        if viewer is not None:
            viewer._update_view()
        self._emit_message(f"nerd mode {'on' if wanted else 'off'}")

    @command("panels_all", aliases=("open_all_panels",))
    def panels_all(self, action: str = "on") -> None:
        """Open every panel the viewer has, or close them again.

        The *try all* button. A viewer's panels are discoverable only if you
        know they exist, and reading a menu is not the same as seeing them --
        so this puts all of them on screen at once, which is also the fastest
        way to find the one that is broken.

        Parameters
        ----------
        action : str, optional
            ``on`` (the default) or ``off``.
        """
        from ..renderer.dbg_window import PANELS

        wanted = str(action).strip().lower() or "on"
        closing = wanted in ("off", "hide", "0", "false")
        opened = 0
        for entry in PANELS:
            name = entry[0].split()[0]
            try:
                self.do(f"{name} {'off' if closing else 'on'}")
                opened += 1
            except Exception as problem:  # noqa: BLE001 - one dead panel is not all of them
                self._emit_error(f"{name}: {problem}")
        self._emit_message(
            f"{'closed' if closing else 'opened'} {opened} panel(s)"
        )
