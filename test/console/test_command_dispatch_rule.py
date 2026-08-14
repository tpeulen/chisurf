"""Which lines the console runs as commands, and which as Python.

A command console takes both, so it needs a rule, and the rule it had made
**every no-argument command unreachable**: `ray`, `split_chains`, `orient` and
`zoom` are all valid Python expressions, so they were evaluated as names and the
console answered ``NameError: name 'ray' is not defined``. A command *with*
arguments worked, because `fetch 1f5n` is a syntax error and fell through to the
command layer -- which is why the failure looked arbitrary rather than total.

These tests drive the console the way a user does. That matters more than it
sounds: every other test of the command layer calls
``_run_object_menu_command``, which is the *menu* path, so the console could be
completely broken with the whole suite green. It was.
"""
from __future__ import annotations

import pytest

pytest.importorskip("qtpy")


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def console(qapp):
    """The viewer's own command console, with its dispatcher attached."""
    from chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )

    window = MolViewPluginWindow()
    window.resize(800, 600)
    window.show()
    for _ in range(5):
        qapp.processEvents()
    panel = window.command_panel
    assert panel.dispatcher is not None, "the console has no command dispatcher"
    yield panel, window, qapp
    window.close()


# --------------------------------------------------------------------------- #
# The rule
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "line", ["ray", "split_chains", "orient", "zoom", "undo", "reinit"]
)
def test_a_bare_command_runs_as_a_command(console, line):
    """The regression, one name per case.

    All of these are syntactically valid Python, and none of them names anything
    Python has -- so evaluating them can only ever raise.
    """
    panel, _window, _qapp = console
    assert panel._is_command(line), f"{line} went to Python"


@pytest.mark.parametrize("line", ["set", "1 + 1", "print", "len('ab')"])
def test_python_still_wins_when_the_name_exists(console, line):
    """The case the old rule was protecting, and it is kept.

    `set` is a chimol command *and* a builtin. Someone typing it alone at a
    Python-capable prompt means the type; someone typing `set fog_start, 0.5`
    means the command, and that is a syntax error so it routes correctly.
    """
    panel, _window, _qapp = console
    assert not panel._is_command(line), f"{line} was taken as a command"


def test_a_command_with_arguments_still_routes(console):
    """It always did -- `fetch 1f5n` is not valid Python -- but it must not
    regress while the bare case is fixed."""
    panel, _window, _qapp = console
    assert panel._is_command("color red, all")
    assert panel._is_command("set fog_start, 0.5")


def test_an_unknown_word_goes_to_the_command_layer(console):
    """So a typo is reported as an unknown command rather than as a Python
    ``NameError``, which at a command prompt explains nothing."""
    panel, _window, _qapp = console
    assert panel._is_command("splitt_chains")


# --------------------------------------------------------------------------- #
# It actually runs
# --------------------------------------------------------------------------- #
def test_split_chains_typed_into_the_console_splits_the_chains(console, tmp_path):
    """End to end through the widget, because the rule above is only half of it."""
    import pathlib

    panel, window, qapp = console
    pdb = (
        pathlib.Path(__file__).resolve().parents[2]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    if not pdb.is_file():
        pytest.skip(f"missing fixture {pdb}")

    def type_line(text: str) -> None:
        panel.input_line.setText(text)
        panel._submit_command_line()
        for _ in range(6):
            qapp.processEvents()

    type_line(f"load {pdb}")
    type_line("split_chains")

    names = [entry.name for entry in window.viewer._objects.values()]
    assert any(name.endswith("_E") for name in names), names
    assert any(name.endswith("_S") for name in names), names


# --------------------------------------------------------------------------- #
# Completion
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "typed,expected", [("spl", "split_chains"), ("orie", "orient"), ("col", "color")]
)
def test_tab_completes_a_command(console, typed, expected):
    """Nothing asked the dispatcher for completions: Tab went straight to the
    Python completer, which knows no chimol command and returned nothing, so
    completion appeared not to work at all."""
    panel, _window, _qapp = console
    result = panel._dispatcher_completions(typed, len(typed))
    assert result is not None, typed
    assert expected in result.matches, (typed, result.matches)


def test_tab_leaves_python_completion_alone(console):
    """The dispatcher answering `None` is what lets `np.ar<Tab>` still work."""
    panel, _window, _qapp = console
    assert panel._dispatcher_completions("np.ar", 5) is None


def test_a_single_match_is_inserted(console, qapp):
    panel, _window, _qapp = console
    panel.input_line.setText("spl")
    panel.input_line.setCursorPosition(3)
    panel.show_completions()
    for _ in range(3):
        _qapp.processEvents()
    assert panel.input_line.text() == "split_chains", panel.input_line.text()
