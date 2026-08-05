"""XTC trajectory files, read and written in-tree.

XTC is GROMACS' compressed coordinate format: coordinates are quantised to a
stated precision, packed as small integers relative to a per-frame bounding
box, and bit-packed with a run-length trick that exploits how water molecules
cluster. It is lossy by construction — the precision is in the file — and
roughly three times smaller than the equivalent DCD.

Ported from GROMACS' ``xdrfile`` (``xdrfile.c``, ``xdrfile_xtc.c``), BSD
2-clause, Copyright (c) 2009-2014 Erik Lindahl, David van der Spoel and
Robert T. McGibbon — a permissive licence, retained here with attribution.
The bit-level routines are ``numba`` kernels: unlike DCD, whose payload is
already ``float32``, every coordinate here has to be unpacked bit by bit, so
this is a genuine decode loop rather than a reshape.

Units
-----
**Nanometres**, as stored — XTC's own unit, and the one place in ChiSurf's
trajectory I/O that is not Ångström, because rescaling on the way through would
hide the quantisation. :func:`read_xtc` returns what the file holds;
multiply by 10 to match :mod:`~chisurf.core.fio.trajectory.dcd`.

Reading only, deliberately. ChiSurf writes trajectories as DCD, which is
lossless; XTC is here to read what other tools produce, and an encoder would
have to reproduce the quantisation ladder exactly to be worth having. See
PRD-80.

Notes
-----
Everything is XDR, i.e. big-endian, with opaque byte blocks padded to a
four-byte boundary. A frame is: magic ``1995``, atom count, step, time, nine
box floats, then the compressed block. Fewer than ten atoms are stored
uncompressed, which is a real branch in the format and not a corner case.
"""

from __future__ import annotations

import dataclasses
import pathlib

import numba as nb
import numpy as np

__all__ = ["XTCHeader", "read_xtc", "xtc_info"]

_MAGIC = 1995

#: The quantisation ladder. ``smallidx`` indexes it, and the encoder walks up
#: and down as the local density of atoms changes.
MAGICINTS = np.array([
    0, 0, 0, 0, 0, 0, 0, 0, 0, 8, 10, 12, 16, 20, 25, 32, 40, 50, 64,
    80, 101, 128, 161, 203, 256, 322, 406, 512, 645, 812, 1024, 1290,
    1625, 2048, 2580, 3250, 4096, 5060, 6501, 8192, 10321, 13003,
    16384, 20642, 26007, 32768, 41285, 52015, 65536, 82570, 104031,
    131072, 165140, 208063, 262144, 330280, 416127, 524287, 660561,
    832255, 1048576, 1321122, 1664510, 2097152, 2642245, 3329021,
    4194304, 5284491, 6658042, 8388607, 10568983, 13316085, 16777216,
], dtype=np.int64)
_FIRSTIDX = 9
_LASTIDX = len(MAGICINTS)


@dataclasses.dataclass
class XTCHeader:
    """What an XTC file says about itself.

    Attributes
    ----------
    n_frames : int
        Frames found by walking the file. XTC frames are variable length —
        the compressed block's size depends on the coordinates — so there is
        no count in the file and no way to seek to frame *k* without scanning.
    n_atoms : int
        Atoms per frame.
    precision : float
        Quantisation of the first frame: coordinates are stored to
        ``1 / precision`` nm.
    """

    n_frames: int
    n_atoms: int
    precision: float = 1000.0


# --- bit-level primitives, ported from xdrfile.c -----------------------------
# The decoder state is (byte cursor, bits still held, the partial byte), kept
# in a small array so the kernels can share and advance it.

@nb.njit(cache=True, inline="always")
def _decodebits(buf, state, n_bits):
    """Pull *n_bits* from *buf*, MSB first, advancing *state*."""
    cnt = state[0]
    lastbits = state[1]
    lastbyte = state[2]
    mask = (np.int64(1) << np.int64(n_bits)) - 1
    num = np.int64(0)
    bits = n_bits
    while bits >= 8:
        # lastbyte is a 32-bit unsigned in the reference; the shift there
        # discards the high bits, and masking reproduces that exactly. Letting
        # it grow in 64-bit would change the value the shift below reads.
        lastbyte = ((lastbyte << 8) | buf[cnt]) & 0xFFFFFFFF
        cnt += 1
        num |= (lastbyte >> lastbits) << (bits - 8)
        bits -= 8
    if bits > 0:
        if lastbits < bits:
            lastbits += 8
            lastbyte = ((lastbyte << 8) | buf[cnt]) & 0xFFFFFFFF
            cnt += 1
        lastbits -= bits
        num |= (lastbyte >> lastbits) & ((np.int64(1) << np.int64(bits)) - 1)
    num &= mask
    state[0] = cnt
    state[1] = lastbits
    state[2] = lastbyte
    return num


