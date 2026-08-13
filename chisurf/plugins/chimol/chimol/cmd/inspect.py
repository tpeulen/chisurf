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
        from ..renderer.ui import text_editor as te

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
        from ..renderer.ui import memory_editor as me

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

            from ..renderer.ui.qt_host import ControlHost
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
