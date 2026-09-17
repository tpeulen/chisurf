"""Segmentation primitives, against the library they replace.

`chisurf.core.roi.segmentation` holds the five functions the imaging tools use
to turn an intensity image into a label image: smooth, threshold, drop the
border objects, find the seeds, flood. They were scikit-image's, and the bar for
replacing them is that they still agree with it — exactly, not approximately,
because every one of them feeds the next and a one-pixel difference in a seed
becomes a whole object boundary in the output.

The watershed is where that bar is hardest and most worth having. Its priority
queue is keyed on ``(value, age)``, and *age is the order neighbours are pushed
in* — so the order of the neighbour offsets, which looks like an implementation
detail, decides how a plateau is divided between two markers. A version that
ordered them by raveled offset instead of by Euclidean distance agreed on 99.8%
of pixels and disagreed on every plateau, which is exactly the kind of "nearly
right" that no downstream assertion catches.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage

from chisurf.core.roi.segmentation import (
    clear_border,
    gaussian,
    peak_local_max,
    threshold_otsu,
    watershed,
)


def two_circles(shape=(80, 80)):
    """The canonical watershed fixture: two overlapping discs."""
    y, x = np.indices(shape)
    return ((x - 28) ** 2 + (y - 28) ** 2 < 16**2) | ((x - 44) ** 2 + (y - 52) ** 2 < 20**2)


def blobs(seed=0, shape=(128, 128), n_range=(8, 25)):
    """Overlapping Gaussian blobs on a noisy background — the realistic case."""
    rng = np.random.default_rng(seed)
    image = np.zeros(shape)
    y, x = np.indices(shape)
    for _ in range(rng.integers(*n_range)):
        centre_y, centre_x = rng.uniform(8, shape[0] - 8, 2)
        radius = rng.uniform(3, 9)
        image += np.exp(-((x - centre_x) ** 2 + (y - centre_y) ** 2) / (2 * radius * radius))
    return image + rng.normal(0, 0.02, shape)


def segment(image):
    """The pipeline both call sites run: smooth, threshold, clear, seed, flood."""
    smoothed = gaussian(image, 1.5)
    threshold = threshold_otsu(smoothed)
    binary = clear_border(smoothed > threshold)
    if not binary.any():
        return None
    distance = ndimage.distance_transform_edt(binary)
    coordinates = peak_local_max(distance, labels=binary, footprint=np.ones((3, 3)))
    seeds = np.zeros(distance.shape, dtype=bool)
    seeds[tuple(coordinates.T)] = True
    markers, _ = ndimage.label(seeds)
    return distance, binary, markers


# ---------------------------------------------------------------------------
# Parity with scikit-image
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(6))
def test_the_whole_pipeline_matches_skimage(seed):
    """Every stage, on the same image, must give the library's answer."""
    pytest.importorskip("skimage")
    import skimage.feature as sk_feature
    import skimage.filters as sk_filters
    import skimage.segmentation as sk_segmentation

    image = blobs(seed)

    smoothed = gaussian(image, 1.5)
    np.testing.assert_array_equal(smoothed, sk_filters.gaussian(image, sigma=1.5))

    threshold = threshold_otsu(smoothed)
    assert threshold == sk_filters.threshold_otsu(smoothed)

    binary = clear_border(smoothed > threshold)
    np.testing.assert_array_equal(binary, sk_segmentation.clear_border(smoothed > threshold))
    if not binary.any():
        pytest.skip("this seed thresholds to nothing")

    distance = ndimage.distance_transform_edt(binary)
    for keywords in (
        {"labels": binary, "footprint": np.ones((3, 3))},
        {"labels": binary, "footprint": np.ones((5, 5))},
        {"labels": binary, "min_distance": 2, "exclude_border": False},
        {"labels": binary, "min_distance": 4, "exclude_border": False},
        {"min_distance": 3},
    ):
        np.testing.assert_array_equal(
            peak_local_max(distance, **keywords),
            sk_feature.peak_local_max(distance, **keywords),
            err_msg=f"peak_local_max{keywords}",
        )

    coordinates = peak_local_max(distance, labels=binary, footprint=np.ones((3, 3)))
    seeds = np.zeros(distance.shape, dtype=bool)
    seeds[tuple(coordinates.T)] = True
    markers, _ = ndimage.label(seeds)
    for connectivity in (1, 2):
        np.testing.assert_array_equal(
            watershed(-distance, markers, mask=binary, connectivity=connectivity),
            sk_segmentation.watershed(-distance, markers, mask=binary, connectivity=connectivity),
            err_msg=f"watershed(connectivity={connectivity})",
        )


