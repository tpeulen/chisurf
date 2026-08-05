"""DCD trajectory files, read and written in-tree.

DCD is the coordinate-trajectory format CHARMM, NAMD and X-PLOR write and that
essentially every MD tool can read, which is why ChiSurf uses it rather than a
container of its own. This module is the reader and writer; there is no
third-party trajectory library behind it.

Ported from the reference C implementation in VMD's molfile plugin
(``dcdplugin.c``, University of Illinois Open Source License, Copyright 2006
Theoretical and Computational Biophysics Group, University of Illinois at
Urbana-Champaign) — a permissive licence, retained here with attribution. The
port is to NumPy rather than a compiled extension: a frame is three contiguous
blocks of ``float32``, so reading one is a ``np.frombuffer``, and no C is
needed to be fast.

Units
-----
**Ångström**, as stored in the file. Nothing is rescaled on the way in or out.
This is deliberate — the MD ecosystem's other convention is nanometres, and a
silent factor of ten in a FRET distance produces results that look plausible.
Callers that want nanometres divide by ten themselves, visibly.

Notes
-----
The layout is a sequence of Fortran unformatted records: a 4-byte length, the
payload, then the same length again. A header record of 84 bytes beginning
``CORD``, a title record, a record holding the atom count, then per frame an
optional 48-byte unit-cell record followed by separate X, Y and Z blocks of
``n_atoms`` floats each.

Three variations are handled because real files use them: 64-bit record markers
(CHARMM ``-i8``), opposite-endian files, and the X-PLOR header variant that
stores the timestep as a double where CHARMM stores a float.
"""

from __future__ import annotations

import dataclasses
import pathlib

import numba as nb
import numpy as np

__all__ = ["DCDHeader", "read_dcd", "write_dcd", "dcd_info"]


@nb.njit(cache=True, parallel=True)
def _gather_frames(flat, frames, atoms, frame_stride, x_offset, gap, out):
    """De-interleave DCD's separate X, Y and Z blocks into ``(frame, atom, 3)``.

    A DCD frame stores all the X values, then all the Y, then all the Z, each
    in its own record. Turning that into the interleaved array everything else
    wants is a gather with a stride, and doing it a frame at a time in Python
    is what the read used to cost -- the decoding itself is free, because the
    payload is already ``float32``.

    Parameters
    ----------
    flat : numpy.ndarray
        The whole post-header payload viewed as ``float32``, record markers
        included. Native byte order.
    frames : numpy.ndarray
        Indices of the frames to gather, in output order.
    atoms : numpy.ndarray
        Indices of the atoms to keep, in output order.
    frame_stride : int
        Distance between frames, in ``float32`` slots.
    x_offset : int
        Slot of the first X value within a frame.
    gap : int
        Slots between the end of one coordinate block and the start of the
        next -- the two record markers that separate them.
    out : numpy.ndarray
        ``(len(frames), len(atoms), 3)`` destination.
    """
    n_atoms_file = (frame_stride - x_offset - 2 * gap) // 3
    for i in nb.prange(frames.shape[0]):
        base = frames[i] * frame_stride + x_offset
        y_base = base + n_atoms_file + gap
        z_base = y_base + n_atoms_file + gap
        for j in range(atoms.shape[0]):
            a = atoms[j]
            out[i, j, 0] = flat[base + a]
            out[i, j, 1] = flat[y_base + a]
            out[i, j, 2] = flat[z_base + a]

#: Header record length, and the magic that follows it.
_HEADER_BYTES = 84
_MAGIC = b"CORD"

#: Bit flags describing which CHARMM extensions a file uses.
_IS_CHARMM = 0x01
_HAS_EXTRA_BLOCK = 0x02
_HAS_4DIMS = 0x04


@dataclasses.dataclass
class DCDHeader:
    """What a DCD file says about itself, before any coordinates are read.

    Attributes
    ----------
    n_frames : int
        Frame count. Taken from the file's own field when it is consistent with
        the file size, and otherwise derived from the size -- writers that
        stream frames often leave the field at its initial value.
    n_atoms : int
        Atoms per frame.
    first_step, step_interval : int
        Step number of the first frame, and steps between saved frames.
    delta : float
        Integration timestep.
    has_unitcell : bool
        Whether each frame carries a unit cell.
    charmm : bool
        CHARMM/NAMD variant rather than X-PLOR.
    big_endian : bool
        Byte order of the file, not of this machine.
    title : list of str
        The 80-character title lines.
    """

    n_frames: int
    n_atoms: int
    first_step: int = 0
    step_interval: int = 1
    delta: float = 1.0
    has_unitcell: bool = False
    charmm: bool = True
    big_endian: bool = False
    title: list[str] = dataclasses.field(default_factory=list)


