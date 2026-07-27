"""Region properties: measuring a region, whatever produced it.

Segmentation is only half of an imaging analysis — the other half is asking what
each region *is*, and every consumer used to answer that on its own (the
molecule-MLE plugin through ``skimage.measure.regionprops``, object
colocalization through hand-rolled ``scipy.ndimage`` reductions). These tests
pin the two things the shared implementation has to get right: it measures a
drawn ROI exactly as it measures a segmentation label, and its numbers are the
established ones — checked against ``skimage.measure.regionprops`` where that is
installed, and against closed-form geometry where it is not.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from chisurf.core.roi import (
    EllipseROI,
    MaskROI,
    PolygonROI,
    RectangleROI,
    RegionProperties,
    ThresholdROI,
    regionprops,
    regionprops_table,
)

skimage_measure = pytest.importorskip("skimage.measure", reason="scikit-image not installed")


@pytest.fixture
def blobs() -> tuple[np.ndarray, np.ndarray]:
    """Return a few irregular labelled blobs and the intensity they came from."""
    from scipy import ndimage as ndi

    rng = np.random.default_rng(3)
    raw = rng.random((64, 64))
    labels, _ = ndi.label(ndi.gaussian_filter(raw, 2) > 0.55)
    intensity = ndi.gaussian_filter(raw, 1) * 100.0
    return labels.astype(np.int32), intensity


# --- one region, many sources ----------------------------------------------
def test_a_drawn_region_measures_like_a_segmented_one():
    """A polygon and the label image it rasterises to give the same numbers.

    This is the point of the module: region properties are a property of the
    region, not of the pipeline that produced it.
    """
    poly = PolygonROI([[2, 2], [18, 2], [18, 10], [2, 10]], name="box")
    drawn = regionprops(poly, shape=(21, 21))[0]

    labels = np.zeros((21, 21), dtype=int)
    labels[poly.to_mask((21, 21))] = 1
    segmented = regionprops(labels)[0]

    assert drawn.area == segmented.area
    assert drawn.centroid == segmented.centroid
    assert drawn.perimeter == segmented.perimeter
    assert drawn.eccentricity == pytest.approx(segmented.eccentricity)


def test_a_boolean_mask_is_one_region():
    """A bare mask needs no labelling to be measured."""
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:5, 3:9] = True
    prop = regionprops(mask)[0]
    assert prop.area == 18
    assert prop.bbox == (2, 3, 5, 9)
    assert prop.extent == 1.0


def test_labels_are_measured_in_order_however_they_are_numbered():
    """Gaps, a non-zero background and a huge label value all behave.

    Measuring each label by scanning the whole frame is the obvious
    implementation and it costs O(labels x frame); cutting each region from its
    own bounding box instead must not change which regions come back, nor
    their order.
    """
    labels = np.zeros((8, 8), dtype=int)
    labels[1:3, 1:3] = 9        # out of order and non-contiguous ...
    labels[5:7, 5:7] = 2        # ... with a gap before it
    props = regionprops(labels)
    assert [p.label for p in props] == [2, 9]
    assert [p.area for p in props] == [4, 4]
    assert props[0].centroid == (5.5, 5.5)

    # A nominated background is excluded, and 0 becomes an ordinary label.
    with_background = regionprops(labels, background=9)
    assert [p.label for p in with_background] == [0, 2]
    assert with_background[0].area == 8 * 8 - 8  # everything but the two blobs


def test_negative_labels_are_refused_rather_than_dropped():
    """Silently skipping them would report fewer regions than the image holds."""
    labels = np.zeros((4, 4), dtype=int)
    labels[0, 0] = -1
    with pytest.raises(ValueError, match="negative"):
        regionprops(labels)


def test_a_float_label_image_is_refused():
    """Casting it silently would merge or split objects, depending on rounding.

    ``TypeError`` is what scikit-image raises, so code that catches it ports.
    """
    labels = np.zeros((4, 4), dtype=float)
    labels[0, 0] = 1.0
    with pytest.raises(TypeError, match="integer dtype"):
        regionprops(labels)


def test_an_unsigned_label_image_measures_like_any_other(blobs):
    """The import path produces uint16: a TIFF from a segmentation tool.

    The fast path casts labels for ``find_objects``; an unsigned dtype must
    survive that unchanged rather than wrapping or being rejected.
    """
    labels, intensity = blobs
    as_uint = labels.astype(np.uint16)
    theirs = skimage_measure.regionprops(as_uint, intensity_image=intensity)
    ours = regionprops(as_uint, intensity)
    assert [p.label for p in ours] == [p.label for p in theirs]
    np.testing.assert_allclose([p.area for p in ours], [p.area for p in theirs])
    np.testing.assert_allclose(
        [p.intensity_mean for p in ours], [p.intensity_mean for p in theirs]
    )


def test_rois_are_measured_in_the_order_given():
    """Several ROIs give several property sets, labelled 1..n and named."""
    rois = [RectangleROI(0, 0, 3, 3, name="a"), RectangleROI(5, 5, 9, 8, name="b")]
    props = regionprops(rois, shape=(10, 10))
    assert [p.label for p in props] == [1, 2]
    assert [p.name for p in props] == ["a", "b"]
    assert [p.area for p in props] == [9, 12]


def test_empty_regions_are_dropped_not_reported_as_zero_area():
    """A region that covers no pixel is absent, rather than a row of NaNs."""
    assert regionprops(RectangleROI(50, 50, 60, 60), shape=(10, 10)) == []
    assert regionprops(np.zeros((8, 8), dtype=int)) == []


def test_an_intensity_dependent_region_can_be_measured():
    """A threshold region needs the image to rasterise, and gets it."""
    image = np.zeros((8, 8))
    image[3:6, 2:7] = 5.0
    prop = regionprops(ThresholdROI(low=1.0), image)[0]
    assert prop.area == 15
    assert prop.intensity_mean == 5.0


def test_measuring_a_roi_without_a_frame_is_an_error():
    """Rasterising needs a grid; asking without one says so."""
    with pytest.raises(ValueError, match="shape"):
        regionprops(RectangleROI(0, 0, 2, 2))


# --- the numbers themselves -------------------------------------------------
def test_geometry_of_a_known_rectangle():
    """Closed-form checks that do not depend on scikit-image being installed."""
    prop = regionprops(RectangleROI(1, 2, 9, 6, name="r"), shape=(12, 12))[0]
    assert prop.area == 8 * 4
    assert prop.bbox == (2, 1, 6, 9)
    assert prop.centroid == (3.5, 4.5)
    assert prop.extent == 1.0
    assert prop.solidity == 1.0
    # A filled convex shape covers its own hull exactly.
    assert prop.area_convex == prop.area
    # 8 x 4 rectangle: major axis of the equivalent ellipse is the longer side.
    assert prop.axis_major_length > prop.axis_minor_length
    assert prop.equivalent_diameter_area == pytest.approx(math.sqrt(4 * 32 / math.pi))


def test_a_disc_is_round_and_a_bar_is_not():
    """Eccentricity and circularity behave the way their names promise."""
    disc = regionprops(EllipseROI(15, 15, 10), shape=(31, 31))[0]
    assert disc.eccentricity == pytest.approx(0.0, abs=1e-2)
    assert disc.circularity == pytest.approx(1.0, abs=0.1)

    bar = np.zeros((13, 21), dtype=bool)
    bar[5:8, 2:19] = True
    stick = regionprops(bar)[0]
    assert stick.eccentricity > 0.98
    assert stick.circularity < 0.6


def test_solidity_falls_when_a_region_is_concave():
    """A ring fills far less of its convex hull than a disc does."""
    disc = EllipseROI(15, 15, 12)
    ring = regionprops(disc - EllipseROI(15, 15, 8), shape=(31, 31))[0]
    assert regionprops(disc, shape=(31, 31))[0].solidity > 0.9
    assert ring.solidity < 0.6


def test_orientation_follows_the_long_axis():
    """A horizontal bar and a vertical bar are a quarter turn apart."""
    horizontal = np.zeros((9, 9), dtype=bool)
    horizontal[4, 1:8] = True
    vertical = horizontal.T.copy()
    a = regionprops(horizontal)[0].orientation
    b = regionprops(vertical)[0].orientation
    assert abs(abs(a - b) - math.pi / 2) < 1e-12


def test_perimeter_weights_diagonal_steps():
    """A 45-degree boundary counts as ``sqrt(2)`` per pixel, not 1.

    Counting border pixels — the obvious implementation — underestimates a
    diagonal edge by 29 %, which is exactly the regime single molecules and
    puncta live in. The neighbourhood weighting is what makes circularity and
    perimeter usable for anything not axis-aligned.
    """
    from scipy import ndimage as ndi

    rr, cc = np.mgrid[:13, :13]
    diamond = (np.abs(rr - 6) + np.abs(cc - 6)) <= 4
    border = diamond & ~ndi.binary_erosion(
        diamond, ndi.generate_binary_structure(2, 1), border_value=0
    )
    measured = regionprops(diamond)[0].perimeter
    assert measured == pytest.approx(math.sqrt(2) * border.sum())
    # ... and that is within ~11 % of the true boundary of the continuous
    # diamond it samples, where the naive count is out by 37 %.
    true_length = 4.0 * math.sqrt(2) * 4.5
    assert abs(measured - true_length) / true_length < 0.12


# --- intensity --------------------------------------------------------------
def test_intensity_statistics_use_only_the_region():
    """Intensity properties ignore everything outside the mask."""
    image = np.zeros((10, 10))
    image[2:4, 2:4] = 10.0
    image[6:8, 6:8] = 1000.0  # a bright blob elsewhere, must not leak in
    prop = regionprops(RectangleROI(1, 1, 5, 5), image)[0]
    assert prop.intensity_max == 10.0
    assert prop.intensity_sum == 40.0
    assert prop.intensity_mean == pytest.approx(40.0 / 16)


def test_weighted_centroid_follows_the_photons():
    """The intensity-weighted centre sits on the bright side of the region."""
    image = np.zeros((10, 10))
    image[3, 6] = 100.0
    prop = regionprops(RectangleROI(1, 1, 9, 9), image)[0]
    assert prop.centroid == (4.5, 4.5)
    assert prop.centroid_weighted == (3.0, 6.0)


def test_negative_pixels_do_not_pull_the_weighted_centroid_outward():
    """Background subtraction leaves negative pixels; they are clipped, not used.

    An unclipped weighted mean can place the centre outside the region, or blow
    up when the weights sum to zero.
    """
    image = np.full((9, 9), -5.0)
    image[4, 7] = 50.0
    prop = regionprops(RectangleROI(0, 0, 9, 9), image)[0]
    assert prop.centroid_weighted == (4.0, 7.0)


def test_intensity_properties_need_an_intensity_image():
    """Asking for brightness without an image is a clear error, not a crash."""
    prop = regionprops(np.ones((4, 4), dtype=bool))[0]
    with pytest.raises(ValueError, match="intensity image"):
        _ = prop.intensity_mean


def test_a_stack_is_summed_over_frames():
    """An image stack measures like the frame-summed image it stands for."""
    stack = np.ones((5, 6, 6))
    prop = regionprops(np.ones((6, 6), dtype=bool), stack)[0]
    assert prop.intensity_mean == 5.0


# --- interoperability -------------------------------------------------------
def test_a_measured_region_is_a_region_again():
    """``to_roi`` closes the loop back to the geometry side of the subsystem."""
    labels = np.zeros((12, 12), dtype=int)
    labels[3:7, 4:9] = 7
    prop = regionprops(labels)[0]
    roi = prop.to_roi()
    assert isinstance(roi, MaskROI)
    assert roi.name == "7"
    np.testing.assert_array_equal(roi.to_mask((12, 12)), labels == 7)
    # ... and measuring it again is a fixed point.
    assert regionprops(roi, shape=(12, 12))[0].area == prop.area


def test_the_table_has_one_column_per_scalar():
    """``regionprops_table`` returns columns, exactly as scikit-image's does."""
    labels = np.array([[1, 1, 0], [1, 1, 0], [0, 0, 2]])
    table = regionprops_table(labels)
    assert list(table["label"]) == [1, 2]
    assert list(table["area"]) == [4, 1]
    assert "intensity_mean" not in table

    with_intensity = regionprops_table(labels, np.ones((3, 3)) * 3.0)
    assert list(with_intensity["intensity_mean"]) == [3.0, 3.0]


