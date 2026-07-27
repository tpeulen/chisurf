"""MRC / CCP4 / MAP reading, into a :class:`~chimol.volume.VolumeGrid`.

Two things in this format are easy to miss and wrong in a way that looks like
data rather than like a bug, so both are taken from the reference
implementation's reader (``map_data/mrc/mrc_format.py``) rather than guessed:

**The axes need not be stored in x, y, z order.** ``mapc``/``mapr``/``maps`` say
which spatial axis each of the file's fast, medium and slow axes is. Ignoring
them loads the map transposed — which for anything but a cube is not even the
right shape, and for a cube is a silently rotated map.

**There are two competing origin conventions.** The MRC 2000 header carries
``xorigin``/``yorigin``/``zorigin``, while older files place the map with
``ncstart``/``nrstart``/``nsstart`` in *voxels*. Many new files leave the former
zero while the latter is correct, so the rule is: prefer the xyz origin when it
is non-zero and plausible, otherwise use the start indices. Getting this wrong
puts a cryo-EM map somewhere near the model instead of around it.

This module parses the format itself rather than taking a dependency. ``IMP.em``
also reads MRC and is present in a full ChiSurf install, but ChiMOL runs
standalone and carries no IMP dependency of its own; the format is short and
documented, and one reader means one behaviour to keep correct. The test suite
cross-checks this reader against IMP's wherever IMP is importable, so the choice
costs no confidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import gzip
import struct

import numpy as np

from ..volume import VolumeGrid

#: Byte offsets of the header fields used here (MRC2014 / CCP4 layout).
_OFF_NC, _OFF_NR, _OFF_NS = 0, 4, 8
_OFF_MODE = 12
_OFF_NCSTART, _OFF_NRSTART, _OFF_NSSTART = 16, 20, 24
_OFF_MX, _OFF_MY, _OFF_MZ = 28, 32, 36
_OFF_XLEN, _OFF_YLEN, _OFF_ZLEN = 40, 44, 48
_OFF_MAPC, _OFF_MAPR, _OFF_MAPS = 64, 68, 72
_OFF_NSYMBT = 92
_OFF_XORIGIN, _OFF_YORIGIN, _OFF_ZORIGIN = 196, 200, 204
_OFF_MAP_MAGIC = 208

_HEADER_BYTES = 1024

#: MRC mode -> sample dtype. Modes 3 and 4 hold complex transforms, which are
#: not densities and are refused rather than reinterpreted as one.
_MODE_DTYPES = {
    0: np.int8,
    1: np.int16,
    2: np.float32,
    6: np.uint16,
    12: np.float16,
}


def _read_raw(path: Path) -> bytes:
    """File contents, transparently decompressed when gzipped."""
    raw = Path(path).read_bytes()
    if not raw:
        raise ValueError(f"Empty MRC file: {path}")
    if raw[:2] == b"\x1f\x8b" or str(path).lower().endswith(".gz"):
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    if len(raw) < _HEADER_BYTES:
        raise ValueError(f"MRC file too short to contain a header: {path}")
    return raw


def _byte_order(header: bytes) -> str:
    """``"<"`` or ``">"``, decided by whether the sizes read plausibly.

    The machine stamp is unreliable in the wild, so this uses the test a person
    would: if the grid dimensions come out absurd one way round, it is the other
    way round.
    """
    for order in ("<", ">"):
        nc, nr, ns = struct.unpack_from(order + "3i", header, _OFF_NC)
        mode = struct.unpack_from(order + "i", header, _OFF_MODE)[0]
        if (
            0 < nc < 1 << 20 and 0 < nr < 1 << 20 and 0 < ns < 1 << 20
            and 0 <= mode <= 32
        ):
            return order
    return "<"


def _axis_permutation(
    mapc: int, mapr: int, maps: int
) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """``(crs_to_ijk, ijk_to_crs)`` from the header's axis assignment.

    Falls back to the identity when the three values are not a permutation of
    1, 2, 3 -- some writers leave them zero, and a partial permutation would
    scramble the map rather than merely misplace it.
    """
    if {mapc, mapr, maps} == {1, 2, 3}:
        crs_to_ijk = (mapc - 1, mapr - 1, maps - 1)
        ijk_to_crs = [0, 0, 0]
        for axis in range(3):
            ijk_to_crs[crs_to_ijk[axis]] = axis
        return crs_to_ijk, (ijk_to_crs[0], ijk_to_crs[1], ijk_to_crs[2])
    return (0, 1, 2), (0, 1, 2)


def _data_origin(header, ijk_to_crs, step, data_size, unit_cell, i32, f32):
    """Where index ``(0, 0, 0)`` sits, by the reference reader's preference rule.

    The MRC 2000 xyz origin wins when it is non-zero and finite; otherwise the
    start indices are used, in voxels, mapped through the axis permutation. Many
    modern files leave one of the two at zero while the other is right, which is
    why this is a preference rather than a choice of format version.
    """
    is_mrc2000 = header[_OFF_MAP_MAGIC:_OFF_MAP_MAGIC + 4] == b"MAP "
    xyz_origin = (f32(_OFF_XORIGIN), f32(_OFF_YORIGIN), f32(_OFF_ZORIGIN))
    if (
        is_mrc2000
        and any(value != 0.0 for value in xyz_origin)
        and all(np.isfinite(value) for value in xyz_origin)
    ):
        return xyz_origin

    crs_start = (i32(_OFF_NCSTART), i32(_OFF_NRSTART), i32(_OFF_NSSTART))
    ijk_start = [crs_start[a] for a in ijk_to_crs]
    # Uninitialised start values show up as absurd numbers rather than as zero;
    # placing a map by them would put it far outside the scene.
    limit = 10 * max(max(unit_cell), max(data_size))
    if any(abs(value) > limit for value in ijk_start):
        return (0.0, 0.0, 0.0)
    return tuple(
        float(start) * float(spacing) for start, spacing in zip(ijk_start, step)
    )


def load_mrc_grid(path: Path) -> VolumeGrid:
    """Read an MRC/CCP4/MAP file into a :class:`~chimol.volume.VolumeGrid`.

    Parameters
    ----------
    path : pathlib.Path
        File to read; ``.gz`` is handled.

    Returns
    -------
    VolumeGrid
        The map, with its axes in x, y, z order and placed at its true origin.

    Raises
    ------
    ValueError
        For a truncated file, an unsupported mode, or header dimensions that make
        no sense. All are refused rather than guessed at, because a map drawn in
        the wrong place looks like a result.
    """
    path = Path(path)
    raw = _read_raw(path)
    header = raw[:_HEADER_BYTES]
    order = _byte_order(header)

    def i32(offset: int) -> int:
        return int(struct.unpack_from(order + "i", header, offset)[0])

    def f32(offset: int) -> float:
        return float(struct.unpack_from(order + "f", header, offset)[0])

    nc, nr, ns = i32(_OFF_NC), i32(_OFF_NR), i32(_OFF_NS)
    if nc <= 0 or nr <= 0 or ns <= 0:
        raise ValueError(f"Invalid MRC grid dimensions in {path}: {nc} x {nr} x {ns}")

    mode = i32(_OFF_MODE)
    dtype = _MODE_DTYPES.get(mode)
    if dtype is None:
        raise ValueError(
            f"Unsupported MRC mode {mode} in {path} "
            f"(supported: {sorted(_MODE_DTYPES)})"
        )

    nsymbt = i32(_OFF_NSYMBT)
    if nsymbt < 0 or nsymbt > len(raw) - _HEADER_BYTES:
        nsymbt = 0
    data_offset = _HEADER_BYTES + nsymbt

    n_voxels = nc * nr * ns
    itemsize = np.dtype(dtype).itemsize
    if data_offset + n_voxels * itemsize > len(raw):
        raise ValueError(
            f"MRC file {path} is truncated: expected at least "
            f"{data_offset + n_voxels * itemsize} bytes, got {len(raw)}"
        )

    samples = np.frombuffer(
        raw,
        dtype=np.dtype(dtype).newbyteorder(order),
        count=n_voxels,
        offset=data_offset,
    ).astype(np.float32)
    # Stored slowest axis first, so this is indexed [s, r, c].
    samples = samples.reshape((ns, nr, nc))

    _crs_to_ijk, ijk_to_crs = _axis_permutation(
        i32(_OFF_MAPC), i32(_OFF_MAPR), i32(_OFF_MAPS)
    )
    # Array axis ``2 - q`` holds crs axis ``q``, so spatial axis ``a`` lives on
    # array axis ``2 - ijk_to_crs[a]``.
    values = np.ascontiguousarray(
        samples.transpose(
            2 - ijk_to_crs[0], 2 - ijk_to_crs[1], 2 - ijk_to_crs[2]
        )
    )

    crs_size = (nc, nr, ns)
    data_size = tuple(crs_size[a] for a in ijk_to_crs)

    mx, my, mz = i32(_OFF_MX), i32(_OFF_MY), i32(_OFF_MZ)
    xlen, ylen, zlen = f32(_OFF_XLEN), f32(_OFF_YLEN), f32(_OFF_ZLEN)
    if mx > 0 and my > 0 and mz > 0 and xlen > 0 and ylen > 0 and zlen > 0:
        step = (xlen / mx, ylen / my, zlen / mz)
    else:
        step = (1.0, 1.0, 1.0)

    origin = _data_origin(
        header, ijk_to_crs, step, data_size, (mx, my, mz), i32, f32
    )
    return VolumeGrid.from_array(values, origin=origin, step=step, name=path.stem)


def load_mrc_as_points(path: Path, max_points: int = 250_000) -> Tuple[np.ndarray, dict]:
    """A map as a thinned point cloud above its default contour.

    Kept for callers that predate :class:`~chimol.volume.VolumeGrid`, and now
    derived from it rather than parsing the file a second time -- two parsers of
    one format is two behaviours to keep correct. New code should load the grid
    and contour it, which is what a map object does.

    Returns
    -------
    tuple
        ``(positions, meta)`` -- ``(N, 3)`` float32 world coordinates and a
        summary dict.
    """
    grid = load_mrc_grid(Path(path))
    level = grid.default_level()

    mask = np.isfinite(grid.values) & (grid.values >= level)
    if not mask.any():
        mask = np.isfinite(grid.values)
    i_idx, j_idx, k_idx = np.nonzero(mask)
    if i_idx.size == 0:
        raise ValueError(f"MRC map in {path} has no finite values to show")

    positions = grid.index_to_world(
        np.column_stack((i_idx, j_idx, k_idx)).astype(float)
    ).astype(np.float32, copy=False)

    n_points = positions.shape[0]
    if max_points > 0 and n_points > max_points:
        positions = positions[:: max(1, n_points // max_points)]
        n_points = positions.shape[0]

    finite = grid.values[np.isfinite(grid.values)]
    meta = {
        "shape": tuple(int(n) for n in reversed(grid.shape)),
        "voxel_size": tuple(float(s) for s in grid.step),
        "n_voxels": grid.voxel_count,
        "threshold": float(level),
        "mean": float(finite.mean()) if finite.size else 0.0,
        "std": float(finite.std()) if finite.size else 0.0,
        "n_points": int(n_points),
        "origin": tuple(float(o) for o in grid.origin),
    }
    return positions, meta


__all__ = ["load_mrc_as_points", "load_mrc_grid"]