def _dtypes(big_endian: bool, marker_bytes: int):
    """Return the ``(int32, float32, float64, marker)`` dtypes for a file."""
    prefix = ">" if big_endian else "<"
    marker = np.dtype(f"{prefix}i{marker_bytes}")
    return (np.dtype(prefix + "i4"), np.dtype(prefix + "f4"),
            np.dtype(prefix + "f8"), marker)


def _read_header(handle) -> tuple[DCDHeader, int, int]:
    """Parse the header, returning ``(header, marker_bytes, first_frame_offset)``."""
    raw = handle.read(8)
    if len(raw) < 8:
        raise OSError("not a DCD file: shorter than its own header")

    # The first record length is 84. A 64-bit-marker file spreads that across
    # two ints (84 then 0), while a 32-bit one is 84 immediately followed by
    # the CORD magic -- which is what tells the two apart, and the byte order
    # with them.
    marker_bytes, big_endian = 0, False
    for endian in (False, True):
        first, second = np.frombuffer(raw, dtype=np.dtype((">" if endian else "<") + "u4"))
        if int(first) + int(second) == _HEADER_BYTES:
            marker_bytes, big_endian = 8, endian
            break
        if int(first) == _HEADER_BYTES and raw[4:8] == _MAGIC:
            marker_bytes, big_endian = 4, endian
            break
    if not marker_bytes:
        raise OSError("not a DCD file: no 84-byte header record or CORD magic")

    if marker_bytes == 8:
        if handle.read(4) != _MAGIC:
            raise OSError("not a DCD file: 64-bit record markers without CORD magic")

    i4, f4, f8, marker = _dtypes(big_endian, marker_bytes)
    body = handle.read(80)
    if len(body) < 80:
        raise OSError("truncated DCD header")
    ints = np.frombuffer(body, dtype=i4)

    # A non-zero version at offset 76 means CHARMM, which also decides how the
    # timestep is stored and whether the extra blocks are present.
    charmm = bool(ints[19])
    flags = 0
    if charmm:
        flags |= _IS_CHARMM
        if ints[10]:
            flags |= _HAS_EXTRA_BLOCK
        if ints[11] == 1:
            flags |= _HAS_4DIMS
    if flags & _HAS_4DIMS:
        raise OSError("DCD files with a fourth dimension are not supported")

    n_frames_field = int(ints[0])
    first_step, step_interval = int(ints[1]), int(ints[2])
    n_fixed = int(ints[8])
    if n_fixed:
        # A fixed-atom file stores every atom only in frame 0 and just the free
        # ones afterwards. Reading it as if all frames were complete silently
        # returns the wrong coordinates, so refuse instead.
        raise OSError(f"DCD files with fixed atoms are not supported ({n_fixed} fixed)")

    delta = float(np.frombuffer(body[36:40], dtype=f4)[0] if charmm
                  else np.frombuffer(body[36:44], dtype=f8)[0])

    if int(np.frombuffer(handle.read(marker_bytes), dtype=marker)[0]) != _HEADER_BYTES:
        raise OSError("malformed DCD: header record does not close")

    # Title record: a count followed by that many 80-character lines.
    title_bytes = int(np.frombuffer(handle.read(marker_bytes), dtype=marker)[0])
    n_title = int(np.frombuffer(handle.read(4), dtype=i4)[0])
    if n_title < 0 or n_title * 80 + 4 != title_bytes:
        raise OSError("malformed DCD: inconsistent title block")
    title = [handle.read(80).decode("ascii", "replace").rstrip("\x00 ")
             for _ in range(n_title)]
    handle.read(marker_bytes)

    # Atom-count record.
    if int(np.frombuffer(handle.read(marker_bytes), dtype=marker)[0]) != 4:
        raise OSError("malformed DCD: atom-count record is not 4 bytes")
    n_atoms = int(np.frombuffer(handle.read(4), dtype=i4)[0])
    handle.read(marker_bytes)
    if n_atoms <= 0:
        raise OSError(f"malformed DCD: {n_atoms} atoms")

    header = DCDHeader(
        n_frames=n_frames_field, n_atoms=n_atoms, first_step=first_step,
        step_interval=step_interval, delta=delta,
        has_unitcell=bool(flags & _HAS_EXTRA_BLOCK), charmm=charmm,
        big_endian=big_endian, title=title,
    )
    return header, marker_bytes, handle.tell()


