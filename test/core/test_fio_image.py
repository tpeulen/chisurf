"""Tests for the one image-I/O seam, :mod:`chisurf.core.fio.image`.

The seam replaced ``tifffile`` and ``imageio``, so what matters is not only that
it round-trips arrays but that it still answers the question those two were
being asked: *which axis is which*. A TIFF is a flat page sequence, and the
whole reason a colocalization or an FRC analysis cares is that six pages might
be six frames or two frames in three colours.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fio import image


def _stack(shape, seed=0):
    """Return a reproducible float32 array of *shape*."""
    return np.random.default_rng(seed).random(shape).astype(np.float32)


@pytest.mark.parametrize(
    "shape, dtype",
    [((8, 9), np.uint8), ((8, 9), np.uint16), ((6, 8, 9), np.float32), ((6, 8, 9), np.float64)],
)
def test_round_trip_preserves_values_and_dtype(tmp_path, shape, dtype):
    arr = (_stack(shape) * 200).astype(dtype)
    path = tmp_path / "plain.tif"
    image.imwrite(path, arr)
    back = image.imread(path)
    assert back.dtype == arr.dtype
    np.testing.assert_array_equal(back, arr)


def test_a_plain_stack_does_not_claim_to_know_what_its_pages_are(tmp_path):
    # "I" is the honest answer for a file with no metadata: it has pages, and it
    # does not say whether they are frames or colours. Reporting "T" here would
    # let a wrong guess travel as if it were read from the file.
    path = tmp_path / "plain.tif"
    image.imwrite(path, _stack((4, 8, 9)))
    assert image.read_labelled(path)[1] == "IYX"


def test_labelled_axes_survive_the_round_trip(tmp_path):
    # The case the seam exists for: frames and channels stay apart.
    arr = _stack((2, 3, 8, 9))
    path = tmp_path / "hyperstack.tif"
    image.imwrite(path, arr, axes="TCYX")
    back, axes = image.read_labelled(path)
    assert axes == "TCYX"
    assert back.shape == (2, 3, 8, 9)
    np.testing.assert_array_equal(back, arr)


def test_voxel_size_survives_the_round_trip(tmp_path):
    path = tmp_path / "volume.tif"
    image.imwrite(
        path, _stack((5, 8, 9)), axes="ZYX",
        resolution=(25.0, 25.0), metadata={"spacing": 0.1, "unit": "um"},
    )
    meta = image.metadata(path)
    assert meta["axes"] == "ZYX"
    assert meta["resolution"] == pytest.approx((25.0, 25.0))
    assert meta["imagej"]["unit"] == "um"
    assert float(meta["imagej"]["spacing"]) == pytest.approx(0.1)


def test_a_png_reads_through_the_same_call(tmp_path):
    # Not every image in a workflow is a TIFF; the caller should not have to
    # know which reader answers.
    from PIL import Image

    path = tmp_path / "mask.png"
    arr = (_stack((8, 9)) * 255).astype(np.uint8)
    Image.fromarray(arr).save(path)
    np.testing.assert_array_equal(image.imread(path), arr)


def test_an_rgb_image_is_labelled_as_samples_not_as_frames(tmp_path):
    # Three planes that are colours must not arrive looking like three frames.
    from PIL import Image

    path = tmp_path / "rgb.png"
    rgb = (_stack((8, 9, 3)) * 255).astype(np.uint8)
    Image.fromarray(rgb, mode="RGB").save(path)
    arr, axes = image.read_labelled(path)
    assert axes == "YXS"
    assert arr.shape == (8, 9, 3)


def test_an_unreadable_file_raises_rather_than_returning_nothing(tmp_path):
    path = tmp_path / "not_an_image.tif"
    path.write_bytes(b"certainly not a TIFF")
    with pytest.raises(OSError):
        image.imread(path)
