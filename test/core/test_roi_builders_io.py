"""Building regions from images, and getting them in and out of files.

``arbitrary_region`` is the port of the reference suite's two-scale selection:
a pixel survives only if its *local* statistics resemble those of its
*neighbourhood*. The tests below are built around what that buys over a plain
threshold — rejecting things that are anomalous locally while being unremarkable
globally, which is exactly what aggregates and debris are.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

# Imported from the submodules rather than the package, so these tests do not
# depend on the package's export surface while it is being extended.
from chisurf.core.roi.builders import arbitrary_region, local_statistics
from chisurf.core.roi.io import (
    load_roi_metadata,
    load_rois,
    roi_from_mask_file,
    rois_from_cellpose,
    rois_from_label_image,
    save_label_image,
    save_rois,
)
from chisurf.core.roi.roi import EllipseROI, MaskROI, RectangleROI


# --- local statistics ------------------------------------------------------
def test_local_statistics_of_a_flat_image():
    """A constant image has the constant as its mean and no variance."""
    img = np.full((16, 16), 7.0)
    mean, var = local_statistics(img, 3)
    np.testing.assert_allclose(mean, 7.0)
    np.testing.assert_allclose(var, 0.0, atol=1e-9)


def test_local_variance_carries_the_population_correction():
    """The variance is the population estimate, not the biased sample one."""
    rng = np.random.default_rng(0)
    img = rng.normal(0.0, 1.0, (128, 128))
    _, var3 = local_statistics(img, 3)
    # the n²/(n²-1) correction lifts the biased estimate towards the true 1.0
    biased = var3 * (8.0 / 9.0)
    assert abs(float(var3.mean()) - 1.0) < abs(float(biased.mean()) - 1.0)


# --- arbitrary region ------------------------------------------------------
def test_absolute_intensity_bounds():
    """The first stage is a plain threshold on the frame-averaged image."""
    img = np.arange(100, dtype=float).reshape(10, 10)
    mask = arbitrary_region(
        img, intensity_min=20, intensity_max=60, intensity_fold_max=None
    ).to_mask((10, 10))
    np.testing.assert_array_equal(mask, (img >= 20) & (img <= 60))


def test_small_aggregate_is_rejected_while_an_extended_feature_survives():
    """Two objects of *identical* brightness are told apart by their extent.

    This is the point of the two-scale test. An absolute threshold cannot
    separate these at all — they have the same intensity. What differs is the
    local-to-neighbourhood contrast: a small aggregate stands out against its
    surroundings (ratio ~6), while the interior of an extended structure looks
    like more of the same (ratio ~1.2).
    """
    img = np.ones((48, 48)) * 10.0
    img[10:20, 10:20] = 100.0  # a legitimately bright, extended feature
    img[34:37, 34:37] = 100.0  # a small aggregate of the same brightness

    roi = arbitrary_region(img, window=3, neighbourhood=11, intensity_fold_max=2.0)
    mask = roi.to_mask(img.shape)

    assert not mask[35, 35], "the aggregate must be rejected"
    assert mask[15, 15], "the interior of the extended feature must survive"


def test_a_single_hot_pixel_needs_a_matched_window():
    """A one-pixel artefact is diluted by a 3x3 window, and caught by a 1x1 one.

    Worth pinning because it is a real trap: the window has to match the scale
    of what you are rejecting. Averaged over 3x3, a single hot pixel lifts the
    local mean only ~1.9x and slips through a 2x fold.
    """
    img = np.ones((48, 48)) * 10.0
    img[35, 35] = 100.0

    diluted = arbitrary_region(img, window=3, neighbourhood=11, intensity_fold_max=2.0).to_mask(
        img.shape
    )
    matched = arbitrary_region(img, window=1, neighbourhood=11, intensity_fold_max=2.0).to_mask(
        img.shape
    )

    assert diluted[35, 35], "a 3x3 window dilutes a single pixel below the fold"
    assert not matched[35, 35], "a 1x1 window sees it at full contrast"


def test_low_variance_patch_is_rejected():
    """An immobile patch has anomalously low local variance for its context."""
    rng = np.random.default_rng(3)
    img = rng.normal(100.0, 12.0, (64, 64))
    img[40:50, 40:50] = 100.0  # perfectly flat: no local variance at all

    roi = arbitrary_region(img, window=3, neighbourhood=11, variance_fold_min=0.2)
    mask = roi.to_mask(img.shape)

    assert not mask[45, 45], "the flat patch must be rejected"
    assert mask.mean() > 0.5, "most of the noisy field must survive"


def test_neighbourhood_must_exceed_the_window():
    """Equal windows make the fold tests meaningless, so they are rejected."""
    with pytest.raises(ValueError, match="must be larger"):
        arbitrary_region(np.zeros((8, 8)), window=5, neighbourhood=5)


def test_rejects_a_four_dimensional_stack():
    """An unusable array shape fails loudly."""
    with pytest.raises(ValueError):
        arbitrary_region(np.zeros((2, 2, 8, 8)))


def test_stack_is_averaged_for_the_absolute_stage():
    """Frame averaging is what makes thresholding work at low photon counts."""
    stack = np.stack([np.zeros((8, 8)), np.full((8, 8), 20.0)])
    mask = arbitrary_region(stack, intensity_min=5.0).to_mask((8, 8))
    assert mask.all(), "the mean (10) is above the threshold even though frame 0 is not"


def test_result_composes_with_other_regions():
    """The builder returns a normal ROI, so it combines like any other."""
    img = np.ones((32, 32)) * 10.0
    img[20, 20] = 400.0
    region = arbitrary_region(img, window=3, neighbourhood=9, intensity_fold_max=2.0)
    combined = region & RectangleROI(0, 0, 16, 16)
    mask = combined.to_mask((32, 32))
    assert mask[5, 5] and not mask[20, 20] and not mask[25, 25]


# --- native persistence ----------------------------------------------------
def test_roi_file_round_trips_every_shape(tmp_path):
    """A saved set reloads to regions that mask identically."""
    rois = [
        RectangleROI(1, 1, 5, 5, name="a"),
        EllipseROI(8, 8, 3, name="b"),
        RectangleROI(0, 0, 4, 4) - EllipseROI(2, 2, 1),
    ]
    path = save_rois(rois, str(tmp_path / "set.roi.json"), metadata={"image": "x.tif"})
    back = load_rois(path)

    assert len(back) == 3
    for original, restored in zip(rois, back):
        np.testing.assert_array_equal(restored.to_mask((16, 16)), original.to_mask((16, 16)))
    assert load_roi_metadata(path) == {"image": "x.tif"}


def test_roi_file_is_plain_readable_json(tmp_path):
    """The native format is diffable text, not an opaque binary blob."""
    save_rois([RectangleROI(0, 0, 2, 2, name="r")], str(tmp_path / "s.json"))
    data = json.loads((tmp_path / "s.json").read_text())
    assert data["format"] == "chisurf-roi"
    assert data["rois"][0]["type"] == "rectangle"
    assert data["rois"][0]["name"] == "r"


def test_a_foreign_json_is_rejected(tmp_path):
    """Loading an unrelated JSON fails loudly rather than yielding nothing."""
    p = tmp_path / "other.json"
    p.write_text(json.dumps({"hello": "world"}))
    with pytest.raises(ValueError, match="not a chisurf-roi file"):
        load_rois(str(p))


# --- segmentation interchange ----------------------------------------------
def test_cellpose_segmentation_becomes_one_region_per_cell(tmp_path):
    """A Cellpose _seg.npy imports as one region per detected object."""
    labels = np.zeros((20, 20), dtype=np.uint16)
    labels[2:6, 2:6] = 1
    labels[10:16, 10:18] = 2
    labels[15:19, 2:5] = 3
    path = tmp_path / "img_seg.npy"
    np.save(path, {"masks": labels, "outlines": np.zeros_like(labels)}, allow_pickle=True)

    rois = rois_from_cellpose(str(path))
    assert [r.name for r in rois] == ["1", "2", "3"]
    assert all(isinstance(r, MaskROI) for r in rois)
    np.testing.assert_array_equal(rois[1].to_mask((20, 20)), labels == 2)


def test_a_plain_label_npy_also_imports(tmp_path):
    """A bare label array works too, not only the dictionary form."""
    labels = np.array([[0, 1], [2, 2]], dtype=np.int32)
    path = tmp_path / "labels.npy"
    np.save(path, labels)
    assert [r.name for r in rois_from_cellpose(str(path))] == ["1", "2"]


def test_a_file_without_masks_is_rejected(tmp_path):
    """A dictionary carrying no label image says so."""
    path = tmp_path / "bad_seg.npy"
    np.save(path, {"flows": np.zeros((4, 4))}, allow_pickle=True)
    with pytest.raises(ValueError, match="no label image"):
        rois_from_cellpose(str(path))


def test_label_image_round_trips_through_a_tiff(tmp_path):
    """Regions rasterise to a label TIFF and import back unchanged."""
    rois = [RectangleROI(1, 1, 4, 4, name="1"), RectangleROI(6, 6, 9, 9, name="2")]
    path = save_label_image(rois, (12, 12), str(tmp_path / "labels.tif"))
    back = rois_from_label_image(path)
    assert len(back) == 2
    for original, restored in zip(rois, back):
        np.testing.assert_array_equal(restored.to_mask((12, 12)), original.to_mask((12, 12)))


def test_binary_mask_file_imports_as_one_region(tmp_path):
    """The reference implementation's export shape: a single boolean mask."""
    from chisurf.core.fio.image import imwrite

    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[3:7, 3:7] = 1
    path = tmp_path / "exported_mask.tif"
    imwrite(path, mask)

    roi = roi_from_mask_file(str(path))
    assert roi.name == "exported_mask"
    np.testing.assert_array_equal(roi.to_mask((10, 10)), mask.astype(bool))


