"""The labelling plan as a circle: what an fps.json becomes.

An fps.json is a network -- positions on chains, distances between pairs --
and neither the JSON nor a table of rows shows the thing that matters about
it: which parts of the structure are labelled, how the pairs cover them, and
which pairs are long against their Förster radius. This is that plot, drawn
with the pyCirclize port in `cmtk.widgets.circle`.

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
from cmtk.testing import RecordingPainter
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


# --------------------------------------------------------------------------- #
# Several datasets in one document
# --------------------------------------------------------------------------- #
class _Scene:
    """The little of a viewer this panel touches: objects and measurements."""

    def __init__(self, measurements=None):
        self.objects = {}
        self.measurements = dict(measurements or {})
        self.updates = 0

    def update_view(self, *args, **kwargs):
        self.updates += 1


def _network() -> FpsModel:
    model = _model(
        {
            "a": {"chain_identifier": "E", "residue_seq_number": 10},
            "b": {"chain_identifier": "E", "residue_seq_number": 50},
            "c": {"chain_identifier": "E", "residue_seq_number": 90},
        },
        {
            "a-b_C1": {"position1_name": "a", "position2_name": "b",
                       "distance": 30.0, "Forster_radius": 52.0},
            "a-c_C1": {"position1_name": "a", "position2_name": "c",
                       "distance": 70.0, "Forster_radius": 52.0},
            "b-c_C2": {"position1_name": "b", "position2_name": "c",
                       "distance": 45.0, "Forster_radius": 52.0},
        },
    )
    model.score_sets = {
        "chi2_C1": {"distances": ["a-b_C1", "a-c_C1"]},
        "chi2_C2": {"distances": ["b-c_C2"]},
    }
    return model


def test_the_documents_score_sets_are_the_datasets():
    """An fps.json's chi-squared sections are subsets of its distances."""
    panel = _panel(_network())
    assert [label for label, _keys in panel.datasets()] == [
        "All distances", "chi2_C1 (2)", "chi2_C2 (1)",
    ]


def test_choosing_a_dataset_draws_only_its_chords():
    panel = _panel(_network())
    assert len(panel.build(0, 0, 400, 400)._links) == 3
    assert panel.choose("chi2_C2")
    assert len(panel.build(0, 0, 400, 400)._links) == 1


def test_a_choice_survives_the_next_draw():
    """The chooser is filled from the document; refilling it must not reset it."""
    panel = _panel(_network())
    panel.choose("chi2_C1")
    panel.draw(RecordingPainter(), _Rect())
    assert panel.dataset.startswith("chi2_C1")
    assert panel.combo.value == panel.dataset


def test_choosing_a_set_the_document_does_not_have_is_refused():
    panel = _panel(_network())
    assert not panel.choose("chi2_nope")


def test_the_choice_governs_the_lines_in_the_scene_too():
    """One switch, both pictures -- ninety-nine lines is a hairball either way."""
    panel = _panel(_network())
    panel.viewer = _Scene({
        "a-b_C1": {"kind": "distance", "color": [1, 1, 0, 1]},
        "a-c_C1": {"kind": "distance", "color": [1, 1, 0, 1]},
        "b-c_C2": {"kind": "distance", "color": [1, 1, 0, 1]},
        "by_hand": {"kind": "distance", "color": [1, 1, 0, 1]},
    })
    panel.choose("chi2_C2")
    visible = {n for n, f in panel.viewer.measurements.items() if f.get("visible", True)}
    assert visible == {"b-c_C2", "by_hand"}, (
        "a line drawn by hand is in no dataset and must not be hidden by one"
    )


# --------------------------------------------------------------------------- #
# Hover: one act, two pictures
# --------------------------------------------------------------------------- #
def _hovering(panel, name):
    """Put the pointer on *name*'s dot, as the chrome would."""
    panel.build(0, 0, 400, 400)          # fills the dot table
    x, y = panel._dots[name]
    return panel.hover(x, y, _Rect())


def test_hovering_a_dot_names_the_position_under_it():
    panel = _panel(_network())
    assert _hovering(panel, "b")
    assert panel.hovered == "b"
    assert not panel.hover(*panel._dots["b"], _Rect()), "no move, no repaint"


def test_the_pointer_leaving_the_panel_clears_the_hover():
    panel = _panel(_network())
    _hovering(panel, "b")
    assert panel.hover(-500.0, -500.0, _Rect())
    assert panel.hovered is None


