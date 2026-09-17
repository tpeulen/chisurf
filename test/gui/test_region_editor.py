"""The shared region GUI: the list, and the shapes drawn on a canvas.

Both halves edit one Qt-free ``RegionCollection``, so what these tests assert is
mostly "the widget and the collection agree" — which is the whole point of
having one type instead of the five bespoke region lists this replaces.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Host:
    """A minimal view-model: an image, a collection and a transient selection."""

    def __init__(self):
        from chisurf.core.roi import RegionCollection

        yy, xx = np.mgrid[0:64, 0:64]
        self.current_image = 10.0 + 90.0 * np.exp(-((yy - 20) ** 2 + (xx - 20) ** 2) / 50)
        self.regions = RegionCollection(combine="or")
        self.painted = np.zeros((64, 64), dtype=bool)
        self.painted[40:50, 40:50] = True

    def selection_roi(self):
        from chisurf.core.roi import MaskROI

        return MaskROI(self.painted, name="brushed") if self.painted.any() else None


@pytest.fixture
def host():
    from chisurf.core.roi import EllipseROI, RectangleROI

    h = _Host()
    h.regions.add(RectangleROI(0, 0, 20, 20, name="cell"))
    h.regions.add(EllipseROI(40.0, 40.0, 8.0, 5.0, name="spot"))
    return h


@pytest.fixture
def editor(qapp, host):
    from chisurf.gui.widgets.roi import RegionEditor

    return RegionEditor(
        host, "regions", image_attr="current_image",
        paint_source="selection_roi", intensity_unit="ph",
    )


def _row(editor, name):
    for i in range(editor.tree.topLevelItemCount()):
        item = editor.tree.topLevelItem(i)
        if item.text(0) == name:
            return item
    raise AssertionError(f"no row named {name!r}")


# --- the list ----------------------------------------------------------------
def test_every_region_gets_a_row_with_its_shape_and_measurement(editor):
    assert editor.tree.topLevelItemCount() == 2
    cell = _row(editor, "cell")
    assert cell.text(1) == "rectangle"
    # 20x20 pixels of a frame whose corner holds the bright spot.
    assert cell.text(2).startswith("400 px, ") and cell.text(2).endswith("ph/px")


def test_unticking_a_row_disables_the_region_without_removing_it(editor, host):
    from qtpy import QtCore

    _row(editor, "spot").setCheckState(0, QtCore.Qt.Unchecked)
    assert host.regions["spot"].enabled is False
    assert len(host.regions) == 2


def test_the_invert_column_flips_the_region(editor, host):
    from qtpy import QtCore

    _row(editor, "cell").setCheckState(3, QtCore.Qt.Checked)
    assert host.regions["cell"].invert is True
    assert host.regions.contains(np.array([[5.0, 5.0]])).tolist() == [False]


def test_renaming_a_row_renames_the_region(editor, host):
    _row(editor, "cell").setText(0, "membrane")
    assert "membrane" in host.regions and "cell" not in host.regions


def test_a_rename_onto_a_taken_name_is_suffixed_and_the_row_follows(editor, host):
    _row(editor, "cell").setText(0, "spot")
    assert sorted(host.regions.names) == ["spot", "spot (2)"]
    _row(editor, "spot (2)")  # the row exists under the name actually used


@pytest.mark.parametrize(
    "kind, expected",
    [("rect", "RectangleROI"), ("ellipse", "EllipseROI"), ("polygon", "PolygonROI")],
)
def test_each_shape_button_creates_that_kind_inside_the_frame(editor, host, kind, expected):
    """`PolygonROI` and `EllipseROI` had no GUI producer at all before this."""
    name = editor.add_shape(kind)
    roi = host.regions.roi(name)
    assert type(roi).__name__ == expected
    # Placed where it can be seen and grabbed, not collapsed at the origin.
    x0, y0, x1, y1 = roi.bounds((64, 64))
    assert 0 <= x0 < x1 <= 64 and 0 <= y0 < y1 <= 64
    assert (x1 - x0) > 4 and (y1 - y0) > 4


def test_the_plus_button_keeps_the_current_painted_selection(editor, host):
    """A brush stroke exists until the next one; this is how it is kept."""
    editor.name_edit.setText("background")
    assert editor.capture_painted() == "background"
    assert host.regions.roi("background").to_mask((64, 64)).sum() == 100


def test_capturing_nothing_says_so_instead_of_adding_an_empty_region(editor, host):
    host.painted[:] = False
    before = len(host.regions)
    assert editor.capture_painted() == ""
    assert len(host.regions) == before
    assert "nothing selected" in editor.summary_label.text()


def test_removing_and_duplicating_act_on_the_selected_row(editor, host):
    editor.select("spot")
    editor.duplicate_selected()
    assert host.regions.names == ["cell", "spot", "spot (2)"]
    editor.select("spot (2)")
    editor.remove_selected()
    assert host.regions.names == ["cell", "spot"]


def test_the_combine_box_sets_the_rule_on_the_collection(editor, host):
    index = editor.combine_box.findData("and")
    editor.combine_box.setCurrentIndex(index)
    assert host.regions.combine == "and"


def test_the_footer_counts_active_regions_and_the_combined_area(editor, host):
    from qtpy import QtCore

    assert "2 of 2" in editor.summary_label.text()
    _row(editor, "spot").setCheckState(0, QtCore.Qt.Unchecked)
    assert "1 of 2" in editor.summary_label.text()


def test_no_active_region_reads_as_the_whole_frame_not_as_nothing(editor, host):
    from qtpy import QtCore

    for name in list(host.regions.names):
        _row(editor, name).setCheckState(0, QtCore.Qt.Unchecked)
    assert "whole frame" in editor.summary_label.text()


def test_a_host_without_the_attribute_gets_a_collection_made_for_it(qapp):
    """Declaring the name is enough; the editor supplies the collection."""
    from chisurf.core.roi import RegionCollection
    from chisurf.gui.widgets.roi import RegionEditor

    class Bare:
        pass

    bare = Bare()
    editor = RegionEditor(bare, "regions")
    assert isinstance(editor.collection, RegionCollection)
    assert isinstance(bare.regions, RegionCollection)


def test_without_an_image_the_rows_carry_no_invented_measurement(qapp, host):
    """Area and brightness belong to a region *and a frame*; say nothing instead."""
    from chisurf.gui.widgets.roi import RegionEditor

    editor = RegionEditor(host, "regions")
    assert _row(editor, "cell").text(2) == ""


# --- the overlay --------------------------------------------------------------
#: One canvas for the whole module, kept alive deliberately. Building a fresh
#: pyqtgraph ``ImageView`` per test and letting it be collected segfaults — the
#: Python wrapper outlives the destroyed C++ item and the ViewBox's itemChange
#: lambda fires into it during garbage collection.
_CANVAS: list = []


@pytest.fixture(scope="module")
def canvas(qapp):
    pytest.importorskip("pyqtgraph")
    from chisurf.gui.chiplot import canvas as C

    view = C.ImageView()
    view.set_image(np.zeros((64, 64)))
    _CANVAS.append(view)
    return view


def test_the_overlay_draws_a_handle_for_every_drawable_region(canvas, host):
    from chisurf.core.roi import MaskROI
    from chisurf.gui.widgets.roi import RegionOverlay

    host.regions.add(MaskROI(host.painted, name="brushed"))
    overlay = RegionOverlay(canvas, lambda: host.regions)
    overlay.refresh()

    # A painted mask has no handful of grips that would edit it, and inventing a
    # bounding box would replace the mask on the first drag.
    assert overlay._names == ["cell", "spot"]


def test_dragging_writes_the_geometry_back_and_keeps_the_region_type(canvas, host):
    from chisurf.core.roi import EllipseROI
    from chisurf.gui.widgets.roi import RegionOverlay

    seen = []
    overlay = RegionOverlay(canvas, lambda: host.regions, on_change=lambda: seen.append(1))
    overlay.refresh()

    handle = overlay._handles[overlay._names.index("spot")]
    handle.set_pos(10.0, 12.0)
    handle.set_size(20.0, 10.0)
    overlay._write_back(handle, "spot")

    roi = host.regions.roi("spot")
    assert isinstance(roi, EllipseROI)          # not silently turned into a rect
    assert (roi.cx, roi.cy) == (20.0, 17.0)
    assert (roi.rx, roi.ry) == (10.0, 5.0)
    assert roi.name == "spot"
    assert seen, "the host was not told the geometry changed"


def test_a_geometry_that_did_not_move_is_not_reported_as_a_drag(canvas, host):
    """pyqtgraph fires its change signal for programmatic moves too."""
    from chisurf.gui.widgets.roi import RegionOverlay

    seen = []
    overlay = RegionOverlay(canvas, lambda: host.regions, on_change=lambda: seen.append(1))
    overlay.refresh()

    handle = overlay._handles[overlay._names.index("cell")]
    overlay._write_back(handle, "cell")
    assert seen == []


def test_a_dragged_polygon_keeps_its_vertices(canvas, host):
    from chisurf.core.roi import PolygonROI
    from chisurf.gui.widgets.roi import RegionOverlay

    host.regions.add(PolygonROI([(5, 5), (25, 8), (15, 30)], name="patch"))
    overlay = RegionOverlay(canvas, lambda: host.regions)
    overlay.refresh()

    handle = overlay._handles[overlay._names.index("patch")]
    handle.set_pos(10.0, 10.0)
    overlay._write_back(handle, "patch")

    roi = host.regions.roi("patch")
    assert isinstance(roi, PolygonROI)
    assert len(roi.vertices) == 3
    # Moved as a whole: every vertex shifted by the same offset.
    shifts = roi.vertices - np.array([(5, 5), (25, 8), (15, 30)], dtype=float)
    assert np.allclose(shifts, shifts[0])


def test_refreshing_removes_the_handles_of_deleted_regions(canvas, host):
    from chisurf.gui.widgets.roi import RegionOverlay

    overlay = RegionOverlay(canvas, lambda: host.regions)
    overlay.refresh()
    host.regions.remove("spot")
    overlay.refresh()
    assert overlay._names == ["cell"]


def test_a_disabled_region_is_drawn_greyed_rather_than_hidden(canvas, host):
    """It is still there, and the picture should say so."""
    from chisurf.gui.widgets.roi import RegionOverlay
    from chisurf.gui.widgets.roi.overlay import DISABLED_PEN, PALETTE

    host.regions.set_enabled("spot", False)
    overlay = RegionOverlay(canvas, lambda: host.regions)
    overlay.refresh()

    assert overlay._names == ["cell", "spot"]
    pens = [h.pen_color for h in overlay._handles]
    assert pens[0].lower() == PALETTE[0].lower()
    assert pens[1].lower() == DISABLED_PEN.lower()


def test_selecting_a_region_does_not_change_its_colour(canvas, host):
    """The palette must be indexed the same way when drawing and when selecting.

    A painted mask contributes no handle, so indexing the *collection* rather
    than the drawn handles gave a region one colour on refresh and another on
    select — picking a row appeared to recolour it.
    """
    from chisurf.core.roi import MaskROI
    from chisurf.gui.widgets.roi import RegionOverlay

    # A region with no handle, placed first so the two indexings disagree.
    host.regions.add(MaskROI(host.painted, name="brushed"))
    host.regions.move("brushed", 0)

    overlay = RegionOverlay(canvas, lambda: host.regions)
    overlay.refresh()
    before = [h.pen_color for h in overlay._handles]

    overlay.select("spot")
    after = [h.pen_color for h in overlay._handles]
    assert before == after
