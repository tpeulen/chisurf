r"""Photon-counting-histogram distributions for a mixture of species.

The maths is tttrlib's (``PhotonCountingHistogram.cpp``); this module is the
argument checking in front of it. What is worth knowing before changing either
half is the pair of conventions the two implementations have to agree on,
because a mismatch in them does not change a number, it changes what a number
*means*:

* The single-molecule term carries the **shell weight** :math:`x^2` of the
  spherically symmetric 3-D Gaussian, whose volume element is
  :math:`\mathrm{d}V = 4\pi w^3 x^2\,\mathrm{d}x`. Dropping it does not merely
  rescale the result -- the sum then describes a *1-D* Gaussian volume and the
  second-order shape factor comes out as :math:`2^{-1/2}` instead of the 3-D
  Gaussian's :math:`\gamma_2 = 2^{-3/2}`, so the recovered brightness is far
  too small. ``test_algorithms.py`` pins :math:`\gamma_2` through the
  convention-free identity :math:`\mathrm{Var}/\langle k\rangle - 1 =
  \varepsilon\gamma_2`.
* ``p1[0]`` is the **complement** of the :math:`k \ge 1` terms, which absorbs
  the constant :math:`4\pi w^3 / V_0` prefactor into the definition of the
  reference volume. The fitted occupancy ``avgN`` is therefore expressed *in
  that reference volume*, while the brightness is convention-free. A library
  normalising this differently would change what ``avgN`` means while leaving
  every amplitude comparison green.

Both hold: ``p1[0]`` agrees with the C++ to the last digit and the arrays to
``1e-16``, which is the check that licensed the delegation.

The Poisson term is evaluated in log space as
:math:`\exp(k\ln\lambda - \ln\Gamma(k+1) - \lambda)` rather than as the ratio
:math:`\lambda^k / k!`. Both parts of that ratio overflow a ``double``: ``k!``
passes ``DBL_MAX`` at ``k = 171``, which would make ``p1[k]`` exactly zero from
there on at *any* brightness, and above :math:`k \gtrsim 308/\log_{10}
\varepsilon` the numerator overflows too and ``inf/inf`` yields ``NaN``, which
``p1[0]`` then spreads over the whole array and hands to the optimiser. A
300-long ``k`` axis is ordinary at 1 ms binning, so neither ceiling is a corner
case.
"""

from __future__ import annotations

import numpy as np
import tttrlib


def _k_max(k_vals) -> int:
    """Validate a photon-count axis and return its largest count.

    The C++ takes a scalar ``k_max`` and builds the axis ``0, 1, ... k_max``
    itself, so it cannot represent a gapped or offset axis -- it would answer
    for a *different* axis than the caller asked about, at the caller's length
    or another, with nothing in the result to say so. Callers that build the
    axis with :func:`numpy.arange` are unaffected; the one that reads it from
    dataset metadata (``pch_model``) is why this is checked rather than assumed.

    Parameters
    ----------
    k_vals : array_like
        Photon-count axis, which must be ``0, 1, ... k_max``.

    Returns
    -------
    int
        ``k_max``, i.e. ``len(k_vals) - 1``.

    Raises
    ------
    ValueError
        If the axis is empty, or is not the consecutive integers from zero.
    """
    axis = np.asarray(k_vals, dtype=float)
    if axis.ndim != 1 or axis.size == 0:
        raise ValueError(
            f"photon-count axis must be a non-empty 1-D array, got shape {axis.shape}."
        )
    expected = np.arange(axis.size, dtype=float)
    if not np.array_equal(axis, expected):
        raise ValueError(
            "photon-count axis must be the consecutive integers 0, 1, ... k_max; "
            f"got {axis[:4]}... (length {axis.size}). A PCH is defined per photon "
            "count, so a gapped or offset axis has no meaning here -- histogram "
            "the counts onto a full axis first."
        )
    return int(axis.size - 1)


def _grid(x_vals, dx) -> tuple[int, float]:
    """Validate a radial quadrature grid and return it as ``(n_grid, x_max)``.

    Parameters
    ----------
    x_vals : array_like
        Radial grid in units of the beam waist; must be uniform and start at 0.
    dx : float
        Spacing, which must agree with ``x_vals``.

    Returns
    -------
    tuple of (int, float)
        Number of grid points and the largest radius.

    Raises
    ------
    ValueError
        If the grid is too short, does not start at zero, is not uniform, or
        disagrees with ``dx``.
    """
    grid = np.asarray(x_vals, dtype=float)
    if grid.ndim != 1 or grid.size < 2:
        raise ValueError(f"radial grid needs at least 2 points, got {grid.size}.")
    if grid[0] != 0.0:
        raise ValueError(
            f"radial grid must start at the centre of the volume, got x[0] = {grid[0]}."
        )
    x_max = float(grid[-1])
    step = x_max / (grid.size - 1)
    if not np.allclose(grid, np.arange(grid.size) * step, rtol=0.0, atol=1e-12 + 1e-9 * step):
        raise ValueError("radial grid must be uniformly spaced.")
    if dx is not None and not np.isclose(float(dx), step, rtol=1e-9, atol=0.0):
        raise ValueError(
            f"dx = {dx} disagrees with the spacing implied by x_vals ({step}). "
            "The grid is the authority; passing an inconsistent dx would silently "
            "rescale p1."
        )
    return int(grid.size), x_max