def test_multi_component_properties_are_split_like_skimage(blobs):
    """``centroid`` becomes ``centroid-0``/``centroid-1``, separator and all."""
    labels, intensity = blobs
    ours = regionprops_table(labels, intensity, ["label", "centroid", "area"])
    theirs = skimage_measure.regionprops_table(
        labels, intensity, ("label", "centroid", "area")
    )
    assert list(ours) == list(theirs)
    for key in theirs:
        np.testing.assert_allclose(ours[key], theirs[key])

    underscored = regionprops_table(labels, properties=["centroid"], separator="_")
    assert list(underscored) == ["centroid_0", "centroid_1"]


def test_the_table_keeps_its_columns_when_there_is_nothing_to_report():
    """An empty result is still a table, so downstream code needs no special case."""
    table = regionprops_table(np.zeros((5, 5), dtype=int), properties=["label", "area"])
    assert list(table) == ["label", "area"]
    assert len(table["area"]) == 0


def test_selected_properties_only():
    """A caller that wants two columns pays for two columns."""
    row = regionprops(np.ones((3, 3), dtype=bool))[0].to_dict(["area", "circularity"])
    assert set(row) == {"area", "circularity"}


def test_extra_properties_are_measured_too():
    """``extra_properties`` is scikit-image's extension point, and it works here."""

    def photon_density(mask, intensity):
        """Photons per pixel, as a user-supplied measurement."""
        return float(intensity[mask].sum() / mask.sum())

    image = np.full((6, 6), 4.0)
    props = regionprops(np.ones((6, 6), dtype=bool), image,
                        extra_properties=[photon_density])
    assert props[0].photon_density == 4.0
    table = regionprops_table(np.ones((6, 6), dtype=bool), image,
                              ["label", "photon_density"],
                              extra_properties=[photon_density])
    assert table["photon_density"].tolist() == [4.0]


