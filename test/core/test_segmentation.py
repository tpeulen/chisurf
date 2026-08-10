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
    return ((x - 28) ** 2 + (y - 28) ** 2 < 16**2) | (
        (x - 44) ** 2 + (y - 52) ** 2 < 20**2
    )


def blobs(seed=0, shape=(128, 128), n_range=(8, 25)):
    """Overlapping Gaussian blobs on a noisy background — the realistic case."""
    rng = np.random.default_rng(seed)
    image = np.zeros(shape)
    y, x = np.indices(shape)
    for _ in range(rng.integers(*n_range)):
        centre_y, centre_x = rng.uniform(8, shape[0] - 8, 2)
        radius = rng.uniform(3, 9)
        image += np.exp(
            -((x - centre_x) ** 2 + (y - centre_y) ** 2) / (2 * radius * radius)
        )
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
    np.testing.assert_array_equal(
        binary, sk_segmentation.clear_border(smoothed > threshold)
    )
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
            sk_segmentation.watershed(
                -distance, markers, mask=binary, connectivity=connectivity
            ),
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
