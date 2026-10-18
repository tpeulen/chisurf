"""A Python console as a terminal session: the built-in engine behind a pane.

The terminal plugin's panes draw whatever speaks their engine seam
(``screen`` / ``write`` / ``resize`` / ``alive`` / ``close``). A PTY child is
one such engine; this module is another: ChiSurf's own console engine
(:class:`chisurf.core.console.shell.Shell`), in-process, driving the same
:class:`~chisurf.plugins.core.terminal.screen.TerminalScreen` grid.

What is added over the engine is a *line discipline*, the small state machine
a terminal has around a running REPL:

* a banner, then ``In [N]: `` prompts (``   ...: `` while a block continues),
  using the same strings and engine configuration as the emtk shell's
  :class:`~chisurf.emtk.console.ShellConsole` so the pane and the dock
  behave identically;
* typed characters echo into the grid, ``BS`` edits the line, ``CR`` submits
  it (the engine runs it synchronously; its ``write`` callback feeds the
  screen, so ``print`` lands as live output);
* ``Up`` / ``Down`` arrows walk persistent command history;
* ``Tab`` triggers symbol and keyword completion via the live engine;
* ``Ctrl+C`` cancels the pending line (``KeyboardInterrupt`` as a terminal
  shows it), ``Ctrl+D`` on an empty line ends the session;
* the trailing-expression result is echoed under ``Out[N]:``, as a REPL does.

Because it is in-process, the console pane has the ChiSurf namespace and its
magics, and it works where PTYs do not exist. The engine's own streams are
captured only while a line runs (the shell's ``sys.stdout`` redirect stays
untouched otherwise).
"""

from __future__ import annotations

import threading
from typing import Any

from chisurf.emtk.console import CONTINUATION as _CONTINUATION_TMPL
from chisurf.emtk.console import PROMPT as _PROMPT_TMPL

from .screen import TerminalScreen

__all__ = ["ConsoleSession"]


