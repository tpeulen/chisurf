"""Rigid-body fitting of atoms into a density map.

The question this answers is the one cryo-EM work turns on: *where in this map
does this model sit, and how well does it agree once it is there?* A correlation
computed at the model's deposited position answers a different and much weaker
question, because a model that is 2 A out scores badly for a reason that has
nothing to do with whether it is right.

Method, following ChimeraX's ``fitmap``: steepest ascent on the map value
sampled at the atoms, moving the model rigidly. Each step needs two directions:

* a **translation** along the weighted mean of the map gradient at the atoms;
* a **rotation**, about the axis given by the weighted mean of ``r x grad`` --
  the torque the density exerts on the model about its own centre.

Both are followed by the same fractional step, halved whenever a step fails to
improve and grown slowly when it succeeds, which is what keeps a shallow
gradient from stalling and a steep one from oscillating.

Two things worth knowing before trusting a number out of this:

* it is a **local** optimiser, and the basin is wider than one might guess.
  Measured on 148L at 6 A: a 45 degree rotation (9.3 A RMSD) comes back to
  0.02 A, and so does a shift of half the structure's own 73 A extent. A **90
  degree** rotation does not -- it starts 17.2 A out and settles 12.8 A out, in
  a different maximum, still reporting an ordinary-looking score. A model that
  misses the map entirely does not move at all, which is correct: outside the
  box the field is flat. Global search means many starts, and belongs on top of
  this rather than inside it;
* the honest "does this agree" number is :func:`map_correlation` -- the model's
  own simulated density against the map, voxel by voxel, both means subtracted.
  The per-atom alternative in :func:`correlation_about_mean` reads like a fit
  quality and is not one: on 148L at 6 A it scored **-0.030 at the true
  position and -0.014 four angstrom away**, preferring the wrong answer.
"""
from __future__ import annotations

import math

import numpy as np

__all__ = [
    "FitResult",
    "correlation_about_mean",
    "fit_points_in_map",
    "interpolate_gradients",
    "interpolate_values",
    "map_correlation",
]


def _to_index(grid, points: np.ndarray) -> np.ndarray:
    """World coordinates to fractional grid indices."""
    rotation = np.asarray(grid.rotation, dtype=float)
    delta = np.asarray(points, dtype=float) - np.asarray(grid.origin, dtype=float)
    # The grid's axes may be rotated; express the offset in them before dividing
    # by the step, or an oriented map samples along the wrong lines.
    local = delta @ rotation
    return local / np.asarray(grid.step, dtype=float)


def interpolate_values(grid, points) -> np.ndarray:
    """Trilinearly interpolated map values at *points*.

    Points outside the grid sample as zero, which is the right answer for a map
    that is only defined where it was measured -- and means an atom pushed out
    of the box pulls the score down rather than raising an error mid-fit.
    """
    values = np.asarray(grid.values, dtype=float)
    ijk = _to_index(grid, points)
    shape = np.asarray(values.shape)

    base = np.floor(ijk).astype(np.int64)
    frac = ijk - base
    inside = np.all((base >= 0) & (base < shape - 1), axis=1)
    out = np.zeros(ijk.shape[0], dtype=float)
    if not np.any(inside):
        return out

    b, f = base[inside], frac[inside]
    i, j, k = b[:, 0], b[:, 1], b[:, 2]
    u, v, w = f[:, 0], f[:, 1], f[:, 2]
    result = np.zeros(b.shape[0], dtype=float)
    for di, wi in ((0, 1.0 - u), (1, u)):
        for dj, wj in ((0, 1.0 - v), (1, v)):
            for dk, wk in ((0, 1.0 - w), (1, w)):
                result += wi * wj * wk * values[i + di, j + dj, k + dk]
    out[inside] = result
    return out


def interpolate_gradients(grid, points) -> np.ndarray:
    """Map gradient at *points*, ``(n, 3)`` in world units.

    Central differences on the interpolated field, one grid step apart. Cheaper
    and steadier than differentiating the trilinear form analytically, whose
    gradient is discontinuous at every voxel boundary -- a discontinuous
    gradient makes a line search chatter.
    """
    step = np.asarray(grid.step, dtype=float)
    rotation = np.asarray(grid.rotation, dtype=float)
    points = np.asarray(points, dtype=float)
    gradient = np.zeros(points.shape, dtype=float)
    for axis in range(3):
        # Step along the *grid's* axis, expressed in world space.
        direction = rotation[:, axis] * step[axis]
        ahead = interpolate_values(grid, points + direction)
        behind = interpolate_values(grid, points - direction)
        gradient += np.outer((ahead - behind) / (2.0 * step[axis]), rotation[:, axis])
    return gradient