def test_item_access_matches_skimage():
    """``prop['area']`` works, because scikit-image's region objects allow it."""
    prop = regionprops(np.ones((3, 3), dtype=bool))[0]
    assert prop["area"] == prop.area
    with pytest.raises(KeyError):
        _ = prop["not_a_property"]


def test_roi_properties_shortcut_and_bounding_box():
    """The convenience seam on ROI itself, used by drift and imaging tools."""
    roi = RectangleROI(2, 1, 6, 4)
    assert roi.bounding_box((10, 10)) == (1, 2, 4, 6)
    assert roi.properties((10, 10)).area == 12
    assert RectangleROI(50, 50, 60, 60).bounding_box((10, 10)) is None
    assert RectangleROI(50, 50, 60, 60).properties((10, 10)) is None


# --- agreement with the established implementation --------------------------
@pytest.mark.parametrize(
    "name",
    [
        "area", "area_bbox", "area_convex", "area_filled", "bbox", "centroid",
        "centroid_local", "centroid_weighted", "eccentricity",
        "equivalent_diameter_area", "euler_number", "extent",
        "axis_major_length", "axis_minor_length", "inertia_tensor",
        "inertia_tensor_eigvals", "intensity_max", "intensity_mean",
        "intensity_min", "intensity_std", "moments", "moments_central",
        "num_pixels", "orientation", "perimeter", "perimeter_crofton", "solidity",
    ],
)
def test_matches_skimage_regionprops(blobs, name):
    """Every shared property agrees with ``skimage.measure.regionprops``.

    The names are only worth borrowing if the numbers come with them. Where an
    algorithm has a choice — the border-weighted perimeter, the Crofton
    weights, the half-pixel-offset convex hull, the inertia-tensor axes, the
    sign convention of ``orientation``, the Euler coefficients — this pins that
    the same choice is made, so a value read here means what it means anywhere
    else in imaging.
    """
    labels, intensity = blobs
    theirs = skimage_measure.regionprops(labels, intensity_image=intensity)
    ours = regionprops(labels, intensity)
    assert len(theirs) == len(ours) > 5

    for a, b in zip(theirs, ours):
        expected = np.asarray(getattr(a, name), dtype=float)
        np.testing.assert_allclose(np.asarray(getattr(b, name), dtype=float), expected,
                                   rtol=1e-9, atol=1e-9)


