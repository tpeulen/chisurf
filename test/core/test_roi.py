"""The shared ROI class: geometry, gating, rasterisation and persistence.

ChiSurf had at least seven separate notions of "region of interest" — rect
ranges in the image correlator, a painted array in colocalization, a rect on the
AutoForm image section, another on the 2-D residual plot, watershed labels in
molecule MLE, and ndX's data-space gates. These tests pin the behaviour the
single replacement has to get right for all of them: the same geometry must
answer both "is this point inside" (gating) and "which pixels are inside"
(imaging), on whatever axes the caller supplies.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.roi import (
    ROI,
    CompositeROI,
    EllipseROI,
    MaskROI,
    PolygonROI,
    RectangleROI,
    ThresholdROI,
    labels_to_rois,
    roi_from_dict,
    rois_to_labels,
)
from chisurf.core.roi.roi import pixel_centres


# --- coordinates -----------------------------------------------------------
def test_pixel_centres_default_to_indices():
    """Without an extent, pixel centres are integer indices."""
    x, y = pixel_centres((2, 3))
    np.testing.assert_allclose(x[0], [0, 1, 2])
    np.testing.assert_allclose(y[:, 0], [0, 1])


def test_pixel_centres_inset_half_a_pixel_under_an_extent():
    """With an extent the centres are inset, not placed on the edges."""
    x, y = pixel_centres((2, 2), extent=(0.0, 10.0, 0.0, 10.0))
    np.testing.assert_allclose(x[0], [2.5, 7.5])
    np.testing.assert_allclose(y[:, 0], [2.5, 7.5])


def test_same_roi_serves_pixel_and_value_axes():
    """One rectangle gates a histogram and masks an image; only axes differ.

    This is the whole point of the class: an ndX gate and a CLSM ROI are the
    same object.
    """
    roi = RectangleROI(0.2, 0.2, 0.8, 0.8)

    # as a data-space gate over scattered points
    pts = np.array([[0.5, 0.5], [0.1, 0.5], [0.9, 0.9]])
    np.testing.assert_array_equal(roi.contains(pts), [True, False, False])

    # as an image mask over a 10x10 frame spanning 0..1 on both axes
    mask = roi.to_mask((10, 10), extent=(0.0, 1.0, 0.0, 1.0))
    assert mask.sum() == 36  # the 6x6 block of centres in [0.2, 0.8)
    assert mask[5, 5] and not mask[0, 0]


# --- shapes ----------------------------------------------------------------
def test_rectangle_is_half_open_so_neighbours_tile():
    """Abutting rectangles cover every pixel exactly once."""
    left = RectangleROI(-0.5, -0.5, 1.5, 3.5)
    right = RectangleROI(1.5, -0.5, 3.5, 3.5)
    a, b = left.to_mask((4, 4)), right.to_mask((4, 4))
    assert not (a & b).any(), "half-open bounds must not overlap"
    assert (a | b).all(), "together they must cover the frame"


def test_rectangle_from_slices_matches_numpy_slicing():
    """from_slices selects exactly the pixels the equivalent slice would."""
    img = np.arange(16).reshape(4, 4)
    roi = RectangleROI.from_slices(y_range=(1, 3), x_range=(0, 2))
    mask = roi.to_mask(img.shape)
    np.testing.assert_array_equal(np.sort(img[mask]), np.sort(img[1:3, 0:2].ravel()))


def test_rectangle_accepts_corners_in_any_order():
    """Dragging a rectangle upward or leftward gives the same region."""
    a = RectangleROI(3, 4, 1, 2).to_mask((6, 6))
    b = RectangleROI(1, 2, 3, 4).to_mask((6, 6))
    np.testing.assert_array_equal(a, b)


def test_ellipse_is_symmetric_and_respects_rotation():
    """A circle is symmetric; a rotated ellipse follows its angle."""
    circle = EllipseROI(2, 2, 1.5).to_mask((5, 5))
    np.testing.assert_array_equal(circle, circle[::-1])
    np.testing.assert_array_equal(circle, circle[:, ::-1])

    wide = EllipseROI(5, 5, 4, 1).to_mask((11, 11))
    tall = EllipseROI(5, 5, 4, 1, angle=np.pi / 2).to_mask((11, 11))
    assert wide.sum() == tall.sum()
    np.testing.assert_array_equal(wide, tall.T)


def test_ellipse_with_a_zero_radius_has_no_extent():
    """A collapsed axis selects the points on it — not the whole plane.

    A zero radius must not read as "unbounded": a zero-radius gate that
    silently selects every point feeds a whole-plane mask into everything
    downstream, with nothing to distinguish it from a real selection.
    """
    points = np.array([[0.0, 0.0], [0.5, 0.5], [1.0, 0.0]])

    point_like = EllipseROI(0.5, 0.5, 0.0)
    np.testing.assert_array_equal(point_like.contains(points), [False, True, False])

    # Only the x extent collapses: a vertical segment through the centre.
    segment = EllipseROI(0.5, 0.5, 0.0, 2.0)
    np.testing.assert_array_equal(segment.contains(points), [False, True, False])
    np.testing.assert_array_equal(
        segment.contains(np.array([[0.5, 0.0], [0.6, 0.5]])), [True, False]
    )


def test_polygon_matches_the_equivalent_rectangle():
    """A 4-vertex polygon and the rectangle it traces agree."""
    poly = PolygonROI([(0.5, 0.5), (3.5, 0.5), (3.5, 2.5), (0.5, 2.5)])
    rect = RectangleROI(0.5, 0.5, 3.5, 2.5)
    np.testing.assert_array_equal(poly.to_mask((5, 5)), rect.to_mask((5, 5)))


def test_polygon_handles_concave_outlines():
    """A concave (freehand-like) outline excludes its notch."""
    poly = PolygonROI([(0, 0), (4, 0), (4, 4), (2, 1), (0, 4)])
    mask = poly.to_mask((5, 5))
    assert mask[0, 2]  # near the top edge, inside
    assert not mask[3, 2]  # inside the notch


def test_polygon_needs_three_vertices():
    """Two points do not bound a region."""
    with pytest.raises(ValueError):
        PolygonROI([(0, 0), (1, 1)])


def test_mask_roi_places_a_cropped_region_by_its_offset():
    """A cropped mask lands back in the right place in the full frame."""
    roi = MaskROI(np.ones((2, 2), dtype=bool), offset=(1, 2))
    mask = roi.to_mask((5, 5))
    assert mask.sum() == 4
    assert mask[1, 2] and mask[2, 3]
    assert not mask[0, 0]


def test_mask_roi_clips_at_the_frame_edge():
    """A mask hanging off the edge is clipped, not wrapped or an error."""
    roi = MaskROI(np.ones((3, 3), dtype=bool), offset=(-1, 3))
    mask = roi.to_mask((4, 4))
    assert mask.sum() == 2  # rows 0..1 x col 3
    assert mask[0, 3] and mask[1, 3]


def test_threshold_selects_by_intensity_and_refuses_point_membership():
    """A threshold is an image question; asking it a geometry one is an error."""
    img = np.arange(9).reshape(3, 3).astype(float)
    np.testing.assert_array_equal(
        ThresholdROI(low=4).to_mask((3, 3), image=img),
        img >= 4,
    )
    with pytest.raises(TypeError):
        ThresholdROI(low=4).contains(np.array([[0.0, 0.0]]))
    with pytest.raises(ValueError):
        ThresholdROI(low=4).to_mask((3, 3))


def test_threshold_percentiles_track_the_data():
    """Percentile bounds adapt to the image rather than to absolute counts."""
    img = np.arange(100).reshape(10, 10).astype(float)
    mask = ThresholdROI(low=90, percentile=True).to_mask((10, 10), image=img)
    assert mask.sum() == 10
    # A stack is averaged over frames before thresholding.
    stack = np.stack([img, img])
    np.testing.assert_array_equal(ThresholdROI(low=50).to_mask((10, 10), image=stack), img >= 50)


# --- composition -----------------------------------------------------------
def test_boolean_operators_build_the_expected_regions():
    """&, |, ^, - and ~ behave as set operations on the masks."""
    a = RectangleROI(-0.5, -0.5, 2.5, 2.5)
    b = RectangleROI(1.5, 1.5, 4.5, 4.5)
    ma, mb = a.to_mask((5, 5)), b.to_mask((5, 5))

    np.testing.assert_array_equal((a & b).to_mask((5, 5)), ma & mb)
    np.testing.assert_array_equal((a | b).to_mask((5, 5)), ma | mb)
    np.testing.assert_array_equal((a ^ b).to_mask((5, 5)), ma ^ mb)
    np.testing.assert_array_equal((a - b).to_mask((5, 5)), ma & ~mb)
    np.testing.assert_array_equal((~a).to_mask((5, 5)), ~ma)


def test_composite_mixes_geometry_with_intensity():
    """'Bright pixels inside this shape' composes cleanly."""
    img = np.zeros((5, 5))
    img[1:4, 1:4] = 10.0
    shape = RectangleROI(-0.5, -0.5, 2.5, 2.5)
    bright = ThresholdROI(low=5.0)
    mask = (shape & bright).to_mask((5, 5), image=img)
    assert mask.sum() == 4  # the 2x2 overlap of the shape and the bright block
    assert mask[1, 1] and not mask[0, 0] and not mask[3, 3]


def test_composite_rejects_wrong_arity():
    """Unary and binary operations check their operand count."""
    r = RectangleROI(0, 0, 1, 1)
    with pytest.raises(ValueError):
        CompositeROI("not", [r, r])
    with pytest.raises(ValueError):
        CompositeROI("sub", [r])
    with pytest.raises(ValueError):
        CompositeROI("nope", [r])


def test_composite_gates_points_too():
    """A composite answers the point question as well as the pixel one."""
    ring = EllipseROI(0, 0, 3) - EllipseROI(0, 0, 1)
    pts = np.array([[0.0, 0.0], [2.0, 0.0], [5.0, 0.0]])
    np.testing.assert_array_equal(ring.contains(pts), [False, True, False])


# --- persistence -----------------------------------------------------------
@pytest.mark.parametrize(
    "roi",
    [
        RectangleROI(1, 2, 3, 4, name="rect"),
        EllipseROI(2, 2, 1, 3, angle=0.4, name="ell"),
        PolygonROI([(0, 0), (3, 0), (3, 3)], name="tri"),
        MaskROI(np.eye(4, dtype=bool), offset=(1, 1), name="diag"),
        ThresholdROI(low=1.0, high=8.0, name="band"),
    ],
)
def test_every_roi_round_trips_through_a_dict(roi):
    """A stored region reloads to something that masks identically."""
    import json

    restored = roi_from_dict(json.loads(json.dumps(roi.to_dict())))
    assert type(restored) is type(roi)
    assert restored.name == roi.name
    img = np.arange(64).reshape(8, 8).astype(float)
    np.testing.assert_array_equal(
        restored.to_mask((8, 8), image=img), roi.to_mask((8, 8), image=img)
    )


def test_nested_composites_round_trip():
    """Serialisation recurses through composites."""
    roi = (RectangleROI(0, 0, 6, 6) - EllipseROI(3, 3, 1.5)) | MaskROI(
        np.ones((2, 2), dtype=bool), offset=(6, 6)
    )
    restored = roi_from_dict(roi.to_dict())
    np.testing.assert_array_equal(restored.to_mask((8, 8)), roi.to_mask((8, 8)))


def test_unknown_roi_type_is_rejected():
    """A bad description fails loudly rather than silently selecting nothing."""
    with pytest.raises(ValueError):
        roi_from_dict({"type": "trapezoid", "x": 1})
    with pytest.raises(ValueError):
        roi_from_dict({"no": "type"})


# --- segmentation bridge ---------------------------------------------------
def test_labels_become_rois_and_back():
    """Segmentation output converts to regions and rasterises back unchanged."""
    labels = np.zeros((6, 6), dtype=int)
    labels[1:3, 1:3] = 1
    labels[4:6, 3:5] = 2

    rois = labels_to_rois(labels)
    assert [r.name for r in rois] == ["1", "2"]
    assert all(isinstance(r, MaskROI) for r in rois)
    # cropped storage keeps only the bounding box
    assert rois[0].mask.shape == (2, 2)
    assert rois[0].offset == (1, 1)

    np.testing.assert_array_equal(rois_to_labels(rois, labels.shape), labels)


def test_labels_to_rois_can_keep_full_size_masks():
    """Uncropped conversion keeps each mask at frame size."""
    labels = np.array([[0, 1], [2, 2]])
    rois = labels_to_rois(labels, crop=False)
    assert all(r.mask.shape == (2, 2) for r in rois)
    assert all(r.offset == (0, 0) for r in rois)


def test_segmented_regions_gate_molecule_positions():
    """A segmentation region answers 'which molecules fell in this object?'.

    This is the molecule-MLE use: watershed labels become regions, and burst or
    molecule coordinates are gated against them.
    """
    labels = np.zeros((10, 10), dtype=int)
    labels[2:5, 2:5] = 1
    roi = labels_to_rois(labels)[0]
    positions = np.array([[3.0, 3.0], [8.0, 8.0], [4.0, 2.0]])
    np.testing.assert_array_equal(roi.contains(positions), [True, False, True])


def test_as_roi_accepts_a_region_its_serialised_form_or_nothing():
    """Settings cross RPC as plain data, so every consumer needs this coercion.

    Four of them were writing it out by hand, which is how ``None`` ends up
    meaning something different in each.
    """
    from chisurf.core.roi import as_roi

    rect = RectangleROI(0, 0, 2, 2)
    assert as_roi(None) is None
    assert as_roi(rect) is rect
    np.testing.assert_array_equal(as_roi(rect.to_dict()).to_mask((4, 4)), rect.to_mask((4, 4)))
    with pytest.raises(ValueError):
        as_roi("a rectangle, please")


def test_as_mask_treats_an_erased_pixel_as_outside():
    """A paint buffer marks removal with a negative, not with zero.

    ``!= 0`` on a signed buffer selects exactly the pixels the erase brush was
    used to remove — the kind of inversion that looks like a rendering bug
    three tools downstream.
    """
    from chisurf.core.roi import as_mask

    painted = np.zeros((3, 3))
    painted[0, 0] = 1.0
    painted[1, 1] = -1.0  # erased
    np.testing.assert_array_equal(
        as_mask(painted, (3, 3)),
        [[True, False, False], [False, False, False], [False, False, False]],
    )

    # None means everything; a ROI is rasterised; a bool array passes through.
    assert as_mask(None, (2, 2)).all()
    assert as_mask(RectangleROI(-0.5, -0.5, 0.5, 1.5), (2, 2)).sum() == 2
    given = np.array([[True, False], [False, True]])
    np.testing.assert_array_equal(as_mask(given, (2, 2)), given)


def test_a_region_addresses_the_flattened_data_vector():
    """A fit holds a 1-D vector; a region on the map says which entries it means.

    An image correlation flattens its lag map row-major before fitting, so the
    2-D residual plot's rectangle has to become data indices. Doing that
    arithmetic by hand in the plot is how the two conventions drift apart.
    """
    roi = RectangleROI.from_slices((1, 3), (2, 4))
    np.testing.assert_array_equal(roi.to_indices((4, 5)), [7, 8, 12, 13])

    # First and last index bracket the contiguous range a fit range needs.
    indices = roi.to_indices((4, 5))
    assert (int(indices[0]), int(indices[-1])) == (7, 13)

    assert RectangleROI(50, 50, 60, 60).to_indices((4, 5)).size == 0


def test_a_mask_painted_on_a_histogram_gates_the_data_behind_it():
    """A bitmap gate needs axes, or it can only ever select pixels.

    Painting a cluster on an E-S plot, a phasor plane or an intensity scatter
    produces a mask over *bins*; what the user means is the data those bins
    hold. Without an extent the mask has no way to say which values it covers,
    which is why every painted gate before this lived outside the ROI system.
    """
    counts = np.zeros((4, 4), dtype=bool)
    counts[2:, 2:] = True  # the upper-right quadrant
    edges = np.linspace(0.0, 1.0, 5)
    gate = MaskROI.from_histogram(counts, edges, edges, name="cluster")

    points = np.array([[0.8, 0.8], [0.1, 0.9], [0.6, 0.55], [0.49, 0.99]])
    np.testing.assert_array_equal(gate.contains(points), [True, False, True, False])

    # Bins are half-open, as histogram bins are: a value on the inner edge
    # belongs to the upper bin.
    np.testing.assert_array_equal(
        gate.contains(np.array([[0.5, 0.5], [0.4999, 0.5]])), [True, False]
    )

    # It knows where it is in value space, and it survives serialisation.
    np.testing.assert_allclose(gate.bounds(), (0.5, 0.5, 1.0, 1.0))
    restored = roi_from_dict(gate.to_dict())
    np.testing.assert_array_equal(restored.contains(points), gate.contains(points))
    assert restored.name == "cluster"


def test_a_value_space_mask_rasterises_onto_a_frame_that_shares_its_axes():
    """The other direction: the gate drawn on a plot masks an image of it."""
    counts = np.zeros((4, 4), dtype=bool)
    counts[2:, 2:] = True
    edges = np.linspace(0.0, 1.0, 5)
    gate = MaskROI.from_histogram(counts, edges, edges)

    # An 8x8 rendering of the same plane: the quadrant is a quarter of it.
    mask = gate.to_mask((8, 8), extent=(0.0, 1.0, 0.0, 1.0))
    assert mask.sum() == 16
    assert mask[4:, 4:].all()


def test_a_pixel_mask_still_means_pixels():
    """The default is unchanged: no extent, no axes, plain pixel indices."""
    m = MaskROI(np.array([[False, True], [False, True]]), offset=(3, 5))
    assert m.extent is None
    np.testing.assert_array_equal(m.contains(np.array([[6.0, 3.0], [5.0, 3.0]])), [True, False])
    np.testing.assert_array_equal(m.to_mask((6, 8))[3:5, 5:7], [[False, True], [False, True]])
    assert roi_from_dict(m.to_dict()).offset == (3, 5)


def test_histogram_edges_must_match_the_mask():
    """A silent off-by-one here would shift every gate by a bin."""
    with pytest.raises(ValueError, match="edges do not match"):
        MaskROI.from_histogram(
            np.zeros((4, 4), dtype=bool), np.linspace(0, 1, 4), np.linspace(0, 1, 5)
        )


def test_analytic_regions_bound_themselves_without_a_grid():
    """``bounds`` is exact where it can be, so a drawn handle does not creep.

    Rasterising a rectangle to find its extent snaps the corners to pixel
    edges; do that on every redraw of an interactive gate and the rectangle
    walks across the image.
    """
    assert RectangleROI(1.25, 2.5, 8.75, 6.0).bounds() == (1.25, 2.5, 8.75, 6.0)
    assert EllipseROI(5, 4, 3, 2).bounds() == (2.0, 2.0, 8.0, 6.0)
    assert PolygonROI([(1, 1), (7, 2), (4, 9)]).bounds() == (1.0, 1.0, 7.0, 9.0)
    # A rotated ellipse still reports the box that contains it.
    rotated = EllipseROI(0, 0, 4, 1, angle=np.pi / 2).bounds()
    np.testing.assert_allclose(rotated, (-1.0, -4.0, 1.0, 4.0), atol=1e-12)


def test_regions_that_need_a_grid_say_so():
    """A mask or a threshold has no geometry to read; it needs rasterising."""
    mask = MaskROI(np.array([[False, True], [False, True]]), offset=(3, 5))
    assert mask.bounds() is None
    assert mask.bounds((10, 10)) == (5.5, 2.5, 6.5, 4.5)
    # Off the grid entirely: nothing to report.
    assert MaskROI(np.ones((2, 2), dtype=bool), offset=(50, 50)).bounds((10, 10)) is None
    # A rectangle, by contrast, knows where it is even off the grid — it is
    # geometry, not pixels.
    assert RectangleROI(50, 50, 60, 60).bounds((10, 10)) == (50.0, 50.0, 60.0, 60.0)


def test_roi_is_the_abstract_base():
    """Every shape is a ROI, so consumers can accept the base type."""
    for roi in (
        RectangleROI(0, 0, 1, 1),
        EllipseROI(0, 0, 1),
        PolygonROI([(0, 0), (1, 0), (1, 1)]),
        MaskROI(np.ones((2, 2), dtype=bool)),
        ThresholdROI(low=0.0),
    ):
        assert isinstance(roi, ROI)
