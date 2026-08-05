"""The in-tree DCD codec (:mod:`chisurf.core.fio.trajectory.dcd`).

A self-round-trip proves almost nothing about a binary interchange format: a
reader and writer that share a misunderstanding — the wrong endianness, a
missed record marker, the unit-cell fields in the wrong order — agree with each
other perfectly and with nobody else. So the tests that matter here read files
written by a *different* implementation.

``test/data/atomic_coordinates/trajectory/dcd/`` holds those: real DCD files
written by mdtraj (whose reader is VMD's C plugin) from this project's own test
trajectory, with the coordinates mdtraj read back stored alongside as the
oracle. They are committed rather than generated so the parity check outlives
mdtraj itself.
"""

from __future__ import annotations

import pathlib
import tempfile

import numpy as np
import pytest

from chisurf.core.fio.trajectory import dcd_info, read_dcd, write_dcd

DATA = pathlib.Path(__file__).resolve().parents[1] / "data/atomic_coordinates/trajectory/dcd"
REAL = DATA / "hgbp1_transition.dcd"
TRICLINIC = DATA / "triclinic_cell.dcd"


def _sample(n_frames=6, n_atoms=17, seed=0):
    """Return reproducible ``(n_frames, n_atoms, 3)`` coordinates in Ångström."""
    return (np.random.default_rng(seed).random((n_frames, n_atoms, 3)) * 60.0).astype(np.float32)


# ---- parity with an independent implementation -----------------------------

def test_reads_a_dcd_written_by_another_implementation():
    """The coordinates must equal what the writing tool itself read back."""
    expected = np.load(DATA / "hgbp1_transition_expected.npz")["xyz_angstrom"]
    xyz, lengths, angles = read_dcd(REAL)
    assert xyz.shape == expected.shape
    np.testing.assert_allclose(xyz, expected, rtol=0, atol=1e-4)
    assert lengths is None and angles is None      # this trajectory has no cell


def test_our_writer_reproduces_the_foreign_file_byte_for_byte():
    """The strongest parity statement available, and it needs no other library.

    Read the coordinates out of a DCD written by the reference implementation,
    write them back out with ours, and compare the coordinate records as bytes.
    Equality here means the reader and the writer are exact inverses of the
    other implementation's — not merely close to it, which is all a tolerance
    comparison can say.
    """
    expected = np.load(DATA / "hgbp1_transition_expected.npz")["xyz_angstrom"]

    def coordinate_records(raw: bytes, n_atoms: int) -> list[bytes]:
        out, pos = [], 0
        while pos < len(raw):
            n = int(np.frombuffer(raw, dtype="<i4", count=1, offset=pos)[0])
            if n == 4 * n_atoms:
                out.append(raw[pos + 4: pos + 4 + n])
            pos += 4 + n + 4
        return out

    xyz, _, _ = read_dcd(REAL)
    with tempfile.TemporaryDirectory() as tmp:
        mine = pathlib.Path(tmp) / "mine.dcd"
        write_dcd(mine, xyz)
        theirs = coordinate_records(REAL.read_bytes(), 5235)
        ours = coordinate_records(mine.read_bytes(), 5235)
    assert len(ours) == len(theirs) == 3 * 3          # 3 frames x X/Y/Z
    assert ours == theirs
    # ...and the values are the ones the other implementation itself reported.
    np.testing.assert_allclose(xyz, expected, rtol=0, atol=1e-4)


def test_reads_the_header_of_a_foreign_file():
    info = dcd_info(REAL)
    assert (info.n_frames, info.n_atoms) == (3, 5235)
    assert info.charmm and not info.big_endian and not info.has_unitcell


def test_reads_a_triclinic_unit_cell_written_by_another_implementation():
    # The six cell values are stored interleaved as (A, gamma, B, beta, alpha,
    # C) and as cosines. Every part of that is easy to get wrong in a way a
    # self-round-trip would hide, and an orthogonal cell would hide too --
    # hence deliberately unequal lengths and non-90 angles.
    ref = np.load(DATA / "triclinic_cell_expected.npz")
    xyz, lengths, angles = read_dcd(TRICLINIC)
    np.testing.assert_allclose(xyz, ref["xyz_angstrom"], rtol=0, atol=1e-4)
    np.testing.assert_allclose(lengths, ref["cell_lengths"], rtol=0, atol=1e-3)
    np.testing.assert_allclose(angles, ref["cell_angles"], rtol=0, atol=1e-3)


# ---- round trip ------------------------------------------------------------