def test_feret_diameter_is_close_to_skimages(blobs):
    """The longest caliper, measured on the hull vertices rather than a contour.

    scikit-image traces the padded hull with marching squares; taking the hull
    vertices directly is the same measurement without the contour tracer, and
    lands within a fraction of a pixel.
    """
    labels, _ = blobs
    theirs = [p.feret_diameter_max for p in skimage_measure.regionprops(labels)]
    ours = [p.feret_diameter_max for p in regionprops(labels)]
    np.testing.assert_allclose(ours, theirs, atol=0.75)


def test_degenerate_shapes_match_skimage():
    """Single pixels, lines and squares — where the axis formulae go singular."""
    shapes = {
        "point": np.array([[0, 0, 0], [0, 1, 0], [0, 0, 0]]),
        "hline": np.array([[0, 0, 0], [1, 1, 1], [0, 0, 0]]),
        "vline": np.array([[0, 1, 0], [0, 1, 0], [0, 1, 0]]),
        "diagonal": np.eye(3, dtype=int),
        "square": np.ones((3, 3), dtype=int),
    }
    for name, mask in shapes.items():
        theirs = skimage_measure.regionprops(mask)[0]
        ours = regionprops(mask)[0]
        assert ours.orientation == pytest.approx(theirs.orientation), name
        assert ours.eccentricity == pytest.approx(theirs.eccentricity), name
        assert ours.solidity == pytest.approx(theirs.solidity), name
        assert ours.perimeter == pytest.approx(theirs.perimeter), name


