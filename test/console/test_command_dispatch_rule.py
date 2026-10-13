"""Which lines chimol's prompt runs as commands, and which as Python.

A command prompt that takes both needs a rule, and the rule it once had made
**every no-argument command unreachable**: `ray`, `split_chains`, `orient` and
`zoom` are all valid Python expressions, so they were evaluated as names and the
console answered ``NameError: name 'ray' is not defined``. A command *with*
arguments worked, because `fetch 1f5n` is a syntax error and fell through to the
command layer -- which is why the failure looked arbitrary rather than total.

These cases were first pinned against the Qt chimol window's console. That
window was retired (chimol's ``hosts/qt/``, 2026-10-13); the rule lives in
:mod:`chimol.repl` (the router every toolkit-free host and the terminal REPL
ask) and the command vocabulary in :class:`chimol.commands.dispatch.ChimolDispatcher`,
so that is what is driven here -- with no toolkit at all.
"""

from __future__ import annotations

import pathlib

import pytest

_PDB = (
    pathlib.Path(__file__).resolve().parents[2]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "148l.pdb"
)


@pytest.fixture(scope="module")
def session():
    """A viewer with no window, its command layer, the dispatcher and the router."""
    from chimol.commands.command import Cmd
    from chimol.commands.dispatch import ChimolDispatcher
    from chimol.core.viewer import Viewer
    from chimol.hosts.base import ViewerHost
    from chimol.repl import router

    viewer = Viewer()  # no renderer factory: the scene-only sink
    host = ViewerHost(viewer)
    cmd = Cmd(None)
    host.cmd = cmd
    cmd.set_window(host)
    namespace = {"cmd": cmd, "do": cmd.do}
    return router(), namespace, ChimolDispatcher(cmd), viewer


# --------------------------------------------------------------------------- #
# The rule
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("line", ["ray", "split_chains", "orient", "zoom", "undo", "reinit"])
def test_a_bare_command_runs_as_a_command(session, line):
    """The regression, one name per case.

    All of these are syntactically valid Python, and none of them names anything
    Python has -- so evaluating them can only ever raise.
    """
    rule, namespace, dispatcher, _viewer = session
    assert dispatcher.handles(line), f"{line} is not a chimol command"
    assert rule.is_command(line, namespace), f"{line} went to Python"


@pytest.mark.parametrize("line", ["set", "1 + 1", "print", "len('ab')"])
def test_python_still_wins_when_the_name_exists(session, line):
    """The case the old rule was protecting, and it is kept.

    `set` is a chimol command *and* a builtin. Someone typing it alone at a
    Python-capable prompt means the type; someone typing `set fog_start, 0.5`
    means the command, and that is a syntax error so it routes correctly.
    """
    rule, namespace, _dispatcher, _viewer = session
    assert not rule.is_command(line, namespace), f"{line} was taken as a command"


def test_a_command_with_arguments_still_routes(session):
    """It always did -- `fetch 1f5n` is not valid Python -- but it must not
    regress while the bare case is fixed.
    """
    rule, namespace, _dispatcher, _viewer = session
    assert rule.is_command("color red, all", namespace)
    assert rule.is_command("set fog_start, 0.5", namespace)


def test_an_unknown_word_goes_to_the_command_layer(session):
    """So a typo is reported as an unknown command rather than as a Python
    ``NameError``, which at a command prompt explains nothing.
    """
    rule, namespace, _dispatcher, _viewer = session
    assert rule.is_command("splitt_chains", namespace)


# --------------------------------------------------------------------------- #
# It actually runs
# --------------------------------------------------------------------------- #
def test_split_chains_through_the_dispatcher_splits_the_chains(session):
    """End to end through the dispatcher, because the rule above is only half of it."""
    if not _PDB.is_file():
        pytest.skip(f"missing fixture {_PDB}")
    _rule, _namespace, dispatcher, viewer = session
    dispatcher.execute(f'load "{_PDB}"')
    dispatcher.execute("split_chains")

    names = [entry["name"] for entry in viewer.list_objects()]
    assert any(name.endswith("_E") for name in names), names
    assert any(name.endswith("_S") for name in names), names


# --------------------------------------------------------------------------- #
# Completion
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "typed,expected", [("spl", "split_chains"), ("orie", "orient"), ("col", "color")]
)
def test_tab_completes_a_command(session, typed, expected):
    """The dispatcher answers command names, so Tab completes chimol commands."""
    _rule, _namespace, dispatcher, _viewer = session
    assert expected in dispatcher.completions(typed, len(typed)), typed


def test_a_single_match_is_the_only_answer(session):
    """ "spl" also matches chimol's ``splat``; "split" has one match."""
    _rule, _namespace, dispatcher, _viewer = session
    assert dispatcher.completions("split", 5) == ["split_chains"]
