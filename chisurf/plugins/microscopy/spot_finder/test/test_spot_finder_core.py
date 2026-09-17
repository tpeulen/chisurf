"""Detection is judged on what it recovers, not on whether it returns something.

Every detector here returns *a* set of regions for any image, so a test that
only checks the call succeeded checks nothing. These plant objects at known
positions and widths and ask whether each detector finds that many, in those
places — and then ask the questions that separate a detector from a filter: are
the labels contiguous, are two overlapping discs still two disjoint regions, and
does confining the search to a region change the threshold it computes.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import column_names, column_values, row_count
from chisurf.plugins.microscopy.spot_finder.core import (
    METHODS,
    SpotFinderSettings,
    detect,
    detect_labels,
)

#: Where the planted spots go, in (row, col).
CENTRES = ((8, 9), (10, 40), (33, 20), (45, 48), (20, 60))


def _field(shape=(64, 72), sigma=1.6, amplitude=200.0, background=2.0):
    """Return a field of Gaussian spots at :data:`CENTRES` on a flat background."""
    rows, cols = np.indices(shape)
    image = np.full(shape, background, dtype=float)
    for cy, cx in CENTRES:
        image += amplitude * np.exp(-(((rows - cy) ** 2 + (cols - cx) ** 2) / (2.0 * sigma**2)))
    return image


def _settings(method: str) -> SpotFinderSettings:
    """Return settings tuned for the planted field, per detector."""
    if method in ("log", "dog"):
        return SpotFinderSettings(
            method=method,
            min_sigma=1.0,
            max_sigma=3.0,
            threshold=0.05,
            min_area=2,
            clear_border=False,
        )
    return SpotFinderSettings(method=method, sigma=1.0, min_area=2, clear_border=False)


def _centroids(table) -> np.ndarray:
    names = column_names(table)
    return np.stack(
        [
            np.asarray(column_values(table, names.index("region.centroid_weighted_y"))),
            np.asarray(column_values(table, names.index("region.centroid_weighted_x"))),
        ],
        axis=1,
    )


@pytest.mark.parametrize("method", METHODS)
def test_every_detector_finds_the_planted_spots_where_they_were_planted(method):
    result = detect(_field(), _settings(method))

    assert result.n_regions == len(CENTRES), f"{method} found {result.n_regions}"

    found = _centroids(result.table)
    for cy, cx in CENTRES:
        distance = np.hypot(found[:, 0] - cy, found[:, 1] - cx).min()
        assert distance < 1.0, f"{method}: nothing within 1 px of ({cy}, {cx})"


@pytest.mark.parametrize("method", METHODS)
def test_labels_are_contiguous_from_one_after_filtering(method):
    """A dropped region leaves a gap, and a gap is a row that owns no pixel."""
    settings = _settings(method)
    settings.min_area = 6  # enough to drop nothing here...
    labels, _extra = detect_labels(_field(), settings)
    present = np.unique(labels)

    assert present[0] == 0
    np.testing.assert_array_equal(present[1:], np.arange(1, present.size))


@pytest.mark.parametrize("method", METHODS)
def test_a_field_with_nothing_in_it_finds_nothing_rather_than_failing(method):
    flat = np.full((32, 32), 5.0)
    result = detect(flat, _settings(method))

    assert result.n_regions == 0
    assert result.labels.max() == 0
    assert row_count(result.table) == 0


def test_min_area_rejects_the_hot_pixel_a_threshold_admits():
    """A spot covers several pixels; a camera defect covers exactly one."""
    image = np.full((32, 32), 2.0)
    image[10, 10] = 900.0  # one hot pixel
    rows, cols = np.indices(image.shape)
    image += 200.0 * np.exp(-(((rows - 20) ** 2 + (cols - 22) ** 2) / (2 * 1.6**2)))

    # A fixed level, not Otsu: with a 900-valued outlier in the frame, Otsu
    # puts the level *above* the real spot and finds only the defect — true,
    # and a different claim from this one.
    admits = detect(
        image,
        SpotFinderSettings(
            method="threshold", sigma=0.0, threshold=50.0, min_area=1, clear_border=False
        ),
    )
    rejects = detect(
        image,
        SpotFinderSettings(
            method="threshold", sigma=0.0, threshold=50.0, min_area=2, clear_border=False
        ),
    )

    assert admits.n_regions == 2
    assert rejects.n_regions == 1


def test_max_area_rejects_the_aggregate_that_dominates_a_histogram():
    image = np.full((48, 48), 2.0)
    image[4:8, 4:8] = 300.0  # 16 px, a molecule
    image[20:40, 20:40] = 300.0  # 400 px, an aggregate

    both = detect(
        image, SpotFinderSettings(method="threshold", sigma=0.0, min_area=2, clear_border=False)
    )
    small = detect(
        image,
        SpotFinderSettings(
            method="threshold", sigma=0.0, min_area=2, max_area=100, clear_border=False
        ),
    )

    assert both.n_regions == 2
    assert small.n_regions == 1


def test_clear_border_drops_the_partly_imaged_object():
    image = np.full((32, 32), 2.0)
    image[0:4, 10:14] = 300.0  # touching the top edge
    image[15:19, 15:19] = 300.0

    kept = detect(
        image, SpotFinderSettings(method="threshold", sigma=0.0, min_area=2, clear_border=False)
    )
    cleared = detect(
        image, SpotFinderSettings(method="threshold", sigma=0.0, min_area=2, clear_border=True)
    )

    assert kept.n_regions == 2
    assert cleared.n_regions == 1


def test_the_blob_detectors_report_the_width_they_measured():
    """The capability a fixed-scale detector does not have."""
    rows, cols = np.indices((64, 64))
    image = np.full((64, 64), 2.0)
    image += 200.0 * np.exp(-(((rows - 16) ** 2 + (cols - 16) ** 2) / (2 * 1.2**2)))
    image += 200.0 * np.exp(-(((rows - 44) ** 2 + (cols - 44) ** 2) / (2 * 3.0**2)))

    result = detect(
        image,
        SpotFinderSettings(
            method="log",
            min_sigma=1.0,
            max_sigma=4.0,
            num_sigma=12,
            threshold=0.05,
            min_area=2,
            clear_border=False,
        ),
    )

    names = column_names(result.table)
    assert "spot.sigma" in names
    sigmas = np.asarray(column_values(result.table, names.index("spot.sigma")))
    assert result.n_regions == 2
    # The narrow spot must come out narrower than the broad one, whichever
    # order they were detected in.
    assert sigmas.min() < 2.0 < sigmas.max()


def test_overlapping_discs_stay_disjoint_regions():
    """A contested pixel belongs to the nearer centre, not to both."""
    rows, cols = np.indices((48, 48))
    image = np.full((48, 48), 2.0)
    for cx in (20, 26):  # 6 px apart, discs of radius ~2.8 overlap
        image += 200.0 * np.exp(-(((rows - 24) ** 2 + (cols - cx) ** 2) / (2 * 2.0**2)))

    labels, _extra = detect_labels(
        image,
        SpotFinderSettings(
            method="log",
            min_sigma=1.0,
            max_sigma=3.0,
            num_sigma=10,
            threshold=0.05,
            min_area=2,
            clear_border=False,
            overlap=1.0,
        ),
    )

    assert labels.max() == 2
    # Disjoint by construction: a label image cannot hold two labels per pixel,
    # so the claim under test is that the second disc did not simply overwrite
    # the first — both survive with pixels of their own.
    counts = np.bincount(labels.ravel())
    assert counts[1] > 0 and counts[2] > 0


def test_a_region_sets_its_own_threshold():
    """The analysis region is applied before Otsu, not after.

    A bright patch elsewhere in the frame pulls a global Otsu level above the
    dim objects inside the region, so cropping *after* thresholding finds
    nothing where cropping before finds them — and the difference is invisible
    in anything but the region count.
    """
    from chisurf.core.roi import RectangleROI

    image = np.full((64, 64), 1.0)
    image[8:12, 8:12] = 3.0  # dim objects, inside the region
    image[8:12, 16:20] = 3.0
    image[36:60, 36:60] = 100.0  # a large bright patch, outside it

    roi = RectangleROI(0, 0, 32, 32)
    confined = detect(
        image,
        SpotFinderSettings(method="threshold", sigma=0.0, min_area=2, clear_border=False, roi=roi),
    )
    whole = detect(
        image, SpotFinderSettings(method="threshold", sigma=0.0, min_area=2, clear_border=False)
    )

    assert confined.n_regions == 2
    # Globally, Otsu separates the bright patch from everything else and the
    # dim objects fall on the background side of it — one region, and not the
    # two that are actually being looked for.
    assert whole.n_regions == 1


def test_an_unknown_method_is_named_rather_than_silently_defaulted():
    with pytest.raises(ValueError, match="unknown detection method"):
        detect(_field(), SpotFinderSettings(method="watershedd"))


def test_background_rate_excludes_the_pixels_touching_a_spot():
    """A spot's tail is not background, and counting it biases the rate up."""
    result = detect(_field(background=3.0), _settings("threshold"))

    tight = result.background_rate(margin=0)
    loose = result.background_rate(margin=3)

    assert loose < tight
    assert abs(loose - 3.0) < 0.5


def test_a_detection_round_trips_through_the_container(tmp_path: Path):
    """The detector's own columns survive beside the shared ones."""
    from chisurf.core.fio.fluorescence.region_container import read_regions
    from chisurf.core.fio.image import imwrite
    from chisurf.core.fio.pto import Measurement

    source = tmp_path / "field.tif"
    imwrite(source, _field().astype(np.uint16), axes="YX")
    with Measurement.create(source, artifact_kind="image_data") as m:
        container = Path(m.path)

    result = detect(_field(), _settings("log"))
    result.write(container, name="spots")

    reopened = read_regions(container, name="spots")
    assert reopened.n_regions == result.n_regions
    assert "spot.sigma" in column_names(reopened.table)
    np.testing.assert_array_equal(reopened.labels, result.labels)