def test_hovering_lights_the_positions_own_distances_in_the_scene():
    panel = _panel(_network())
    panel.viewer = _Scene({
        "a-b_C1": {"kind": "distance", "color": [1, 1, 0, 1],
                   "positions_named": ("a", "b")},
        "b-c_C2": {"kind": "distance", "color": [1, 1, 0, 1],
                   "positions_named": ("b", "c")},
        "a-c_C1": {"kind": "distance", "color": [1, 1, 0, 1],
                   "positions_named": ("a", "c")},
    })
    _hovering(panel, "b")
    lit = {n for n, f in panel.viewer.measurements.items()
           if tuple(f["color"]) != (1, 1, 0, 1)}
    assert lit == {"a-b_C1", "b-c_C2"}

    panel.hover(-500.0, -500.0, _Rect())
    assert all(tuple(f["color"]) == (1, 1, 0, 1)
               for f in panel.viewer.measurements.values()), (
        "the highlight outlived the hover"
    )


def test_the_pair_comes_from_the_measurement_not_from_its_name():
    """A real document names a distance after the experiment: `19-119_C1`."""
    panel = _panel(_network())
    assert panel._pair_of("19-119_C1", {"positions_named": ("19D", "119A")}) == ("19D", "119A")
    # ...then the document, then the name -- in that order.
    assert panel._pair_of("a-b_C1", {}) == ("a", "b")
    assert panel._pair_of("x_y", {}) == ("x", "y")


def test_the_hover_hook_is_wired_to_the_window():
    """Without it the panel is told about presses and never about the pointer."""
    panel = _panel(_network())
    window = panel.window()
    assert window.on_hover is not None and window.on_press is not None


# --------------------------------------------------------------------------- #
# One window: the network, the records, and the document
# --------------------------------------------------------------------------- #
def test_the_panel_has_the_four_tabs():
    """A plan is one thing, so it is one window."""
    from chimol.plugins.labelling.circle_window import TABS

    panel = _panel(_network())
    assert [item.label for item in panel.tabs.items] == list(TABS)
    assert TABS == ("Network", "Positions", "Distances", "JSON")


def _open(panel, name: str):
    panel.tabs.select([item.label for item in panel.tabs.items].index(name))
    return panel


def test_the_positions_tab_lists_them_and_edits_the_selected_one():
    panel = _open(_panel(_network()), "Positions")
    p = RecordingPainter()
    panel.draw(p, _Rect())
    assert panel._rows["Positions"].row_count() == 3
    name, fields = panel._record("Positions")
    assert name and fields is not None
    editor = panel._editor("Positions")
    assert editor is not None
    keys = {row.key for row in editor.model.settings}
    assert "field.chain_identifier" in keys and "field.residue_seq_number" in keys
    editor.model.setter("field.residue_seq_number", 42)
    assert fields["residue_seq_number"] == 42, "the form did not write to the document"


def test_the_distances_tab_edits_a_distance():
    panel = _open(_panel(_network()), "Distances")
    panel.draw(RecordingPainter(), _Rect())
    name, fields = panel._record("Distances")
    assert name in panel.model.distances
    panel._editor("Distances").model.setter("field.Forster_radius", 60.0)
    assert fields["Forster_radius"] == 60.0


def test_a_record_can_be_added_and_removed():
    panel = _panel(_network())
    before = len(panel.model.positions)
    added = panel.add_record("Positions")
    assert added and len(panel.model.positions) == before + 1
    assert set(panel.model.positions[added]) >= {"chain_identifier", "residue_seq_number"}
    panel._lists["Positions"].selection.set_count(panel._rows["Positions"].row_count())
    panel.remove_record("Positions")
    assert len(panel.model.positions) == before


def test_removing_a_position_takes_its_distances_with_it():
    """A distance to a position that is gone is not a distance."""
    panel = _panel(_network())
    panel.draw(RecordingPainter(), _Rect())
    _open(panel, "Positions")
    panel.draw(RecordingPainter(), _Rect())
    name, _fields = panel._record("Positions")
    panel.remove_record("Positions")
    for fields in panel.model.distances.values():
        assert name not in (fields["position1_name"], fields["position2_name"])


def test_the_json_tab_shows_the_document_and_applies_it_back():
    panel = _open(_panel(_network()), "JSON")
    panel.draw(RecordingPainter(), _Rect())
    text = panel._json_editor().text
    assert '"Positions"' in text and '"Distances"' in text
    panel._json.set_text(text.replace('"residue_seq_number": 10',
                                      '"residue_seq_number": 11'))
    assert panel.apply_json()
    assert panel.model.positions["a"]["residue_seq_number"] == 11


def test_invalid_json_is_refused_rather_than_swallowing_the_document():
    panel = _open(_panel(_network()), "JSON")
    panel.draw(RecordingPainter(), _Rect())
    panel._json.set_text("{ this is not json")
    assert not panel.apply_json()
    assert len(panel.model.positions) == 3, "a typo emptied the document"