def correlation_about_mean(weights, values) -> float:
    """Pearson correlation between the weights and the sampled map values.

    Both means are subtracted. Without that, two quantities that are positive
    everywhere correlate strongly whatever their shapes, and the number stops
    distinguishing a fit from a near-miss.

    Returns
    -------
    float
        ``nan`` when either side has no variance -- in particular when the
        weights are all equal, which is the default. This asks whether the map
        is *stronger where the atoms are heavier*, so with one weight for every
        atom there is no question to answer, and returning 0.0 there would make
        a perfect fit read as a total failure.
    """
    a = np.asarray(weights, dtype=float).reshape(-1)
    b = np.asarray(values, dtype=float).reshape(-1)
    if a.size < 2 or a.size != b.size:
        return float("nan")
    a = a - a.mean()
    b = b - b.mean()
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 0.0:
        return float("nan")
    return float(np.dot(a, b) / denominator)


def map_correlation(first, second, *, about_mean: bool = True) -> float:
    """Correlation between two maps on the same lattice.

    This is the number that answers "how well does this model agree with this
    density". The per-atom alternative -- correlating each atom's weight with
    the map value under it -- reads as a fit quality and is not one: measured on
    148L at 6 A it scored **-0.030 at the true position and -0.014 four
    angstrom away**, i.e. it prefers the wrong answer. Simulate the model's own
    density onto the map's grid (:func:`~.molmap.simulate_map` with ``on_grid``)
    and compare voxels.

    Parameters
    ----------
    first, second : VolumeGrid
        Must have the same shape; simulating ``on_grid`` is what guarantees it.
    about_mean : bool
        Subtract each map's mean first. On by default: both maps are positive
        nearly everywhere, so without it the number sits near 1 for any pair.

    Raises
    ------
    ValueError
        If the shapes differ -- silently comparing two different lattices would
        produce a number that means nothing.
    """
    a = np.asarray(first.values, dtype=float).reshape(-1)
    b = np.asarray(second.values, dtype=float).reshape(-1)
    if a.shape != b.shape:
        raise ValueError(
            f"maps have different shapes: {first.shape} and {second.shape}; "
            "simulate onto the experimental map's grid to compare them"
        )
    if about_mean:
        a = a - a.mean()
        b = b - b.mean()
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 0.0:
        return float("nan")
    return float(np.dot(a, b) / denominator)


class FitResult:
    """What a fit did and how well it ended up.

    Attributes
    ----------
    rotation : numpy.ndarray
        ``3x3``, applied about *centre*.
    translation : numpy.ndarray
        Applied after the rotation.
    centre : numpy.ndarray
        The point the rotation is about -- the weighted centre of the atoms at
        the start. Keeping it explicit matters: the same rotation about a
        different centre is a different motion.
    steps : int
        Steps taken before the step size collapsed or the budget ran out.
    average : float
        Weighted mean map value at the atoms, at the end.
    correlation : float
        Correlation about the mean, at the end; ``nan`` for uniform weights.
    shift : float
        How far the centre moved, in map units.
    angle : float
        Rotation applied, in degrees.
    """

    __slots__ = (
        "rotation", "translation", "centre", "steps",
        "average", "correlation", "shift", "angle",
    )

    def __init__(self, rotation, translation, centre, steps, average, correlation):
        self.rotation = np.asarray(rotation, dtype=float)
        self.translation = np.asarray(translation, dtype=float)
        self.centre = np.asarray(centre, dtype=float)
        self.steps = int(steps)
        self.average = float(average)
        self.correlation = float(correlation)
        self.shift = float(np.linalg.norm(self.translation))
        trace = float(np.clip((np.trace(self.rotation) - 1.0) / 2.0, -1.0, 1.0))
        self.angle = float(np.degrees(np.arccos(trace)))

    def apply(self, points) -> np.ndarray:
        """Move *points* the way the fit moved the model."""
        pts = np.asarray(points, dtype=float)
        return (pts - self.centre) @ self.rotation.T + self.centre + self.translation


