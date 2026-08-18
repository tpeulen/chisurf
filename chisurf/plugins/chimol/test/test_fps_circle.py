"""The labelling plan as a circle: what an fps.json becomes.

An fps.json is a network -- positions on chains, distances between pairs --
and neither the JSON nor a table of rows shows the thing that matters about
it: which parts of the structure are labelled, how the pairs cover them, and
which pairs are long against their Förster radius. This is that plot, drawn
with the pyCirclize port in `chimol.cmtk.widgets.circle`.

What is checked is the **mapping**, not the pixels: which sectors a document
becomes, where a position lands, how many chords are drawn and what colours
them. `FpsCirclePanel.build` returns the plot rather than drawing it for
exactly that reason.
"""
from __future__ import annotations

import json
import pathlib

import pytest

import chimol
from chimol.cmtk.testing import RecordingPainter
from chimol.plugins.labelling.circle_window import (
    FpsCirclePanel,
    efficiency,
    make_fps_circle_panel,
)
from chimol.plugins.labelling.fps import FpsModel

#: The shipped example plan, found through the package rather than by counting
#: parent directories -- chimol is a checkout of its own, not a subdirectory of
#: this one, and a path that silently misses turns this file into a skip.
EXAMPLE = (
    pathlib.Path(chimol.__file__).resolve().parent.parent
    / "examples" / "labeling_network.fps.json"
)


def _model(positions, distances=None) -> FpsModel:
    model = FpsModel()
    for name, fields in positions.items():
        model.add_position(name, fields)
    for name, fields in (distances or {}).items():
        model.add_distance(name, fields)
    return model


def _panel(model) -> FpsCirclePanel:
    panel = FpsCirclePanel(viewer=None, model=model)
    panel.source = "a file"        # so `refresh` does not reach for a viewer
    return panel


class _Rect:
    x = y = 0.0
    w = h = 420.0


# --------------------------------------------------------------------------- #
# The mapping
# --------------------------------------------------------------------------- #
def test_a_chain_becomes_a_sector_spanning_what_it_labels():
    """Not the whole chain: a plan labels a handful of sites."""
    panel = _panel(_model({
        "a": {"chain_identifier": "E", "residue_seq_number": 40},
        "b": {"chain_identifier": "E", "residue_seq_number": 60},
    }))
    (low, high), = panel.chains().values()
    assert low < 40 and high > 60
    assert high - low < 120, "the sector covers far more than the plan does"


def test_every_chain_gets_its_own_sector():
    panel = _panel(_model({
        "a": {"chain_identifier": "E", "residue_seq_number": 40},
        "b": {"chain_identifier": "S", "residue_seq_number": 12},
    }))
    circle = panel.build(0, 0, 400, 400)
    assert sorted(s.name for s in circle.sectors) == ["E", "S"]


def test_a_position_lands_at_its_residue_number():
    panel = _panel(_model({
        "start": {"chain_identifier": "E", "residue_seq_number": 10},
        "end": {"chain_identifier": "E", "residue_seq_number": 90},
    }))
    circle = panel.build(0, 0, 400, 400)
    sector = circle.get_sector("E")
    assert len(circle._points) == 2
    angles = sorted(point.rad for point in circle._points)
    assert angles[0] == pytest.approx(sector.x_to_rad(10))
    assert angles[1] == pytest.approx(sector.x_to_rad(90))


def test_each_distance_becomes_one_chord():
    panel = _panel(_model(
        {
            "a": {"chain_identifier": "E", "residue_seq_number": 10},
            "b": {"chain_identifier": "E", "residue_seq_number": 90},
        },
        {"a_b": {"position1_name": "a", "position2_name": "b"}},
    ))
    circle = panel.build(0, 0, 400, 400)
    assert len(circle._links) == 1
    assert circle._links[0].width > 0.0, "a position is a point, so its chord is a line"


def test_a_distance_naming_a_position_that_is_not_there_is_skipped():
    """A document being edited is a document that is briefly wrong."""
    panel = _panel(_model(
        {"a": {"chain_identifier": "E", "residue_seq_number": 10}},
        {"a_ghost": {"position1_name": "a", "position2_name": "ghost"}},
    ))
    assert panel.build(0, 0, 400, 400)._links == []


