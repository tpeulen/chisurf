"""The editor's "Model settings" scalars take typed numbers, operated with real pointer and keyboard input."""

from __future__ import annotations

import pytest

from chisurf.plugins.fret_line.gui.app import FRETLineApp
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

from .test_emtk_fret_line_clicks import open_expert, tab
from .test_emtk_fret_line_parity import BIG, hermetic  # noqa: F401  (hermetic is autouse)


@pytest.fixture
def drv():
    app = FRETLineApp()
    d = Driver(app, BIG)
    d.draw(3)
    open_expert(d)
    yield d
    app.close()


def test_a_model_scalar_is_typed_including_a_negative_value(drv):
    model = drv.app.model.selected["model"]
    tab(drv, "Live model editor")
    drv.click(drv.text_rect("> Model settings"))
    drv.draw(2)
    for _ in range(12):  # the editor window is 384 px tall: wheel it until the scalar is inside its content
        x, y, w, h = drv.rect("scalar.amplitude_threshold")
        if y + h <= 400:
            break
        drv.wheel(700, 200, -3)
        drv.draw(2)
    assert y + h <= 400, "the scalar could not be scrolled into the editor window"
    name = "amplitude_threshold"
    drv.type_into(f"scalar.{name}", "0.25")
    assert model.get_scalar(name) == 0.25
    # the library refuses a negative threshold: the typed value is rolled back and the reason shown
    drv.type_into(f"scalar.{name}", "-2.5")
    assert model.get_scalar(name) == 0.25 and "negative" in drv.app.error
    drv.type_into(f"scalar.{name}", "0.125")
    assert model.get_scalar(name) == 0.125 and drv.app.error == ""
    drv.type_into(f"scalar.{name}", "abc")
    assert model.get_scalar(name) == 0.125, "text that is not a number leaves the value"
    assert name in drv.app.error
