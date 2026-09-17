"""Picking and region drawing belong to the canvas, not to every tool.

Two capabilities that were being re-implemented per plugin — draw a
:class:`~chisurf.core.roi.ROI` on an image, and turn a click into a region —
now live on :class:`chisurf.gui.chiplot.ImageView`. These tests pin the parts
that were getting done differently each time: the ellipse's radius-versus-
diameter convention, and that a click is a *seed* the fit refines rather than
the answer itself.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("qtpy")

from chisurf.core.roi import EllipseROI, MaskROI, PolygonROI, RectangleROI


def _field(cy=20.0, cx=24.0, sigma=1.8, shape=(48, 56)):
    rows, cols = np.indices(shape)
    return 5.0 + 300.0 * np.exp(
        -0.5 * (((rows - cy) / sigma) ** 2 + ((cols - cx) / sigma) ** 2)
    )


#: Views are kept for the life of the module rather than let go between tests.
#: pyqtgraph registers every ViewBox in a process-wide list and, on destruction,
#: walks the *other* views' context menus to update it — touching a combo box
#: whose C++ object Qt has already deleted, which aborts the interpreter after
#: the tests have all passed. Holding them is cheaper than the alternative.
_VIEWS: list = []


def _image_view(image=None):
    from chisurf.gui import chiplot

    iv = chiplot.ImageView()
    iv.set_image(_field() if image is None else image)
    _VIEWS.append(iv)
    return iv


@pytest.fixture
def view(qapp):
    return _image_view()


@pytest.fixture(scope="module", autouse=True)
def _dispose_views():
    """Destroy the views deterministically, while Qt is still alive.

    Letting them go at interpreter shutdown is what aborts: pyqtgraph's
    process-wide ViewBox registry walks the *other* views' context menus when
    one is destroyed, and by then their combo boxes are deleted C++ objects.
    Taking them down one at a time, with the event loop still running, keeps
    that walk on live objects.
    """
    yield
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance()
    while _VIEWS:
        view = _VIEWS.pop()
        view.setParent(None)
        view.deleteLater()
        if app is not None:
            app.processEvents()


def test_an_ellipse_is_drawn_at_the_size_it_describes(view):
    """The convention that was wrong in more than one hand-rolled conversion.

    pyqtgraph takes a bounding box, a region carries radii, and drawing the
    radius as the size produces an ellipse half the size of the region — which
    looks entirely plausible in a screenshot.
    """
    handle = view.add_region(EllipseROI(24.0, 20.0, 6.0, 4.0))

    assert handle is not None
    pos, size = handle.pos, handle.size
    assert tuple(size) == pytest.approx((12.0, 8.0))
    assert tuple(pos) == pytest.approx((18.0, 16.0))


def test_a_rectangle_is_drawn_from_its_bounds(view):
    handle = view.add_region(RectangleROI(4.0, 6.0, 14.0, 21.0))

    assert tuple(handle.pos) == pytest.approx((4.0, 6.0))
    assert tuple(handle.size) == pytest.approx((10.0, 15.0))


def test_a_polygon_is_drawn_from_its_vertices(view):
    handle = view.add_region(PolygonROI([[2, 2], [10, 2], [10, 9]]))

    assert handle is not None


def test_a_mask_region_says_to_use_an_overlay(view):
    """No analytic outline, and the error names what to do instead."""
    with pytest.raises(TypeError, match="add_overlay"):
        view.add_region(MaskROI(np.zeros((48, 56), dtype=bool)))


def test_a_drawn_region_is_not_movable_by_default(view):
    """A region from a measurement is a result; dragging it would claim to edit it."""
    handle = view.add_region(EllipseROI(24.0, 20.0, 3.0, 3.0))

    assert not handle.movable


def test_a_click_is_refined_by_the_fit_before_it_becomes_a_pick(view, qapp):
    """The point of picking living here: the gesture and the refinement together."""
    picks = []
    view.picked.connect(picks.append)
    view.enable_picking(window=11)

    # The click is two pixels off the planted spot at (20, 24).
    view.clicked.emit(26.0, 22.0)
    qapp.processEvents()

    assert len(picks) == 1
    spot = picks[0]
    assert spot.success, spot.reason
    assert spot.y == pytest.approx(20.0, abs=0.2)
    assert spot.x == pytest.approx(24.0, abs=0.2)


def test_a_pick_that_fails_is_still_emitted_with_its_reason(view, qapp):
    """A silently dropped click is indistinguishable from a click that did nothing."""
    flat = _image_view(np.full((48, 56), 7.0))
    picks = []
    flat.picked.connect(picks.append)
    flat.enable_picking()

    flat.clicked.emit(20.0, 20.0)
    qapp.processEvents()

    assert len(picks) == 1
    assert not picks[0].success
    assert picks[0].reason


def test_picking_without_a_fit_takes_the_click_as_given(view, qapp):
    picks = []
    view.picked.connect(picks.append)
    view.enable_picking(fit="none")

    view.clicked.emit(31.0, 7.0)
    qapp.processEvents()

    assert picks[0].success
    assert (picks[0].y, picks[0].x) == (7.0, 31.0)


def test_the_canvas_remembers_the_image_so_a_caller_need_not_hand_it_over_twice(view):
    assert view._last_image is not None
    assert view._last_image.shape == (48, 56)


def test_a_rotated_ellipse_is_drawn_rotated(view):
    """The exploration tool's Gaussian gates are tilted, and an axis-aligned ellipse is a different gate.

    Drawing a correlated population's ellipse without its rotation either leaks
    in the corners or cuts the population's own diagonal off — and it looks
    entirely reasonable on screen either way.
    """
    import numpy as np

    handle = view.add_region(EllipseROI(24.0, 20.0, 8.0, 3.0, angle=np.pi / 4))

    assert handle.angle == pytest.approx(45.0, abs=1e-6)
    # And the centre has not wandered (pyqtgraph rotates about `pos`, so its
    # backend has to hold the centre still by hand).
    (x, y), (w, h) = handle.pos, handle.size
    assert (x + w / 2.0, y + h / 2.0) == pytest.approx((24.0, 20.0), abs=1e-6)


def test_a_cluster_picked_from_points_becomes_that_ellipse(view):
    """The gesture ndX needs: click a population, get the gate that describes it."""
    import numpy as np

    from chisurf.core.roi import cluster_roi, fit_gaussian_cluster

    rng = np.random.default_rng(11)
    points = rng.multivariate_normal([10.0, 4.0], [[1.0, 0.6], [0.6, 0.5]], size=4000)

    # Clicked on the shoulder, not the centre.
    cluster = fit_gaussian_cluster(points, 11.2, 4.6, radius=3.0)

    assert cluster.success, cluster.reason
    assert cluster.mu[0] == pytest.approx(10.0, abs=0.25)
    assert cluster.mu[1] == pytest.approx(4.0, abs=0.25)

    handle = view.add_region(cluster_roi(cluster, "population"))
    assert handle is not None
