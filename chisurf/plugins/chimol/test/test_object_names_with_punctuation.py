"""An object called `EMD-3061` must be usable from the menus.

Reported as a wall of red: *"Selection parse error: Unexpected token
Token(INT, '3061')"*, repeated once per menu click on a loaded EMDB map.

The name is not chosen by the selection grammar — an EMDB entry arrives called
`EMD-3061` — and a hyphen there is the **range** operator `resi 1-40` needs, so
the name lexed as `EMD`, `-`, `3061` and **every** A/S/H/L/C command on that
object was a parse error. Quoting did not help either: there was no string
token at all.

The same class of bug is already recorded in the tokenizer for `1dg3`, which
used to lex as INT + IDENT. This is its punctuation half.
"""
from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from chimol.cmd.sele_parser import tokenize  # noqa: E402
from chimol.object_menus import (  # noqa: E402
    quote_selection_name,
)


# --------------------------------------------------------------------------- #
# Lexing
# --------------------------------------------------------------------------- #
def test_a_quoted_name_is_one_identifier():
    for text in ('"EMD-3061"', "'EMD-3061'"):
        tokens = tokenize(text)
        assert [(t.type, t.value) for t in tokens] == [("IDENT", "EMD-3061")]


def test_a_range_is_still_a_range():
    """The hyphen has a job, which is why the bare name cannot simply absorb it."""
    kinds = [t.type for t in tokenize("resi 1-40")]
    assert kinds == ["IDENT", "INT", "MINUS", "INT"]


def test_a_digit_led_name_still_lexes_whole():
    """The precedent this repeats: `1dg3` once lexed as INT + IDENT."""
    assert [(t.type, t.value) for t in tokenize("1dg3")] == [("IDENT", "1dg3")]


# --------------------------------------------------------------------------- #
# Quoting
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["148l", "1dg3", "sele", "all", "obj_2"])
def test_a_bare_name_is_left_alone(name):
    """So the commands echoed at the prompt stay readable."""
    assert quote_selection_name(name) == name


@pytest.mark.parametrize("name", ["EMD-3061", "my map", "a+b", "x,y"])
def test_anything_else_is_quoted(name):
    quoted = quote_selection_name(name)
    assert quoted == f'"{name}"'
    assert [(t.type, t.value) for t in tokenize(quoted)] == [("IDENT", name)]


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def hyphenated(request):
    import pathlib

    from qtpy import QtWidgets

    from chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chimol.cmd import cmd as shared

    pdb = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    if not pdb.is_file():
        pytest.skip(f"missing fixture {pdb}")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MolViewPluginWindow()
    win.show()
    for _ in range(4):
        app.processEvents()

    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    def run(line: str) -> list[str]:
        before = len(errors)
        win._run_object_menu_command(line)
        for _ in range(3):
            app.processEvents()
        return errors[before:]

    run(f"load {pdb}")
    run("set_name 148l, EMD-3061")
    yield run
    win.close()


@pytest.mark.parametrize(
    "template",
    [
        "zoom {sele}",
        "orient {sele}",
        "color red, {sele}",
        "show cartoon, {sele}",
        "hide everything, solvent and {sele}",
        "cnc {sele}",
    ],
)
def test_the_menu_commands_work_on_a_hyphenated_object(hyphenated, template):
    command = template.replace("{sele}", quote_selection_name("EMD-3061"))
    complained = hyphenated(command)
    assert not complained, f"{command} -> {complained}"
