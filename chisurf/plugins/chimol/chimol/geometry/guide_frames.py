"""Per-residue guide frames for the cartoon, following PyMOL's pipeline.

chimol used to derive the ribbon's tangents from the *sampled spline*, which
works but leaves no place to put the two conditioning steps PyMOL applies **per
residue** before any sampling happens — and those are on by default and visible:
``cartoon_refine_tips`` (10) aims the arrowhead at each strand end, and
``cartoon_refine_normals`` keeps the ribbon's face from flipping between
neighbours. Patching them onto a spline-derived frame is not possible; the frame
has to exist per residue first.

This module is that stage, transcribed from ``layer2/RepCartoon.cpp``:

===========================================  =====================================
PyMOL                                        here
===========================================  =====================================
``RepCartoonComputeDifferencesAndNormals``   :func:`differences_and_normals`
``RepCartoonComputeTangents``                :func:`tangents_from_normals`
``RepCartoonRefineNormals``                  :func:`refine_normals`
``RepCartoonFlattenSheetsRefineTips``        :func:`refine_sheet_tips`
===========================================  =====================================

and run in PyMOL's order by :func:`build_guide_frames`. Everything is vectorised
over residues where the recurrence allows and looped where it does not, because
several of these passes are genuinely sequential — the flip-consistency sweep
reads the neighbour it just wrote.

The distinction between ``nv`` and ``tv`` is easy to lose and matters: ``nv[a]``
is the unit vector from residue ``a`` to ``a+1`` (a *segment* direction, so there
are ``n-1`` meaningful ones), while ``tv[a]`` is the tangent *at* residue ``a``,
the normalised sum of the two segment directions meeting there.
"""

from __future__ import annotations

from dataclasses import dataclass

import math

import numpy as np

__all__ = [
    "GuideFrames",
    "build_guide_frames",
    "differences_and_normals",
    "tangents_from_normals",
    "refine_normals",
    "refine_sheet_tips",
]

#: PyMOL's ``R_SMALL4``, below which a step is treated as degenerate.
_R_SMALL4 = 0.0001

#: ``RepCartoonRefineNormals`` softens a kink when the product of the dot
#: products with both neighbours falls below this ("could be a setting").
_KINK_THRESHOLD = -0.10


@dataclass
class GuideFrames:
    """The per-residue frame the cartoon is extruded along.

    Attributes
    ----------
    positions : numpy.ndarray
        ``(n, 3)`` guide positions, after any flattening.
    normals : numpy.ndarray
        ``(n, 3)`` segment directions; ``normals[a]`` points from residue ``a``
        to ``a+1``, and the last entry is zero.
    tangents : numpy.ndarray
        ``(n, 3)`` tangent at each residue.
    orientations : numpy.ndarray
        ``(n, 3)`` ribbon up-vectors, orthogonal to the tangent.
    lengths : numpy.ndarray
        ``(n,)`` distance from residue ``a`` to ``a+1``; last entry is zero.
    """

    positions: np.ndarray
    normals: np.ndarray
    tangents: np.ndarray
    orientations: np.ndarray
    lengths: np.ndarray


def _unit(vectors: np.ndarray) -> np.ndarray:
    """Row-wise unit vectors, leaving degenerate rows untouched."""
    out = np.array(vectors, dtype=float)
    lengths = np.linalg.norm(out, axis=1, keepdims=True)
    np.divide(out, lengths, out=out, where=lengths > 1e-12)
    return out


def _remove_component(vectors: np.ndarray, axis: np.ndarray) -> np.ndarray:
    """PyMOL's ``remove_component3f``: strip the part along ``axis``."""
    along = np.einsum("ij,ij->i", vectors, axis)
    return vectors - along[:, None] * axis