def test_saving_needs_a_file_and_says_so():
    panel = _panel(_network())
    assert not panel.save()


def test_the_tabs_can_be_opened_from_a_command():
    """`fps_circle <plan>, , Positions`, and `fps_edit` on the JSON tab."""
    import inspect

    from chimol.plugins.labelling.commands import LabellingCommands

    assert "tab" in inspect.signature(LabellingCommands.fps_circle).parameters
    assert "JSON" in inspect.getsource(LabellingCommands.fps_edit)


def test_labelling_has_its_own_submenu():
    from chimol.ui.menus.bar import menu_bar

    tools = dict(menu_bar()).get("Tools", ())
    labelling = [row for row in tools if str(getattr(row, "label", "")) == "Labelling"]
    assert labelling, "Tools has no Labelling submenu"
    children = [child.command for child in (labelling[0].children or ())]
    assert any("fps_circle" in str(c) for c in children)
    assert any("fps_edit" in str(c) for c in children)
    assert any("wizard labelling" in str(c) for c in children)
    # ...and the rows are not also loose in Tools itself.
    loose = [row for row in tools if "Labelling:" in str(getattr(row, "label", ""))]
    assert not loose, loose


# --------------------------------------------------------------------------- #
# Selecting a position: one act, two pictures, three colours
# --------------------------------------------------------------------------- #
def test_selecting_a_position_and_clearing_it():
    panel = _panel(_network())
    assert panel.select("a") and panel.selected == "a"
    assert not panel.select("a"), "selecting the same one again is not a change"
    assert panel.select(None) and panel.selected is None


def test_the_partners_are_the_ones_it_is_measured_against():
    panel = _panel(_network())
    assert panel.partners("a") == {"b", "c"}
    assert panel.partners("b") == {"a", "c"}


def test_the_partners_are_taken_from_the_dataset_that_is_drawn():
    """What is on screen is what the question is about."""
    panel = _panel(_network())
    panel.choose("chi2_C2")            # only b-c
    assert panel.partners("a") == set()
    assert panel.partners("b") == {"c"}


def test_the_circle_draws_the_three_roles():
    from chimol.plugins.labelling.circle_window import MUTED, PARTNER, SELECTED

    panel = _panel(_network())
    panel.select("a")
    circle = panel.build(0, 0, 400, 400)
    colours = {tuple(point.colour) for point in circle._points}
    assert tuple(SELECTED) in colours and tuple(PARTNER) in colours
    selected = [p for p in circle._points if tuple(p.colour) == tuple(SELECTED)]
    partners = [p for p in circle._points if tuple(p.colour) == tuple(PARTNER)]
    assert len(selected) == 1 and len(partners) == 2
    assert selected[0].radius > partners[0].radius, (
        "the selected dot should be the biggest thing in the circle"
    )


def test_a_selected_positions_chords_are_thick_and_the_rest_are_not():
    from chimol.plugins.labelling.circle_window import MUTED, SELECTED

    panel = _panel(_network())
    panel.select("a")
    links = panel.build(0, 0, 400, 400)._links
    mine = [link for link in links if tuple(link.colour) == tuple(SELECTED)]
    others = [link for link in links if tuple(link.colour) == tuple(MUTED)]
    assert len(mine) == 2 and len(others) == 1
    assert mine[0].width > others[0].width * 1.5


def test_chords_are_not_hairlines_when_nothing_is_selected():
    """"Thicker in general": a hundred chords at one pixel is a smudge."""
    panel = _panel(_network())
    assert all(link.width >= 2.0 for link in panel.build(0, 0, 400, 400)._links)


def test_a_press_on_a_dot_selects_it_and_a_press_beside_it_clears():
    panel = _panel(_network())
    panel.draw(RecordingPainter(), _Rect())
    x, y = panel._dots["b"]
    assert panel.press(x, y, _Rect())
    assert panel.selected == "b"
    panel.draw(RecordingPainter(), _Rect())
    centre_x = sum(dot[0] for dot in panel._dots.values()) / len(panel._dots)
    centre_y = sum(dot[1] for dot in panel._dots.values()) / len(panel._dots)
    assert panel.press(centre_x, centre_y, _Rect())
    assert panel.selected is None


def test_a_hover_does_not_take_the_answer_off_the_structure():
    """With a selection showing, moving the pointer must not repaint the scene."""
    panel = _panel(_network())
    panel.viewer = _Scene()
    panel.draw(RecordingPainter(), _Rect())
    panel.select("a")
    before = panel.viewer.updates
    panel.hover(*panel._dots["b"], _Rect())
    assert panel.hovered == "b"
    assert panel.viewer.updates == before, "the hover repainted the selection away"