def test_properties_are_computed_once():
    """Measuring thousands of molecules must not re-walk the mask per access."""
    prop = RegionProperties(np.ones((4, 4), dtype=bool))
    assert prop.area == 16
    prop.image[:] = False  # invalidating the source must not change a cached answer
    assert prop.area == 16


# --- anisotropic pixels -------------------------------------------------------
#: Properties whose value must track a physical pixel spacing, and which
#: scikit-image also defines under one. The perimeters are excluded on purpose:
#: they are counted from pixel-border configurations whose weights assume square
#: pixels, so both libraries refuse an anisotropic spacing rather than return a
#: number that looks plausible.
SPACING_PROPERTIES = (
    "area", "area_bbox", "area_convex", "area_filled", "num_pixels",
    "centroid", "centroid_local", "centroid_weighted", "centroid_weighted_local",
    "axis_major_length", "axis_minor_length", "eccentricity",
    "equivalent_diameter_area", "extent", "feret_diameter_max",
    "inertia_tensor", "inertia_tensor_eigvals", "solidity", "euler_number",
    "moments", "moments_central", "moments_weighted", "moments_weighted_central",
)


@pytest.mark.parametrize("spacing", [(1.0, 1.0), 0.25, (0.65, 0.65), (0.2, 0.05), (3.0, 1.0)])
def test_every_scaled_property_matches_skimage_under_a_spacing(blobs, spacing):
    """A confocal voxel is rarely square; the numbers must be in real units.

    ``orientation`` is left out: it is undefined for a rotationally symmetric
    region, and the two libraries then differ by floating-point dust — see
    :func:`test_a_symmetric_region_has_no_orientation_to_agree_on`.
    """
    labels, intensity = blobs
    theirs = {p.label: p for p in skimage_measure.regionprops(
        labels, intensity_image=intensity, spacing=spacing)}
    ours = {p.label: p for p in regionprops(
        labels, intensity_image=intensity, spacing=spacing)}
    assert set(ours) == set(theirs)

    for name in SPACING_PROPERTIES:
        for key in theirs:
            np.testing.assert_allclose(
                np.asarray(getattr(ours[key], name), dtype=float),
                np.asarray(getattr(theirs[key], name), dtype=float),
                rtol=1e-8, atol=1e-8,
                err_msg=f"{name} of region {key} at spacing {spacing}",
            )


def test_area_becomes_physical_but_a_pixel_count_never_does():
    """``area`` carries units under a spacing; ``num_pixels`` is always a count."""
    labels = np.zeros((30, 30), dtype=int)
    labels[5:15, 8:20] = 1                      # 10 x 12 = 120 pixels

    plain = regionprops(labels)[0]
    assert plain.area == 120 and plain.num_pixels == 120

    scaled = regionprops(labels, spacing=(2.0, 3.0))[0]
    assert scaled.area == pytest.approx(120 * 6.0)
    assert scaled.num_pixels == 120


def test_a_spacing_moves_the_centroid_into_the_same_units():
    labels = np.zeros((30, 30), dtype=int)
    labels[5:15, 8:20] = 1
    plain = regionprops(labels)[0]
    scaled = regionprops(labels, spacing=(2.0, 0.5))[0]
    assert scaled.centroid == pytest.approx(
        (plain.centroid[0] * 2.0, plain.centroid[1] * 0.5)
    )


