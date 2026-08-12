from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from .argparse2 import CommandError, bind_and_call, split_statements, tokenize
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
        """Execute *line*, which may hold several ``;``-separated statements."""
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

        for statement in self._statements(line):
            self._do_one(statement)

    def _statements(self, line: str) -> list[str]:
        """Split *line* on top-level ``;``, unless the command captures it.

        A command whose tail is taken verbatim (``mode="raw1"``/``"raw2"`` —
        ``iterate``, ``alter``, ``mdo``, …) is handed a Python expression or a
        command list of its own, and a ``;`` in there is part of the argument.
        """
        if ";" not in line:
            return [line]
        spec = self._registry.resolve(line.split(None, 1)[0].lower())
        if spec is not None and spec.mode != "normal":
            return [line]
        return split_statements(line)

    def _do_one(self, line: str) -> None:
        """Execute a single statement (no ``;`` handling — see :meth:`do`)."""
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

    @staticmethod
    def _unquote_name(name: str) -> str:
        """Strip the quotes a name may arrive in.

        A name that is not a bare identifier -- an EMDB map is called
        `EMD-3061`, and the hyphen is the selection grammar's range operator --
        has to be quoted to survive the parser. The commands that look an object
        up **by name** never reach the parser, so they see the quotes and match
        nothing: `zoom "EMD-3061"` reported *matched no atoms* about an object
        that was right there.
        """
        text = (name or "").strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
            return text[1:-1]
        return text

    def _find_object_by_name(self, viewer, name: str) -> dict | None:
        target = self._unquote_name(name).lower()
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
        """Show available commands, or the help for one, in the info panel.

        Into the **info panel** rather than only the prompt's feedback line,
        which shows one line at a time: the command list is over a hundred
        names and a docstring is a paragraph, so the answer scrolled straight
        past. The panel holds it and scrolls, and the text is still returned so
        a script or the console sees it too.
        """
        if not name:
            names = self._registry.names()
            # Hand the panel the names *and* their summaries, so its filter can
            # search what a command does as well as what it is called.
            items = []
            for one in sorted(names):
                spec = self._registry.resolve(one)
                doc = (spec.doc or "").strip().splitlines() if spec else []
                items.append((one, doc[0] if doc else ""))
            if self._show_listing_in_info_panel("Commands", items):
                return f"Commands ({len(names)})"
            text = f"Commands ({len(names)}):\n\n" + "\n".join(
                "  " + line for line in self._columns(names)
            )
        else:
            spec = self._registry.resolve(name.lower())
            if spec is None:
                text = f"No help available for unknown command: {name}"
            elif not spec.doc:
                text = f"No detailed help available for '{spec.name}'"
            else:
                text = f"Help for '{spec.name}':\n" + "-" * 20 + "\n" + spec.doc
        self._show_in_info_panel(text)
        return text

    @staticmethod
    def _columns(names, per_row: int = 3) -> list[str]:
        """Lay names out in even columns, so a long list stays readable."""
        ordered = sorted(names)
        width = max((len(n) for n in ordered), default=0) + 2
        return [
            "".join(n.ljust(width) for n in ordered[i:i + per_row])
            for i in range(0, len(ordered), per_row)
        ]

    def _show_listing_in_info_panel(self, title: str, items) -> bool:
        """Put a *filterable* listing in the info panel. False without one.

        Distinct from :meth:`_show_in_info_panel`, which takes finished text: a
        listing keeps its items, so the panel can re-lay them as the user types
        into its filter. Falls back to the plain text when the renderer draws no
        chrome (a script, the console, the headless sink).
        """
        viewer = getattr(self.window, "viewer", None)
        gui = getattr(getattr(viewer, "_renderer", None), "_internal_gui", None)
        setter = getattr(gui, "set_info_listing", None)
        if not callable(setter):
            return False
        try:
            setter(title, items)
            viewer.set_system_info_visible(True)
        except Exception:
            return False
        return True

    def _show_in_info_panel(self, text: str) -> bool:
        """Put *text* in the info panel and open it. False without a viewer."""
        viewer = getattr(self.window, "viewer", None)
        setter = getattr(viewer, "set_system_info_text", None)
        if not callable(setter):
            return False
        try:
            # Prose replaces a listing, and has to say so: the listing owns the
            # panel's text while it is active.
            gui = getattr(getattr(viewer, "_renderer", None), "_internal_gui", None)
            clear = getattr(gui, "clear_info_listing", None)
            if callable(clear):
                clear()
            setter(str(text))
            viewer.set_system_info_visible(True)
        except Exception:
            return False
        return True

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
