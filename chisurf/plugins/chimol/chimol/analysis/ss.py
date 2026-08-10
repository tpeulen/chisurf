"""Secondary-structure (SS) assignment helpers for Chimol.

This module implements a simplified DSSP-style algorithm to assign
C3-type secondary structure codes ("H", "E", "C") from protein
backbone coordinates.

The implementation is inspired by the PyDSSP project
(Shintaro Minami, https://github.com/ShintaroMinami/PyDSSP) and the
original DSSP algorithm by Kabsch & Sander (1983):

    Kabsch, W. & Sander, C. (1983)
    "Dictionary of protein secondary structure: pattern recognition of
    hydrogen-bonded and geometrical features", Biopolymers 22, 25772637.

For Chimol we only need an approximate classification for
visualization, so several aspects are deliberately simplified:

- Only backbone atoms (N, CA, C, O) are used; H positions are modeled
  geometrically.
- Hydrogen bonds are detected using the classic KabschSander
  electrostatic energy formula with a single threshold.
- C3 codes are assigned using simple helix (i,i+4) and strand (long-range
  H-bond) patterns.

This keeps the dependency surface small (NumPy + Biopython only) and
avoids depending on external DSSP binaries or mdtraj.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional

import numpy as np

CONST_Q1Q2 = 0.084
CONST_F = 332.0
DEFAULT_CUTOFF = -0.5
DEFAULT_MARGIN = 1.0

# Cartoon-cleanup thresholds. A raw per-residue H-bond assignment is fine for
# analysis but not for drawing: it leaves one-residue gaps inside a strand and
# isolated single-residue elements, which the cartoon renders as detached
# fragments with no arrowheads. PyMOL's ``dss`` emits contiguous elements, so
# the same tidy-up is applied here before the codes reach the renderer.
# Strands lose single bridges readily, so one missing residue inside a strand is
# noise worth closing. Helices are hydrogen-bond dense: a one-residue break
# between two helical runs is a real kink (PyMOL keeps 93-106 and 108-113 apart
# in 148L), so bridging them would fuse two helices into one long ribbon.
SS_MAX_GAP = {"H": 0, "E": 1}
SS_MIN_LENGTH = {"H": 4, "E": 2}


def _build_backbone_from_atoms(atoms: np.ndarray) -> Optional[np.ndarray]:
    """Return backbone coordinates array of shape (N, 4, 3) or ``None``.

    Axes are: residue index, atom index, xyz. Atom order is (N, CA, C, O).
    Built directly from a ChiSurf-style ``atoms`` structured array.
    Residues missing any of these atoms are skipped.
    """

    if not isinstance(atoms, np.ndarray):
        return None
    fields = set(atoms.dtype.fields or {})
    if "atom_name" not in fields or "xyz" not in fields:
        return None

    names = atoms["atom_name"]
    try:
        text = np.char.strip(names.astype(str))
    except Exception:
        text = np.array([str(n).strip() for n in names])

    xyz = np.asarray(atoms["xyz"], dtype=float)

    if "res_id" in fields:
        res_ids = np.asarray(atoms["res_id"])
    else:
        res_ids = np.arange(len(atoms))

    try:
        chains = atoms["chain"] if "chain" in fields else np.zeros(len(atoms), dtype="U1")
    except Exception:
        chains = np.zeros(len(atoms), dtype="U1")

    res_ids_arr = np.asarray(res_ids)
    chains_arr = np.asarray(chains).astype(str)

    ca_mask = text == "CA"
    if not ca_mask.any():
        return None
    ca_indices = np.nonzero(ca_mask)[0]

    bb_list: list[np.ndarray] = []
    for idx in ca_indices:
        rid = res_ids_arr[idx]
        chain = chains_arr[idx]
        same_res = res_ids_arr == rid
        if "chain" in fields:
            same_res &= chains_arr == chain

        n_idx = np.nonzero(same_res & (text == "N"))[0]
        c_idx = np.nonzero(same_res & (text == "C"))[0]
        o_idx = np.nonzero(same_res & (text == "O"))[0]
        if n_idx.size == 0 or c_idx.size == 0 or o_idx.size == 0:
            continue

        n_coord = xyz[n_idx[0]]
        ca_coord = xyz[idx]
        c_coord = xyz[c_idx[0]]
        o_coord = xyz[o_idx[0]]
        bb = np.stack([n_coord, ca_coord, c_coord, o_coord], axis=0).astype(float)
        bb_list.append(bb)

    if not bb_list:
        return None

    return np.stack(bb_list, axis=0)


def _pydssp_check_input(coord: np.ndarray) -> tuple[np.ndarray, tuple[int, ...]]:
    """Ensure a batch dimension on ``coord`` (adapted from PyDSSP).

    Accepts either ``(L, A, 3)`` or ``(B, L, A, 3)`` and always returns a
    4D array plus the original shape.
    """

    org_shape = coord.shape
    if coord.ndim == 3:
        coord_b = coord[None, ...]
    elif coord.ndim == 4:
        coord_b = coord
    else:
        raise ValueError(
            "Backbone coord must have shape (L, A, 3) or (B, L, A, 3)"
        )
    return coord_b, org_shape


def _pydssp_get_hydrogen_atom_position(coord_b: np.ndarray) -> np.ndarray:
    """Return modeled backbone H positions (PyDSSP geometry).

    Parameters
    ----------
    coord_b:
        Array of shape ``(B, L, A, 3)`` with atoms ordered as ``(N, CA, C, O)
        or (N, CA, C, O, H)``.
    """

    # coord_b[:, 1:, 0] -> N_i   for i = 1..L-1
    # coord_b[:, :-1, 2] -> C_{i-1}
    vec_cn = coord_b[:, 1:, 0] - coord_b[:, :-1, 2]
    vec_cn /= np.linalg.norm(vec_cn, axis=-1, keepdims=True)

    vec_can = coord_b[:, 1:, 0] - coord_b[:, 1:, 1]
    vec_can /= np.linalg.norm(vec_can, axis=-1, keepdims=True)

    vec_nh = vec_cn + vec_can
    vec_nh /= np.linalg.norm(vec_nh, axis=-1, keepdims=True)
    return coord_b[:, 1:, 0] + 1.01 * vec_nh


def _pydssp_get_hbond_map(
    coord: np.ndarray,
    donor_mask: Optional[np.ndarray] = None,
    cutoff: float = DEFAULT_CUTOFF,
    margin: float = DEFAULT_MARGIN,
    return_e: bool = False,
) -> np.ndarray:
    """Compute continuous H-bond map as in PyDSSP (NumPy port).

    Parameters
    ----------
    coord:
        Backbone coordinates of shape ``(L, 4, 3)`` or ``(B, L, 4, 3)`` with
        atom order (N, CA, C, O).
    donor_mask:
        Optional length-``L`` mask (1=can donate, 0=cannot), e.g. for Proline.
    cutoff, margin:
        Same meaning as in PyDSSP: electrostatic cutoff and smoothing margin.
    """

    coord_b, org_shape = _pydssp_check_input(coord)
    b, l, a, _ = coord_b.shape
    if a not in (4, 5):
        raise ValueError("coord must have 4 or 5 backbone atoms (N,CA,C,O[,H])")

    # Add pseudo-H atom positions if not available
    if a == 5:
        h = coord_b[:, 1:, 4]
    else:
        h = _pydssp_get_hydrogen_atom_position(coord_b)

    # Donor (N, H) for residues 1..L-1, acceptor (C,O) for residues 0..L-2
    N = coord_b[:, 1:, 0]  # (B, L-1, 3)
    C = coord_b[:, :-1, 2]  # (B, L-1, 3)
    O = coord_b[:, :-1, 3]  # (B, L-1, 3)

    N_i = N[:, :, None, :]  # (B, L-1, 1, 3)
    H_i = h[:, :, None, :]  # (B, L-1, 1, 3)
    C_j = C[:, None, :, :]  # (B, 1, L-1, 3)
    O_j = O[:, None, :, :]  # (B, 1, L-1, 3)

    def _dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        d = a - b
        return np.linalg.norm(d, axis=-1)

    d_on = _dist(O_j, N_i)
    d_ch = _dist(C_j, H_i)
    d_oh = _dist(O_j, H_i)
    d_cn = _dist(C_j, N_i)

    # Electrostatic interaction energy
    e = CONST_Q1Q2 * CONST_F * (
        1.0 / d_on + 1.0 / d_ch - 1.0 / d_oh - 1.0 / d_cn
    )
    # Pad to full (L, L) as in PyDSSP
    e = np.pad(e, ((0, 0), (1, 0), (0, 1)))  # (B, L, L)

    if return_e:
        return e if coord.ndim == 4 else e[0]

    # Local pair mask (i,i), (i,i+1), (i,i+2)
    local_mask = ~np.eye(l, dtype=bool)
    if l > 1:
        local_mask &= ~np.eye(l, k=-1, dtype=bool)
    if l > 2:
        local_mask &= ~np.eye(l, k=-2, dtype=bool)

    # Donor mask (e.g. Proline); default: all can donate
    if donor_mask is not None:
        dmask = np.asarray(donor_mask, dtype=float).reshape(l)
    else:
        dmask = np.ones(l, dtype=float)
    donor_2d = dmask[:, None] * np.ones((1, l), dtype=float)

    # Continuous H-bond map
    hbond_map = np.clip(cutoff - margin - e, a_min=-margin, a_max=margin)
    hbond_map = (np.sin(hbond_map / margin * (np.pi / 2.0)) + 1.0) / 2.0
    hbond_map *= local_mask[None, :, :]
    hbond_map *= donor_2d[None, :, :]

    return hbond_map if coord.ndim == 4 else hbond_map[0]


def _pydssp_unfold(a: np.ndarray, window: int, axis: int) -> np.ndarray:
    """Sliding-window view along an axis (PyDSSP-style)."""

    # Follow the original PyDSSP numpy implementation closely: respect
    # negative ``axis`` values as-is so that ``axis-1`` in ``moveaxis`` has
    # the same semantics. Normalizing ``axis`` to a positive index changes
    # this behavior and breaks the expected output shape.

    idx = (
        np.arange(window)[:, None]
        + np.arange(a.shape[axis] - window + 1)[None, :]
    )
    unfolded = np.take(a, idx, axis=axis)
    return np.moveaxis(unfolded, axis - 1, -1)


def _pydssp_assign_onehot(
    coord: np.ndarray,
    donor_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Return one-hot C3 labels (loop, helix, strand) as in PyDSSP.

    Parameters
    ----------
    coord:
        Backbone coordinates ``(L, 4, 3)`` or ``(B, L, 4, 3)``.
    donor_mask:
        Optional donor mask of length L.
    """

    coord_b, org_shape = _pydssp_check_input(coord)

    # Hydrogen-bond map: shape (B, L, L)
    hbmap = _pydssp_get_hbond_map(coord_b, donor_mask=donor_mask)
    # Convert into "i:C=O, j:N-H" form
    hbmap = hbmap.transpose(0, 2, 1)

    # Identify turn 3, 4, 5
    turn3 = np.diagonal(hbmap, axis1=-2, axis2=-1, offset=3) > 0.0
    turn4 = np.diagonal(hbmap, axis1=-2, axis2=-1, offset=4) > 0.0
    turn5 = np.diagonal(hbmap, axis1=-2, axis2=-1, offset=5) > 0.0

    # Assignment of helical SS
    h3 = np.pad(turn3[:, :-1] * turn3[:, 1:], ((0, 0), (1, 3)))
    h4 = np.pad(turn4[:, :-1] * turn4[:, 1:], ((0, 0), (1, 4)))
    h5 = np.pad(turn5[:, :-1] * turn5[:, 1:], ((0, 0), (1, 5)))

    helix4 = h4 + np.roll(h4, 1, 1) + np.roll(h4, 2, 1) + np.roll(h4, 3, 1)
    h3 = h3 * ~np.roll(helix4, -1, 1) * ~helix4
    h5 = h5 * ~np.roll(helix4, -1, 1) * ~helix4
    helix3 = h3 + np.roll(h3, 1, 1) + np.roll(h3, 2, 1)
    helix5 = (
        h5
        + np.roll(h5, 1, 1)
        + np.roll(h5, 2, 1)
        + np.roll(h5, 3, 1)
        + np.roll(h5, 4, 1)
    )

    # Identify bridges and ladders
    unfoldmap = _pydssp_unfold(_pydssp_unfold(hbmap, 3, -2), 3, -2) > 0.0
    unfoldmap_rev = np.swapaxes(unfoldmap, 1, 2)

    p_bridge = (
        unfoldmap[:, :, :, 0, 1] * unfoldmap_rev[:, :, :, 1, 2]
        + unfoldmap_rev[:, :, :, 0, 1] * unfoldmap[:, :, :, 1, 2]
    )
    p_bridge = np.pad(p_bridge, ((0, 0), (1, 1), (1, 1)))

    a_bridge = (
        unfoldmap[:, :, :, 1, 1] * unfoldmap_rev[:, :, :, 1, 1]
        + unfoldmap[:, :, :, 0, 2] * unfoldmap_rev[:, :, :, 0, 2]
    )
    a_bridge = np.pad(a_bridge, ((0, 0), (1, 1), (1, 1)))

    ladder = (p_bridge + a_bridge).sum(-1) > 0

    # Final C3 one-hot labels
    helix = (helix3 + helix4 + helix5) > 0
    strand = ladder
    loop = (~helix) & (~strand)

    onehot = np.stack([loop, helix, strand], axis=-1)
    if len(org_shape) == 3:
        onehot = onehot[0]
    return onehot