def test_a_ratio_is_unchanged_by_an_isotropic_spacing():
    """`extent` and `solidity` are areas over areas, so the units cancel."""
    labels = np.zeros((40, 40), dtype=int)
    labels[5:25, 8:30] = 1
    labels[10:14, 12:16] = 0                     # a hole, so solidity < 1
    plain = regionprops(labels)[0]
    scaled = regionprops(labels, spacing=0.37)[0]
    assert scaled.extent == pytest.approx(plain.extent)
    assert scaled.solidity == pytest.approx(plain.solidity)


def test_an_isotropic_spacing_scales_the_perimeter():
    labels = np.zeros((30, 30), dtype=int)
    labels[5:15, 8:20] = 1
    plain = regionprops(labels)[0]
    scaled = regionprops(labels, spacing=0.5)[0]
    assert scaled.perimeter == pytest.approx(plain.perimeter * 0.5)
    assert scaled.perimeter_crofton == pytest.approx(plain.perimeter_crofton * 0.5)


def test_an_anisotropic_perimeter_is_refused_rather_than_guessed():
    """The border weights assume square pixels; scikit-image refuses it too."""
    labels = np.zeros((30, 30), dtype=int)
    labels[5:15, 8:20] = 1
    props = regionprops(labels, spacing=(1.0, 2.0))[0]
    with pytest.raises(NotImplementedError, match="isotropic"):
        _ = props.perimeter
    with pytest.raises(NotImplementedError, match="isotropic"):
        _ = props.perimeter_crofton


def test_the_table_takes_a_spacing_too():
    labels = np.zeros((30, 30), dtype=int)
    labels[5:15, 8:20] = 1
    table = regionprops_table(
        labels, properties=("label", "area", "centroid"), spacing=(2.0, 3.0)
    )
    assert table["area"][0] == pytest.approx(720.0)
    assert table["centroid-0"][0] == pytest.approx(19.0)


@pytest.mark.parametrize("bad", [(1.0, 0.0), (1.0, -2.0), (np.inf, 1.0), (1.0, 2.0, 3.0)])
def test_an_impossible_spacing_is_refused(bad):
    """A silently dropped spacing turns physical units back into pixels."""
    labels = np.zeros((8, 8), dtype=int)
    labels[2:4, 2:4] = 1
    with pytest.raises(ValueError):
        regionprops(labels, spacing=bad)


def test_a_symmetric_region_has_no_orientation_to_agree_on():
    """An annulus is rotationally symmetric, so its orientation is a convention.

    Both libraries fall back on the sign of a cross-moment that is exactly zero
    in exact arithmetic, and pick their branch on floating-point dust — under a
    scaling scikit-image's inertia tensor keeps ~1e-15 of asymmetry where this
    one is exactly symmetric, so the two can differ by pi/4. The axis lengths,
    which are what a symmetric region actually determines, agree.
    """
    labels = np.zeros((80, 80), dtype=int)
    yy, xx = np.mgrid[0:80, 0:80]
    radius = np.hypot(yy - 40, xx - 40)
    labels[(radius <= 20) & (radius > 9)] = 1

    for spacing in (1.0, 0.65):
        ours = regionprops(labels, spacing=spacing)[0]
        theirs = skimage_measure.regionprops(labels, spacing=spacing)[0]
        assert ours.axis_major_length == pytest.approx(theirs.axis_major_length)
        assert ours.axis_minor_length == pytest.approx(theirs.axis_minor_length)
        # Degenerate: equal principal moments, so no axis is preferred.
        assert ours.inertia_tensor[0, 0] == pytest.approx(ours.inertia_tensor[1, 1])


# --- full scikit-image parity ------------------------------------------------
def test_every_scikit_image_property_exists_here(blobs):
    """The compatibility claim, checked against scikit-image's own registry.

    ``skimage.measure._regionprops.PROPS`` maps every name the library answers
    to — historical and modern — onto its canonical one. Nothing in the modern
    set may be missing, or ported code fails on an attribute that reads as
    supported everywhere else.
    """
    from skimage.measure._regionprops import PROPS

    labels, intensity = blobs
    props = regionprops(labels, intensity_image=intensity)[0]
    missing = sorted(n for n in set(PROPS.values()) if not hasattr(props, n))
    assert not missing, f"scikit-image properties with no counterpart: {missing}"


@pytest.mark.parametrize("name", ["moments_normalized", "moments_weighted_normalized",
                                  "moments_hu", "moments_weighted_hu"])