def differences_and_normals(
    positions: np.ndarray, segments: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Step differences, unit directions and lengths between residues.

    ``RepCartoonComputeDifferencesAndNormals``. Entries that would cross a
    segment boundary are zeroed, and a degenerate step copies the previous
    direction rather than producing a zero vector mid-chain.

    Parameters
    ----------
    positions : numpy.ndarray
        ``(n, 3)`` guide positions.
    segments : numpy.ndarray
        ``(n,)`` segment id per residue; a change marks a chain break.

    Returns
    -------
    tuple
        ``(differences, normals, lengths)``, each of length ``n`` with the final
        entry zero.
    """
    n = positions.shape[0]
    differences = np.zeros((n, 3), dtype=float)
    normals = np.zeros((n, 3), dtype=float)
    lengths = np.zeros(n, dtype=float)
    if n < 2:
        return differences, normals, lengths

    same = segments[:-1] == segments[1:]
    step = positions[1:] - positions[:-1]
    differences[:-1][same] = step[same]
    lengths[:-1][same] = np.linalg.norm(step[same], axis=1)

    # Three cases per step: a well-defined direction, a degenerate one that
    # copies its predecessor, and a segment break that stays zero. Only the
    # middle one depends on the step before it -- and copying a predecessor that
    # itself copied is a *forward fill*, which is a running maximum over the
    # indices that were not copies.
    m = n - 1
    span = lengths[:m]
    assigned = same & (span > _R_SMALL4)
    copied = same & ~assigned
    copied[0] = False  # nothing before the first step to copy

    base = np.zeros((m, 3), dtype=float)
    if np.any(assigned):
        base[assigned] = differences[:m][assigned] / span[assigned][:, None]
    source = np.maximum.accumulate(np.where(~copied, np.arange(m), -1))
    normals[:m] = base[source]
    return differences, normals, lengths


def tangents_from_normals(
    normals: np.ndarray, segments: np.ndarray
) -> np.ndarray:
    """Tangent at each residue from the segment directions around it.

    ``RepCartoonComputeTangents``: inside a segment the tangent is the
    normalised **head-to-tail sum** of the two directions meeting at the
    residue; at a segment's first or last residue it is simply the one direction
    that exists.

    Parameters
    ----------
    normals : numpy.ndarray
        ``(n, 3)`` segment directions from :func:`differences_and_normals`.
    segments : numpy.ndarray
        ``(n,)`` segment id per residue.

    Returns
    -------
    numpy.ndarray
        ``(n, 3)`` tangents.
    """
    n = normals.shape[0]
    tangents = np.zeros((n, 3), dtype=float)
    if n == 0:
        return tangents
    tangents[0] = normals[0]
    if n > 1:
        tangents[-1] = normals[-2]

    if n > 2:
        # No dependence between residues here, so the whole interior at once.
        before = segments[1:-1] == segments[:-2]
        after = segments[1:-1] == segments[2:]
        inside = normals[1:-1]
        preceding = normals[:-2]
        tangents[1:-1] = np.where(
            (before & after)[:, None],
            inside + preceding,
            np.where(
                before[:, None],
                preceding,
                np.where(after[:, None], inside, 0.0),
            ),
        )
    return _unit(tangents)


def refine_normals(
    orientations: np.ndarray,
    tangents: np.ndarray,
    normals: np.ndarray,
    segments: np.ndarray,
    is_helix: np.ndarray,
) -> np.ndarray:
    """Make the ribbon's face consistent between neighbours.

    ``RepCartoonRefineNormals`` (``cartoon_refine_normals``, on for single-state
    objects). Four passes, in order:

    1. orthogonalise each interior orientation against its tangent;
    2. offer two candidates per residue, the vector and its inverse — **except
       in a helix**, where inverting would confuse inside and outside;
    3. sweep forward choosing, at each residue, whichever candidate agrees best
       with the neighbour already decided, both projected perpendicular to the
       chain direction. This is what stops the ribbon flipping face between
       consecutive residues;
    4. soften kinks: where a residue disagrees with *both* neighbours
       (``dot(v, v_next) * dot(v, v_prev) < -0.1``), blend it toward their sum,
       by an amount that grows with how sharp the kink is.

    Parameters
    ----------
    orientations : numpy.ndarray
        ``(n, 3)`` ribbon up-vectors; not modified in place.
    tangents, normals : numpy.ndarray
        ``(n, 3)`` from the two functions above.
    segments : numpy.ndarray
        ``(n,)`` segment id per residue.
    is_helix : numpy.ndarray
        ``(n,)`` boolean; helical residues are not offered the inverted
        candidate.

    Returns
    -------
    numpy.ndarray
        ``(n, 3)`` refined orientations.
    """
    n = orientations.shape[0]
    out = _unit(np.array(orientations, dtype=float))
    if n < 3:
        return out

    interior = np.zeros(n, dtype=bool)
    interior[1:-1] = (segments[1:-1] == segments[:-2]) & (
        segments[1:-1] == segments[2:]
    )
    if not interior.any():
        return out

    # 1. perpendicular to the tangent
    out[interior] = _unit(
        _remove_component(out[interior], _unit(tangents[interior]))
    )

    # 2. candidates: the vector, and its inverse away from helices
    candidates = np.empty((n, 2, 3), dtype=float)
    candidates[:, 0] = out
    candidates[:, 1] = np.where(is_helix[:, None], out, -out)

    # 3. forward sweep -- sequential: each step reads the neighbour just written,
    # so it stays a loop. The arithmetic is on plain floats, though: at three
    # components per residue, the four NumPy calls this used to make per step
    # were almost entirely call overhead and temporary arrays.
    out_rows = out.tolist()
    candidate_rows = candidates.tolist()
    normal_rows = normals.tolist()
    interior_rows = interior.tolist()
    for a in range(1, n - 1):
        if not interior_rows[a]:
            continue
        ax, ay, az = normal_rows[a - 1]
        if ax == 0.0 and ay == 0.0 and az == 0.0:
            continue
        axis_len = math.sqrt(ax * ax + ay * ay + az * az)
        ax, ay, az = ax / axis_len, ay / axis_len, az / axis_len

        ox, oy, oz = out_rows[a - 1]
        along = ox * ax + oy * ay + oz * az
        px, py, pz = ox - along * ax, oy - along * ay, oz - along * az
        plen = math.sqrt(px * px + py * py + pz * pz)
        if plen > 1e-12:
            px, py, pz = px / plen, py / plen, pz / plen

        best = -math.inf
        chosen = candidate_rows[a][0]
        for candidate in candidate_rows[a]:
            cx, cy, cz = candidate
            along = cx * ax + cy * ay + cz * az
            qx, qy, qz = cx - along * ax, cy - along * ay, cz - along * az
            qlen = math.sqrt(qx * qx + qy * qy + qz * qz)
            if qlen > 1e-12:
                qx, qy, qz = qx / qlen, qy / qlen, qz / qlen
            score = qx * px + qy * py + qz * pz
            if score > best:
                best = score
                chosen = candidate
        out_rows[a] = chosen
    out[:] = out_rows

    # 4. soften kinks -- reads only the swept result, never its own output, so
    # every residue is independent and the whole pass is one set of array ops.
    softened = np.array(out, dtype=float)
    middle = np.nonzero(interior)[0]
    if middle.size:
        agreement = np.einsum("ij,ij->i", out[middle], out[middle + 1]) * np.einsum(
            "ij,ij->i", out[middle], out[middle - 1]
        )
        kinked = agreement < _KINK_THRESHOLD
        if np.any(kinked):
            rows = middle[kinked]
            agreement = agreement[kinked]
            here = out[rows]
            # PyMOL's 0.001 nudge keeps the sum from vanishing when the two
            # neighbours are exactly opposed.
            target = out[rows + 1] + out[rows - 1] + 0.001 * here
            target = _unit(_remove_component(target, tangents[rows]))
            facing = np.einsum("ij,ij->i", here, target)
            blended = _unit(np.where(facing[:, None] < 0.0, here - target, here + target))
            weight = np.minimum(2.0 * (_KINK_THRESHOLD - agreement), 1.0)[:, None]
            softened[rows] = _unit((1.0 - weight) * here + weight * blended)
    return softened


def refine_sheet_tips(
    tangents: np.ndarray,
    is_sheet: np.ndarray,
    segments: np.ndarray,
    weight: float = 10.0,
) -> np.ndarray:
    """Aim the tangent at each strand end along the strand.

    ``RepCartoonFlattenSheetsRefineTips`` (``cartoon_refine_tips``, default
    **10**). At a strand's first residue the tangent is biased toward the *next*
    one, at its last toward the *previous*, then renormalised. With a weight of
    10 the neighbour dominates, which is the point: a strand tip otherwise takes
    its direction from the loop it joins, and the arrowhead then points off the
    strand axis.

    Note that PyMOL applies this to ``tv``, the **tangents** — the
    ``/* normal */`` comment in the C++ is stale, since ``tv`` is written by
    ``RepCartoonComputeTangents``.

    Parameters
    ----------
    tangents : numpy.ndarray
        ``(n, 3)`` tangents; not modified in place.
    is_sheet : numpy.ndarray
        ``(n,)`` boolean strand mask.
    segments : numpy.ndarray
        ``(n,)`` segment id per residue.
    weight : float, optional
        ``cartoon_refine_tips``.

    Returns
    -------
    numpy.ndarray
        ``(n, 3)`` tangents with the strand tips re-aimed.
    """
    n = tangents.shape[0]
    out = np.array(tangents, dtype=float)
    if n < 3 or weight == 0.0 or not np.any(is_sheet):
        return out

    for a in range(1, n - 1):
        if not is_sheet[a]:
            continue
        if segments[a] != segments[a + 1] or segments[a] != segments[a - 1]:
            continue
        starts = is_sheet[a + 1] and not is_sheet[a - 1]
        ends = not is_sheet[a + 1] and is_sheet[a - 1]
        if starts:
            out[a] = tangents[a] + weight * tangents[a + 1]
        elif ends:
            out[a] = tangents[a] + weight * tangents[a - 1]
    return _unit(out)


def build_guide_frames(
    positions: np.ndarray,
    orientations: np.ndarray,
    *,
    segments: np.ndarray | None = None,
    is_helix: np.ndarray | None = None,
    is_sheet: np.ndarray | None = None,
    refine_normals_enabled: bool = True,
    refine_tips: float = 10.0,
) -> GuideFrames:
    """Run PyMOL's per-residue conditioning in its own order.

    The order is load-bearing and comes from ``RepCartoonGeneratePoints``:
    normals and tangents are computed, the orientations refined against them,
    and only then — after the caller has flattened the sheets, which moves the
    positions — are the tangents recomputed and the strand tips re-aimed. Doing
    the tips before the flattening would aim them along a path that is about to
    change.

    Parameters
    ----------
    positions : numpy.ndarray
        ``(n, 3)`` guide positions, already flattened if that is wanted.
    orientations : numpy.ndarray
        ``(n, 3)`` ribbon up-vectors.
    segments : numpy.ndarray, optional
        ``(n,)`` segment id; defaults to one segment.
    is_helix, is_sheet : numpy.ndarray, optional
        ``(n,)`` boolean masks; default all false.
    refine_normals_enabled : bool, optional
        ``cartoon_refine_normals``.
    refine_tips : float, optional
        ``cartoon_refine_tips``; 0 disables.

    Returns
    -------
    GuideFrames
    """
    pts = np.asarray(positions, dtype=float)
    n = pts.shape[0]
    ups = _unit(np.asarray(orientations, dtype=float))
    seg = (
        np.zeros(n, dtype=int) if segments is None
        else np.asarray(segments).reshape(-1)
    )
    helix = (
        np.zeros(n, dtype=bool) if is_helix is None
        else np.asarray(is_helix, dtype=bool)
    )
    sheet = (
        np.zeros(n, dtype=bool) if is_sheet is None
        else np.asarray(is_sheet, dtype=bool)
    )

    _, normals, lengths = differences_and_normals(pts, seg)
    tangents = tangents_from_normals(normals, seg)
    if refine_normals_enabled:
        ups = refine_normals(ups, tangents, normals, seg, helix)
    if refine_tips:
        tangents = refine_sheet_tips(tangents, sheet, seg, weight=refine_tips)

    return GuideFrames(
        positions=pts,
        normals=normals,
        tangents=tangents,
        orientations=ups,
        lengths=lengths,
    )
