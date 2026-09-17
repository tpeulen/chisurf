"""The photon range the window shows has to be the one the plots draw.

``First photon`` / ``Last photon`` are AutoForm fields bound, through a
view-model, to two hidden spin boxes. Two things broke the link, and both made
the plots look like they were ignoring the range:

* the form reads the spins when it is *built*, and the spins are re-clamped
  every time diagnostics load -- so the form went on displaying the default of
  100000 over a plot drawing all 1.8 million photons;
* the re-clamp reset to the whole file, and diagnostics reload on every filter
  change -- so a range the user narrowed by hand was thrown away the moment
  they touched any other setting.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.burst.burst_selection.gui.tool import (
    DEFAULT_PLOT_MAX,
    BurstSelectionTool,
)

pytest.importorskip("qtpy.QtWidgets")


@pytest.fixture
def tool(qtbot):
    widget = BurstSelectionTool()
    qtbot.addWidget(widget)
    return widget


def test_the_form_shows_the_range_the_plots_use(tool):
    """Clamping the spins pushes the new value out to the visible fields."""
    assert tool._display_view_model.photon_last == DEFAULT_PLOT_MAX

    tool._sync_plot_range_controls(1_791_775, reset=True)

    assert tool.plot_max_spin.value() == 1_791_774
    assert tool._display_view_model.photon_last == 1_791_774
    field = _photon_last_field(tool)
    assert field is not None, "no 'Last photon' field found in the display form"
    assert int(field.value()) == 1_791_774


def test_a_narrowed_range_survives_a_reload_of_the_same_photons(tool):
    """Only a *different* photon count resets the range."""
    tool._sync_plot_range_controls(1_791_775, reset=True)
    tool._display_view_model.photon_last = 100_000

    tool._sync_plot_range_controls(1_791_775, reset=False)

    assert tool.plot_max_spin.value() == 100_000


def test_a_narrower_file_set_clamps_rather_than_widens(tool):
    """A range past the end of the new data is clamped, never left dangling."""
    tool._sync_plot_range_controls(1_791_775, reset=True)
    tool._sync_plot_range_controls(1_000, reset=False)

    assert tool.plot_max_spin.value() == 999
    assert tool._display_view_model.photon_last == 999


def _photon_last_field(tool):
    """Return the AutoForm widget bound to ``photon_last``, if it is there."""
    from qtpy import QtWidgets

    form = tool.__dict__.get("_display_form")
    if form is None:
        return None
    for widget in form.findChildren(QtWidgets.QWidget):
        if getattr(widget, "attr_name", None) == "photon_last" and hasattr(widget, "value"):
            return widget
    # Fall back to the spin box holding the largest allowed value: the form
    # renders an int field as a spin box, and only two of them are bound here.
    spins = [w for w in form.findChildren(QtWidgets.QAbstractSpinBox) if hasattr(w, "value")]
    return max(spins, key=lambda w: w.value()) if spins else None