def _model_hydrogen(n: np.ndarray, ca: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Model backbone H position from N, CA, C.

    Very simple geometry: place H at 1.0  from N in the direction of the
    bisector between N->CA and N->C. This is sufficient for approximate
    hydrogen-bond energy evaluation.
    """

    v1 = ca - n
    v2 = c - n
    v = v1 + v2
    norm = np.linalg.norm(v, axis=-1, keepdims=True)
    # Fallback direction if degenerate
    v[norm[:, 0] == 0.0] = np.array([1.0, 0.0, 0.0])
    norm[norm == 0.0] = 1.0
    v /= norm
    return n + 1.0 * v


def _compute_hbond_energy_matrix(bb: np.ndarray) -> np.ndarray:
    """Compute NxN hydrogen-bond energy matrix using DSSP-like formula.

    Parameters
    ----------
    bb:
        Backbone coordinates of shape (N, 4, 3) with atoms (N, CA, C, O).

    Returns
    -------
    E:
        Array of shape (N, N) with electrostatic energies (kcal/mol). Larger
        negative values indicate stronger hydrogen bonds.
    """

    n = bb[:, 0, :]
    ca = bb[:, 1, :]
    c = bb[:, 2, :]
    o = bb[:, 3, :]

    h = _model_hydrogen(n, ca, c)

    # Broadcast to pairwise distances: i = donor (N-H-C), j = acceptor (C=O)
    N_i = n[:, None, :]
    H_i = h[:, None, :]
    C_j = c[None, :, :]
    O_j = o[None, :, :]

    # Distances
    def _dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        d = a - b
        return np.linalg.norm(d, axis=-1)

    r_ON = _dist(N_i, O_j)
    r_CH = _dist(C_j, H_i)
    r_OH = _dist(O_j, H_i)
    r_CN = _dist(C_j, N_i)

    # Avoid division by zero
    eps = 1e-6
    r_ON = np.maximum(r_ON, eps)
    r_CH = np.maximum(r_CH, eps)
    r_OH = np.maximum(r_OH, eps)
    r_CN = np.maximum(r_CN, eps)

    # Kabsch–Sander electrostatic energy (approximate constants), as in
    # DSSP and PyDSSP: E = q1*q2*F*(1/r_ON + 1/r_CH - 1/r_OH - 1/r_CN)
    E = CONST_Q1Q2 * CONST_F * (
        1.0 / r_ON
        + 1.0 / r_CH
        - 1.0 / r_OH
        - 1.0 / r_CN
    )

    return E



def _energy_to_hbond_map(
    E: np.ndarray,
    cutoff: float = DEFAULT_CUTOFF,
    margin: float = DEFAULT_MARGIN,
) -> np.ndarray:
    """Convert electrostatic energy matrix to continuous H-bond map.

    This mirrors the definition used in PyDSSP:

        Hbond(i,j) = (1 + sin((cutoff - margin - E(i,j))/margin * pi/2)) / 2

    Values lie in [0, 1]. We also mask out local pairs (i,i), (i,i+1),
    (i,i+2) which are not considered backbone hydrogen bonds.
    """

    # Continuous extension of the original DSSP thresholding
    h = np.clip(cutoff - margin - E, a_min=-margin, a_max=margin)
    h = (np.sin(h / margin * (np.pi / 2.0)) + 1.0) / 2.0

    L = E.shape[0]
    local_mask = ~np.eye(L, dtype=bool)
    if L > 1:
        local_mask &= ~np.eye(L, k=-1, dtype=bool)
    if L > 2:
        local_mask &= ~np.eye(L, k=-2, dtype=bool)
    return h * local_mask


def tidy_ss_runs(
    codes: List[str],
    max_gap: Optional[dict] = None,
    min_length: Optional[dict] = None,
) -> List[str]:
    """Make raw per-residue SS codes contiguous enough to draw as a cartoon.

    Two passes, in this order:

    1. **Bridge short gaps** — a run of at most ``max_gap`` coil residues
       flanked by the same SS type on both sides is absorbed into it, so a
       single missing H-bond does not split one strand into two.
    2. **Drop stubs** — any remaining run shorter than ``min_length`` for its
       type becomes coil.

    Without this, a hydrogen-bond assignment of 148L yields seven strand
    fragments (including three single-residue ones) where PyMOL's ``dss``
    yields three strands; the cartoon then shows detached slivers instead of
    arrows, because an arrowhead needs a run long enough to taper.

    Parameters
    ----------
    codes : list of str
        Per-residue C3 codes, each ``"H"``, ``"E"`` or ``"C"``.
    max_gap : dict, optional
        Longest coil run that may be absorbed between two like elements, per SS
        type; defaults to :data:`SS_MAX_GAP`.
    min_length : dict, optional
        Minimum run length per SS type; defaults to :data:`SS_MIN_LENGTH`.

    Returns
    -------
    list of str
        Cleaned per-residue codes, same length as ``codes``.
    """
    if not codes:
        return codes
    limits = SS_MIN_LENGTH if min_length is None else min_length
    gaps = SS_MAX_GAP if max_gap is None else max_gap
    out = list(codes)

    def _runs(seq):
        spans = []
        start = 0
        for i in range(1, len(seq) + 1):
            if i == len(seq) or seq[i] != seq[start]:
                spans.append((seq[start], start, i))
                start = i
        return spans

    spans = _runs(out)
    # Decide every bridge against the original run layout, then apply, so
    # filling one gap cannot renumber the runs still being examined.
    fills = [
        (lo, hi, spans[k - 1][0])
        for k, (kind, lo, hi) in enumerate(spans)
        if kind == "C"
        and 0 < k < len(spans) - 1
        and spans[k - 1][0] == spans[k + 1][0] != "C"
        and hi - lo <= int(gaps.get(spans[k - 1][0], 0))
    ]
    for lo, hi, kind in fills:
        for i in range(lo, hi):
            out[i] = kind

    for kind, lo, hi in _runs(out):
        if kind == "C":
            continue
        if hi - lo < int(limits.get(kind, 1)):
            for i in range(lo, hi):
                out[i] = "C"
    return out


def assign_ss_c3_from_atoms(
    atoms: np.ndarray,
    n_res: int,
    verbose: bool = True,
) -> Optional[List[str]]:
    """Assign C3 codes (H/E/C) from a ChiSurf-style atoms array.

    If ``verbose`` is True (default), prints a short summary of the
    assignment (backbone length, requested length, and H/E/C counts).
    """

    if n_res <= 0:
        return None

    bb = _build_backbone_from_atoms(atoms)
    if bb is None or bb.shape[0] == 0:
        if verbose:
            print("Chimol SS: no valid backbone could be built from atoms")
        return None

    # Use full PyDSSP-style assignment on backbone coordinates to obtain
    # one-hot (loop, helix, strand) labels.
    try:
        onehot = _pydssp_assign_onehot(bb)
    except Exception as e:
        if verbose:
            print(f"Chimol SS: PyDSSP onehot assignment failed: {e!r}")
        return None

    if onehot is None or onehot.size == 0 or onehot.ndim != 2 or onehot.shape[1] != 3:
        if verbose:
            shape = None if onehot is None else onehot.shape
            print(f"Chimol SS: invalid onehot output shape={shape}")
        return None

    helix = np.asarray(onehot[:, 1], dtype=bool)
    strand = np.asarray(onehot[:, 2], dtype=bool)

    n_bb = onehot.shape[0]
    ss_arr = np.full(n_bb, "C", dtype="U1")
    ss_arr[helix] = "H"
    ss_arr[strand & ~helix] = "E"

    ss_codes = tidy_ss_runs(ss_arr.tolist())

    # Align with n_res
    if len(ss_codes) < n_res:
        ss_codes.extend(["C"] * (n_res - len(ss_codes)))
    elif len(ss_codes) > n_res:
        ss_codes = ss_codes[:n_res]

    if verbose:
        n_total = len(ss_codes)
        n_H = sum(c == "H" for c in ss_codes)
        n_E = sum(c == "E" for c in ss_codes)
        n_C = sum(c == "C" for c in ss_codes)
        print(
            "Chimol SS: n_backbone=%d, n_res_requested=%d, "
            "assigned=%d (H=%d, E=%d, C=%d)" % (n_bb, n_res, n_total, n_H, n_E, n_C)
        )

    return ss_codes


def assign_ss_c3_from_file(
    filename: str,
    n_res: int,
    verbose: bool = True,
) -> Optional[List[str]]:
    """Assign C3 secondary-structure codes (H/E/C) from a structure file.

    Thin wrapper that loads a ChiSurf-style atoms array using the
    IMP-based coordinate reader and then delegates to
    :func:`assign_ss_c3_from_atoms`.
    """

    if n_res <= 0:
        return None

    try:  # Lazy import to avoid hard-wiring Chimol to IMP at import time
        from chisurf.core.fio.structure import coordinates as _coords  # type: ignore[import]
    except Exception:
        return None

    try:
        atoms = _coords.read_coordinates(str(filename))
    except Exception as e:
        if verbose:
            print(f"Chimol SS: failed to read coordinates from {filename!r}: {e!r}")
        return None

    if atoms is None or getattr(atoms, "size", 0) == 0:
        if verbose:
            print(f"Chimol SS: empty atoms array from {filename!r}")
        return None

    return assign_ss_c3_from_atoms(atoms, n_res, verbose=verbose)
