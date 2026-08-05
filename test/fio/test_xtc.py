"""The in-tree XTC decoder (:mod:`chisurf.core.fio.trajectory.xtc`).

XTC is bit-packed and lossy, so unlike DCD there is no round-trip to lean on:
the only way to know the decoder is right is to decode files produced by
GROMACS' own implementation and compare against what *it* reads back. Those
files are committed under ``test/data/atomic_coordinates/trajectory/xtc/``,
with the reference coordinates alongside, so the check outlives the library
that generated them.

The bar is bit-exactness, not a tolerance. Both implementations reconstruct
from the same quantised integers, so any difference at all means the bit
stream was walked differently.

The oracle is what the reference implementation **reads back**, not what was
handed to it to write. That distinction is the whole point with a lossy format:
storing the pre-write coordinates as "expected" makes the test fail by
0.0005 nm against a decoder that is perfectly correct, and invites someone to
loosen the tolerance until the real bugs fit through too.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fio.trajectory.xtc import read_xtc, xtc_info

DATA = pathlib.Path(__file__).resolve().parents[1] / "data/atomic_coordinates/trajectory/xtc"
REAL = DATA / "hgbp1_transition.xtc"
TINY = DATA / "tiny_uncompressed.xtc"


def test_decodes_a_gromacs_written_file_bit_exactly():
    expected = np.load(DATA / "hgbp1_transition_expected.npz")
    xyz, box, time, step = read_xtc(REAL)
    assert xyz.shape == expected["xyz_nm"].shape
    # Bit-exact: both decoders rebuild from the same stored integers.
    assert np.array_equal(xyz, expected["xyz_nm"])
    np.testing.assert_allclose(time, expected["time"], rtol=0, atol=1e-6)
    assert box.shape == (xyz.shape[0], 3, 3)


def test_the_uncompressed_branch_is_taken_for_nine_atoms_or_fewer():
    """Below ten atoms XTC skips compression entirely — a real branch.

    It is easy to miss because every ordinary trajectory takes the other path,
    and its frame layout differs: the coordinates sit behind the atom-count
    field that only the compressed branch otherwise reads.
    """
    expected = np.load(DATA / "tiny_uncompressed_expected.npz")["xyz_nm"]
    xyz, _, _, _ = read_xtc(TINY)
    assert xyz.shape == expected.shape
    assert np.array_equal(xyz, expected)


def test_header_is_read_without_decoding():
    info = xtc_info(REAL)
    assert (info.n_frames, info.n_atoms) == (3, 5235)
    assert info.precision == 1000.0


def test_frames_are_counted_by_walking_the_file():
    # XTC frames are variable length and the file carries no count, so the
    # frame total is only knowable by walking. A wrong frame stride shows up
    # here before it shows up as wrong coordinates.
    assert xtc_info(REAL).n_frames == read_xtc(REAL)[0].shape[0] == 3


def test_stride_and_atom_indices():
    xyz, _, _, _ = read_xtc(REAL)
    strided, _, _, _ = read_xtc(REAL, stride=2)
    assert np.array_equal(strided, xyz[::2])
    picked, _, _, _ = read_xtc(REAL, atom_indices=[7, 2, 0])
    assert np.array_equal(picked, xyz[:, [7, 2, 0]])


def test_an_out_of_range_atom_is_refused():
    with pytest.raises(IndexError):
        read_xtc(REAL, atom_indices=[999999])


@pytest.mark.parametrize("content", [b"", b"nope", b"\x00" * 64])
def test_a_non_xtc_file_raises(tmp_path, content):
    path = tmp_path / "bad.xtc"
    path.write_bytes(content)
    with pytest.raises(OSError):
        read_xtc(path)


def test_a_partly_written_final_frame_is_dropped_not_decoded(tmp_path):
    # A trajectory still being written ends mid-frame. Decoding those bytes
    # would produce plausible-looking coordinates from whatever is there, so
    # the walker stops at the last complete frame instead.
    truncated = tmp_path / "cut.xtc"
    raw = REAL.read_bytes()
    truncated.write_bytes(raw[: len(raw) - 200])
    assert xtc_info(truncated).n_frames == 2
    xyz, _, _, _ = read_xtc(truncated)
    assert xyz.shape[0] == 2
    np.testing.assert_array_equal(
        xyz, np.load(DATA / "hgbp1_transition_expected.npz")["xyz_nm"][:2])
