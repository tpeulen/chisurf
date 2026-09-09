"""Distances between accessible volumes, and the scores built on them.

Every function here is ``IMP.bff``'s, in C++. They take coordinates and
return numbers, which by the layering rule makes them the library's and not
the application's; this module is the name the plugin imports them under, and
the place a reader looks to see which of them the plugin uses.

The *evaluator* objects an ``fps.json`` describes -- ``DistanceEvaluator`` and
the rest -- are the application's shape for a labelling experiment, and live
in the plugin's ``evaluators`` package.
"""

from __future__ import annotations

# A module attribute rather than an import at module scope: importing IMP.bff
# pulls a large native stack in, and the plugin is discovered (manifest, menu
# entry) long before anyone computes a distance.
_BFF = None


def _bff():
    """Return ``IMP.bff``, imported on first use.

    Returns
    -------
    module
        The ``IMP.bff`` module.
    """
    global _BFF
    if _BFF is None:
        import IMP.bff as bff

        _BFF = bff
    return _BFF


#: What this module re-exports from ``IMP.bff``. Named rather than star-imported
#: so that a name disappearing upstream is an error here and not a mystery at
#: the call site.
_NAMES = (
    "random_distances",
    "av_pair_statistics",
    "fit_transfer_polynomial",
    "polynomial_transfer",
    "gaussian_rmp_to_rda_mean",
    "chi2_score",
    "fret_efficiency",
    "distance_from_fret_efficiency",
)


def __getattr__(name: str):
    """Resolve a re-exported name against ``IMP.bff`` on first access.

    Parameters
    ----------
    name : str
        The attribute being looked up.

    Returns
    -------
    object
        The corresponding ``IMP.bff`` attribute.

    Raises
    ------
    AttributeError
        For a name this module does not re-export, or one the installed
        ``IMP.bff`` does not have -- with the build named, because the
        IMP-free wheel is a build that legitimately lacks some of them.
    """
    if name not in _NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    bff = _bff()
    try:
        return getattr(bff, name)
    except AttributeError:
        raise AttributeError(
            f"this IMP.bff has no {name} "
            f"(build {getattr(bff, 'get_build', lambda: '?')()})"
        ) from None


def __dir__():
    """The re-exported names, so that ``dir()`` and tab-completion work."""
    return sorted(set(globals()) | set(_NAMES))


def _flat_points(av):
    """The volume's points as the flat vector the kernels take.

    Parameters
    ----------
    av : AccessibleVolume or array_like
        A volume, or its ``(N, 4)`` points.

    Returns
    -------
    numpy.ndarray
        ``4 * N`` values, x, y, z and weight per point.
    """
    import numpy as np

    return np.ascontiguousarray(
        np.asarray(getattr(av, "points", av), dtype=np.float64).reshape(-1)
    )


def average_distance(av1, av2, n_samples=50000, seed=0):
    """Mean donor-acceptor distance over sampled pairs, Angstrom."""
    return _bff().average_distance(_flat_points(av1), _flat_points(av2),
                                   int(n_samples), int(seed))


def mean_fret_distance(av1, av2, forster_radius=52.0, n_samples=50000, seed=0):
    """The FRET-averaged distance <R_DA>_E, Angstrom."""
    return _bff().mean_fret_distance(_flat_points(av1), _flat_points(av2),
                                     float(forster_radius), int(n_samples),
                                     int(seed))


def distance_between_mean_positions(av1, av2):
    """Distance between the two clouds' mean positions, Angstrom."""
    import numpy as np

    return float(
        np.linalg.norm(
            np.asarray(av1.mean_position, dtype=np.float64)
            - np.asarray(av2.mean_position, dtype=np.float64)
        )
    )


def standard_deviation_of_distances(av1, av2, n_samples=50000, seed=0):
    """Spread of the sampled donor-acceptor distances, Angstrom."""
    return _bff().standard_deviation_of_distances(
        _flat_points(av1), _flat_points(av2), int(n_samples), int(seed)
    )