def test_round_trip_is_bit_exact(tmp_path):
    # float32 in, float32 out, no scaling anywhere: exact, not allclose.
    xyz = _sample()
    path = tmp_path / "t.dcd"
    write_dcd(path, xyz)
    back, lengths, angles = read_dcd(path)
    assert np.array_equal(back, xyz)
    assert lengths is None and angles is None


def test_round_trip_keeps_the_unit_cell(tmp_path):
    xyz = _sample(n_frames=4)
    lengths = np.tile([31.0, 42.0, 53.0], (4, 1))
    angles = np.tile([70.0, 80.0, 110.0], (4, 1))
    path = tmp_path / "cell.dcd"
    write_dcd(path, xyz, cell_lengths=lengths, cell_angles=angles)
    back, got_l, got_a = read_dcd(path)
    assert np.array_equal(back, xyz)
    np.testing.assert_allclose(got_l, lengths, rtol=0, atol=1e-3)
    np.testing.assert_allclose(got_a, angles, rtol=0, atol=1e-3)


def test_an_orthogonal_cell_comes_back_as_exactly_ninety(tmp_path):
    # The cosine encoding exists so that a right angle survives the round trip
    # as 90.0 rather than 89.99997; asserting it loosely would defeat the point.
    path = tmp_path / "ortho.dcd"
    write_dcd(path, _sample(n_frames=2), cell_lengths=np.tile([30.0, 30.0, 30.0], (2, 1)),
              cell_angles=np.tile([90.0, 90.0, 90.0], (2, 1)))
    _, _, angles = read_dcd(path)
    assert np.all(angles == 90.0)


def test_a_cell_stored_in_degrees_is_read_as_degrees(tmp_path):
    """NAMD 2.5 wrote the angles themselves where CHARMM writes their cosines.

    Both are legal and there is no flag: a reader distinguishes them by whether
    all three values fall inside [-1, 1]. Feeding degrees through the cosine
    branch would turn 70 degrees into a value ``arcsin`` cannot take, so this
    is the difference between reading a cell and returning nonsense.
    """
    xyz = _sample(n_frames=2, n_atoms=5)
    path = tmp_path / "degrees.dcd"
    write_dcd(path, xyz, cell_lengths=np.tile([30.0, 40.0, 50.0], (2, 1)),
              cell_angles=np.tile([70.0, 80.0, 110.0], (2, 1)))

    # Rewrite each 48-byte cell record with plain degrees, as NAMD 2.5 would.
    raw, out, pos = path.read_bytes(), bytearray(), 0
    while pos < len(raw):
        n = int(np.frombuffer(raw, dtype="<i4", count=1, offset=pos)[0])
        payload = raw[pos + 4: pos + 4 + n]
        if n == 48:
            payload = np.array([30.0, 110.0, 40.0, 80.0, 70.0, 50.0],
                               dtype="<f8").tobytes()
        out += raw[pos:pos + 4] + payload + raw[pos + 4 + n: pos + 8 + n]
        pos += 4 + n + 4
    path.write_bytes(bytes(out))

    _, lengths, angles = read_dcd(path)
    np.testing.assert_allclose(lengths, np.tile([30.0, 40.0, 50.0], (2, 1)), atol=1e-3)
    np.testing.assert_allclose(angles, np.tile([70.0, 80.0, 110.0], (2, 1)), atol=1e-3)


# ---- byte order and record width -------------------------------------------

def _byteswapped(path_in, path_out, marker_bytes=4):
    """Rewrite a little-endian DCD as big-endian, record by record."""
    raw = pathlib.Path(path_in).read_bytes()
    out, pos = bytearray(), 0
    while pos < len(raw):
        n = int(np.frombuffer(raw, dtype="<i4", count=1, offset=pos)[0])
        payload = raw[pos + 4: pos + 4 + n]
        marker = np.array(n, dtype=">i4").tobytes()
        if len(out) == 0:
            # Header record: 'CORD' then int32s; the magic must not be swapped.
            body = np.frombuffer(payload[4:], dtype="<i4").byteswap().tobytes()
            payload = payload[:4] + body
        elif n == 4 or (n - 4) % 80 == 0:
            count = np.frombuffer(payload, dtype="<i4", count=1).byteswap().tobytes()
            payload = count + payload[4:]
        elif n == 48:
            payload = np.frombuffer(payload, dtype="<f8").byteswap().tobytes()
        else:
            payload = np.frombuffer(payload, dtype="<f4").byteswap().tobytes()
        out += marker + payload + marker
        pos += 4 + n + 4
    pathlib.Path(path_out).write_bytes(bytes(out))


