"""The editor's "Model settings" scalars take typed numbers, operated with real pointer and keyboard input."""

from __future__ import annotations

import pytest

from chisurf.plugins.fret_line.gui.app import FRETLineApp
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

from .test_emtk_fret_line_parity import BIG, hermetic  # noqa: F401  (hermetic is autouse)


@pytest.fixture
def drv():
    app = FRETLineApp()
    d = Driver(app, BIG)
    d.draw(3)
    yield d
    app.close()


def test_a_model_scalar_is_typed_including_a_negative_value(drv):
    model = drv.app.model.selected["model"]
    drv.click(drv.text_rect("> Model settings"))
    drv.draw(2)
    name = "amplitude_threshold"  # a scalar that is valid at any sign, so the model keeps drawing
    drv.type_into(f"scalar.{name}", "-2.5")
    assert model.get_scalar(name) == -2.5
    drv.type_into(f"scalar.{name}", "0.125")
    assert model.get_scalar(name) == 0.125
    drv.type_into(f"scalar.{name}", "abc")
    assert model.get_scalar(name) == 0.125, "text that is not a number leaves the value"
    assert name in drv.app.error
