"""A fit page declares its settings as an AutoForm spec over a plain model.

Pages are not widgets and bring no toolkit controller: ``settings_view`` is drawn by emtk
(``page.draw_settings``) onto the *Plot settings* dock. The dock's host was a Qt widget and is
gone with the Qt shell; these drive the page's own settings model and draw it on an emtk
``ImApp`` with the recording painter.
"""

from __future__ import annotations

import pytest

from chisurf.emtk.fit_pages.pages.lineplot.lineplot import LinePlot
from test.gui.test_tcspc_project_visual_roundtrip import _simulated_fit


def _draw_settings(page, width: float = 440.0, height: float = 640.0) -> set:
    """Draw the page's settings onto an emtk app and return the names of the drawn fields."""
    from emtk import im
    from emtk.app import ImApp
    from emtk.testing import RecordingPainter

    def gui():
        im.begin("##s", (0.0, 0.0, width, height), flags=im.WindowFlags.NO_TITLE_BAR)
        page.draw_settings()
        im.end()

    app = ImApp(gui)
    for _ in range(2):
        app.draw(RecordingPainter(), 0, 0, width, height)
    return set(page.settings_form.rects)


@pytest.fixture
def lineplot():
    plot = LinePlot(_simulated_fit())
    plot.update()
    return plot


def test_the_lineplot_settings_are_drawn_from_its_spec(lineplot):
    rects = _draw_settings(lineplot)
    for name in (
        "log_x",
        "log_y",
        "is_density",
        "display_group",
        "reference_mode",
        "xmin_enabled",
        "xmax_value",
        "x_shift",
        "y_shift",
    ):
        assert name in rects, f"{name} was not drawn"


def test_the_log_x_setting_changes_the_plot(lineplot):
    assert not lineplot.settings.data_is_log_x
    lineplot.settings.log_x = True
    assert lineplot.settings.get_state()["scale_x"] == "log"


def test_a_curve_unticked_in_the_table_is_hidden(lineplot):
    rows = lineplot.settings.curve_rows()
    assert rows and all(row["shown"] for row in rows)
    lineplot.settings.curve_edited(rows[0], "shown", False)
    assert not lineplot.settings.getCheckState(rows[0]["name"])
    assert lineplot.settings.get_state()["curve_visibility"][rows[0]["name"]] is False


def test_a_page_without_settings_says_so():
    from chisurf.emtk.fit_pages.pages.wr_plot import ResidualPlot

    page = ResidualPlot(_simulated_fit())
    assert not page.has_settings()