def test_reads_a_big_endian_file(tmp_path):
    # DCD carries no byte-order field; a reader tells them apart by whether the
    # leading record length reads as 84. A file from a big-endian machine must
    # give the same numbers, not mangled ones.
    xyz = _sample(n_frames=3, n_atoms=9)
    little, big = tmp_path / "l.dcd", tmp_path / "b.dcd"
    write_dcd(little, xyz)
    _byteswapped(little, big)
    info = dcd_info(big)
    assert info.big_endian
    got, _, _ = read_dcd(big)
    assert np.array_equal(got, xyz)


# ---- selection -------------------------------------------------------------

def test_stride_and_atom_indices(tmp_path):
    xyz = _sample(n_frames=10, n_atoms=8)
    path = tmp_path / "s.dcd"
    write_dcd(path, xyz)
    strided, _, _ = read_dcd(path, stride=3)
    assert np.array_equal(strided, xyz[::3])
    # Order is respected, not sorted -- a caller asking for [3, 1] gets that.
    picked, _, _ = read_dcd(path, atom_indices=[3, 1])
    assert np.array_equal(picked, xyz[:, [3, 1]])


# ---- refusals --------------------------------------------------------------

def test_a_frame_count_the_header_lies_about_is_taken_from_the_file(tmp_path):
    # Writers that stream frames leave the header count at its initial value,
    # so the file's size is the honest answer.
    xyz = _sample(n_frames=5, n_atoms=6)
    path = tmp_path / "lying.dcd"
    write_dcd(path, xyz)
    raw = bytearray(path.read_bytes())
    raw[8:12] = np.array(0, dtype="<i4").tobytes()      # claim zero frames
    path.write_bytes(bytes(raw))
    assert dcd_info(path).n_frames == 5
    assert read_dcd(path)[0].shape[0] == 5


def test_half_a_unit_cell_is_refused(tmp_path):
    with pytest.raises(ValueError, match="together"):
        write_dcd(tmp_path / "x.dcd", _sample(), cell_lengths=np.ones((6, 3)))


@pytest.mark.parametrize("content", [b"", b"not a dcd file at all", b"\x00" * 200])
def test_a_non_dcd_file_raises(tmp_path, content):
    path = tmp_path / "bad.dcd"
    path.write_bytes(content)
    with pytest.raises(OSError):
        read_dcd(path)


def test_a_truncated_frame_raises_rather_than_returning_short(tmp_path):
    path = tmp_path / "cut.dcd"
    write_dcd(path, _sample(n_frames=4, n_atoms=7))
    raw = path.read_bytes()
    path.write_bytes(raw[: len(raw) - 30])
    # The lost bytes make the last frame incomplete; it must not come back as
    # zeros or silently vanish.
    info = dcd_info(path)
    assert info.n_frames == 3
    xyz, _, _ = read_dcd(path)
    assert xyz.shape[0] == 3


def test_a_bad_shape_is_refused(tmp_path):
    with pytest.raises(ValueError, match=r"n_frames, n_atoms, 3"):
        write_dcd(tmp_path / "x.dcd", np.zeros((4, 3)))


# ---- streaming ---------------------------------------------------------------

def test_streaming_writer_matches_writing_all_at_once(tmp_path):
    """Frames appended in chunks must give the same file as one call.

    This is the path the trajectory tools take for files too large to hold, so
    a difference here would only show up on the largest inputs.
    """
    from chisurf.core.fio.trajectory.dcd import DCDWriter

    xyz = _sample(n_frames=7, n_atoms=11)
    whole, streamed = tmp_path / "whole.dcd", tmp_path / "streamed.dcd"
    write_dcd(whole, xyz)
    with DCDWriter(streamed, n_atoms=11) as writer:
        writer.write(xyz[:3])
        writer.write(xyz[3])            # a single frame, not a block
        writer.write(xyz[4:])
    assert streamed.read_bytes() == whole.read_bytes()
    np.testing.assert_array_equal(read_dcd(streamed)[0], xyz)


def test_the_streaming_writer_patches_the_frame_count(tmp_path):
    # The count is written before the frames exist. Our reader falls back to
    # the file size, but other tools trust the header, so it must be corrected.
    from chisurf.core.fio.trajectory.dcd import DCDWriter

    path = tmp_path / "streamed.dcd"
    with DCDWriter(path, n_atoms=4) as writer:
        writer.write(_sample(n_frames=5, n_atoms=4))
    header = np.frombuffer(path.read_bytes(), dtype="<i4", count=1, offset=8)[0]
    assert int(header) == 5


def test_the_streaming_writer_refuses_a_wrong_atom_count(tmp_path):
    from chisurf.core.fio.trajectory.dcd import DCDWriter

    with DCDWriter(tmp_path / "x.dcd", n_atoms=4) as writer:
        with pytest.raises(ValueError, match="expected"):
            writer.write(_sample(n_frames=2, n_atoms=5))
