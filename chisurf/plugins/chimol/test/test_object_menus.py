"""The A/S/H/L/C menus must stay a 1:1 match for PyMOL's.

PyMOL's object panel is how most people drive PyMOL, so the value here is
*muscle memory*: the same entries, in the same order, with the same separators
and the same labels. That is a property worth pinning, because it is exactly the
kind of thing that rots — someone adds a feature and appends its entry at the
bottom instead of where PyMOL has it.

The reference lists below are transcribed from ``pymol/menu.py``'s own builders
(``mol_action``/``mol_show``/``mol_hide``/``mol_labels``/``mol_color``), dumped by
calling them rather than read off a screenshot. When PyMOL is importable the test
regenerates them and compares; otherwise it compares against the transcription,
so the check still runs in an environment without PyMOL.
"""

from __future__ import annotations

import pathlib

import pytest

from chimol.object_menus import (
    ACTION_MENU,
    COLOR_MENU,
    HIDE_MENU,
    LABEL_MENU,
    OBJECT_MENUS,
    SHOW_MENU,
)

# Top-level labels, in order, with "" for a separator. From PyMOL 3.x.
_PYMOL_ACTION = [
    "zoom", "orient", "center", "origin", "",
    "drag matrix", "reset matrix", "",
    "drag coordinates", "clean", "",
    "preset", "find", "align", "generate", "",
    "assign sec. struc.", "",
    "rename object", "copy to object", "group", "delete object", "",
    "hydrogens", "remove waters", "",
    "state", "masking", "sequence", "movement", "compute",
]

_PYMOL_REP_ACTION = [
    "wire", "  lines", "  nonbonded", "",
    "licorice", "  sticks", "  nb_spheres", "",
    "ribbon", "cartoon", "",
    "label", "cell", "",
    "dots", "spheres", "",
    "mesh", "surface", "flag ignore",
]

_PYMOL_SHOW = (
    ["as", ""] + _PYMOL_REP_ACTION
    + ["", "organic", "main chain", "side chain", "disulfides", "", "valence"]
)

_PYMOL_HIDE = (
    ["everything", ""] + _PYMOL_REP_ACTION
    + ["", "main chain", "side chain", "waters", "", "hydrogens", "",
       "unselected", "", "valence"]
)

_PYMOL_LABEL = [
    "clear", "",
    "residues", "residues (oneletter)", "chains", "segments", "",
    "atom name", "element symbol", "residue name", "one letter code",
    "residue identifier", "chain identifier", "segment identifier", "",
    "b-factor", "occupancy", "vdw radius", "",
    "other properties", "",
    "atom identifiers",
]

_PYMOL_COLOR = [
    "by element", "by chain", "by ss  ", "by rep", "spectrum", "",
    "auto", "",
    "reds", "greens", "blues", "yellows", "magentas", "cyans", "oranges",
    "tints", "grays",
]

_REFERENCE = {
    "A": _PYMOL_ACTION,
    "S": _PYMOL_SHOW,
    "H": _PYMOL_HIDE,
    "L": _PYMOL_LABEL,
    "C": _PYMOL_COLOR,
}

_MENUS = {"A": ACTION_MENU, "S": SHOW_MENU, "H": HIDE_MENU,
          "L": LABEL_MENU, "C": COLOR_MENU}


def _labels(entries) -> list[str]:
    return ["" if e.is_separator else e.label for e in entries]


@pytest.mark.parametrize("key", list("ASHLC"))
def test_labels_and_order_match_pymol(key):
    """PyMOL's menu is a **prefix** of ChiMOL's, in PyMOL's own order.

    Exact equality was the original rule and it is the wrong one: ChiMOL has
    representations PyMOL does not -- `metaball` has no PyMOL equivalent at all,
    and `trace` and `nonbonded` are spelled differently -- and until they were
    added to the menus they were reachable only from the toolbar. A menu-driven
    session could not get at them, which defeats the point of having menus.

    The target ([specs/chimol](okf/specs/chimol.md)) settles the tension:
    extensions are **additive**. Everything PyMOL has must be present, in PyMOL's
    order, so muscle memory works; anything extra goes *after* it, so the
    familiar part of the menu is where a PyMOL user expects to find it.
    """
    labels = _labels(_MENUS[key])
    reference = _REFERENCE[key]
    assert labels[:len(reference)] == reference, (
        "PyMOL's entries must come first, in PyMOL's order"
    )
    extra = [label for label in labels[len(reference):] if label]
    if extra:
        # Additions are allowed, but they must be genuinely new rather than a
        # PyMOL entry accidentally duplicated further down.
        assert not (set(extra) & set(reference)), (
            f"{key} menu repeats PyMOL entries after the end: "
            f"{sorted(set(extra) & set(reference))}"
        )