def compute_p1(k_vals, brightness, x_vals, dx):
    r"""Single-molecule photon-count distribution on an explicit radial grid.

    Evaluates :math:`p^{(1)}(k) \propto \int (\varepsilon\,\mathrm{PSF})^k / k!\,
    e^{-\varepsilon\,\mathrm{PSF}}\,\mathrm{d}V` for the 3-D Gaussian
    :math:`\mathrm{PSF}(x) = e^{-2x^2}`, with ``x = r / w`` the radial distance
    in units of the beam waist. See the module docstring for the shell weight
    and the meaning of ``p1[0]``.

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon-count axis ``0, 1, ... k_max``.
    brightness : float
        Molecular brightness :math:`\varepsilon` (counts per molecule per bin)
        at the centre of the detection volume.
    x_vals : numpy.ndarray
        Uniform radial quadrature grid starting at zero.
    dx : float
        Spacing of ``x_vals``.

    Returns
    -------
    numpy.ndarray
        ``p1[k]`` for every ``k`` in ``k_vals``, summing to 1.
    """
    k_max = _k_max(k_vals)
    n_grid, x_max = _grid(x_vals, dx)
    return np.asarray(
        tttrlib.pch_single_species(k_max, float(brightness), n_grid, x_max),
        dtype=float,
    )


def pch_single_species(k_vals, brightness):
    r"""``p1(k)`` of one molecule in a 3-D Gaussian volume on the default grid.

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon-count axis ``0, 1, ... k_max``.
    brightness : float
        Molecular brightness :math:`\varepsilon` (counts per molecule per bin).

    Returns
    -------
    numpy.ndarray
        :func:`compute_p1` on ``x in [0, 5]`` (1000 points) -- the profile has
        decayed to :math:`e^{-50}` there, so the truncation is irrelevant.
    """
    return np.asarray(
        tttrlib.pch_single_species(_k_max(k_vals), float(brightness), 1000, 5.0),
        dtype=float,
    )


def pch_open_system(k_vals, brightness, avgN, maxN=30):
    r"""PCH of one species in an open volume (Poisson-distributed occupancy).

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon-count axis ``0, 1, ... k_max``.
    brightness : float
        Molecular brightness :math:`\varepsilon` (counts per molecule per bin).
    avgN : float
        Mean number of molecules in the reference volume (see the module
        docstring for which volume that is).
    maxN : int
        Largest occupancy kept in the Poisson sum.

    Returns
    -------
    numpy.ndarray
        ``P(k)``, the photon-counting histogram of the species.
    """
    return np.asarray(
        tttrlib.pch_open_system(
            _k_max(k_vals), float(brightness), float(avgN), int(maxN)
        ),
        dtype=float,
    )


def pch_mixture(k_vals, epsilons, avgNs):
    """PCH of a mixture of independent species (convolution of their PCHs).

    Parameters
    ----------
    k_vals : numpy.ndarray
        Photon-count axis ``0, 1, ... k_max``.
    epsilons : sequence of float
        Molecular brightness per species.
    avgNs : sequence of float
        Mean occupancy per species, in the same order as ``epsilons``.

    Returns
    -------
    numpy.ndarray
        ``P(k)`` of the mixture.

    Raises
    ------
    ValueError
        If the two per-species lists have different lengths.

    Notes
    -----
    **Fixed upstream, 2026-08-10** (tttrlib ``okf/BUGS.md``, "``pch_mixture``
    indexes ``avg_numbers`` by the length of ``brightnesses``, and reads past
    the end"): a mismatched pair used to iterate the brightnesses and
    subscript the occupancies with the same index, with no bounds check, so
    an unequal pair read past the end of a ``std::vector``. It did not crash
    -- the memory there was zero, the ``avg_numbers[s] <= 0.0`` guard on the
    next line then skipped the species whose occupancy was never supplied,
    and the result was a normalised finite histogram of *fewer species than
    were asked for*, silently. ``pch_mixture`` now throws
    ``std::invalid_argument`` naming both sizes, which this wrapper surfaces
    as the same :class:`ValueError` below. Recorded in this repo's
    ``okf/references/known-issues.md`` under the same title.

    The length check here is kept anyway, deliberately, as defense in depth:
    it fails one call earlier, with a message this module controls, and it
    means this wrapper does not depend on which tttrlib build a given
    environment happens to have linked.
    """
    eps = [float(e) for e in epsilons]
    ns = [float(n) for n in avgNs]
    if len(eps) != len(ns):
        raise ValueError(
            f"a mixture needs one occupancy per brightness, got {len(eps)} "
            f"brightness value(s) and {len(ns)} occupancy value(s)."
        )
    return np.asarray(tttrlib.pch_mixture(_k_max(k_vals), eps, ns), dtype=float)