def test_a_position_with_no_residue_number_is_skipped_not_fatal():
    panel = _panel(_model({
        "broken": {"chain_identifier": "E", "residue_seq_number": "not a number"},
        "fine": {"chain_identifier": "E", "residue_seq_number": 20},
    }))
    circle = panel.build(0, 0, 400, 400)
    assert len(circle._points) == 1


# --------------------------------------------------------------------------- #
# What the colour says
# --------------------------------------------------------------------------- #
def test_efficiency_is_the_forster_curve():
    assert efficiency(52.0, 52.0) == pytest.approx(0.5)
    assert efficiency(26.0, 52.0) > 0.98
    assert efficiency(104.0, 52.0) < 0.02
    assert efficiency(30.0, 0.0) == 0.0        # a pair with no R0 says nothing


def test_a_short_pair_and_a_long_one_are_not_the_same_colour():
    """The whole reason the chord is coloured: measurable, or not."""
    panel = _panel(_model(
        {
            "a": {"chain_identifier": "E", "residue_seq_number": 10},
            "b": {"chain_identifier": "E", "residue_seq_number": 50},
            "c": {"chain_identifier": "E", "residue_seq_number": 90},
        },
        {
            "a_b": {"position1_name": "a", "position2_name": "b",
                    "distance": 25.0, "Forster_radius": 52.0},
            "a_c": {"position1_name": "a", "position2_name": "c",
                    "distance": 95.0, "Forster_radius": 52.0},
        },
    ))
    hot, cold = panel.build(0, 0, 400, 400)._links
    assert hot.colour != cold.colour
    assert hot.colour[0] > cold.colour[0], "the measurable pair should read warmer"
    assert cold.colour[2] > hot.colour[2]


def test_a_distance_with_no_declared_value_still_draws():
    panel = _panel(_model(
        {
            "a": {"chain_identifier": "E", "residue_seq_number": 10},
            "b": {"chain_identifier": "E", "residue_seq_number": 90},
        },
        {"a_b": {"position1_name": "a", "position2_name": "b"}},
    ))
    assert len(panel.build(0, 0, 400, 400)._links) == 1


# --------------------------------------------------------------------------- #
# The panel
# --------------------------------------------------------------------------- #
def test_the_shipped_example_draws_as_its_own_network():
    if not EXAMPLE.is_file():
        pytest.skip(f"missing {EXAMPLE}")
    payload = json.loads(EXAMPLE.read_text())
    panel = _panel(_model(payload["Positions"], payload["Distances"]))
    circle = panel.build(0, 0, 400, 400)
    assert len(circle._points) == len(payload["Positions"])
    assert len(circle._links) == len(payload["Distances"])
    p = RecordingPainter()
    panel.draw(p, _Rect())
    assert any("positions" in s for s in p.strings)


def test_an_empty_document_says_so_instead_of_drawing_a_bare_ring():
    panel = _panel(FpsModel())
    p = RecordingPainter()
    panel.draw(p, _Rect())
    assert any("add_dye" in s or "fps_load" in s for s in p.strings)


def test_the_panel_follows_the_scene_when_no_file_was_given():
    """`fps_circle` with no argument draws what is loaded, and keeps up."""
    from chimol.commands.command import Cmd
    from chimol.testing.mock_viewer import MockViewer, MockWindow

    cmd = Cmd(MockWindow(MockViewer()))
    panel = make_fps_circle_panel(type("Ctx", (), {"viewer": cmd.window.viewer, "cmd": cmd})())
    panel.refresh()
    assert panel.source == "scene"
    assert panel.model is not None


def test_the_command_and_the_menu_row_are_registered():
    from chimol.commands.command import Cmd
    from chimol.testing.mock_viewer import MockViewer, MockWindow

    cmd = Cmd(MockWindow(MockViewer()))
    assert "fps_circle" in cmd.panels.keys(), cmd.panels.why_not("fps_circle", cmd)
    said: list[str] = []
    cmd.set_error_callback(said.append)
    cmd.do("fps_circle")
    assert not any("no such" in line.lower() for line in said), said

    from chimol.ui.menus.bar import menu_bar

    rows = [row for menu in menu_bar() for row in (menu[1] or ())]
    assert any("fps_circle" in str(row) for row in rows), "no menu row opens it"
