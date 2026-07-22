from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from .argparse2 import CommandError, bind_and_call, tokenize
from .registry import collect_commands, command

if TYPE_CHECKING:
    from ..app.molview_main_window import MolViewPluginWindow


MessageCallback = Callable[[str], None]


class BaseCmd:
    """Shared infrastructure for the Moview/Chimol command layer."""

    def __init__(self, window: MolViewPluginWindow | None = None) -> None:
        self.window = window
        self._message_callback: MessageCallback | None = None
        self._error_callback: MessageCallback | None = None
        self._named_selections: dict[str, dict[str, object]] = {}
        # Declarative registry built from every @command-decorated method on the
        # MRO (see registry.py / argparse2.py).
        self._registry = collect_commands(self)

    # ------------------------------------------------------------------ #
    # Public API and core plumbing
    # ------------------------------------------------------------------ #
    def set_window(self, window: MolViewPluginWindow | None) -> None:
        self.window = window

    def set_message_callback(self, callback: MessageCallback | None) -> None:
        self._message_callback = callback

    def set_error_callback(self, callback: MessageCallback | None) -> None:
        self._error_callback = callback

    def command_names(self) -> list[str]:
        """Return every registered command name and alias (for completion/help)."""
        return self._registry.names()

    def do(self, line: str) -> None:
        line = (line or "").strip()
        if not line:
            return

        # Script execution: '@filename' runs a text file with one command per line.
        if line.startswith("@"):
            script_path = line[1:].strip()
            if not script_path:
                self._emit_error("Usage: @<script_file>")
                return
            self._run_script_file(script_path)
            return

        head_rest = line.split(None, 1)
        name = head_rest[0].lower()
        rest = head_rest[1] if len(head_rest) > 1 else ""

        spec = self._registry.resolve(name)
        if spec is None:
            self._emit_error(
                f"Command '{name}' is not implemented in Moview/MolView cmd (PyMOL compatibility layer)."
            )
            return

        try:
            pairs = tokenize(rest, spec.mode)
            result = bind_and_call(spec.func, pairs)
        except CommandError as exc:
            self._emit_error(f"{spec.name}: {exc}")
            return
        except Exception as exc:
            self._emit_error(f"Error in command '{spec.name}': {exc}")
            return

        if result is not None:
            self._emit_message(str(result))

    def _run_script_file(self, path: str) -> None:
        """Execute a simple cmd script file, one command per non-empty line.

        Lines starting with '#' are treated as comments and skipped. This is
        similar in spirit to PyMOL's '@script.pml' support, but limited to the
        Moview cmd language (no arbitrary Python execution).
        """
        try:
            p = Path(path).expanduser()
        except Exception as exc:
            self._emit_error(f"Invalid script path {path!r}: {exc}")
            return

        if not p.exists():
            self._emit_error(f"Script file not found: {p}")
            return

        try:
            with p.open("rt", encoding="utf-8") as fh:
                for raw in fh:
                    line = (raw or "").strip()
                    if not line or line.startswith("#"):
                        continue
                    self.do(line)
        except Exception as exc:
            self._emit_error(f"Failed to run script {p!s}: {exc}")

    # ------------------------------------------------------------------ #
    # Shared helpers
    # ------------------------------------------------------------------ #
    def _require_window_and_viewer(self):
        window = self.window
        if window is None:
            self._emit_error("No viewer window is attached")
            return None, None
        viewer = getattr(window, "viewer", None)
        if viewer is None:
            self._emit_error("Attached window has no 'viewer' attribute")
            return window, None
        return window, viewer

    def _find_object_by_name(self, viewer, name: str) -> dict | None:
        target = (name or "").strip().lower()
        if not target:
            return None
        try:
            objects = viewer.list_objects()
        except Exception:
            return None
        for obj in objects:
            obj_id = str(obj.get("id", ""))
            obj_name = str(obj.get("name", ""))
            if not obj_id and not obj_name:
                continue
            if target == obj_id.lower() or target == obj_name.lower():
                return obj
        return None

    def _emit_message(self, text: str) -> None:
        callback = self._message_callback
        if callback is not None:
            callback(text)

    def _emit_error(self, text: str) -> None:
        callback = self._error_callback or self._message_callback
        if callback is not None:
            callback(text)

    # ------------------------------------------------------------------ #
    # Common commands
    # ------------------------------------------------------------------ #
    @command("help", aliases=("?",))
    def help(self, name: str = "") -> str:
        """Show available commands or detailed help for a specific command."""
        if not name:
            return "Available commands: " + ", ".join(self._registry.names())

        spec = self._registry.resolve(name.lower())
        if spec is None:
            return f"No help available for unknown command: {name}"
        if not spec.doc:
            return f"No detailed help available for '{spec.name}'"
        return f"Help for '{spec.name}':\n" + "-" * 20 + "\n" + spec.doc

    @command("quit", aliases=("exit",))
    def quit(self) -> None:
        """Close the viewer window."""
        window = self.window
        if window is None:
            return
        try:
            window.close()
        except Exception:
            pass
