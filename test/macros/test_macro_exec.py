"""Running a macro file through the main window's ``onRunMacro``.

This used to be a script rather than a test: its whole body ran at *import*
time, built a ``Main`` window, and executed the **Pong game plugin** as a macro.
That plugin ends in the usual ``if __name__ == '__main__':`` block, and
``run_macro`` execs with ``__name__`` set to ``"__main__"`` — so the game
started a ``QApplication`` and called ``app.exec()``, which never returns. The
whole pytest session stopped there, during collection, with no output and no
failing test to point at.

It only bit when *something else* had already created a ``QApplication``,
because the guard below skips the module otherwise. That made it invisible to a
one-module-at-a-time import check and unaffected by
``-k 'not gui and not widget and not window'`` — the file is named
``test_macro_exec``.

So the macro under test is now a temporary file this test writes itself, which
records that it ran. That is what the original was trying to establish, and it
can be asserted instead of printed.
"""
import pathlib

import pytest
from qtpy import QtWidgets

# Building the ChiSurf main window needs a running QApplication: without one
# Qt does not raise, it aborts the whole process and takes the test session
# with it. The non-GUI suite has no application, so skip at import time.
if QtWidgets.QApplication.instance() is None:
    pytest.skip(
        "the ChiSurf main window needs a QApplication", allow_module_level=True
    )


@pytest.fixture(scope="module")
def main_window():
    from chisurf.gui.main import Main
    return Main()


def test_exec_executor_runs_the_file(main_window, tmp_path):
    """The macro body executes, and side effects reach the filesystem."""
    marker = tmp_path / "macro-ran.txt"
    macro = tmp_path / "macro_under_test.py"
    macro.write_text(
        "import pathlib\n"
        f"pathlib.Path(r'{marker}').write_text('ran')\n"
    )

    main_window.onRunMacro(filename=macro, executor="exec")

    assert marker.exists(), "the macro did not run"
    assert marker.read_text() == "ran"


def test_a_macro_that_raises_propagates(main_window, tmp_path):
    """A broken macro must not fail silently.

    ``run_macro`` logs and re-raises; a macro runner that swallowed the error
    would leave the user with a menu entry that does nothing and says nothing.
    """
    macro = tmp_path / "broken_macro.py"
    macro.write_text("raise ValueError('deliberate')\n")

    with pytest.raises(ValueError, match="deliberate"):
        main_window.onRunMacro(filename=macro, executor="exec")


def test_a_missing_macro_raises(main_window, tmp_path):
    with pytest.raises(FileNotFoundError):
        main_window.onRunMacro(
            filename=tmp_path / "does_not_exist.py", executor="exec"
        )


def test_running_a_plugin_as_a_macro_does_not_block(main_window):
    """A plugin entry point must not launch itself as a standalone app.

    Plugin ``__init__.py`` files branch on ``__name__``: ``"plugin"`` builds the
    widget, ``"__main__"`` starts a standalone ``QApplication`` and calls
    ``app.exec()``. If the macro runner claims ``"__main__"`` — as it used to —
    running a plugin from the macro menu enters a nested event loop that never
    returns, and ChiSurf simply stops, with no error. Pong is the sharpest case
    because it is a game with its own loop, so if this test returns at all, the
    right branch ran.
    """
    plugin = (
        pathlib.Path(__file__).resolve().parents[2]
        / "chisurf" / "plugins" / "misc" / "games" / "pong" / "__init__.py"
    )
    main_window.onRunMacro(filename=plugin, executor="exec")