def _frame_bytes(header: DCDHeader, marker_bytes: int) -> int:
    """Return the on-disk size of one frame, markers included."""
    size = 3 * (2 * marker_bytes + 4 * header.n_atoms)
    if header.has_unitcell:
        size += 2 * marker_bytes + 48
    return size


def _angles_from_cell(cell: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split the stored six-value cell into lengths and angles in degrees.

    The stored order is ``(A, gamma, B, beta, alpha, C)`` -- lengths and angles
    interleaved, not three of each. CHARMM and NAMD after 2.5 store the *cosine*
    of each angle, earlier NAMD stores degrees; a value inside ``[-1, 1]`` for
    all three is what distinguishes them, as it does in the reference reader.
    """
    lengths = cell[:, [0, 2, 5]]
    raw = cell[:, [4, 3, 1]]                       # alpha, beta, gamma
    cosine = np.all((raw >= -1.0) & (raw <= 1.0), axis=1)
    angles = np.where(
        cosine[:, None],
        90.0 - np.degrees(np.arcsin(np.clip(raw, -1.0, 1.0))),
        raw,
    )
    return lengths.astype(np.float32), angles.astype(np.float32)


def dcd_info(path) -> DCDHeader:
    """Describe a DCD file without decoding its coordinates.

    Parameters
    ----------
    path : str or os.PathLike
        DCD file to inspect.

    Returns
    -------
    DCDHeader
        With :attr:`DCDHeader.n_frames` reconciled against the file size.
    """
    path = pathlib.Path(path)
    with open(path, "rb") as handle:
        header, marker_bytes, offset = _read_header(handle)
    payload = path.stat().st_size - offset
    per_frame = _frame_bytes(header, marker_bytes)
    actual = payload // per_frame if per_frame else 0
    # The header's frame count is written before the frames are, so a stream
    # that was interrupted -- or simply never rewound -- leaves it at zero. The
    # file's own size is the honest count.
    if actual != header.n_frames:
        header = dataclasses.replace(header, n_frames=int(actual))
    return header


def read_dcd(path, *, stride: int | None = None, atom_indices=None):
    """Read a DCD trajectory.

    Parameters
    ----------
    path : str or os.PathLike
        DCD file to read.
    stride : int, optional
        Keep every *stride*-th frame.
    atom_indices : array_like of int, optional
        Keep only these atoms, in this order.

    Returns
    -------
    xyz : numpy.ndarray
        ``(n_frames, n_atoms, 3)`` float32, in **Ångström**.
    cell_lengths : numpy.ndarray or None
        ``(n_frames, 3)`` float32 in Ångström, or ``None`` when the file has no
        unit cell.
    cell_angles : numpy.ndarray or None
        ``(n_frames, 3)`` float32 in **degrees** (alpha, beta, gamma), or
        ``None``.
    """
    path = pathlib.Path(path)
    with open(path, "rb") as handle:
        header, marker_bytes, offset = _read_header(handle)
        _, f4, f8, _ = _dtypes(header.big_endian, marker_bytes)
        per_frame = _frame_bytes(header, marker_bytes)
        if per_frame % 4:
            raise OSError("malformed DCD: frame size is not a whole number of floats")
        n_frames = (path.stat().st_size - offset) // per_frame

        keep = np.arange(0, int(n_frames), int(stride) if stride else 1, dtype=np.int64)
        atoms = (np.arange(header.n_atoms, dtype=np.int64) if atom_indices is None
                 else np.asarray(atom_indices, dtype=np.int64))
        if atoms.size and (atoms.min() < 0 or atoms.max() >= header.n_atoms):
            raise IndexError(f"atom index out of range for {header.n_atoms} atoms")

        handle.seek(offset)
        payload = handle.read(int(n_frames) * per_frame)

    # One buffer, one pass. Reading frame by frame meant a seek, a read and
    # three strided assignments per frame in Python, which is where the time
    # went -- the bytes themselves are already float32 and need no decoding.
    flat = np.frombuffer(payload, dtype=f4)
    if header.big_endian:
        # numba works in native byte order only, and a big-endian DCD is rare
        # enough that the one extra pass costs nothing worth avoiding.
        flat = flat.byteswap().view(np.float32)
    flat = np.ascontiguousarray(flat, dtype=np.float32)

    slots = marker_bytes // 4                      # markers, in float32 slots
    cell_slots = (2 * slots + 12) if header.has_unitcell else 0
    xyz = np.empty((keep.size, atoms.size, 3), dtype=np.float32)
    _gather_frames(flat, keep, atoms, per_frame // 4,
                   cell_slots + slots, 2 * slots, xyz)

    if not header.has_unitcell:
        return xyz, None, None
    cells = np.empty((keep.size, 6), dtype=np.float64)
    for out, frame in enumerate(keep):
        start = frame * per_frame + marker_bytes
        cells[out] = np.frombuffer(payload, dtype=f8, count=6, offset=int(start))
    lengths, angles = _angles_from_cell(cells)
    return xyz, lengths, angles


def write_dcd(path, xyz, *, cell_lengths=None, cell_angles=None,
              first_step: int = 0, step_interval: int = 1, delta: float = 1.0,
              title: str = "Created by ChiSurf") -> None:
    """Write a DCD trajectory.

    Writes the variant every reader accepts: standard 32-bit record markers,
    native byte order, CHARMM header.

    Parameters
    ----------
    path : str or os.PathLike
        Destination.
    xyz : array_like
        ``(n_frames, n_atoms, 3)`` coordinates in **Ångström**.
    cell_lengths : array_like, optional
        ``(n_frames, 3)`` in Ångström. Requires *cell_angles*.
    cell_angles : array_like, optional
        ``(n_frames, 3)`` in degrees (alpha, beta, gamma). Requires
        *cell_lengths*.
    first_step, step_interval : int, optional
        Step bookkeeping recorded in the header.
    delta : float, optional
        Integration timestep.
    title : str, optional
        First title line; truncated to 80 characters.
    """
    xyz = np.ascontiguousarray(xyz, dtype=np.float32)
    if xyz.ndim != 3 or xyz.shape[2] != 3:
        raise ValueError(f"expected (n_frames, n_atoms, 3), got {xyz.shape}")
    n_frames, n_atoms = xyz.shape[0], xyz.shape[1]

    if (cell_lengths is None) != (cell_angles is None):
        # Half a unit cell is not a unit cell: the file format has one record
        # holding both, and a reader given lengths with no angles would invent
        # 90 degrees.
        raise ValueError("cell_lengths and cell_angles must be given together")
    has_cell = cell_lengths is not None
    if has_cell:
        cell_lengths = np.asarray(cell_lengths, dtype=np.float64).reshape(n_frames, 3)
        cell_angles = np.asarray(cell_angles, dtype=np.float64).reshape(n_frames, 3)

    i4 = np.dtype("<i4")

    def record(payload: bytes) -> bytes:
        length = np.array(len(payload), dtype=i4).tobytes()
        return length + payload + length

    header = np.zeros(20, dtype=i4)
    header[0] = n_frames
    header[1] = first_step
    header[2] = step_interval
    header[10] = 1 if has_cell else 0
    header[19] = 24                                   # CHARMM version 24
    body = bytearray(header.tobytes())
    body[36:40] = np.array(delta, dtype="<f4").tobytes()

    with open(path, "wb") as handle:
        handle.write(record(_MAGIC + bytes(body)))
        lines = [title.encode("ascii", "replace")[:80].ljust(80, b" "),
                 b"REMARKS".ljust(80, b" ")]
        handle.write(record(np.array(len(lines), dtype=i4).tobytes() + b"".join(lines)))
        handle.write(record(np.array(n_atoms, dtype=i4).tobytes()))

        for frame in range(n_frames):
            if has_cell:
                a, b, c = cell_lengths[frame]
                alpha, beta, gamma = cell_angles[frame]
                # Stored interleaved as (A, gamma, B, beta, alpha, C), and as
                # cosines -- the convention CHARMM and modern NAMD use, and the
                # one that lets an orthogonal cell round-trip to exactly 90.
                cell = np.array([a, np.cos(np.radians(gamma)), b,
                                 np.cos(np.radians(beta)),
                                 np.cos(np.radians(alpha)), c], dtype="<f8")
                handle.write(record(cell.tobytes()))
            frame_xyz = xyz[frame]
            for axis in range(3):
                handle.write(record(
                    np.ascontiguousarray(frame_xyz[:, axis], dtype="<f4").tobytes()))