def test_watershed_neighbour_order_matters():
    """Pin the ordering rule, because getting it wrong looks like success.

    The offsets must be ordered by Euclidean distance from the centre. Ordering
    them any other way still produces a valid segmentation with the right number
    of labels — it only moves the boundary on plateaus, which is why this is
    asserted directly rather than left to the parity test to notice.
    """
    from chisurf.core.roi.segmentation import _raveled_neighbour_offsets

    structure = ndimage.generate_binary_structure(2, 2)
    offsets = _raveled_neighbour_offsets((10, 10), structure)
    assert offsets.shape == (8,), "eight neighbours in a 2-D full connectivity"
    # The four face neighbours are at distance 1 and must come first; the four
    # diagonals are at sqrt(2).
    assert set(offsets[:4].tolist()) == {-10, -1, 1, 10}
    assert set(offsets[4:].tolist()) == {-11, -9, 9, 11}


# ---------------------------------------------------------------------------
# What each function is for
# ---------------------------------------------------------------------------


def test_watershed_splits_touching_objects():
    """The reason the watershed is here at all."""
    binary = two_circles()
    one_label, count = ndimage.label(binary)
    assert count == 1, "the fixture is supposed to be a single connected blob"

    distance = ndimage.distance_transform_edt(binary)
    coordinates = peak_local_max(distance, labels=binary, footprint=np.ones((3, 3)))
    seeds = np.zeros(distance.shape, dtype=bool)
    seeds[tuple(coordinates.T)] = True
    markers, _ = ndimage.label(seeds)
    labels = watershed(-distance, markers, mask=binary)
    assert labels.max() == 2, "the two discs must come apart"
    assert (labels[binary] > 0).all(), "every masked pixel belongs to a basin"
    assert (labels[~binary] == 0).all(), "nothing outside the mask is labelled"


def test_clear_border_keeps_the_interior():
    """Only the objects that touch the frame go."""
    image = np.zeros((20, 20), dtype=int)
    image[0:3, 0:3] = 1  # corner: touches
    image[8:12, 8:12] = 2  # middle: stays
    image[17:20, 10:14] = 3  # bottom edge: touches
    cleared = clear_border(image)
    assert set(np.unique(cleared)) == {0, 2}


def test_threshold_otsu_separates_two_populations():
    """A bimodal image must land between its modes."""
    rng = np.random.default_rng(1)
    values = np.concatenate([rng.normal(2, 0.3, 5000), rng.normal(8, 0.3, 5000)])
    threshold = threshold_otsu(values.reshape(100, 100))
    assert 3.0 < threshold < 7.0


def test_threshold_otsu_refuses_a_flat_image():
    """One value has no two classes; answering anything would be a guess."""
    with pytest.raises(ValueError, match="one value"):
        threshold_otsu(np.full((10, 10), 3.0))


def test_peak_local_max_finds_one_seed_per_object():
    """Two discs, two seeds — the property the watershed depends on."""
    binary = two_circles()
    distance = ndimage.distance_transform_edt(binary)
    coordinates = peak_local_max(distance, labels=binary, footprint=np.ones((3, 3)))
    assert len(coordinates) == 2
    # Each seed sits inside a disc, near its centre.
    for row, column in coordinates:
        assert binary[row, column]


def test_peak_local_max_honours_min_distance():
    """Peaks closer together than the spacing are thinned, brightest kept."""
    image = np.zeros((40, 40))
    image[10, 10] = 5.0
    image[10, 12] = 4.0  # two pixels away: suppressed at min_distance=5
    image[30, 30] = 3.0
    coordinates = peak_local_max(image, min_distance=5, exclude_border=False)
    assert sorted(map(tuple, coordinates)) == [(10, 10), (30, 30)]


