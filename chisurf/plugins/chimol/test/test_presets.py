"""PyMOL's presets, and the chain colour cycle they are built on.

A preset is the one-click path from "loaded" to "looks like a figure", and it is
the busiest entry in PyMOL's object menu. Ours were four hand-rolled lines --
``hide everything; show cartoon`` -- wearing PyMOL's labels: same words,
different picture. The recipes are transcribed from ``modules/pymol/preset.py``
now, so what is worth pinning is that each one *runs*, that the ones chimol can
do exactly are exact, and that the ones it cannot do fully **say what they
skipped** rather than quietly doing less.

The chain colour cycle is here too because ``simple`` and ``technical`` are
built on it, and because it is the commonest colouring in structural biology: an
invented eight-colour palette assigned in first-seen order -- which is what
stood here -- gave a different picture from PyMOL for every multi-chain
structure, and a different one again depending on how the file was written.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chimol.core.colors import (
    CHAIN_COLOR_CYCLE,
    _build_chain_color_array,
    get_pymol_color,
)
from chimol.plugins.presets.commands import PresetCommands

_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


# --------------------------------------------------------------------------- #
# The chain colour cycle
# --------------------------------------------------------------------------- #
def test_the_cycle_is_pymols_in_pymols_order():
    """``util._color_cycle``, transcribed. The order is the meaning."""
    assert len(CHAIN_COLOR_CYCLE) == 40
    assert CHAIN_COLOR_CYCLE[:5] == (
        "carbon", "cyan", "lightmagenta", "yellow", "salmon"
    )
    assert CHAIN_COLOR_CYCLE[-1] == "brown"


def test_every_colour_in_the_cycle_is_a_colour_we_know():
    for name in CHAIN_COLOR_CYCLE:
        get_pymol_color(name)  # raises KeyError if not


def test_chains_are_coloured_in_sorted_order_not_first_seen():
    """PyMOL walks ``get_chains``, which is sorted, so chain A is always first.

    Assigning in the order the atoms happen to appear made the same structure
    come out differently depending on how the file was written.
    """
    chains = np.array(["B", "B", "A", "A"])
    colors = _build_chain_color_array(chains, 4)
    a_colour = np.asarray(get_pymol_color(CHAIN_COLOR_CYCLE[0]))
    b_colour = np.asarray(get_pymol_color(CHAIN_COLOR_CYCLE[1]))
    assert np.allclose(colors[2], a_colour), "chain A did not take the first colour"
    assert np.allclose(colors[0], b_colour), "chain B did not take the second"


def test_more_chains_than_colours_wraps():
    """Chain 41 takes the first colour again, as PyMOL's modulo does.

    The ids are single letters so that sorting them is unambiguous -- with
    ``"0"``..``"44"`` the sorted order is ``0, 1, 10, 11, ...``, which is a
    property of string sorting rather than of the cycle.
    """
    letters = [chr(ord("A") + i) for i in range(26)]
    ids = letters + [a + b for a in "AB" for b in letters]      # A..Z, AA..BZ
    chains = np.array(ids[:41])
    colors = _build_chain_color_array(chains, 41)
    order = {chid: i for i, chid in enumerate(sorted(set(chains.tolist())))}
    wrapped = next(c for c in chains.tolist() if order[c] == 40)
    first = next(c for c in chains.tolist() if order[c] == 0)
    row = int(np.where(chains == wrapped)[0][0])
    assert np.allclose(colors[row], colors[int(np.where(chains == first)[0][0])])


# --------------------------------------------------------------------------- #
# The presets
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    pytest.importorskip("chisurf.core.structure")
    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
    win.load_structure_from_path(_PDB)
    for _ in range(20):
        qapp.processEvents()

    messages: list[str] = []
    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        messages.clear()
        errors.clear()
        shared.do(line)
        for _ in range(8):
            qapp.processEvents()

    yield win, do, messages, errors
    win.close()


def _state(win):
    return win.viewer.objects[win.viewer.get_active_object_id()].state


@pytest.mark.parametrize("name", sorted(PresetCommands.PRESETS))
def test_every_preset_runs(session, name):
    """A preset that raises is worse than no preset: the menu entry is dead."""
    _win, do, messages, errors = session
    do(f"preset {name}")
    assert errors == [], f"preset {name} -> {errors[-1]}"
    assert messages and messages[-1].startswith(f"preset {name}: applied")


def test_an_unknown_preset_is_named(session):
    _win, do, _messages, errors = session
    do("preset gorgeous")
    assert errors and "gorgeous" in errors[-1]


def test_a_preset_names_what_it_could_not_do(session):
    """The whole reason to transcribe rather than approximate.

    A preset that quietly does less than PyMOL's leaves a picture that is
    silently not the one PyMOL makes. ``technical`` scopes ``dash_width`` to its
    own contact object, which chimol's one global display config cannot do, so
    that is what it has left to report.
    """
    _win, do, messages, _errors = session
    do("preset technical")
    assert "not applied" in messages[-1]
    assert "dash_width" in messages[-1]


def test_technical_draws_real_polar_contacts(session):
    """The step this preset used to skip, and the reason the finder exists."""
    win, do, _messages, errors = session
    do("preset technical")
    assert errors == []
    contacts = win.viewer.measurements.get("polar_conts")
    assert contacts is not None, "the preset drew no contact object"
    assert contacts["kind"] == "dashes"
    assert contacts["positions"].shape[0] >= 2
    # `label=0`: a few hundred numbers over a structure is unreadable, and
    # PyMOL hides them straight after creating the object for the same reason.
    assert contacts["labels"] == []


def test_classified_sets_a_representation_per_atom_class(session):
    """The one preset chimol can do exactly, so it is pinned exactly."""
    win, do, _messages, errors = session
    do("preset classified")
    assert errors == []
    state = _state(win)
    assert state.show_cartoon, "the polymer got no cartoon"
    assert state.show_sticks, "the organic ligand got no sticks"
    assert state.show_atoms, "the inorganic atoms got no spheres"


def test_simple_colours_the_first_chain_pymols_first_colour(session):
    """``util.cbc`` starts at the carbon green, and chain A is the first chain."""
    win, do, _messages, errors = session
    do("preset simple")
    assert errors == []
    state = _state(win)
    override = state.colors_per_residue_override
    assert override is not None, "preset simple coloured nothing"

    chains = np.asarray(win.viewer._residue_chain_ids).astype(str)
    first = sorted({c.strip() for c in chains.tolist() if c.strip()})[0]
    rows = np.where(chains == first)[0]
    expected = np.asarray(get_pymol_color(CHAIN_COLOR_CYCLE[0]))[:3]
    got = override[rows[0], :3]
    assert np.allclose(got, expected, atol=1e-6), (
        f"chain {first} is {got}, not PyMOL's {CHAIN_COLOR_CYCLE[0]} {expected}"
    )


def test_b_factor_putty_switches_the_cartoon_to_putty(session):
    win, do, _messages, errors = session
    from chimol.core.settings.config import _DISPLAY_CONFIG

    style_before = _DISPLAY_CONFIG.get("cartoon", {}).get("style")
    try:
        do("preset b_factor_putty")
        assert errors == []
        assert _DISPLAY_CONFIG["cartoon"]["style"] == "putty"
        assert _state(win).colors_per_atom_override is not None
    finally:
        # One process-wide config: leaving it on putty breaks other test files.
        _DISPLAY_CONFIG.setdefault("cartoon", {})["style"] = style_before


# --------------------------------------------------------------------------- #
# The menu that runs them
# --------------------------------------------------------------------------- #
def _menu_commands(entry):
    """Every command under a menu entry, including its submenus."""
    out: list[str] = []
    for child in entry.children:
        if child.children:
            out.extend(_menu_commands(child))
        elif child.command:
            out.append(child.command)
    return out


def test_the_menu_offers_pymols_presets_and_runs_the_real_ones():
    """The four hand-rolled entries are what this replaces.

    PyMOL's menu lists thirteen presets plus a *submenu* for the ligand-site
    variants, which is where ``ligand_cartoon`` lives.
    """
    from chimol.ui.menus.objects import ACTION_MENU

    entry = next(e for e in ACTION_MENU if e.label == "preset")
    commands = _menu_commands(entry)
    assert all(c.startswith("preset ") for c in commands), commands
    names = {c.split()[1].rstrip(",") for c in commands}
    assert names <= set(PresetCommands.PRESETS), names - set(PresetCommands.PRESETS)
    # Everything the command offers is reachable from the menu, or it is a
    # feature nobody can find.
    assert names == set(PresetCommands.PRESETS), set(PresetCommands.PRESETS) - names


def test_every_disabled_ligand_site_variant_says_why():
    """A greyed row with no tooltip is indistinguishable from a bug."""
    from chimol.ui.menus.objects import ACTION_MENU

    entry = next(e for e in ACTION_MENU if e.label == "preset")
    sites = next(c for c in entry.children if c.label == "ligand sites")
    for child in sites.children:
        if child.is_separator or child.command:
            continue
        assert child.note.strip(), f"{child.label!r} is disabled with no reason"
