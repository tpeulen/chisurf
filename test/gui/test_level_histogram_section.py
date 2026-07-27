"""The shared ``level_histogram`` section: thresholds picked off a distribution.

What these pin is that the *model* owns the levels. The widget keeps no copy, so
a level dragged on screen and a level read back from the model cannot disagree —
which is the failure this codebase keeps finding whenever a view caches what it
displays.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.gui.autoform.sections.registry import get_section_factory


class _Model:
    """A view-model of the shape the section expects."""

    def __init__(self, levels=None):
        self.levels = list(levels if levels is not None else [{"level": 0.0}])
        self.applied = 0
        self._values = np.random.default_rng(3).normal(0.0, 1.0, 20_000)

    def histogram(self):
        return np.histogram(self._values, bins=64)

    def bounds(self):
        return -4.0, 4.0

    def apply(self):
        self.applied += 1

    # Deliberately a property, to prove the section refuses to read one as a
    # source rather than silently rendering nothing.
    @property
    def histogram_property(self):
        return np.histogram(self._values, bins=64)


@pytest.fixture
def widget(qtbot):
    factory = get_section_factory("level_histogram")
    assert factory is not None, "the section did not register"

    def build(model, **options):
        options.setdefault("source", "histogram")
        options.setdefault("range_source", "bounds")
        options.setdefault("on_change", "apply")
        built = factory(model, "levels", **options)
        qtbot.addWidget(built)
        return built

    return build


# --------------------------------------------------------------------------- #
# The model owns the levels
# --------------------------------------------------------------------------- #
def test_the_markers_come_from_the_model(widget):
    model = _Model([{"level": 1.0}, {"level": 2.0}])
    view = widget(model).view
    assert [entry["level"] for entry in view._levels] == [1.0, 2.0]


def test_moving_a_marker_writes_through_to_the_model(widget):
    model = _Model([{"level": 1.0}])
    built = widget(model)
    built._level_moved(0, 2.5)
    assert model.levels[0]["level"] == pytest.approx(2.5)
    assert model.applied == 1, "the model should be told to redraw"


def test_adding_and_removing_go_through_the_model(widget):
    model = _Model([{"level": 1.0}])
    built = widget(model)
    built._level_added(-2.0)
    assert [round(e["level"], 3) for e in model.levels] == [1.0, -2.0]
    built._level_removed(0)
    assert [round(e["level"], 3) for e in model.levels] == [-2.0]


def test_a_typed_value_moves_the_selected_level(widget):
    model = _Model([{"level": 1.0}, {"level": 3.0}])
    built = widget(model)
    built.view.select(1)
    built._value.setText("0.25")
    built._value_typed()
    assert model.levels[1]["level"] == pytest.approx(0.25)
    assert model.levels[0]["level"] == pytest.approx(1.0)


def test_nonsense_typed_into_the_level_box_is_ignored(widget):
    model = _Model([{"level": 1.0}])
    built = widget(model)
    built._value.setText("not a number")
    built._value_typed()
    assert model.levels[0]["level"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Levels stay inside the data
# --------------------------------------------------------------------------- #
def test_a_level_dragged_past_the_end_is_held_inside_the_range(widget):
    """A level exactly at an extreme selects everything or nothing.

    Arriving there by dragging, and seeing the drawing vanish, explains nothing.
    """
    model = _Model([{"level": 0.0}])
    built = widget(model)
    built._level_moved(0, 1e6)
    assert -4.0 < model.levels[0]["level"] < 4.0
    built._level_moved(0, -1e6)
    assert -4.0 < model.levels[0]["level"] < 4.0


def test_a_bare_list_of_numbers_is_accepted(widget):
    """Not every model wants dicts; the simple shape has to work."""
    model = _Model([0.5, 1.5])
    built = widget(model)
    assert [entry["level"] for entry in built.view._levels] == [0.5, 1.5]


# --------------------------------------------------------------------------- #
# Sources are methods
# --------------------------------------------------------------------------- #
def test_a_property_source_is_refused_loudly(widget, caplog):
    """A ``@property`` renders the section blank with no error otherwise.

    That has cost this codebase real time before, so it warns.
    """
    model = _Model()
    with caplog.at_level("WARNING"):
        built = widget(model, source="histogram_property")
    assert not built.isEnabled()
    assert any("method" in record.message for record in caplog.records)


def test_no_data_disables_the_section_rather_than_drawing_nothing(widget):
    class _Empty(_Model):
        def histogram(self):
            return None

    built = widget(_Empty())
    assert not built.isEnabled()


# --------------------------------------------------------------------------- #
# The optional controls
# --------------------------------------------------------------------------- #
def test_styles_are_offered_only_when_asked_for(widget):
    plain = widget(_Model())
    assert plain._style.isHidden()
    styled = widget(_Model(), styles=["surface", "mesh"])
    assert not styled._style.isHidden()
    assert [styled._style.itemText(i) for i in range(styled._style.count())] == [
        "surface", "mesh"
    ]


def test_changing_the_style_writes_it_onto_the_level(widget):
    model = _Model([{"level": 1.0, "style": "surface"}])
    built = widget(model, styles=["surface", "mesh"])
    built.view.select(0)
    built._style_changed("mesh")
    assert model.levels[0]["style"] == "mesh"


def test_adding_and_removing_can_be_switched_off(widget):
    model = _Model([{"level": 1.0}])
    built = widget(model, allow_add=False, allow_remove=False)
    assert built.view._allow_add is False
    assert built.view._allow_remove is False


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
def test_value_and_pixel_map_to_each_other(widget):
    built = widget(_Model())
    view = built.view
    view.resize(200, 100)
    for value in (-3.0, 0.0, 2.5):
        assert view.x_to_value(view.value_to_x(value)) == pytest.approx(value, abs=1e-6)


def test_a_click_near_a_marker_grabs_it_and_elsewhere_does_not(widget):
    model = _Model([{"level": 0.0}])
    built = widget(model)
    view = built.view
    view.resize(200, 100)
    at_marker = view.value_to_x(0.0)
    assert view._marker_at(at_marker) == 0
    assert view._marker_at(at_marker + 40) is None
