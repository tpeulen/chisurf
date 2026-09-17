"""A detection is a pair, and the half that can be lost is the useful one.

A segmentation written as a table of measurements reads back perfectly and is
useless: the analysis that follows it reaches a region's photons through the
region's *pixels*, and a centroid is not a pixel list. So the contract is a
label raster plus a table joined by ``label``, and these tests ask the questions
that separate a pair that round-trips from one that merely looks like it did —
is the raster still integer-valued, are the labels contiguous, is there a row
for every region including the ones an analysis would skip, and does the table
name the raster as its parent so the pixels can be found from the numbers.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import column_names, column_values, row_count
from chisurf.core.fio.fluorescence.region_container import (
    list_region_sets,
    read_regions,
    region_table,
    write_regions,
)
from chisurf.core.fio.pto import Measurement


def _labels() -> np.ndarray:
    """Return three regions of different sizes in a 32x32 field, none touching."""
    labels = np.zeros((32, 32), dtype=np.int32)
    labels[2:6, 2:6] = 1  # 16 px
    labels[10:13, 20:26] = 2  # 18 px
    labels[24:31, 8:11] = 3  # 21 px
    return labels


def _intensity(labels: np.ndarray) -> np.ndarray:
    """Return an intensity image whose regions differ in brightness."""
    image = np.full(labels.shape, 3.0)
    for label, level in ((1, 100.0), (2, 250.0), (3, 40.0)):
        image[labels == label] = level
    return image


@pytest.fixture
def container(tmp_path: Path) -> Path:
    """Return a container whose primary datum is an image, not a photon stream."""
    source = tmp_path / "field.tif"
    from chisurf.core.fio.image import imwrite

    imwrite(source, _intensity(_labels()).astype(np.uint16), axes="YX")
    with Measurement.create(source, artifact_kind="image_data") as m:
        return Path(m.path)


def test_a_detection_reopens_with_its_pixels_intact(container: Path):
    """The raster is the half that decides whether the regions can be analysed."""
    labels = _labels()
    write_regions(container, labels, _intensity(labels), name="spots")

    regions = read_regions(container, name="spots")

    assert regions.n_regions == 3
    np.testing.assert_array_equal(regions.labels, labels)
    # Integer, not the 8-bit picture a viewer would have made of it: label 250
    # and label 3 must still be distinguishable as *labels*.
    assert np.issubdtype(regions.labels.dtype, np.integer)


def test_the_table_reopens_column_for_column(container: Path):
    labels = _labels()
    written = region_table(labels, _intensity(labels))
    write_regions(container, labels, _intensity(labels), name="spots")

    read = read_regions(container, name="spots").table

    assert column_names(read) == column_names(written)
    for index, name in enumerate(column_names(written)):
        np.testing.assert_allclose(
            np.asarray(column_values(read, index), dtype=float),
            np.asarray(column_values(written, index), dtype=float),
            rtol=0,
            atol=0,
            err_msg=f"column {name} changed on the way through the container",
        )


def test_label_is_first_and_areas_are_what_was_drawn(container: Path):
    labels = _labels()
    write_regions(container, labels, _intensity(labels))

    table = read_regions(container).table
    names = column_names(table)
    assert names[0] == "label"
    np.testing.assert_array_equal(column_values(table, 0), [1, 2, 3])

    areas = np.asarray(column_values(table, names.index("region.area")))
    np.testing.assert_array_equal(areas, [16.0, 18.0, 21.0])


def test_gaps_in_the_labels_cannot_reach_the_file(container: Path):
    """Deleting labels leaves gaps, and a gap is a region that owns no pixel.

    Every filtering step — minimum area, border clearing — deletes labels, and a
    consumer that reads a label image as "1 to max" then measures regions that
    are not there. The file is where that has to stop, because the file outlives
    whichever segmentation wrote it.
    """
    labels = _labels()
    labels[labels == 3] = 7  # a gap at 3..6, and a maximum of 7
    labels[labels == 2] = 0  # and label 2 deleted outright

    write_regions(container, labels, _intensity(_labels()), name="gappy")
    regions = read_regions(container, name="gappy")

    assert regions.n_regions == 2
    assert sorted(np.unique(regions.labels)) == [0, 1, 2]
    np.testing.assert_array_equal(column_values(regions.table, 0), [1, 2])
    # Every row owns pixels. This is the failure a gap produces: a row of zeros.
    areas = np.asarray(
        column_values(regions.table, column_names(regions.table).index("region.area"))
    )
    assert (areas > 0).all()


def test_a_row_survives_for_a_region_an_analysis_would_skip(container: Path):
    """One row per region, always — a skipped region is a sentinel, not a gap.

    The table is merged against later results, and a table that drops its
    uninteresting rows does not fail: it silently lands one region's numbers on
    another's.
    """
    labels = _labels()
    photons = np.array([412.0, np.nan, 7.0])  # region 2 was not measured

    write_regions(
        container,
        labels,
        _intensity(labels),
        name="sparse",
        extra={"spot.n_photons": photons},
    )
    table = read_regions(container, name="sparse").table

    assert row_count(table) == 3
    values = np.asarray(
        column_values(table, column_names(table).index("spot.n_photons")), dtype=float
    )
    assert np.isnan(values[1])
    np.testing.assert_allclose(values[[0, 2]], [412.0, 7.0])


def test_an_extra_column_of_the_wrong_length_is_refused(container: Path):
    labels = _labels()
    with pytest.raises(ValueError, match="one row per region"):
        region_table(labels, extra={"spot.n_photons": [1.0, 2.0]})


def test_the_intensity_columns_are_absent_rather_than_zero_without_an_image(
    container: Path,
):
    """A detection made on a mask has no brightness and must not claim one."""
    names = column_names(region_table(_labels()))
    assert "region.intensity_mean" not in names
    assert "region.centroid_weighted_y" not in names
    assert "region.area" in names


def test_the_table_names_the_raster_as_its_parent(container: Path):
    """The numbers must lead back to the pixels, or the pair is two files."""
    labels = _labels()
    write_regions(container, labels, _intensity(labels), name="spots")

    with Measurement.open(container, writable=False) as m:
        chain = m.lineage("spots.regions")
        names = [step.get("name", "") for step in chain]
        uids = [step.get("uid") for step in chain]
        primary = m.instrument_uid

    assert "spots.labels" in names, names
    # And the chain does not stop there: photons/image -> labels -> regions is
    # three deep, and a provenance graph is only worth having if every artifact
    # in it reaches the primary datum.
    assert primary in uids, (primary, uids, names)


def test_a_detection_without_its_raster_is_refused_and_says_what_is_there(
    container: Path,
):
    labels = _labels()
    write_regions(container, labels, _intensity(labels), name="spots")

    with pytest.raises(FileNotFoundError) as excinfo:
        read_regions(container, name="molecules")

    message = str(excinfo.value)
    assert "molecules" in message
    assert "spots" in message, "the error must list what the container does hold"


def test_only_complete_pairs_are_listed(container: Path, tmp_path: Path):
    from chisurf.core.fio.fluorescence.imaging_container import write_image

    labels = _labels()
    write_regions(container, labels, _intensity(labels), name="spots")
    # A raster with no table: half a detection, and nothing can use it.
    write_image(container, labels, name="orphan.labels", axes="YX")

    assert list_region_sets(container) == ["spots"]


def test_two_detections_coexist_under_their_own_names(container: Path):
    labels = _labels()
    coarse = labels.copy()
    coarse[coarse == 3] = 0

    write_regions(container, labels, _intensity(labels), name="fine")
    write_regions(container, coarse, _intensity(labels), name="coarse")

    assert list_region_sets(container) == ["coarse", "fine"]
    assert read_regions(container, name="fine").n_regions == 3
    assert read_regions(container, name="coarse").n_regions == 2


def test_regions_come_back_as_rois_that_select_the_same_pixels(container: Path):
    """The point of keeping the pixels: a region is a gate again on reopen."""
    labels = _labels()
    write_regions(container, labels, _intensity(labels))

    rois = read_regions(container).rois()

    assert len(rois) == 3
    mask = rois[1].to_mask(labels.shape)
    np.testing.assert_array_equal(mask, labels == 2)
