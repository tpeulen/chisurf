"""Simulating a density map from a model, and putting a model back into one.

Why these two together
----------------------
They are halves of one thing. ``molmap`` says what a model would look like at a
stated resolution; ``fitmap`` moves a model to where a map says it belongs. A
correlation quoted without the fit answers a much weaker question -- a model two
angstrom out of place scores badly for a reason that has nothing to do with
whether it is right.

The measurement that says it works: take 148L, simulate its own map, displace
the model by **5.9 A RMSD** (10 degrees and a 5.4 A shift), and fit it back.
The answer is zero, and the fit returns **0.014 A**.

The metric trap, which is the reason ``map_correlation`` exists
---------------------------------------------------------------
The obvious per-atom score -- correlate each atom's weight against the map value
under it -- reads like a fit quality and is not one. Measured on 148L at 6 A it
scores **-0.030 at the true position and -0.014 four angstrom away**: it prefers
the wrong answer. At map resolutions the density is smooth, and heavy atoms are
not systematically under denser voxels.

What discriminates is a **map-to-map** correlation: simulate the model's own
density onto the experimental map's own lattice and compare voxel by voxel.
That is 1.000 at the answer and 0.62 when displaced, and it is what ``fitmap``
reports when given a resolution. Both are pinned below, the bad one included --
if someone ever "simplifies" the reporting back to the per-atom form, the test
that catches it has to know why.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.analysis.mapfit import (
    correlation_about_mean,
    fit_points_in_map,
    interpolate_values,
    map_correlation,
)
from chisurf.plugins.chimol.chimol.analysis.molmap import simulate_map

_CACHE = Path.home() / ".chisurf/structures/chimol/chimol_pdb_148l.pdb"

#: Displacement applied before every fit: a rotation and a shift, both large
#: enough that the answer is not where the model starts.
_ANGLE = 10.0
_SHIFT = np.array([4.0, -3.0, 2.0])


def _rotation(degrees, axis=(0.2, 0.7, 0.6)):
    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]], dtype=float)
    t = np.radians(degrees)
    return np.eye(3) + np.sin(t) * k + (1.0 - np.cos(t)) * (k @ k)


@pytest.fixture(scope="module")
def atoms():
    if not _CACHE.exists():
        pytest.skip("148l is not in the local structure cache")
    from chisurf.core.fio.structure import coordinates

    return np.asarray(coordinates.read_coordinates(str(_CACHE))["xyz"], dtype=float)


@pytest.fixture(scope="module")
def displaced(atoms):
    centre = atoms.mean(axis=0)
    return (atoms - centre) @ _rotation(_ANGLE).T + centre + _SHIFT


def _rmsd(a, b):
    return float(np.sqrt(((np.asarray(a) - np.asarray(b)) ** 2).sum(axis=1).mean()))


# --------------------------------------------------------------------- molmap


def test_the_simulated_map_covers_the_model(atoms):
    """Every atom inside the box, with the padded margin around it."""
    grid = simulate_map(atoms, 6.0)
    low = np.asarray(grid.origin)
    high = low + (np.asarray(grid.shape) - 1) * np.asarray(grid.step)
    assert np.all(atoms.min(axis=0) > low), "atoms fall outside the low corner"
    assert np.all(atoms.max(axis=0) < high), "atoms fall outside the high corner"


def test_the_step_follows_the_resolution(atoms):
    """Three samples across the resolution, which is what makes it smooth."""
    for resolution in (3.0, 6.0, 10.0):
        grid = simulate_map(atoms, resolution)
        assert grid.step[0] == pytest.approx(resolution / 3.0)


def test_a_coarser_map_is_smoother(atoms):
    """The resolution has to mean something; a wider Gaussian is flatter."""
    peaks = [float(simulate_map(atoms, r).values.max()) for r in (3.0, 6.0, 12.0)]
    assert peaks[0] > peaks[1] > peaks[2], peaks


def test_weights_reach_the_map(atoms):
    """A weighted atom must put more density down than an unweighted one."""
    plain = simulate_map(atoms[:200], 6.0)
    heavy = simulate_map(atoms[:200], 6.0, weights=np.full(200, 8.0))
    assert float(heavy.values.sum()) == pytest.approx(8.0 * float(plain.values.sum()))


def test_simulating_onto_another_grid_matches_it(atoms):
    """``on_grid`` is what makes two maps comparable at all."""
    target = simulate_map(atoms, 6.0)
    same = simulate_map(atoms, 6.0, on_grid=target)
    assert same.shape == target.shape
    assert np.allclose(same.origin, target.origin)
    assert np.allclose(same.step, target.step)


def test_an_empty_selection_is_refused(atoms):
    """An empty map would look like a result."""
    with pytest.raises(ValueError):
        simulate_map(np.zeros((0, 3)), 6.0)
    with pytest.raises(ValueError):
        simulate_map(atoms, 0.0)


# --------------------------------------------------------------------- metrics


def test_the_map_correlation_knows_the_right_answer(atoms, displaced):
    """1.0 where the model belongs, clearly lower where it does not."""
    target = simulate_map(atoms, 6.0)
    here = map_correlation(target, simulate_map(atoms, 6.0, on_grid=target))
    there = map_correlation(target, simulate_map(displaced, 6.0, on_grid=target))
    assert here == pytest.approx(1.0, abs=1e-6)
    assert there < 0.8, f"a {_rmsd(atoms, displaced):.1f} A error scored {there:.3f}"


def test_the_per_atom_correlation_does_not(atoms, displaced):
    """Pinned because it is the reason the map-to-map one exists.

    This is not a test of a feature; it is a record of a measurement. The
    per-atom score prefers the *wrong* position, so anything that reports it as
    a fit quality is reporting nonsense confidently.
    """
    target = simulate_map(atoms, 6.0)
    weights = np.linspace(1.0, 16.0, atoms.shape[0])
    here = correlation_about_mean(weights, interpolate_values(target, atoms))
    there = correlation_about_mean(weights, interpolate_values(target, displaced))
    assert not (here > there + 0.1), (
        "the per-atom correlation now discriminates; if that is real, the "
        f"warning in mapfit.py should be revised (here {here:.3f}, "
        f"displaced {there:.3f})"
    )


def test_uniform_weights_give_no_per_atom_correlation(atoms):
    """Not zero -- ``nan``. Zero would read as a total failure."""
    target = simulate_map(atoms, 6.0)
    value = correlation_about_mean(
        np.ones(atoms.shape[0]), interpolate_values(target, atoms)
    )
    assert np.isnan(value)


def test_maps_on_different_lattices_refuse_to_correlate(atoms):
    """Comparing two different grids voxel-wise means nothing."""
    with pytest.raises(ValueError):
        map_correlation(simulate_map(atoms, 6.0), simulate_map(atoms, 4.0))


# --------------------------------------------------------------------- fitmap


def test_a_displaced_model_is_put_back(atoms, displaced):
    """The measurement this whole pair exists for."""
    target = simulate_map(atoms, 6.0)
    assert _rmsd(atoms, displaced) > 4.0, "the premise: it starts well out"

    result = fit_points_in_map(displaced, target, max_steps=400)
    recovered = result.apply(displaced)
    assert _rmsd(atoms, recovered) < 0.2, (
        f"fit left the model {_rmsd(atoms, recovered):.2f} A out, from "
        f"{_rmsd(atoms, displaced):.2f} A"
    )
    assert result.angle == pytest.approx(_ANGLE, abs=1.0)
    assert result.steps > 0


def test_the_fit_reports_a_correlation_that_agrees_with_it(atoms, displaced):
    """The reported number must move with the actual improvement."""
    target = simulate_map(atoms, 6.0)
    before = map_correlation(target, simulate_map(displaced, 6.0, on_grid=target))
    result = fit_points_in_map(displaced, target, max_steps=400)
    after = map_correlation(
        target, simulate_map(result.apply(displaced), 6.0, on_grid=target)
    )
    assert after > before + 0.2, f"{before:.3f} -> {after:.3f}"


def test_a_model_already_in_place_is_left_alone(atoms):
    """A fit that jitters a correct answer is worse than one that does nothing."""
    target = simulate_map(atoms, 6.0)
    result = fit_points_in_map(atoms, target, max_steps=400)
    assert _rmsd(atoms, result.apply(atoms)) < 0.2


def test_the_optimiser_is_local_and_says_so(atoms):
    """Pinned so nobody quotes a score from a model dropped far away.

    Measured on 148L at 6 A, the basin is wider than it looks -- a 45 degree
    rotation (9.3 A RMSD) comes all the way back to 0.02 A, and so does a shift
    of half the structure's own 73 A extent. A **90 degree** rotation does not:
    it starts 17.2 A out and settles 12.8 A out, in a different maximum, still
    reporting a perfectly ordinary-looking score. That is the failure mode a
    user has to know about, and it is why a global search means many starts
    rather than a longer run of this.
    """
    target = simulate_map(atoms, 6.0)
    centre = atoms.mean(axis=0)
    turned = (atoms - centre) @ _rotation(90.0).T + centre
    result = fit_points_in_map(turned, target, max_steps=600)
    assert _rmsd(atoms, result.apply(turned)) > 5.0, (
        "the fit recovered from a 90 degree rotation; if the optimiser really "
        "became that robust, the warning in mapfit.py should be revised"
    )


def test_a_model_entirely_off_the_map_does_not_move(atoms):
    """No gradient anywhere means no direction to go, and it must not invent one.

    Sampling outside the box returns zero, so a model that misses the map
    completely sits in a flat field. Standing still is the right answer -- the
    danger would be drifting somewhere and reporting it.
    """
    target = simulate_map(atoms, 6.0)
    extent = float(np.linalg.norm(atoms.max(axis=0) - atoms.min(axis=0)))
    away = atoms + np.array([1.5 * extent, 0.0, 0.0])
    result = fit_points_in_map(away, target, max_steps=200)
    assert result.shift == pytest.approx(0.0, abs=1e-9)
    assert np.isnan(result.average) or result.average == pytest.approx(0.0)