@nb.njit(cache=True, inline="always")
def _decodeints(buf, state, n_bits, sizes, out, scratch):
    """Unpack three small integers that were multiplied into one big one."""
    for i in range(4):
        scratch[i] = 0
    n_bytes = 0
    bits = n_bits
    while bits > 8:
        scratch[n_bytes] = _decodebits(buf, state, 8)
        n_bytes += 1
        bits -= 8
    if bits > 0:
        scratch[n_bytes] = _decodebits(buf, state, bits)
        n_bytes += 1
    for i in range(2, 0, -1):
        num = np.int64(0)
        for j in range(n_bytes - 1, -1, -1):
            num = (num << 8) | scratch[j]
            p = num // sizes[i]
            scratch[j] = p
            num -= p * sizes[i]
        out[i] = num
    out[0] = (scratch[0] | (scratch[1] << 8)
              | (scratch[2] << 16) | (scratch[3] << 24))


@nb.njit(cache=True)
def _sizeofint(size):
    """Smallest number of bits that can hold *size*."""
    num = np.int64(1)
    n_bits = 0
    while size >= num and n_bits < 32:
        n_bits += 1
        num <<= 1
    return n_bits


@nb.njit(cache=True)
def _sizeofints(sizes, scratch):
    """Bits needed for three integers multiplied into one."""
    n_bytes = 1
    scratch[0] = 1
    n_bits = 0
    for i in range(3):
        tmp = np.int64(0)
        bytecnt = 0
        while bytecnt < n_bytes:
            tmp = scratch[bytecnt] * sizes[i] + tmp
            scratch[bytecnt] = tmp & 0xFF
            tmp >>= 8
            bytecnt += 1
        while tmp != 0:
            scratch[bytecnt] = tmp & 0xFF
            tmp >>= 8
            bytecnt += 1
        n_bytes = bytecnt
    num = np.int64(1)
    n_bytes -= 1
    while scratch[n_bytes] >= num:
        n_bits += 1
        num *= 2
    return n_bits + n_bytes * 8


@nb.njit(cache=True)
def _decompress(buf, n_atoms, minint, maxint, smallidx, precision, out, magicints):
    """Decode one compressed frame into ``out`` (``(n_atoms, 3)`` float32).

    A faithful port of ``xdrfile_decompress_coord_float``. The run-length
    branch is the part worth understanding: after each explicitly coded atom
    the stream may say "the next *run*/3 atoms are within a small box of this
    one", which is how a water molecule's hydrogens cost a handful of bits. The
    first atom of such a run is *swapped* with the one before it, which is not
    an optimisation detail but part of the format — decode it in the wrong
    order and the oxygens and hydrogens change places.
    """
    sizeint = np.empty(3, dtype=np.int64)
    bitsizeint = np.zeros(3, dtype=np.int64)
    sizesmall = np.empty(3, dtype=np.int64)
    thiscoord = np.zeros(3, dtype=np.int64)
    prevcoord = np.zeros(3, dtype=np.int64)
    scratch = np.zeros(32, dtype=np.int64)
    state = np.zeros(3, dtype=np.int64)

    for i in range(3):
        sizeint[i] = maxint[i] - minint[i] + 1

    if (sizeint[0] | sizeint[1] | sizeint[2]) > 0xFFFFFF:
        # Too large to multiply together: each axis gets its own field.
        for i in range(3):
            bitsizeint[i] = _sizeofint(sizeint[i])
        bitsize = 0
    else:
        bitsize = _sizeofints(sizeint, scratch)

    # The reference derives maxidx, minidx and `larger` here; all three are
    # read only by the encoder, so they are left out rather than computed and
    # ignored.
    tmp = smallidx - 1
    tmp = _FIRSTIDX if _FIRSTIDX > tmp else tmp
    smaller = magicints[tmp] // 2
    smallnum = magicints[smallidx] // 2
    for i in range(3):
        sizesmall[i] = magicints[smallidx]

    inv_precision = np.float32(1.0) / np.float32(precision)
    run = 0
    i = 0
    written = 0
    while i < n_atoms:
        if bitsize == 0:
            thiscoord[0] = _decodebits(buf, state, bitsizeint[0])
            thiscoord[1] = _decodebits(buf, state, bitsizeint[1])
            thiscoord[2] = _decodebits(buf, state, bitsizeint[2])
        else:
            _decodeints(buf, state, bitsize, sizeint, thiscoord, scratch)
        i += 1
        for k in range(3):
            thiscoord[k] += minint[k]
            prevcoord[k] = thiscoord[k]

        flag = _decodebits(buf, state, 1)
        is_smaller = 0
        if flag == 1:
            run = _decodebits(buf, state, 5)
            is_smaller = run % 3
            run -= is_smaller
            is_smaller -= 1
        # `run` deliberately persists when the flag bit is 0: a second water
        # molecule of the same length costs that single bit and reuses the
        # previous run. Resetting it here decodes the first molecule and then
        # walks off the stream -- which is exactly what it did.

        if run > 0:
            for k in range(0, run, 3):
                _decodeints(buf, state, smallidx, sizesmall, thiscoord, scratch)
                i += 1
                for m in range(3):
                    thiscoord[m] += prevcoord[m] - smallnum
                if k == 0:
                    # Swap this atom with the previous one: water compresses
                    # better when the heavy atom is coded second.
                    for m in range(3):
                        swap = thiscoord[m]
                        thiscoord[m] = prevcoord[m]
                        prevcoord[m] = swap
                    for m in range(3):
                        out[written, m] = prevcoord[m] * inv_precision
                    written += 1
                else:
                    for m in range(3):
                        prevcoord[m] = thiscoord[m]
                for m in range(3):
                    out[written, m] = thiscoord[m] * inv_precision
                written += 1
        else:
            for m in range(3):
                out[written, m] = thiscoord[m] * inv_precision
            written += 1

        smallidx += is_smaller
        if is_smaller < 0:
            smallnum = smaller
            smaller = magicints[smallidx - 1] // 2 if smallidx > _FIRSTIDX else 0
        elif is_smaller > 0:
            smaller = smallnum
            smallnum = magicints[smallidx] // 2
        for m in range(3):
            sizesmall[m] = magicints[smallidx]
        if sizesmall[0] == 0:
            return -1
    return written