# ---------------------------------------------------------------------------
# Degenerate input
# ---------------------------------------------------------------------------


def test_watershed_refuses_what_it_does_not_implement():
    """A silently ignored argument is a wrong segmentation nobody sees."""
    image = np.zeros((5, 5))
    markers = np.zeros((5, 5), dtype=int)
    markers[2, 2] = 1
    with pytest.raises(NotImplementedError, match="compact"):
        watershed(image, markers, compactness=0.5)
    with pytest.raises(NotImplementedError, match="watershed line"):
        watershed(image, markers, watershed_line=True)
    with pytest.raises(NotImplementedError, match="automatic markers"):
        watershed(image, 3)


def test_watershed_ignores_markers_outside_the_mask():
    """A marker the mask excludes must not leave an empty label behind."""
    binary = np.zeros((20, 20), dtype=bool)
    binary[5:15, 5:15] = True
    markers = np.zeros((20, 20), dtype=int)
    markers[10, 10] = 1
    markers[1, 1] = 2  # outside the mask
    labels = watershed(np.zeros((20, 20)), markers, mask=binary)
    assert set(np.unique(labels)) == {0, 1}


def test_watershed_shape_mismatch_is_refused():
    with pytest.raises(ValueError, match="same shape"):
        watershed(np.zeros((5, 5)), np.zeros((6, 6), dtype=int))
    with pytest.raises(ValueError, match="same shape"):
        watershed(np.zeros((5, 5)), np.zeros((5, 5), dtype=int), mask=np.ones((6, 6), bool))


def test_peak_local_max_on_an_empty_image():
    assert peak_local_max(np.zeros((0, 0))).shape == (0, 2)


def test_watershed_works_in_three_dimensions():
    """Two overlapping spheres, the 3-D case the imaging tools may reach."""
    z, y, x = np.indices((40, 40, 40))
    binary = ((x - 14) ** 2 + (y - 14) ** 2 + (z - 20) ** 2 < 9**2) | (
        (x - 26) ** 2 + (y - 26) ** 2 + (z - 20) ** 2 < 9**2
    )
    distance = ndimage.distance_transform_edt(binary)
    coordinates = peak_local_max(distance, labels=binary, footprint=np.ones((3, 3, 3)))
    seeds = np.zeros(distance.shape, dtype=bool)
    seeds[tuple(coordinates.T)] = True
    markers, _ = ndimage.label(seeds)
    labels = watershed(-distance, markers, mask=binary)
    assert labels.max() == 2
    assert (labels[binary] > 0).all()


# ---------------------------------------------------------------------------
# The second tranche: cleaning up, enhancing, and finding at unknown scale
# ---------------------------------------------------------------------------


def _random_labels(seed=0, shape=(64, 64), density=0.6):
    """A field of many small components — the shape that stresses label code."""
    mask = np.random.default_rng(seed).random(shape) > density
    return ndimage.label(mask)[0], mask


@pytest.mark.parametrize("seed", range(4))
def test_label_utilities_match_skimage(seed):
    """remove_small_objects/holes, relabel_sequential, expand_labels, find_boundaries."""
    pytest.importorskip("skimage")
    import skimage.morphology as sk_morphology
    import skimage.segmentation as sk_segmentation

    from chisurf.core.roi.segmentation import (
        expand_labels,
        find_boundaries,
        relabel_sequential,
        remove_small_holes,
        remove_small_objects,
    )

    labels, mask = _random_labels(seed)

    for size in (2, 5, 20):
        # `min_size=n` here means "strictly fewer than n", which is
        # scikit-image's `max_size=n - 1`. Its own `min_size` is mid-deprecation
        # and its meaning moved during it, so the stable spelling is compared
        # against rather than the one that is going away.
        np.testing.assert_array_equal(
            remove_small_objects(labels.copy(), size),
            sk_morphology.remove_small_objects(labels.copy(), max_size=size - 1),
        )
        np.testing.assert_array_equal(
            remove_small_objects(mask.copy(), size),
            sk_morphology.remove_small_objects(mask.copy(), max_size=size - 1),
        )
        np.testing.assert_array_equal(
            remove_small_holes(mask.copy(), size),
            sk_morphology.remove_small_holes(mask.copy(), max_size=size - 1),
        )

    mine, forward, _ = relabel_sequential(labels)
    theirs, their_forward, _ = sk_segmentation.relabel_sequential(labels)
    np.testing.assert_array_equal(mine, theirs)
    np.testing.assert_array_equal(np.asarray(forward), np.asarray(their_forward))

    for distance in (1.0, 2.5, 5.0):
        np.testing.assert_array_equal(
            expand_labels(labels, distance),
            sk_segmentation.expand_labels(labels, distance),
        )

    for mode in ("thick", "inner", "outer"):
        for connectivity in (1, 2):
            np.testing.assert_array_equal(
                find_boundaries(labels, connectivity=connectivity, mode=mode),
                sk_segmentation.find_boundaries(labels, connectivity=connectivity, mode=mode),
                err_msg=f"mode={mode} connectivity={connectivity}",
            )