def _rotation_about(axis: np.ndarray, angle: float) -> np.ndarray:
    """Rodrigues' rotation matrix."""
    norm = float(np.linalg.norm(axis))
    if norm <= 0.0 or angle == 0.0:
        return np.eye(3)
    x, y, z = axis / norm
    cross = np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
    return (
        np.eye(3)
        + math.sin(angle) * cross
        + (1.0 - math.cos(angle)) * (cross @ cross)
    )


def fit_points_in_map(
    points,
    grid,
    *,
    weights=None,
    max_steps: int = 500,
    shift_tolerance: float = 0.001,
    angle_tolerance: float = 0.01,
) -> FitResult:
    """Move *points* rigidly to the nearest maximum of the map.

    Parameters
    ----------
    points : array_like
        ``(n, 3)`` atom positions, in the map's units.
    grid : VolumeGrid
    weights : array_like, optional
        Per-atom weight, atomic number being the meaningful choice for a
        density. Defaults to 1 each.
    max_steps : int
        Budget. The optimiser usually stops long before this on the tolerances.
    shift_tolerance, angle_tolerance : float
        Stop once a step moves the model less than this (map units, degrees).

    Returns
    -------
    FitResult

    Notes
    -----
    The step size is expressed as a fraction of one voxel, so the same
    tolerances behave the same way on a 1 A map and a 4 A one. It halves on a
    step that does not improve the score and grows by a factor 1.2 on one that
    does -- so a fit that starts far out takes long strides and then settles.
    """
    original = np.asarray(points, dtype=float)
    if original.ndim != 2 or original.shape[1] != 3:
        raise ValueError(f"points must be (n, 3); got {original.shape}")
    if original.shape[0] == 0:
        raise ValueError("cannot fit no atoms")

    if weights is None:
        mass = np.ones(original.shape[0], dtype=float)
    else:
        mass = np.asarray(weights, dtype=float).reshape(-1)
        if mass.shape[0] != original.shape[0]:
            raise ValueError(f"got {mass.shape[0]} weights for {original.shape[0]} atoms")
    total = float(mass.sum()) or 1.0

    centre = (original * mass[:, None]).sum(axis=0) / total
    rotation = np.eye(3)
    translation = np.zeros(3)

    def placed():
        return (original - centre) @ rotation.T + centre + translation

    def score(pts):
        return float((interpolate_values(grid, pts) * mass).sum() / total)

    current = placed()
    best = score(current)
    voxel = float(np.min(np.asarray(grid.step, dtype=float)))
    size = 0.5  # in voxels
    taken = 0

    for _ in range(int(max_steps)):
        gradient = interpolate_gradients(grid, current)
        weighted = gradient * mass[:, None]
        direction = weighted.sum(axis=0) / total
        offset = current - centre - translation
        torque = np.cross(offset, weighted).sum(axis=0) / total

        d_norm = float(np.linalg.norm(direction))
        t_norm = float(np.linalg.norm(torque))
        if d_norm <= 0.0 and t_norm <= 0.0:
            break

        # Scale both motions so the *largest atom displacement* they cause is
        # one step size. Without that the rotation term's magnitude depends on
        # how far the model extends, and a large complex spins wildly while a
        # small one barely turns.
        reach = float(np.max(np.linalg.norm(offset, axis=1))) or 1.0
        move = size * voxel
        shift_step = direction / d_norm * move if d_norm > 0.0 else np.zeros(3)
        angle_step = (move / reach) if t_norm > 0.0 else 0.0

        trial_rotation = _rotation_about(torque, angle_step) @ rotation
        trial_translation = translation + shift_step
        trial = (original - centre) @ trial_rotation.T + centre + trial_translation
        value = score(trial)

        if value > best:
            rotation, translation, current, best = (
                trial_rotation, trial_translation, trial, value
            )
            taken += 1
            size *= 1.2
            if move < shift_tolerance and np.degrees(angle_step) < angle_tolerance:
                break
        else:
            size *= 0.5
            if size * voxel < shift_tolerance:
                break

    values = interpolate_values(grid, current)
    return FitResult(
        rotation,
        translation,
        centre,
        taken,
        float((values * mass).sum() / total),
        correlation_about_mean(mass, values),
    )
