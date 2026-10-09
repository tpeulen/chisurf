"""The optimisation fields of the docked emtk H2MM controls take typed numbers, operated with real keyboard input.

The controls re-read the tool's spin boxes every frame, so a typed value counts only once it was written back to
them; the stub spin boxes below stand in for the Qt ones and keep their ranges.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chisurf.plugins.burst.burst_h2mm.gui.app import H2mmApp
from chisurf.plugins.emtk_test_input import Driver


class SpinBox:
    """The two calls the controls make on a ``QSpinBox``, with its clamping range."""

    def __init__(self, value, low, high):
        self._value, self.low, self.high = value, low, high

    def value(self):
        return self._value

    def setValue(self, value):  # noqa: N802 - Qt spelling
        self._value = max(self.low, min(self.high, int(value)))


@pytest.fixture
def drv():
    tool = SimpleNamespace(
        _result=None, _bundle=None, data_folder=None, _fit_task=None,
        sb_restarts=SpinBox(2, 1, 20), sb_max_iter=SpinBox(500, 10, 5000), sb_min_photons=SpinBox(5, 2, 1000),
    )
    return Driver(H2mmApp(tool))


def test_typed_values_reach_the_tool_and_are_clamped_to_the_qt_ranges(drv):
    tool = drv.app.tool
    drv.type_into_name("restarts", "7")
    assert tool.sb_restarts.value() == 7
    drv.type_into_name("max_iter", "1234")
    assert tool.sb_max_iter.value() == 1234
    drv.type_into_name("min_photons", "-3")
    assert tool.sb_min_photons.value() == 2, "a negative count is clamped to the Qt minimum"
    drv.type_into_name("restarts", "99")
    assert tool.sb_restarts.value() == 20
    drv.draw(2)
    assert drv.app.h2mm_gui.restarts == 20, "the next frame's re-read keeps the typed value"


def test_text_that_is_not_a_number_leaves_the_value(drv):
    drv.type_into_name("max_iter", "abc")
    assert drv.app.tool.sb_max_iter.value() == 500
