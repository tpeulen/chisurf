"""Tests for the command-language infrastructure (registry + parser + binder)."""

from __future__ import annotations

import pytest

from chimol.cmd.argparse2 import (
    CommandError,
    bind_and_call,
    split_statements,
    tokenize,
)
from chimol.cmd.base import BaseCmd
from chimol.cmd.registry import collect_commands, command
from chimol.cmd.selection_types import Selection


# --------------------------------------------------------------------------- #
# tokenize
# --------------------------------------------------------------------------- #
def test_tokenize_positional_and_keyword():
    assert tokenize("polymer, 5") == [(None, "polymer"), (None, "5")]
    assert tokenize("polymer, buffer=3") == [(None, "polymer"), ("buffer", "3")]
    assert tokenize("") == []


def test_tokenize_keeps_brackets_and_quotes_intact():
    # commas inside (), [] and quotes must not split the argument
    assert tokenize("(chain A and resi 5), 3") == [
        (None, "(chain A and resi 5)"),
        (None, "3"),
    ]
    assert tokenize("[1, 2, 3], sel") == [(None, "[1, 2, 3]"), (None, "sel")]
    assert tokenize("'a, b', c") == [(None, "'a, b'"), (None, "c")]


def test_tokenize_raw_modes_capture_rest_of_line():
    # raw1: one normal arg, then the whole remainder verbatim (alter/iterate)
    assert tokenize("(sele), b=0, x=1", mode="raw1") == [
        (None, "(sele)"),
        (None, "b=0, x=1"),
    ]
    # raw2: two normal args then verbatim
    assert tokenize("name, resi, foo=bar, baz", mode="raw2") == [
        (None, "name"),
        (None, "resi"),
        (None, "foo=bar, baz"),
    ]


def test_leading_double_equals_is_not_a_keyword():
    assert tokenize("b==1") == [(None, "b==1")]


# --------------------------------------------------------------------------- #
# registry + binder
# --------------------------------------------------------------------------- #
class _Demo:
    @command("zoom", aliases=("zo",))
    def zoom(self, sel: Selection = "all", buffer: float = 2.0):
        return (sel, buffer)

    @command("count")
    def count(self, n: int, flag: bool = False):
        return (n, flag)

    @command("label", mode="raw1")
    def label(self, sel: Selection, expr: str):
        return (sel, expr)

    @command("tune")
    def tune(self, preset: str = "", **overrides):
        return (preset, overrides)

    @command("scale")
    def scale(self, **factors: float):
        return factors


def test_registry_resolves_name_alias_and_prefix():
    reg = collect_commands(_Demo())
    assert reg.resolve("zoom").name == "zoom"
    assert reg.resolve("zo").name == "zoom"       # alias
    assert reg.resolve("cou").name == "count"     # unique prefix
    assert reg.resolve("nope") is None


def test_binder_coerces_by_annotation():
    reg = collect_commands(_Demo())
    z = reg.resolve("zoom").func
    assert bind_and_call(z, tokenize("polymer, 5")) == ("polymer", 5.0)
    assert bind_and_call(z, tokenize("buffer=7")) == ("all", 7.0)  # default sel
    c = reg.resolve("count").func
    assert bind_and_call(c, tokenize("3, flag=on")) == (3, True)
    assert bind_and_call(c, tokenize("4, flag=false")) == (4, False)


def test_binder_missing_required_and_unknown_keyword():
    reg = collect_commands(_Demo())
    c = reg.resolve("count").func
    with pytest.raises(CommandError):
        bind_and_call(c, tokenize(""))            # missing n
    with pytest.raises(CommandError):
        bind_and_call(c, tokenize("3, bogus=1"))  # unknown keyword


def test_binder_routes_unmatched_keywords_into_var_keyword():
    """A ``**kwargs`` command is reachable from the command line.

    Without this the whole keyword half of such a command is dead: the binder
    rejected every name it could not find among the declared parameters.
    """
    reg = collect_commands(_Demo())
    t = reg.resolve("tune").func
    assert bind_and_call(t, tokenize("soft, key_light_intensity=0.5")) == (
        "soft",
        {"key_light_intensity": "0.5"},
    )
    assert bind_and_call(t, tokenize("silhouette=off")) == (
        "",
        {"silhouette": "off"},
    )
    assert bind_and_call(t, tokenize("soft")) == ("soft", {})


def test_binder_coerces_var_keyword_values_by_its_annotation():
    reg = collect_commands(_Demo())
    s = reg.resolve("scale").func
    assert bind_and_call(s, tokenize("x=2, y=0.5")) == {"x": 2.0, "y": 0.5}


def test_raw_mode_command_passes_expression_verbatim():
    reg = collect_commands(_Demo())
    lb = reg.resolve("label").func
    assert bind_and_call(lb, tokenize("(chain A), b=0+1", mode="raw1")) == (
        "(chain A)",
        "b=0+1",
    )


# --------------------------------------------------------------------------- #
# compound lines
# --------------------------------------------------------------------------- #
class _RecordingCmd(BaseCmd):
    """A cmd whose commands only record that they were reached."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.errors: list[str] = []
        super().__init__()
        self.set_error_callback(self.errors.append)

    @command("hide")
    def hide(self, representation: str = "", selection: Selection = "all"):
        self.calls.append(("hide", representation, selection))

    @command("show")
    def show(self, representation: str = "", selection: Selection = "all"):
        self.calls.append(("show", representation, selection))

    @command("iterate", mode="raw1")
    def iterate(self, selection: Selection = "", expression: str = ""):
        self.calls.append(("iterate", selection, expression))


def test_split_statements_keeps_separators_inside_quotes_and_brackets():
    assert split_statements("hide everything, x; show cartoon, x") == [
        "hide everything, x",
        "show cartoon, x",
    ]
    assert split_statements("label sel, 'a; b'") == ["label sel, 'a; b'"]
    assert split_statements("set_color c, [1; 0; 0]") == ["set_color c, [1; 0; 0]"]
    assert split_statements("zoom all;  ; ") == ["zoom all"]
    assert split_statements("") == []


def test_do_runs_every_statement_of_a_compound_line():
    """The object menus' presets are one ``;``-separated line (RF-846).

    Without the split the whole line reached ``hide`` as its arguments and every
    preset answered "too many positional arguments" — dead in the viewport panel,
    which emits the entry verbatim, and alive in the docked one, which happened
    to split it itself.
    """
    cmd = _RecordingCmd()
    cmd.do("hide everything, 1abc; show cartoon, 1abc")
    assert cmd.calls == [
        ("hide", "everything", "1abc"),
        ("show", "cartoon", "1abc"),
    ]
    assert cmd.errors == []


def test_do_leaves_a_raw_command_its_own_semicolons():
    """``iterate``/``alter``/``mdo`` are handed a statement list of their own."""
    cmd = _RecordingCmd()
    cmd.do("iterate name CA, stored.a.append(b); stored.c.append(q)")
    assert cmd.calls == [
        ("iterate", "name CA", "stored.a.append(b); stored.c.append(q)")
    ]
    assert cmd.errors == []