def _sample_av_distance(av1, av2, n_samples=50000):
    """Sampled donor-acceptor distances between two volumes.

    Parameters
    ----------
    av1, av2 : AccessibleVolume or IMP.bff.States
        The two labelling positions.
    n_samples : int
        How many pairs to draw.

    Returns
    -------
    numpy.ndarray
        The sampled distances, Angstrom.
    """
    import numpy as np

    def _points(av):
        pts = np.asarray(
            getattr(av, "points", av), dtype=np.float64
        ).reshape(-1, 4)
        return np.ascontiguousarray(pts)

    # A fixed seed by default: two calls on one pair are the same answer, and
    # a sampled distance that moves between runs is a defect nobody can
    # reproduce. A caller wanting a spread asks for one explicitly.
    return np.asarray(
        _bff().random_distances(_points(av1), _points(av2),
                                int(n_samples), 0),
        dtype=np.float64,
    )


__all__ = list(_NAMES) + [
    "as_states",
    "average_distance",
    "distance_between_mean_positions",
    "mean_fret_distance",
    "standard_deviation_of_distances",
    "histogram_rda",
    "model_distance",
    "_sample_av_distance",
]


def as_states(av):
    """Turn a plugin :class:`~...core.av.AccessibleVolume` into ``IMP.bff.States``.

    Parameters
    ----------
    av : AccessibleVolume or IMP.bff.States
        A volume. A ``States`` is returned unchanged, so a caller that
        already has one need not know which it holds.

    Returns
    -------
    IMP.bff.States
        The same points and attachment point, in the type the distance
        functions take.

    Notes
    -----
    ``States`` is bff's word for "where a label can be", and it is what
    ``model_distance`` and the histogram take -- an accessible volume is one
    kind of it, and a rotamer cloud is another. The plugin's dataclass is the
    application's record of the same thing, so this is the one place the two
    meet rather than a conversion at every call site.
    """
    import numpy as np

    bff = _bff()
    if isinstance(av, bff.States):
        return av
    points = np.ascontiguousarray(
        np.asarray(av.points, dtype=np.float64)
    ).reshape(-1)
    attachment = np.ascontiguousarray(
        np.asarray(av.attachment_point, dtype=np.float64)
    ).reshape(-1)
    return bff.States(points, attachment)


def model_distance(av1, av2, distance_type, forster_radius=52.0,
                   n_samples=50000):
    """A model distance of the named type between two volumes.

    Parameters
    ----------
    av1, av2 : AccessibleVolume or IMP.bff.States
        The two labelling positions.
    distance_type : str
        ``"Rmp"``, ``"RDAMean"`` or ``"RDAMeanE"``.
    forster_radius : float
        The Foerster radius, Angstrom; used by ``RDAMeanE``.
    n_samples : int
        Pair samples drawn from the two clouds.

    Returns
    -------
    float
        The distance, Angstrom.
    """
    return _bff().model_distance(
        as_states(av1), as_states(av2), str(distance_type),
        float(forster_radius), int(n_samples),
    )


def histogram_rda(av1, av2, axis=None, n_samples=50000, normalize=True,
                  rda_min=None, rda_max=None, n_rda_bins=None):
    """The distance distribution P(R_DA) of a pair of volumes.

    Parameters
    ----------
    av1, av2 : AccessibleVolume or IMP.bff.States
        The two labelling positions.
    axis : array_like, optional
        Bin edges; empty lets the library choose.
    n_samples : int
        Pair samples drawn.
    normalize : bool
        Return a density rather than counts.

    rda_min, rda_max, n_rda_bins : float, float, int, optional
        A range and a bin count, as the evaluators describe a histogram.
        Turned into ``axis`` here: upstream takes edges, which is the more
        general shape, and an application that thinks in ranges should not
        have to build them at every call site.

    Returns
    -------
    tuple of numpy.ndarray
        ``(counts, axis)`` -- the histogram and the bin edges it is over.
        Upstream returns the counts alone, because the caller passed the
        edges; a caller that passed a *range* has not seen them, and a
        histogram without its axis cannot be plotted or integrated.
    """
    import numpy as np

    if axis is None and None not in (rda_min, rda_max, n_rda_bins):
        # linspace and not arange: the caller named the two ends, and arange
        # is the version that quietly drops the last bin to floating point.
        axis = np.linspace(float(rda_min), float(rda_max),
                           int(n_rda_bins) + 1)

    edges = np.ascontiguousarray(
        np.asarray(axis if axis is not None else [], dtype=np.float64)
    ).reshape(-1)
    counts = np.asarray(
        _bff().histogram_rda(as_states(av1), as_states(av2), edges,
                             int(n_samples), bool(normalize)),
        dtype=np.float64,
    )
    return counts, edges