def test_the_moment_invariants_match_skimage(blobs, name):
    """Hu's invariants are a shape *signature*: same object, different size and
    angle, same numbers. They are only useful if they are the same numbers
    everyone else computes."""
    labels, intensity = blobs
    theirs = {p.label: p for p in skimage_measure.regionprops(
        labels, intensity_image=intensity)}
    ours = {p.label: p for p in regionprops(labels, intensity_image=intensity)}
    for key in theirs:
        a = np.asarray(getattr(ours[key], name), dtype=float)
        b = np.asarray(getattr(theirs[key], name), dtype=float)
        np.testing.assert_array_equal(np.isnan(a), np.isnan(b))
        finite = ~np.isnan(b)
        np.testing.assert_allclose(a[finite], b[finite], rtol=1e-10, atol=1e-12)


def test_hu_invariants_are_refused_under_a_spacing():
    """The normalisation divides by one scale, which is not what an anisotropic
    pixel does; scikit-image refuses the same case."""
    labels = np.zeros((20, 20), dtype=int)
    labels[4:10, 5:14] = 1
    props = regionprops(labels, spacing=(1.0, 2.0))[0]
    with pytest.raises(NotImplementedError, match="spacing"):
        _ = props.moments_hu


def test_an_offset_moves_the_coordinates_and_nothing_else():
    """`offset` says where an analysed crop sat in a larger image."""
    labels = np.zeros((20, 20), dtype=int)
    labels[3:9, 4:12] = 1

    plain = regionprops(labels)[0]
    shifted = regionprops(labels, offset=(100, 200))[0]
    theirs = skimage_measure.regionprops(labels, offset=(100, 200))[0]

    assert shifted.centroid == pytest.approx(theirs.centroid)
    np.testing.assert_array_equal(shifted.coords, theirs.coords)
    # The box, the slice and the area describe the crop, not where it came from.
    assert shifted.bbox == plain.bbox == theirs.bbox
    assert shifted.area == plain.area


@pytest.mark.parametrize(
    "old, modern",
    [("Area", "area"), ("BoundingBox", "bbox"), ("max_intensity", "intensity_max"),
     ("weighted_centroid", "centroid_weighted"), ("equivalent_diameter",
      "equivalent_diameter_area"), ("major_axis_length", "axis_major_length")],
)
def test_a_historical_scikit_image_name_still_answers(blobs, old, modern):
    """There is a lot of code written against older releases; refusing its
    property names only makes it fail for no reason."""
    labels, intensity = blobs
    props = regionprops(labels, intensity_image=intensity)[0]
    assert props[old] is not None
    np.testing.assert_allclose(
        np.asarray(props[old], dtype=float),
        np.asarray(getattr(props, modern), dtype=float),
    )
    assert np.allclose(np.asarray(getattr(props, old), dtype=float),
                       np.asarray(getattr(props, modern), dtype=float))


def test_every_historical_name_resolves(blobs):
    from chisurf.core.roi.props import LEGACY_PROPERTY_NAMES

    labels, intensity = blobs
    props = regionprops(labels, intensity_image=intensity)[0]
    unresolved = sorted(n for n in LEGACY_PROPERTY_NAMES if not hasattr(props, n))
    assert not unresolved, unresolved


def test_a_historical_name_works_in_the_table(blobs):
    labels, intensity = blobs
    table = regionprops_table(labels, intensity_image=intensity,
                              properties=("label", "Area", "max_intensity"))
    modern = regionprops_table(labels, intensity_image=intensity,
                               properties=("label", "area", "intensity_max"))
    np.testing.assert_allclose(table["Area"], modern["area"])
    np.testing.assert_allclose(table["max_intensity"], modern["intensity_max"])


def test_a_negative_label_is_refused_where_skimage_loses_it():
    """The one deliberate divergence, and the reason for it.

    scikit-image accepts a negative label and then never reports that region —
    it is dropped with no warning, so an object disappears from the results
    while the analysis reads as complete.
    """
    labels = np.zeros((10, 10), dtype=int)
    labels[2:5, 2:5] = 1
    labels[7:9, 7:9] = -3

    found = skimage_measure.regionprops(labels)
    assert [p.label for p in found] == [1], "skimage's behaviour has changed"

    with pytest.raises(ValueError, match="negative"):
        regionprops(labels)
