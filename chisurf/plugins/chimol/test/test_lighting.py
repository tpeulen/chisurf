"""``lighting`` — ChimeraX's presets, and honesty about the ones we cannot do.

Not a PyMOL command: PyMOL has no equivalent outside its ray tracer, so this is
one of the places ChiMOL is deliberately ahead of it. The preset and parameter
names are ChimeraX's, transcribed from ``std_commands/src/lighting.py``.

Two of the preset keys need shadow maps, which are not built. They are kept in
the table rather than dropped, and the command **names what it could not apply** —
a preset that quietly does three of its five things is worse than one that says
so, because `full` without its shadows is a different look and the user should
know which one they got.
"""

from __future__ import annotations

import pathlib

import pytest

_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.cmd import cmd as shared

    win = MolViewPluginWindow()
    win.resize(700, 500)
    win.show()
    for _ in range(12):
        qapp.processEvents()
    win._load_structure_from_path(_PDB)
    for _ in range(20):
        qapp.processEvents()

    messages: list[str] = []
    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(8):
            qapp.processEvents()

    yield win.viewer, shared, do, messages, errors
    win.close()


def _state(viewer):
    return viewer._renderer.lighting_state()


# --------------------------------------------------------------------------- #
# The presets
# --------------------------------------------------------------------------- #
def test_every_chimerax_preset_is_present():
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd

    assert set(Cmd.LIGHTING_PRESETS) >= {
        "simple", "full", "soft", "gentle", "flat", "default"
    }


def test_a_preset_changes_the_lighting(session):
    viewer, _shared, do, _messages, errors = session
    before = _state(viewer)
    do("lighting soft")
    assert errors == []
    assert _state(viewer) != before


def test_soft_is_all_ambient_and_no_key_light(session):
    """That is what makes it soft; a key light would defeat the preset."""
    viewer, _shared, do, _messages, _errors = session
    do("lighting soft")
    state = _state(viewer)
    assert state["key_light_intensity"] == pytest.approx(0.0)
    assert state["fill_light_intensity"] == pytest.approx(0.0)
    assert state["ambient_light_intensity"] > 1.0


def test_simple_has_a_key_and_a_fill_light(session):
    viewer, _shared, do, _messages, _errors = session
    do("lighting simple")
    state = _state(viewer)
    assert state["key_light_intensity"] > 0.5
    assert state["fill_light_intensity"] > 0.0


def test_flat_turns_silhouettes_on(session):
    """Flat shading needs outlines, or the shapes stop reading."""
    viewer, _shared, do, _messages, _errors = session
    do("lighting default")
    assert _state(viewer)["silhouette"] is False
    do("lighting flat")
    assert _state(viewer)["silhouette"] is True


def test_default_restores_a_key_light(session):
    viewer, _shared, do, _messages, _errors = session
    do("lighting soft")
    do("lighting default")
    assert _state(viewer)["key_light_intensity"] > 0.5


# --------------------------------------------------------------------------- #
# What it cannot do, it says
# --------------------------------------------------------------------------- #
def test_a_preset_needing_shadows_says_what_it_skipped(session):
    viewer, _shared, do, messages, errors = session
    messages.clear()
    do("lighting full")
    assert errors == []
    joined = " ".join(messages)
    assert "not applied" in joined
    assert "shadows" in joined and "multishadow" in joined


def test_a_preset_needing_nothing_extra_reports_no_gap(session):
    viewer, _shared, do, messages, _errors = session
    messages.clear()
    do("lighting simple")
    assert not any("not applied" in m for m in messages)


def test_soft_and_gentle_are_identical_until_multishadow_exists(session):
    """Not a bug: in ChimeraX they differ *only* in multishadow map size and
    depth bias, neither of which can be applied yet. Pinned so that when
    multishadow lands, this test fails and forces the difference to be real."""
    viewer, _shared, do, _messages, _errors = session
    do("lighting soft")
    soft = _state(viewer)
    do("lighting gentle")
    assert _state(viewer) == soft


# --------------------------------------------------------------------------- #
# Reporting and errors
# --------------------------------------------------------------------------- #
def test_with_no_argument_it_reports_the_current_state(session):
    viewer, _shared, do, messages, errors = session
    messages.clear()
    do("lighting")
    assert errors == []
    assert messages and "ambient_light_intensity" in messages[-1]


def test_an_unknown_preset_lists_the_real_ones(session):
    viewer, _shared, do, _messages, errors = session
    do("lighting nosuchpreset")
    assert errors and "nosuchpreset" in errors[-1]
    assert "soft" in errors[-1]


def test_the_state_round_trips_through_the_setter(session):
    """The command layer needs no translation table because the names match."""
    viewer, _shared, _do, _messages, _errors = session
    viewer._renderer.set_lighting(
        key_light_intensity=0.25, ambient_light_intensity=0.75
    )
    state = _state(viewer)
    assert state["key_light_intensity"] == pytest.approx(0.25)
    assert state["ambient_light_intensity"] == pytest.approx(0.75)
