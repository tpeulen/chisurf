"""Tests for the one image-I/O seam, :mod:`chisurf.core.fio.image`.

The seam replaced ``tifffile`` and ``imageio``, so what matters is not only that
it round-trips arrays but that it still answers the question those two were
being asked: *which axis is which*. A TIFF is a flat page sequence, and the
whole reason a colocalization or an FRC analysis cares is that six pages might
be six frames or two frames in three colours.

The other thing worth pinning is what the seam refuses. Measurement images are
TIFF; the consumer formats hold 8-bit colour and would silently discard a
16-bit count or a float lifetime map.
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


@pytest.mark.parametrize("name", ["mask.png", "frame.jpg", "scan.bmp", "movie.gif"])
def test_the_consumer_formats_are_refused_in_both_directions(tmp_path, name):
    # A measurement image is a TIFF. The consumer formats store 8-bit colour, so
    # writing a uint16 photon count or a float lifetime map into one throws the
    # measurement away -- quietly, which is why this refuses instead of
    # converting. Reading is refused for the same reason: a PNG in this position
    # means the data was already flattened somewhere upstream.
    path = tmp_path / name
    with pytest.raises(ValueError, match="TIFF only"):
        image.imwrite(path, _stack((8, 9)))
    with pytest.raises(ValueError, match="TIFF only"):
        image.imread(path)


def test_an_unreadable_file_raises_rather_than_returning_nothing(tmp_path):
    path = tmp_path / "not_an_image.tif"
    path.write_bytes(b"certainly not a TIFF")
    with pytest.raises(OSError):
        image.imread(path)