class ConsoleSession:
    """The built-in Python console as one terminal session (the engine seam).

    Parameters
    ----------
    namespace : dict, optional
        Seeded into the console's namespace (the shell passes its own, with
        ``gui`` and the session's ``api`` in it).
    banner : str, optional
        Drawn before the first prompt; ``None`` uses the engine's own.
    columns, rows : int
        The initial grid size.
    history_path : path or bool, optional
        The input history file; ``False`` keeps none (tests), ``None`` the settings default.
    """

    def __init__(
        self,
        namespace: dict | None = None,
        *,
        banner: str | None = None,
        columns: int = 80,
        rows: int = 24,
        history_path: Any = None,
    ) -> None:
        from chisurf.core.console.history import HistoryManager
        from chisurf.core.console.settings import console_init_source
        from chisurf.core.console.shell import Shell

        self.screen = TerminalScreen(columns, rows)
        self._lock = threading.Lock()
        self._alive = True
        self._line = ""
        self._pending_lines: list[str] = []
        self._history_stash = ""
        self._history_prefix = ""
        self._history_index: int | None = None

        user_ns: dict[str, Any] = {}
        try:
            import chisurf

            user_ns["cs"] = chisurf
        except Exception:  # noqa: BLE001
            pass
        try:
            import numpy as np

            user_ns["np"] = np
        except Exception:  # noqa: BLE001
            pass
        import os

        user_ns["os"] = os
        try:
            from chisurf.core.api import ChiSurfAPI

            api = ChiSurfAPI.instance(create=False)
            if api is not None:
                user_ns["api"] = api
        except Exception:  # noqa: BLE001
            pass
        if namespace:
            user_ns.update(namespace)

        self._engine = Shell(
            user_ns=user_ns,
            write=self._write,
            display=self._display,
            history=HistoryManager(history_path),
        )
        self._engine.enable_inline_figures()

        source = console_init_source()
        if source and source.strip():
            self._engine.run_cell(source, store_history=False, silent=True)

        # Do not override execution_count: Shell starts at 1, matching ShellConsole.
        text = self._banner(banner)
        self._out(f"\x1b[1m{text}\x1b[0m\r\n")
        self._prompt()

    # ── the engine seam ───────────────────────────────────────────────────

    @property
    def alive(self) -> bool:
        return self._alive

    def write(self, data: bytes | str) -> None:
        """Keystrokes from the pane, one key or a paste at a time."""
        if isinstance(data, bytes):
            data = data.decode("utf-8", "replace")
        with self._lock:
            i = 0
            n = len(data)
            while i < n:
                if data[i] == "\x1b":
                    if i + 2 < n and data[i + 1] == "[":
                        code = data[i + 2]
                        if code == "A":
                            self._history_up()
                            i += 3
                            continue
                        if code == "B":
                            self._history_down()
                            i += 3
                            continue
                        if code in ("C", "D"):
                            i += 3
                            continue
                self._key(data[i])
                i += 1

    def resize(self, columns: int, rows: int) -> None:
        with self._lock:
            self.screen.resize(columns, rows)

    def close(self) -> None:
        self._alive = False

    def push(self, variables: dict) -> None:
        """Push *variables* into the console's live namespace."""
        with self._lock:
            self._engine.push(variables)

    # ── the line discipline ───────────────────────────────────────────────

    def _key(self, char: str) -> None:
        if not self._alive:
            return
        if char == "\r":  # CR: submit the line
            self._history_index = None
            self._submit()
        elif char == "\x7f" or char == "\b":  # BS: edit
            self._history_index = None
            if self._line:
                self._line = self._line[:-1]
                self._out("\b \b")
        elif char == "\x03":  # Ctrl+C: cancel the line
            self._history_index = None
            self._out(f"^{chr(ord('C') - 64)}\r\n")
            self._write("stderr", "KeyboardInterrupt\r\n")
            self._line = ""
            self._prompt()
        elif char == "\x04":  # Ctrl+D: EOF on an empty line
            if not self._line:
                self._out(f"^{chr(ord('D') - 64)}\r\n")
                self.close()
        elif char == "\x15":  # Ctrl+U: kill the line
            self._history_index = None
            self._out("\r\x1b[K")
            self._line = ""
            self._prompt()
        elif char == "\t":
            self._tab()
        elif char >= " " or char == "\n":
            self._history_index = None
            self._insert(char)

    def _tab(self) -> None:
        if not self._line.strip():
            self._insert("    ")
            return
        result = self._engine.complete(self._line, len(self._line))
        if not result or not result.matches:
            return
        cursor = len(self._line)
        typed_len = cursor - result.start
        if result.common_prefix and len(result.common_prefix) > typed_len:
            extension = result.common_prefix[typed_len:]
            self._insert(extension)
            if len(result.matches) == 1:
                return
        elif len(result.matches) == 1:
            match = result.matches[0]
            if len(match) > typed_len:
                self._insert(match[typed_len:])
            return
        if len(result.matches) > 1:
            matches_text = "  ".join(result.matches[:30])
            self._out(f"\r\n{matches_text}\r\n")
            self._prompt()
            self._out(self._line)

    def _history_up(self) -> None:
        entries = self._engine.history.entries
        if not entries:
            return
        if self._history_index is None:
            self._history_stash = self._line
            self._history_prefix = self._line
            self._history_index = len(entries)
        matches = [i for i, entry in enumerate(entries) if entry.startswith(self._history_prefix)]
        if not matches:
            matches = list(range(len(entries)))
        earlier = [i for i in matches if i < self._history_index]
        if not earlier:
            return
        self._history_index = earlier[-1]
        self._set_line(entries[self._history_index])

    def _history_down(self) -> None:
        if self._history_index is None:
            return
        entries = self._engine.history.entries
        matches = [i for i, entry in enumerate(entries) if entry.startswith(self._history_prefix)]
        if not matches:
            matches = list(range(len(entries)))
        later = [i for i in matches if i > self._history_index]
        if not later:
            self._history_index = None
            self._set_line(self._history_stash)
            return
        self._history_index = later[0]
        self._set_line(entries[self._history_index])

    def _set_line(self, new_line: str) -> None:
        self._out("\r\x1b[K")
        self._prompt()
        self._line = new_line
        self._out(new_line)

    def _insert(self, char: str) -> None:
        self._line += char
        self._out(char)

    def _submit(self) -> None:
        line = self._line
        self._line = ""
        self._out("\r\n")
        if self._continuing:
            if line.strip():
                self._pending_lines.append(line)
                self._prompt()
                return
            source = "\n".join(self._pending_lines)
            self._pending_lines = []
        else:
            source = line
            if not line.strip():
                self._prompt()
                return
            status, indent = self._engine.check_complete(source)
            if status == "incomplete":
                self._pending_lines = [line]
                self._prompt()
                self._insert(indent)  # a block body starts indented, as a REPL
                return
        self._run(source)

    def _run(self, source: str) -> None:
        self._engine.run_cell(source, store_history=True)
        self._prompt()

    def _prompt(self) -> None:
        if self._continuing:
            self._out(_CONTINUATION_TMPL)
        else:
            self._out(_PROMPT_TMPL.format(n=self._engine.execution_count))

    @property
    def _continuing(self) -> bool:
        return bool(self._pending_lines)

    # ── output into the grid ──────────────────────────────────────────────

    def _out(self, text: str) -> None:
        self.screen.feed(self._nl_to_crlf(text))

    @staticmethod
    def _nl_to_crlf(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\n", "\r\n")

    def _write(self, name: str, text: str) -> None:
        colour = "\x1b[31m" if name == "stderr" else ""
        reset = "\x1b[0m" if colour else ""
        self._out(f"{colour}{text}{reset}")

    def _display(
        self, data: dict, metadata: dict, kind: str, execution_count: int | None
    ) -> None:
        text = (data or {}).get("text/plain")
        if text is None and "text/html" in (data or {}):
            from chisurf.emtk.console import _html_as_text

            text = _html_as_text(data["text/html"])
        if text:
            if kind == "execute_result" and execution_count is not None:
                out = f"Out[{execution_count}]: {text}"
                self._out(out if out.endswith("\n") else out + "\n")
            else:
                self._out(text if text.endswith("\n") else text + "\n")

    @staticmethod
    def _banner(banner: str | None) -> str:
        if banner is not None:
            return banner
        from chisurf.emtk.console import ShellConsole

        return ShellConsole._banner().strip()