@nb.njit(cache=True, parallel=True)
def _decompress_many(buf, starts, n_atoms, minints, maxints, smallidxs,
                     precisions, out, magicints, status):
    """Decode every frame, one per thread.

    Each frame is its own self-contained compressed block -- the bit stream
    never runs across a frame boundary -- so although unpacking one is strictly
    serial, the frames are embarrassingly parallel. That is the whole reason
    this beats the reference C, which decodes them one after another.
    """
    for f in nb.prange(starts.shape[0]):
        status[f] = _decompress(
            buf[starts[f]:], n_atoms, minints[f], maxints[f],
            smallidxs[f], precisions[f], out[f], magicints)


# --- file walking ------------------------------------------------------------

_I4 = np.dtype(">i4")
_F4 = np.dtype(">f4")


def _frame_offsets(raw: bytes) -> tuple[list[int], int, float]:
    """Walk the file, returning ``(offsets, n_atoms, precision)``.

    XTC frames are variable length, so the only way to address frame *k* is to
    walk from the start. There is no index in the file.
    """
    offsets, pos, n_atoms, precision = [], 0, None, 1000.0
    total = len(raw)
    while pos + 16 <= total:
        magic, natoms, _step = np.frombuffer(raw, dtype=_I4, count=3, offset=pos)
        if int(magic) != _MAGIC:
            raise OSError(f"not an XTC file: expected magic {_MAGIC} at byte {pos}")
        natoms = int(natoms)
        if n_atoms is None:
            n_atoms = natoms
        elif natoms != n_atoms:
            raise OSError(f"XTC frame at byte {pos} has {natoms} atoms, not {n_atoms}")
        offsets.append(pos)
        body = pos + 16 + 36                       # header + 9 box floats
        if natoms <= 9:
            # Uncompressed, but still behind the atom-count field the
            # compressed branch reads first.
            pos = body + 4 + 4 * 3 * natoms
            continue
        # lsize, precision, minint[3], maxint[3], smallidx, nbytes
        if not offsets[:-1]:
            precision = float(np.frombuffer(raw, dtype=_F4, count=1, offset=body + 4)[0])
        n_bytes = int(np.frombuffer(raw, dtype=_I4, count=1, offset=body + 36)[0])
        pos = body + 40 + ((n_bytes + 3) // 4) * 4   # opaque data is padded
        if pos > total:
            # A partly written frame: stop at the last complete one rather
            # than decoding whatever bytes happen to follow.
            offsets.pop()
            break
    if n_atoms is None:
        raise OSError("not an XTC file: no complete frame")
    return offsets, n_atoms, precision


def xtc_info(path) -> XTCHeader:
    """Describe an XTC file without decoding its coordinates.

    Parameters
    ----------
    path : str or os.PathLike
        XTC file to inspect.

    Returns
    -------
    XTCHeader
    """
    raw = pathlib.Path(path).read_bytes()
    offsets, n_atoms, precision = _frame_offsets(raw)
    return XTCHeader(n_frames=len(offsets), n_atoms=n_atoms, precision=precision)


def read_xtc(path, *, stride: int | None = None, atom_indices=None):
    """Read an XTC trajectory.

    Parameters
    ----------
    path : str or os.PathLike
        XTC file to read.
    stride : int, optional
        Keep every *stride*-th frame. The file still has to be walked in full —
        XTC has no index — but only the kept frames are decoded.
    atom_indices : array_like of int, optional
        Keep only these atoms, in this order. Applied after decoding, since a
        frame is one compressed block.

    Returns
    -------
    xyz : numpy.ndarray
        ``(n_frames, n_atoms, 3)`` float32, in **nanometres**.
    box : numpy.ndarray
        ``(n_frames, 3, 3)`` float32 box vectors, in nanometres.
    time : numpy.ndarray
        ``(n_frames,)`` float32 simulation time.
    step : numpy.ndarray
        ``(n_frames,)`` int32 step numbers.
    """
    raw = pathlib.Path(path).read_bytes()
    offsets, n_atoms, _ = _frame_offsets(raw)
    keep = offsets[:: int(stride)] if stride else offsets
    indices = None if atom_indices is None else np.asarray(atom_indices, dtype=np.intp)
    if indices is not None and indices.size and (
            indices.min() < 0 or indices.max() >= n_atoms):
        raise IndexError(f"atom index out of range for {n_atoms} atoms")

    n_frames = len(keep)
    box = np.empty((n_frames, 3, 3), dtype=np.float32)
    time = np.empty(n_frames, dtype=np.float32)
    step = np.empty(n_frames, dtype=np.int32)
    decoded = np.empty((n_frames, n_atoms, 3), dtype=np.float32)
    buffer = np.frombuffer(raw, dtype=np.uint8)

    # Gather the per-frame parameters first, then decode them all in one
    # parallel pass -- the loop here must stay cheap, since it is the only
    # serial part left.
    starts = np.empty(n_frames, dtype=np.int64)
    minints = np.empty((n_frames, 3), dtype=np.int64)
    maxints = np.empty((n_frames, 3), dtype=np.int64)
    smallidxs = np.empty(n_frames, dtype=np.int64)
    precisions = np.empty(n_frames, dtype=np.float32)

    # Every frame in a file has the same atom count, so the uncompressed
    # branch is all-or-nothing rather than per frame.
    uncompressed = n_atoms <= 9

    for out, pos in enumerate(keep):
        step[out] = int(np.frombuffer(raw, dtype=_I4, count=1, offset=pos + 8)[0])
        time[out] = float(np.frombuffer(raw, dtype=_F4, count=1, offset=pos + 12)[0])
        box[out] = np.frombuffer(raw, dtype=_F4, count=9, offset=pos + 16).reshape(3, 3)
        body = pos + 52
        if uncompressed:
            decoded[out] = np.frombuffer(
                raw, dtype=_F4, count=3 * n_atoms, offset=body + 4).reshape(n_atoms, 3)
            continue
        precisions[out] = np.frombuffer(raw, dtype=_F4, count=1, offset=body + 4)[0]
        bounds = np.frombuffer(raw, dtype=_I4, count=6, offset=body + 8)
        minints[out] = bounds[:3]
        maxints[out] = bounds[3:]
        smallidxs[out] = int(np.frombuffer(raw, dtype=_I4, count=1, offset=body + 32)[0])
        starts[out] = body + 40

    if not uncompressed and n_frames:
        status = np.zeros(n_frames, dtype=np.int64)
        _decompress_many(buffer, starts, n_atoms, minints, maxints,
                         smallidxs, precisions, decoded, MAGICINTS, status)
        bad = np.nonzero(status != n_atoms)[0]
        if bad.size:
            raise OSError(f"corrupt XTC: frame {int(bad[0])} decoded "
                          f"{int(status[bad[0]])} of {n_atoms} atoms")

    xyz = decoded if indices is None else decoded[:, indices]
    return xyz, box, time, step
