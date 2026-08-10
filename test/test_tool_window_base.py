"""Every tool window is a ``ChisurfDockTool``, not a bare ``QMainWindow``.

A tool that subclasses ``QMainWindow`` directly re-implements -- differently --
the things the shared base already does: path drag-drop, error/warning
reporting, window-geometry persistence, the ``?``/**Guide** buttons, and lazy
metadata-store access that does no I/O on construction. That is the whole
point of the base: a fix to any of them has to reach every tool, and it cannot
reach a tool that forked.

The allowlist below is the list of windows that legitimately are *not* tools.
It is a **shrinking** list of exceptions, never a place to add a new tool.

This is an AST check: it needs no Qt and no display.
"""

from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1] / "chisurf"

#: ``module path -> class name`` pairs that may subclass ``QMainWindow`` directly.
ALLOWED = {
    # The application's own main window is the host of the tools, not a tool.
    ("gui/main.py", "Main"),
    # The base itself -- something has to subclass QMainWindow.
    ("gui/widgets/tools/chisurf_dock_tool.py", "ChisurfDockTool"),
    # The games are not analysis tools and have no files, no docks and no store.
    # Pong and Breakout were ported to the chigame engine and are plain QWidgets
    # now, so their exceptions are struck rather than inherited. Tetris follows.
    ("plugins/misc/games/tetris/tetris.py", "Tetris"),
}


def _main_window_subclasses() -> list[tuple[str, str]]:
    """Return ``(relative path, class name)`` for every direct QMainWindow subclass."""
    found: list[tuple[str, str]] = []
    for path in sorted(ROOT.rglob("*.py")):
        text = str(path)
        if "__pycache__" in text or "/test" in text:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = " ".join(ast.unparse(base) for base in node.bases)
            if "ChisurfDockTool" in bases:
                continue
            if "QMainWindow" in bases:
                found.append((path.relative_to(ROOT).as_posix(), node.name))
    return found


def test_tool_windows_use_the_shared_base():
    """No new window may subclass QMainWindow instead of the shared tool base."""
    offenders = [entry for entry in _main_window_subclasses() if entry not in ALLOWED]
    assert not offenders, (
        "these windows subclass QMainWindow directly instead of ChisurfDockTool:\n"
        + "\n".join(f"  {name} in chisurf/{path}" for path, name in offenders)
    )


def test_the_allowlist_does_not_rot():
    """An allowlist entry that no longer exists hides the next real offender."""
    present = set(_main_window_subclasses())
    stale = sorted(ALLOWED - present)
    assert not stale, (
        "these allowlist entries no longer subclass QMainWindow and must be removed:\n"
        + "\n".join(f"  {name} in chisurf/{path}" for path, name in stale)
    )
