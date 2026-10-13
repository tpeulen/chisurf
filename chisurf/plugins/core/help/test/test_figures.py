"""How a figure is sized in the page, and opened out of it (emtk help browser).

Ported from the retired Qt viewer's tests. Two defects this covers, both of which a construction
test cannot see:

* a plot narrower than the reading column was drawn at its own pixel size, so a 470-pixel figure
  sat in an 860-pixel measure looking like a thumbnail with half the page empty beside it;
* there was no way to see it any bigger than the column, which for a four-panel figure is not
  big enough to read the axes.

The sizing is asserted in numbers rather than judged from a screenshot, because "looks small"
is exactly the kind of regression that creeps back.
"""

from __future__ import annotations

import base64
import io
import pathlib

import pytest
from emtk.testing import Driver

from chisurf.plugins.core.help.api.toc import repository_root
from chisurf.plugins.core.help.gui.help_app import HelpApp
from chisurf.plugins.core.help.gui.reader import MAX_UPSCALE, figure_size, load_figure

FIGURE = repository_root() / "docs/guides/figures/perrin.png"
PAGE = repository_root() / "docs/fundamentals/polarization_and_rotation.md"


@pytest.fixture
def browser():
    """A help browser showing a page that carries a wide figure, at 1500 x 950."""
    if not PAGE.is_file():
        pytest.skip("the sample page is not in this tree")
    app = HelpApp()
    app.model.open_page(PAGE)
    driver = Driver(app, (1500, 950))
    driver.frame(4)
    yield app, driver
    app.close()


def _visible_centre(rect, height=950.0):
    """The middle of the part of a figure that is on screen (a tall page runs past the window)."""
    x, y, w, h = rect[:4]
    return (x + w / 2, y + (min(y + h, height - 4.0) - y) / 2)


def _column(app) -> float:
    return app.help_gui.reader_column - 28.0  # the figure's max width inside the column


# -- sizing in the page ---------------------------------------------------------------------------- #


def test_a_figure_is_enlarged_to_fill_the_column(browser):
    """A plot smaller than the measure used to stay small."""
    app, _driver = browser
    rects = app.help_gui.figure_rects
    assert rects, "the page has no figures on screen"
    widest = max(rect[2] for rect in rects)
    assert widest >= _column(app) - 2, (widest, _column(app))


def test_no_figure_overflows_the_column(browser):
    """One pixel over and the page would need a horizontal scrollbar."""
    app, _driver = browser
    assert all(rect[2] <= _column(app) + 1 for rect in app.help_gui.figure_rects)


def test_an_inline_image_is_never_enlarged():
    """A typeset formula scaled up would tower over the line it sits in."""
    assert figure_size(40, 20, 800, upscale=False) == (40.0, 20.0)


def test_a_figure_is_enlarged_but_not_indefinitely():
    """Past a couple of times its own pixels a raster figure is just soft."""
    w, h = figure_size(100, 50, 2000)
    assert w == pytest.approx(100 * MAX_UPSCALE) and h == pytest.approx(50 * MAX_UPSCALE)


def test_an_oversized_figure_is_scaled_to_the_column_keeping_its_aspect():
    """Manual screenshots must not blow up the layout."""
    assert figure_size(2000, 1000, 400) == (400.0, 200.0)
    assert figure_size(400, 1600, 800, max_height=600) == (150.0, 600.0)


# -- opening it big -------------------------------------------------------------------------------- #


def test_a_figure_is_found_under_the_pointer(browser):
    """There is no clickable image widget, so the hit test is ours and can rot."""
    app, driver = browser
    rect = app.help_gui.figure_rects[0]
    assert rect[4]
    driver.hover(_visible_centre(rect))
    assert app.help_gui.hovered_figure == rect[4]


def test_clicking_a_figure_opens_it(browser):
    app, driver = browser
    driver.click(_visible_centre(app.help_gui.figure_rects[0]))
    viewer = app.help_gui.figure_viewer
    assert viewer is not None and app.help_gui.figure_window.open
    drawn = [t[5] for t in driver.frame(2).texts]
    assert "Fit to window" in drawn and "Actual size" in drawn and "Zoom in" in drawn


@pytest.mark.skipif(not FIGURE.is_file(), reason="the sample figure is not in this tree")
def test_the_viewer_shows_the_file_not_the_thumbnail():
    """The point is the real pixels, not an enlargement of what the page drew."""
    app = HelpApp()
    try:
        assert app.help_gui.open_figure(str(FIGURE))
        viewer = app.help_gui.figure_viewer
        natural = viewer.natural_size
        viewer.fit()
        fitted = viewer.displayed_size((400.0, 300.0))
        assert fitted[0] <= 400.0 + 1e-6 and fitted[1] <= 300.0 + 1e-6
        viewer.actual_size()
        assert viewer.displayed_size((400.0, 300.0))[0] == pytest.approx(natural[0])
        viewer.zoom(2.0)
        assert viewer.displayed_size((400.0, 300.0))[0] == pytest.approx(natural[0] * 2, abs=2)
        driver = Driver(app, (1200, 800))
        driver.frame(2)
        driver.click("Fit to window")
        assert viewer.mode == "fit"
        driver.click("Actual size")
        assert viewer.mode == "zoom" and viewer.zoom_factor == 1.0
        driver.click("Zoom in")
        assert viewer.zoom_factor > 1.0
    finally:
        app.close()


def test_the_viewer_reads_an_inline_image():
    """A typeset formula is a data URI, not a file."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 4)).save(buffer, "PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    texture = load_figure(f"data:image/png;base64,{encoded}")
    assert texture is not None and texture.width == 8


def test_an_unreadable_name_is_not_an_exception():
    assert load_figure("") is None
    assert load_figure("nowhere/at/all.png") is None
    assert load_figure("data:image/png;base64,not-an-image") is None
    app = HelpApp()
    try:
        assert app.help_gui.open_figure("nowhere/at/all.png") is False
        assert app.help_gui.figure_viewer is None
    finally:
        app.close()


def test_figure_paths_resolve_relative_to_the_page(browser):
    app, _driver = browser
    name = app.help_gui.figure_rects[0][4]
    assert app.help_gui.open_figure(name)
    assert pathlib.Path(app.help_gui.figure_window.title).suffix
