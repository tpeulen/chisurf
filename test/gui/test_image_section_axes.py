"""The reusable AutoForm ``image`` section draws a 2-D array the numpy way.

pyqtgraph's default maps a 2-D array's axis 0 to *x* — it draws the transpose.
Every other part of :class:`ImageMapWidget` is written the other way round:
markers are placed at ``(x, y) = (col, row)``, clicks are bounds-checked against
``shape[:2]`` read as ``(ny, nx)``, the rectangle gate builds a ``RectangleROI``
whose x is a column, and the 3-D path already passes ``axes={'x': 2, 'y': 1}``.
Only the 2-D display disagreed, so a marker on any 2-D map — a picked PSF bead,
a molecule centroid — landed transposed, and so did a region overlay. Nothing
else in the suite notices: the image still renders, the marker still appears,
just not where the pixel it names is.
"""

from __future__ import annotations

import os

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _image_widget(qtbot, host, **options):
    """Build an image section under ``qtbot``, which owns its lifetime."""
    from chisurf.gui.autoform.sections.builtin import ImageMapWidget

    widget = ImageMapWidget(host, "img", **options)
    qtbot.addWidget(widget)
    widget.refresh()
    return widget


def test_a_2d_array_is_drawn_the_way_numpy_holds_it(qtbot):
    """Rows are y, columns are x — and the marker lands on the pixel it names."""

    class Host:
        def __init__(self):
            self.img = np.zeros((20, 60))
            self.img[4:8, 40:50] = 1.0

        def markers(self):
            return [(0, 6, 45)]  # (z, row, col)

    widget = _image_widget(qtbot, Host(), markers_source="markers")

    rect = widget._image.getImageItem().boundingRect()
    assert (rect.width(), rect.height()) == (60.0, 20.0)

    (marker,) = widget._marker_items
    xs, ys = marker.getData()
    assert (xs[0], ys[0]) == (45.0, 6.0)  # on the bright block, not beside it


def test_a_three_dimensional_stack_keeps_the_same_orientation(qtbot):
    """The 3-D path already agreed; it must not move."""

    class Host:
        img = np.zeros((3, 20, 60))

    widget = _image_widget(qtbot, Host())
    rect = widget._image.getImageItem().boundingRect()
    assert (rect.width(), rect.height()) == (60.0, 20.0)


def test_a_region_drawn_on_the_section_lands_on_its_own_pixels(qtbot):
    """The end-to-end check a screenshot made obvious.

    An overlay places a region by its ``(x, y) = (column, row)`` geometry; with
    the canvas disagreeing about which axis is which, every shape sat
    transposed — visibly so for anything that is not square.
    """
    from chisurf.core.roi import RectangleROI, RegionCollection
    from chisurf.gui.widgets.roi import RegionOverlay

    class Host:
        img = np.zeros((20, 60))

    host = Host()
    host.regions = RegionCollection()
    host.regions.add(RectangleROI(40, 4, 50, 8, name="block"))
    widget = _image_widget(qtbot, host)

    overlay = RegionOverlay(widget, lambda: host.regions)
    overlay.refresh()
    handle = overlay._handles[0]
    assert handle.pos == (40.0, 4.0)
    assert handle.size == (10.0, 4.0)