def test_relabel_sequential_closes_the_gaps():
    """The point of it: no consumer should see a label that owns no pixel."""
    from chisurf.core.roi.segmentation import relabel_sequential

    labels = np.array([[0, 1, 0], [0, 5, 5], [9, 0, 0]])
    relabelled, forward, inverse = relabel_sequential(labels)
    assert sorted(np.unique(relabelled)) == [0, 1, 2, 3]
    assert forward[5] == 2 and inverse[2] == 5
    np.testing.assert_array_equal(inverse[relabelled], labels)


def test_expand_labels_does_not_merge_neighbours():
    """Two labels growing towards each other must meet, not fuse."""
    from chisurf.core.roi.segmentation import expand_labels

    labels = np.zeros((21, 21), dtype=int)
    labels[10, 4] = 1
    labels[10, 16] = 2
    grown = expand_labels(labels, distance=8)
    assert set(np.unique(grown)) == {0, 1, 2}
    # The midline belongs to neither exclusively, but the two never touch as
    # one component.
    assert ndimage.label(grown == 1)[1] == 1
    assert ndimage.label(grown == 2)[1] == 1


@pytest.mark.parametrize("seed", range(3))
def test_difference_of_gaussians_matches_skimage(seed):
    pytest.importorskip("skimage")
    import skimage.filters as sk_filters

    from chisurf.core.roi.segmentation import difference_of_gaussians

    image = np.random.default_rng(seed).random((64, 64))
    for low, high in ((1.0, None), (1.0, 3.0), (2.0, 5.0)):
        np.testing.assert_allclose(
            difference_of_gaussians(image, low, high),
            sk_filters.difference_of_gaussians(image, low, high),
            atol=1e-12,
        )


def test_difference_of_gaussians_refuses_an_inverted_band():
    from chisurf.core.roi.segmentation import difference_of_gaussians

    with pytest.raises(ValueError, match="inverted"):
        difference_of_gaussians(np.zeros((8, 8)), 4.0, 1.0)


def test_white_tophat_removes_a_gradient_and_keeps_the_spot():
    """The property it is for: a spot survives an illumination ramp.

    The ramp is suppressed rather than erased, and by a knowable amount: the
    opening of a ramp is the ramp shifted by roughly gradient x half-footprint,
    so a 0.02/pixel gradient under a 15-pixel footprint leaves about 0.14
    behind. That residue is the reason `size` has to be chosen against the
    illumination scale and not just against the spots.
    """
    from chisurf.core.roi.segmentation import white_tophat

    y, x = np.indices((64, 64))
    ramp = 0.02 * x + 0.01 * y
    spot = np.exp(-((x - 32) ** 2 + (y - 32) ** 2) / 8.0)
    raw = ramp + spot
    corrected = white_tophat(raw, size=15)

    assert corrected[32, 32] > 0.8, "the spot must survive"
    corners = [(2, 2), (2, 61), (61, 2), (61, 61)]
    before = max(raw[r, c] for r, c in corners)
    after = max(corrected[r, c] for r, c in corners)
    assert after < before / 5, "the ramp must be suppressed several-fold"
    assert after < 0.25 * corrected[32, 32], "and left well below the spot"


