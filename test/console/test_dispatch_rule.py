"""The command-or-Python rule itself, away from any prompt.

The companion file drives the Qt console. This one tests the rule directly,
because the rule is not the Qt console's -- it was written out once per prompt
(the widget, the ptpython binding, the ``input()`` fallback) and the three
copies had drifted into three different rules:

* the widget's was correct;
* the ptpython binding asked only whether the line compiles, so every
  no-argument command was evaluated as a name and answered ``NameError`` -- the
  defect the widget had already fixed;
* the ``input()`` fallback asked nothing about Python at all, so ``set`` reached
  chimol's ``set`` instead of the builtin -- the opposite defect.

Nothing here needs Qt, so the rule is testable at the level it exists at, and
the last test refuses to let a fourth copy appear.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.core.console import dispatch


# --------------------------------------------------------------------------- #
# The rule
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("line", ["ray", "split_chains", "orient", "zoom", "undo", "reinit"])
def test_a_bare_command_is_a_command(line):
    """Valid Python, and bound to nothing -- evaluating it can only raise."""
    assert dispatch.is_command(line, namespace={})


@pytest.mark.parametrize("line", ["set", "print", "1 + 1", "len('ab')", "[1, 2]"])
def test_python_wins_when_the_name_exists(line):
    """`set` is a chimol command *and* a builtin; alone, it means the type."""
    assert not dispatch.is_command(line, namespace={})


@pytest.mark.parametrize(
    "line", ["fetch 1f5n", "color red, all", "set fog_start, 0.5", "load a.pdb"]
)
def test_a_command_with_arguments_is_a_command(line):
    """Not valid Python, so this half always worked.

    It must stay working while the bare case is fixed.
    """
    assert dispatch.is_command(line, namespace={})


def test_an_unknown_word_goes_to_the_command_layer():
    """A typo at a command prompt is answered by name.

    Not as a ``NameError`` about a language the user was not writing.
    """
    assert dispatch.is_command("splitt_chains", namespace={})


def test_a_bound_name_beats_the_command():
    """Someone who types `ray = 5` gets their variable back.

    The same precedence a shell gives a function over a program of the same
    name.
    """
    assert not dispatch.is_command("ray", namespace={"ray": 5})
    assert not dispatch.is_command("ray.bit_length()", namespace={"ray": 5})


def test_no_dispatcher_means_everything_is_python():
    assert not dispatch.is_command("ray", has_dispatcher=False, namespace={})


@pytest.mark.parametrize("line", ["", "   ", "\t"])
def test_blank_lines_are_not_commands(line):
    assert not dispatch.is_command(line, namespace={})


# --------------------------------------------------------------------------- #
# Unfinished blocks
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("line", ["for i in range(3):", "if x:", "def f():"])
def test_an_unfinished_block_is_not_a_command(line):
    """A prompt where Enter can continue a block must ask this first.

    An opening line does not compile, so the rule alone would call it a
    command -- and once Enter is swallowed by the command layer the body can
    never be typed at all.
    """
    assert dispatch.is_incomplete_python(line)


@pytest.mark.parametrize("line", ["ray", "fetch 1f5n", "x = 1", "for i in []: pass"])
def test_a_finished_line_is_not_incomplete(line):
    assert not dispatch.is_incomplete_python(line)


def test_a_syntax_error_is_not_incomplete():
    """`color red, all` is invalid Python, not half-written Python.

    So it reaches the rule and routes to the command layer.
    """
    assert not dispatch.is_incomplete_python("color red, all")


# --------------------------------------------------------------------------- #
# No fourth copy
# --------------------------------------------------------------------------- #
def test_no_prompt_reimplements_the_rule():
    """The drift is the defect, so it is what is guarded.

    Each prompt is allowed to *use* ``dispatch``; none of them is allowed to
    decide command-or-Python by compiling the line itself, which is how all
    three copies started.
    """
    repo = pathlib.Path(__file__).resolve().parents[2]
    prompts = [
        repo / "chisurf" / "gui" / "chinsole" / "widget.py",
        repo / "chisurf" / "plugins" / "chimol" / "chimol" / "app" / "cli.py",
    ]
    for path in prompts:
        if not path.is_file():
            pytest.skip(f"missing {path}")
        source = path.read_text()
        assert "dispatch.is_command" in source, f"{path.name} does not use the shared rule"
        assert "compile(" not in source, (
            f"{path.name} compiles the line itself -- that is the rule being "
            f"written out a fourth time; call chisurf.core.console.dispatch"
        )
