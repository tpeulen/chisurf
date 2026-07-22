"""Tests for the command-language infrastructure (registry + parser + binder)."""

from __future__ import annotations

import pytest

from chisurf.plugins.chimol.chimol.cmd.argparse2 import (
    CommandError,
    bind_and_call,
    tokenize,
)
from chisurf.plugins.chimol.chimol.cmd.registry import collect_commands, command
from chisurf.plugins.chimol.chimol.cmd.selection_types import Selection


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


def test_raw_mode_command_passes_expression_verbatim():
    reg = collect_commands(_Demo())
    lb = reg.resolve("label").func
    assert bind_and_call(lb, tokenize("(chain A), b=0+1", mode="raw1")) == (
        "(chain A)",
        "b=0+1",
    )