@pytest.mark.parametrize("fully_connected", ["low", "high"])
def test_find_contours_matches_skimage(fully_connected):
    pytest.importorskip("skimage")
    import skimage.measure as sk_measure

    from chisurf.core.roi.segmentation import find_contours

    mask = two_circles((60, 60)).astype(float)
    mine = find_contours(mask, 0.5, fully_connected=fully_connected)
    theirs = sk_measure.find_contours(mask, 0.5, fully_connected=fully_connected)
    assert len(mine) == len(theirs)
    for a, b in zip(mine, theirs):
        np.testing.assert_allclose(a, b)


def test_find_contours_traces_a_closed_loop_around_a_disc():
    """A contour is geometry, not a raster: it should close and enclose the area."""
    from chisurf.core.roi.segmentation import find_contours

    y, x = np.indices((60, 60))
    disc = ((x - 30) ** 2 + (y - 30) ** 2 < 12**2).astype(float)
    contours = find_contours(disc, 0.5)
    assert len(contours) == 1
    contour = contours[0]
    np.testing.assert_allclose(contour[0], contour[-1], atol=1e-9)
    # Shoelace area of the traced polygon against the pixel count.
    rows, columns = contour[:, 0], contour[:, 1]
    area = 0.5 * abs(np.dot(rows[:-1], columns[1:]) - np.dot(columns[:-1], rows[1:]))
    assert abs(area - disc.sum()) / disc.sum() < 0.05


@pytest.mark.parametrize("detector", ["blob_dog", "blob_log"])
def test_blob_detectors_match_skimage(detector):
    pytest.importorskip("skimage")
    import skimage.feature as sk_feature

    from chisurf.core.roi import segmentation

    y, x = np.indices((80, 80))
    image = np.zeros((80, 80))
    for centre_y, centre_x, sigma in [(20, 20, 2.0), (50, 30, 4.0), (30, 60, 3.0)]:
        image += np.exp(-((x - centre_x) ** 2 + (y - centre_y) ** 2) / (2 * sigma * sigma))
    keywords = (
        {"min_sigma": 1, "max_sigma": 8, "threshold": 0.02}
        if detector == "blob_dog"
        else {"min_sigma": 1, "max_sigma": 8, "num_sigma": 8, "threshold": 0.05}
    )
    mine = getattr(segmentation, detector)(image, **keywords)
    theirs = getattr(sk_feature, detector)(image, **keywords)
    assert mine.shape == theirs.shape
    np.testing.assert_allclose(mine[np.lexsort(mine.T)], theirs[np.lexsort(theirs.T)])


def test_blob_detectors_recover_the_width_they_were_given():
    """The capability a fixed-scale detector does not have: it reports the size."""
    from chisurf.core.roi.segmentation import blob_log

    y, x = np.indices((120, 120))
    truth = [(30, 30, 2.0), (30, 90, 4.0), (90, 60, 6.0)]
    image = np.zeros((120, 120))
    for centre_y, centre_x, sigma in truth:
        image += np.exp(-((x - centre_x) ** 2 + (y - centre_y) ** 2) / (2 * sigma * sigma))
    blobs = blob_log(image, min_sigma=1, max_sigma=9, num_sigma=17, threshold=0.05)
    assert len(blobs) == 3
    found = {(round(r), round(c)): s for r, c, s in blobs}
    for centre_y, centre_x, sigma in truth:
        matches = [
            s for (r, c), s in found.items() if abs(r - centre_y) <= 1 and abs(c - centre_x) <= 1
        ]
        assert matches, f"no blob near ({centre_y}, {centre_x})"
        assert abs(matches[0] - sigma) <= 1.0, f"width {matches[0]} vs {sigma}"


def test_blob_detectors_merge_duplicate_scales():
    """One spot must be reported once, not once per scale it survives."""
    from chisurf.core.roi.segmentation import blob_dog

    y, x = np.indices((60, 60))
    image = np.exp(-((x - 30) ** 2 + (y - 30) ** 2) / 8.0)
    assert len(blob_dog(image, min_sigma=1, max_sigma=10, threshold=0.02)) == 1
