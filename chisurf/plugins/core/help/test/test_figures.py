"""How a figure is sized in the page, and opened out of it.

Two defects this covers, both of which a construction test cannot see:

* a plot narrower than the reading column was drawn at its own pixel size,
  so a 470-pixel figure sat in an 860-pixel measure looking like a thumbnail
  with half the page empty beside it;
* there was no way to see it any bigger than the column, which for a
  four-panel figure is not big enough to read the axes.

The sizing is asserted in numbers rather than judged from a screenshot,
because "looks small" is exactly the kind of regression that creeps back.
"""

from __future__ import annotations

import pathlib

import pytest
from qtpy.QtCore import QPoint
from qtpy.QtGui import QImage

from chisurf.plugins.core.help.gui import figure_view

FIGURE = pathlib.Path("docs/guides/figures/perrin.png")


@pytest.fixture
def browser(qapp, qtbot):
    """Return a help browser showing a page that carries a wide figure."""
    from chisurf.plugins.core.help.gui.tool import HelpWidget

    widget = HelpWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.resize(1500, 950)
    qapp.processEvents()
    widget.navigate(pathlib.Path("docs/fundamentals/polarization_and_rotation.md").resolve())
    qapp.processEvents()
    widget.viewer.apply_measure()
    qapp.processEvents()
    return widget


def _image_widths(viewer) -> list[int]:
    """Return the rendered width of every image in the document."""
    widths = []
    document = viewer.document()
    block = document.begin()
    while block.isValid():
        fragments = block.begin()
        while not fragments.atEnd():
            fragment = fragments.fragment()
            if fragment.charFormat().isImageFormat():
                widths.append(round(fragment.charFormat().toImageFormat().width()))
            fragments += 1
        block = block.next()
    return widths


# ── sizing in the page ────────────────────────────────────────────────


def test_a_figure_is_enlarged_to_fill_the_column(browser):
    """A plot smaller than the measure used to stay small."""
    column = browser.viewer.text_column_width()
    widths = _image_widths(browser.viewer)
    assert widths, "the page has no images"
    assert max(widths) >= column - 2, f"widest image {max(widths)} < column {column}"


def test_no_figure_overflows_the_column(browser):
    """One pixel over and the whole page gets a horizontal scrollbar."""
    column = browser.viewer.text_column_width()
    assert all(width <= column + 1 for width in _image_widths(browser.viewer))
    assert browser.viewer.horizontalScrollBar().maximum() == 0


def test_an_inline_image_is_never_enlarged(qapp, qtbot):
    """A typeset formula scaled up would tower over the line it sits in."""
    from chisurf.plugins.core.help.gui.tool import HelpTextBrowser

    viewer = HelpTextBrowser()
    qtbot.addWidget(viewer)
    fmt = _image_format("inline.png", 40, 20)
    scaled = viewer._scaled_image(fmt, column=800, upscale=False)
    assert scaled is None or scaled.width() <= 40


def test_a_figure_is_enlarged_but_not_indefinitely(qapp, qtbot):
    """Past a couple of times its own pixels a raster figure is just soft."""
    from chisurf.plugins.core.help.gui.tool import HelpTextBrowser

    viewer = HelpTextBrowser()
    qtbot.addWidget(viewer)
    fmt = _image_format("tiny.png", 100, 50)
    scaled = viewer._scaled_image(fmt, column=2000, upscale=True)
    assert scaled is not None
    assert scaled.width() == pytest.approx(100 * HelpTextBrowser.MAX_UPSCALE, abs=1)


def _image_format(name: str, width: int, height: int):
    """Return a char format carrying an image of this name and size."""
    from qtpy.QtGui import QTextCharFormat, QTextImageFormat

    image = QTextImageFormat()
    image.setName(name)
    image.setWidth(width)
    image.setHeight(height)
    fmt = QTextCharFormat(image)
    return fmt


# ── opening it big ────────────────────────────────────────────────────


def test_a_figure_is_found_under_the_pointer(browser, qapp):
    """Qt has no clickable image, so the hit test is ours and can rot."""
    viewer = browser.viewer
    # Walk down the middle of the viewport until an image is hit.
    found = ""
    for y in range(10, viewer.viewport().height(), 12):
        found = viewer.image_at(QPoint(viewer.viewport().width() // 2, y))
        if found:
            break
    if not found:
        pytest.skip("no figure is on screen at this window size")
    assert found


def test_clicking_a_figure_asks_the_browser_to_open_it(browser, qapp, monkeypatch):
    opened = []
    monkeypatch.setattr(browser, "_open_figure", opened.append)
    browser.viewer.imageClicked = browser._open_figure
    browser.viewer.imageClicked("figures/perrin.png")
    assert opened == ["figures/perrin.png"]


@pytest.mark.skipif(not FIGURE.is_file(), reason="the sample figure is not in this tree")
def test_the_dialog_shows_the_file_not_the_thumbnail(qapp, qtbot):
    """The point is the real pixels, not an enlargement of what the page drew."""
    image = figure_view.load_image(str(FIGURE.resolve()))
    assert image is not None and not image.isNull()

    dialog = figure_view.FigureDialog(image, title="perrin.png")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.resize(400, 300)
    qapp.processEvents()
    dialog.fit()
    assert dialog.label.pixmap() is not None
    assert dialog.label.pixmap().width() <= 400

    dialog.actual_size()
    assert dialog.label.pixmap().width() == image.width()

    dialog.zoom(2.0)
    assert dialog.label.pixmap().width() == pytest.approx(image.width() * 2, abs=2)


def test_the_dialog_reads_an_inline_image(qapp):
    """A typeset formula is a data URI, not a file."""
    import base64

    from qtpy.QtCore import QBuffer

    source = QImage(8, 4, QImage.Format_RGB32)
    source.fill(0)
    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    source.save(buffer, "PNG")
    encoded = base64.b64encode(bytes(buffer.data())).decode()

    image = figure_view.load_image(f"data:image/png;base64,{encoded}")
    assert image is not None
    assert image.width() == 8


def test_an_unreadable_name_is_not_an_exception(qapp):
    assert figure_view.load_image("") is None
    assert figure_view.load_image("nowhere/at/all.png") is None
    assert figure_view.show_figure("nowhere/at/all.png") is False