def test_a_selection_survives_a_full_round_trip(tmp_path):
    """An image-derived region saves, reloads and still selects the same pixels.

    The end-to-end case the feature exists for: build a selection from the data,
    store it, and get exactly it back in another session.
    """
    rng = np.random.default_rng(7)
    img = rng.normal(50.0, 6.0, (40, 40))
    img[30, 30] = 900.0

    region = arbitrary_region(img, window=3, neighbourhood=9, intensity_fold_max=2.0)
    path = save_rois([region], str(tmp_path / "sel.json"))
    restored = load_rois(path)[0]

    np.testing.assert_array_equal(restored.to_mask(img.shape), region.to_mask(img.shape))
    assert not restored.to_mask(img.shape)[30, 30]


# --- one loader for every kind ---------------------------------------------
def test_load_regions_reads_each_kind_by_what_the_file_holds(tmp_path):
    """One entry point, and a label image does not arrive as a single blob.

    Dispatching on the extension alone merges a label image into one region,
    silently, because a label image is also a valid mask. Consumers were each
    re-implementing that dispatch — and each getting the same case wrong.
    """
    from chisurf.core.fio.image import imwrite
    from chisurf.core.roi import RectangleROI
    from chisurf.core.roi.io import load_region, load_regions

    labels = np.zeros((12, 12), dtype=np.uint16)
    labels[1:4, 1:4] = 1
    labels[7:10, 7:10] = 2
    label_path = tmp_path / "cells.tif"
    imwrite(str(label_path), labels)

    regions = load_regions(str(label_path))
    assert len(regions) == 2, "a label image is one region per object"
    assert sorted(r.to_mask((12, 12)).sum() for r in regions) == [9, 9]

    # ... and the same file as one gate is their union.
    assert load_region(str(label_path)).to_mask((12, 12)).sum() == 18

    # A binary mask stays a single region.
    mask_path = tmp_path / "cell.tif"
    imwrite(str(mask_path), (labels > 0).astype(np.uint8))
    assert len(load_regions(str(mask_path))) == 1

    # The native format round-trips whatever it holds, shapes included.
    native = save_rois(
        [RectangleROI(0, 0, 3, 3), RectangleROI(5, 5, 8, 8)], str(tmp_path / "two.json")
    )
    assert len(load_regions(native)) == 2
    assert load_region(native).to_mask((12, 12)).sum() == 18


def test_union_of_leaves_a_single_region_alone():
    """The common case must not pay for a composite wrapper."""
    from chisurf.core.roi import RectangleROI, union_of

    one = RectangleROI(0, 0, 2, 2)
    assert union_of([one]) is one

    both = union_of([one, RectangleROI(3, 3, 5, 5)], name="cells")
    assert both.to_mask((6, 6)).sum() == 8
    assert both.name == "cells"

    with pytest.raises(ValueError):
        union_of([])