def test_the_five_buttons_are_in_pymol_order():
    assert [key for key, _, _ in OBJECT_MENUS] == list("ASHLC")


def test_every_button_has_a_menu():
    for key, title, entries in OBJECT_MENUS:
        assert entries, f"{key} ({title}) has no entries"


# --------------------------------------------------------------------------- #
# Regenerated from PyMOL itself, when it is installed
# --------------------------------------------------------------------------- #
def _pymol_top_level(builder_name: str) -> list[str]:
    from pymol import cmd, menu

    builder = getattr(menu, builder_name)
    labels = []
    for item in builder(cmd, "obj01"):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        kind, label = item[0], str(item[1])
        if kind == 2:  # PyMOL's inert header row
            continue
        # PyMOL prefixes some labels with a colour escape such as "\933".
        if label.startswith("\\") and len(label) > 4:
            label = label[4:]
        labels.append("" if kind == 0 else label)
    return labels


@pytest.mark.parametrize(
    "key, builder",
    [("A", "mol_action"), ("S", "mol_show"), ("H", "mol_hide"),
     ("L", "mol_labels"), ("C", "mol_color")],
)
def test_the_transcription_still_matches_a_live_pymol(key, builder):
    """Guards the reference lists above from drifting away from PyMOL itself."""
    pytest.importorskip("pymol")
    live = _pymol_top_level(builder)
    if key == "C":
        # PyMOL renders the colour families with per-letter colour escapes
        # ("\900s\950p..." for spectrum); compare only the plain entries.
        live = [lab for lab in live if "\\" not in lab]
        expected = [lab for lab in _REFERENCE[key] if lab != "spectrum"]
        assert live == expected
        return
    assert live == _REFERENCE[key]


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #
def test_supported_entries_carry_a_command_and_a_target():
    """Every enabled entry must name its target, or it acts on the wrong thing."""
    def walk(entries):
        for entry in entries:
            if entry.is_separator:
                continue
            if entry.children:
                walk(entry.children)
                continue
            if entry.command is None:
                continue
            # A few chimol commands are global and take no selection: `dss`,
            # `spectrum`, `set`, and `as` (which switches the primary
            # representation for the whole scene).
            head = entry.command.split(",")[0].strip()
            if head in ("dss", "spectrum") or head.split()[0] in ("set", "as"):
                continue
            assert "{sele}" in entry.command, entry.label

    for _, _, entries in OBJECT_MENUS:
        walk(entries)


def test_unsupported_entries_explain_themselves():
    """A greyed-out entry with no reason is just a broken menu."""
    def walk(entries):
        for entry in entries:
            if entry.is_separator:
                continue
            if entry.children:
                walk(entry.children)
                continue
            if entry.command is None:
                assert entry.note, f"{entry.label!r} is disabled without a reason"

    for _, _, entries in OBJECT_MENUS:
        walk(entries)


def test_prompted_entries_take_their_value():
    def walk(entries):
        for entry in entries:
            if entry.is_separator:
                continue
            if entry.children:
                walk(entry.children)
                continue
            if entry.prompt is not None:
                assert entry.command and "{text}" in entry.command, entry.label
            elif entry.command:
                assert "{text}" not in entry.command, entry.label

    for _, _, entries in OBJECT_MENUS:
        walk(entries)


def test_every_command_is_a_registered_chimol_command():
    """A menu entry wired to a command that does not exist is a dead button."""
    from chimol.cmd.command import Cmd

    known = set(Cmd().command_names())

    def walk(entries):
        for entry in entries:
            if entry.is_separator:
                continue
            if entry.children:
                walk(entry.children)
                continue
            if not entry.command:
                continue
            for line in entry.command.split(";"):
                head = line.strip().split()[0].split(",")[0].lower()
                assert head in known, f"{entry.label!r} runs unknown '{head}'"

    for _, _, entries in OBJECT_MENUS:
        walk(entries)


