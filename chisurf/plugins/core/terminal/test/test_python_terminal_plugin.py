"""The python_terminal plugin: open from the shell, drive, assert In [N]: prompts.

Two tests, each driven through the real plugin-host machinery:

* **open** -- :meth:`~chisurf.emtk.main_app.EmtkShellApp.open_plugin` resolves
  the ``python_terminal`` manifest, builds :func:`~chisurf.plugins.core.terminal.app.make_console_app`,
  and the resulting pane's screen contains ``In [`` prompt text (not ``>>>``).
* **eval** -- typing ``"21*2\\r"`` through the emtk
  :class:`~emtk.testing.Driver` renders ``42`` in the pane's screen, proving
  the engine runs and the line discipline submits the cell correctly.

No PTY, no real filesystem access: the ``python`` pane is the in-process
``ConsoleSession``, which works everywhere.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("emtk")

from emtk.testing import Driver

from chisurf.emtk.console import unwrap
from chisurf.plugins.core.terminal.app import make_console_app

# ── helpers ──────────────────────────────────────────────────────────────


def _make_shell_with_python_terminal():
    """Return ``(shell, made)`` where *made* is populated by the loader."""
    from chisurf.emtk.main_app import EmtkShellApp
    from chisurf.emtk.plugins import manifests

    catalog = manifests()
    assert "python_terminal" in catalog, "python_terminal manifest not found"
    made: dict = {}

    def loader(plugin_id: str):
        app = make_console_app()
        made[plugin_id] = app
        return app

    shell = EmtkShellApp(
        catalog,
        loader=loader,
        console_history=False,
        console_session_file=False,
    )
    return shell, made


def _pane_text(app) -> str:
    """All visible lines of the first (active) python pane joined by newlines."""
    key = app.workspace.active_key
    if key is None or key not in app.workspace.panes:
        return ""
    screen = app.workspace.panes[key].control.screen
    return "\n".join(screen.line_text(i) for i in range(screen.total_lines))


# ── tests ────────────────────────────────────────────────────────────────


def test_open_plugin_python_terminal_shows_in_prompt():
    """open_plugin('python_terminal') builds a python pane whose screen has In [.

    The hosted app must have a pane of kind ``"python"`` and the pane's screen
    must contain the ``In [`` prefix of the ``In [N]: `` prompt, proving
    ConsoleSession now uses the same prompt as ShellConsole, not ``>>>``.
    """
    shell = None
    try:
        shell, made = _make_shell_with_python_terminal()
        shell.open_plugin("python_terminal")

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and "python_terminal" not in made:
            time.sleep(0.05)
        assert "python_terminal" in made, "plugin was never built"

        app = made["python_terminal"]
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not app.workspace.panes:
            time.sleep(0.05)

        assert app.workspace.panes, "no pane was created"
        key = app.workspace.active_key
        assert key is not None
        pane = app.workspace.panes[key]
        assert pane.kind == "python", f"expected python pane, got {pane.kind!r}"

        # The pane's screen must contain the In [ prompt — not >>>.
        assert "In [" in _pane_text(app), (
            "expected 'In [' in pane screen; got: " + repr(_pane_text(app)[:200])
        )
    finally:
        if shell is not None:
            shell.close()


def test_typing_21_times_2_renders_42():
    """Typing ``21*2\\r`` through the Driver renders ``42`` in the pane.

    The Driver settles the shell, types ``"21*2\\r"`` through the input
    pipeline to the active pane's ``ConsoleSession``, and asserts ``42``
    appears in the screen.
    """
    shell = None
    try:
        shell, made = _make_shell_with_python_terminal()
        shell.open_plugin("python_terminal")

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and "python_terminal" not in made:
            time.sleep(0.05)
        assert "python_terminal" in made

        app = made["python_terminal"]
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not app.workspace.panes:
            time.sleep(0.05)
        assert app.workspace.panes

        driver = Driver(shell, (1440, 900))
        driver.frame(3)  # settle the shell and pane

        driver.type("21*2\r")
        driver.frame(2)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and "42" not in _pane_text(app):
            time.sleep(0.02)
            driver.frame(1)

        assert "42" in _pane_text(app), (
            "expected '42' in pane screen after typing '21*2\\r'; got: "
            + repr(_pane_text(app)[:300])
        )
    finally:
        if shell is not None:
            shell.close()


def test_split_python_pane_preserves_python_kind():
    """Splitting a python pane (horizontally or vertically) opens another python pane."""
    shell = None
    try:
        shell, made = _make_shell_with_python_terminal()
        shell.open_plugin("python_terminal")

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and "python_terminal" not in made:
            time.sleep(0.05)
        assert "python_terminal" in made

        app = made["python_terminal"]
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not app.workspace.panes:
            time.sleep(0.05)
        assert app.workspace.panes

        p1 = app.workspace.active
        assert p1 is not None and p1.kind == "python"

        # Split horizontally
        p2 = app.split_pane("right")
        assert p2 is not None
        assert p2.kind == "python", f"expected python pane after right split, got {p2.kind!r}"
        assert len(app.workspace.panes) == 2

        # Split vertically
        p3 = app.split_pane("down")
        assert p3 is not None
        assert p3.kind == "python", f"expected python pane after down split, got {p3.kind!r}"
        assert len(app.workspace.panes) == 3
    finally:
        if shell is not None:
            shell.close()


def test_python_pane_output_drawn_on_screen():
    """Commands executed in python pane update folds and actually render on screen."""
    from emtk.testing import RecordingPainter

    from chisurf.plugins.core.terminal.app import make_console_app

    app = make_console_app()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 800, 600)

    active = app.workspace.active
    assert active is not None and active.kind == "python"

    active.console.execute("val = 19 * 3")
    active.console.execute("print('computed:', val)")

    painter2 = RecordingPainter()
    app.draw(painter2, 0, 0, 800, 600)
    assert any("computed:" in s for s in painter2.strings), f"'computed:' not found in {painter2.strings}"
    assert any("57" in s for s in painter2.strings), f"'57' not found in {painter2.strings}"


def test_chisurf_console_dock_is_cmux_python_terminal():
    """The shell's console dock is backed by the cmux python terminal with tabs and splits."""
    from chisurf.emtk.main_app import EmtkShellApp

    shell = EmtkShellApp(console_history=False, console_session_file=False)
    try:
        driver = Driver(shell, size=(1400, 900))
        driver.frame(3)

        assert hasattr(shell, "console_terminal")
        assert shell.console_terminal.default_kind == "python"
        assert shell.console_terminal.workspace.panes

        # Pane 1 is shell.console
        p1 = shell.console_terminal.workspace.active
        assert p1.kind == "python"
        assert p1.console is shell.console

        # Split pane in console dock
        p2 = shell.console_terminal.split_pane("right")
        assert p2 is not None
        assert p2.kind == "python"
        assert len(shell.console_terminal.workspace.panes) == 2
    finally:
        shell.close()



def test_a_second_console_dock_pane_has_the_first_panes_names():
    """A Python pane opened in the Console dock gets cs, np, os and gui, as pane 1 has them."""
    from chisurf.emtk.main_app import EmtkShellApp

    shell = EmtkShellApp(console_history=False, console_session_file=False)
    try:
        driver = Driver(shell, size=(1400, 900))
        driver.frame(3)
        pane = shell.console_terminal.new_pane("python")
        assert pane.console is not shell.console
        names = pane.console.engine.user_ns
        for name in ("cs", "np", "os", "gui"):
            assert name in names, name
        assert unwrap(names["gui"]) is shell, "gui is the shell (behind its frame proxy)"
        assert pane.console in shell._python_consoles()
    finally:
        shell.close()
