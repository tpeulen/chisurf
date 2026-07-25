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
    CompositeROI,
    EllipseROI,
    MaskROI,
    PolygonROI,
    RectangleROI,
    ROI,
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
    assert mask.sum() == 36            # the 6x6 block of centres in [0.2, 0.8)
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


def test_polygon_matches_the_equivalent_rectangle():
    """A 4-vertex polygon and the rectangle it traces agree."""
    poly = PolygonROI([(0.5, 0.5), (3.5, 0.5), (3.5, 2.5), (0.5, 2.5)])
    rect = RectangleROI(0.5, 0.5, 3.5, 2.5)
    np.testing.assert_array_equal(poly.to_mask((5, 5)), rect.to_mask((5, 5)))


def test_polygon_handles_concave_outlines():
    """A concave (freehand-like) outline excludes its notch."""
    poly = PolygonROI([(0, 0), (4, 0), (4, 4), (2, 1), (0, 4)])
    mask = poly.to_mask((5, 5))
    assert mask[0, 2]           # near the top edge, inside
    assert not mask[3, 2]       # inside the notch


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
    assert mask.sum() == 2          # rows 0..1 x col 3
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
    np.testing.assert_array_equal(
        ThresholdROI(low=50).to_mask((10, 10), image=stack), img >= 50
    )


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
    assert mask.sum() == 4          # the 2x2 overlap of the shape and the bright block
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
@pytest.mark.parametrize("roi", [
    RectangleROI(1, 2, 3, 4, name="rect"),
    EllipseROI(2, 2, 1, 3, angle=0.4, name="ell"),
    PolygonROI([(0, 0), (3, 0), (3, 3)], name="tri"),
    MaskROI(np.eye(4, dtype=bool), offset=(1, 1), name="diag"),
    ThresholdROI(low=1.0, high=8.0, name="band"),
])
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


def test_roi_is_the_abstract_base():
    """Every shape is a ROI, so consumers can accept the base type."""
    for roi in (RectangleROI(0, 0, 1, 1), EllipseROI(0, 0, 1),
                PolygonROI([(0, 0), (1, 0), (1, 1)]),
                MaskROI(np.ones((2, 2), dtype=bool)), ThresholdROI(low=0.0)):
        assert isinstance(roi, ROI)