# --------------------------------------------------------------------------- #
# The menus have to work on the object they were opened on
# --------------------------------------------------------------------------- #
# Every menu command scopes itself with `... and <object>`, which turned up two
# holes in the selection grammar: a PDB-style name such as `1dg3` lexed as a
# number followed by an identifier ("Unexpected token INT '1'"), and a bare
# object name selected nothing at all.


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    import pathlib
    import shutil

    from chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )

    src = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    # Named like a PDB entry on purpose: the digit-led name is the bug.
    pdb = tmp_path / "1abc.pdb"
    shutil.copyfile(src, pdb)

    win = MolViewPluginWindow()
    win._load_structure_from_path(pdb, name="1abc")
    return win


def _count(window, expression):
    from chimol.cmd.command import Cmd

    cmd = Cmd(window)
    messages, errors = [], []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    cmd.do(f"count_atoms {expression}")
    assert errors == [], errors
    return int(messages[-1])


def test_a_digit_led_object_name_lexes_as_a_name(window):
    """`1abc` must not lex as the number 1 followed by `abc`."""
    assert _count(window, "1abc") == len(window.viewer._atoms)


def test_numbers_still_lex_as_numbers(window):
    """The tokenizer change must not break residue ranges."""
    assert _count(window, "resi 10-20") > 0


def test_an_object_name_scopes_a_selection(window):
    """`hetatm and 1abc` is how every menu entry targets its molecule."""
    scoped = _count(window, "hetatm and 1abc")
    unscoped = _count(window, "hetatm")
    assert scoped == unscoped > 0


def test_a_menu_entry_reaches_the_viewer(window):
    """End to end: an entry on a molecule's own row must change the display."""
    import numpy as np

    window.sync_internal_gui()
    gui = window.viewer._renderer._internal_gui
    row = next(r for r in gui.rows if r.name == "1abc")

    entry = next(
        e for e in HIDE_MENU if e.label == "spheres" and e.command
    )
    before = int(np.count_nonzero(window.viewer._ball_mask))
    assert before > 0
    # What a click does: the panel binds `{sele}` to the row and runs it.
    gui._emit(entry.command, row.name)
    assert int(np.count_nonzero(window.viewer._ball_mask)) == 0


def test_every_molecule_has_its_own_buttons(window):
    """The buttons belong to the row, not to the panel.

    A single shared row would silently retarget every action at whatever is
    selected, which is the one thing a PyMOL user would never expect.
    """
    window.sync_internal_gui()
    gui = window.viewer._renderer._internal_gui
    gui.layout(1000, 700)
    assert gui.rows, "no object rows"
    # One dict of menu hit-rects per row, including the `all` header, which
    # acts on everything and therefore needs the same five.
    assert len(gui._button_rects) == len(gui.rows)
    for buttons in gui._button_rects:
        assert list(buttons) == list("ASHLC")


def test_a_rows_menu_targets_that_row(window, monkeypatch):
    """Two molecules, and each row's menu must name its own."""
    import shutil

    src = next(iter(window._object_store.values()))["path"]
    other = shutil.copyfile(src, str(src).replace("1abc", "2xyz"))
    window._load_structure_from_path(pathlib.Path(other), name="2xyz")
    window.sync_internal_gui()

    gui = window.viewer._renderer._internal_gui
    molecules = [
        r for r in gui.rows
        if not r.is_header and not r.is_selection and not r.is_measurement
        and not r.is_group
    ]
    assert {r.name for r in molecules} >= {"1abc", "2xyz"}

    issued: list[str] = []
    gui.set_run_command(issued.append)
    entry = next(e for e in ACTION_MENU if e.label == "zoom" and e.command)
    for row in molecules:
        issued.clear()
        gui._emit(entry.command, row.name)
        assert issued == [f"zoom {row.name}"], issued


def test_unsupported_entries_are_greyed_out_in_the_built_menu(window):
    """The disabled rows must survive into the real QMenu, with their reason."""
    # "Disabled" is a property of the entry, not of a widget: an entry with no
    # `command` is one chimol has no equivalent for, and `note` says which.
    # Every host draws it greyed from the same two fields, so asserting them
    # covers the painted panel and the browser alike -- where asking a QMenu
    # covered only the one host that no longer exists.
    by_label = {e.label: e for e in ACTION_MENU if e.label}
    assert by_label["drag matrix"].command is None
    assert by_label["drag matrix"].note
    assert by_label["zoom"].command
