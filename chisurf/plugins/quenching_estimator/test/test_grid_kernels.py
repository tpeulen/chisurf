"""Equivalence and behaviour tests for the AV grid kernels.

``subav``, ``slow_factor_grid`` and ``additive_factor_grid`` only visit the
voxels inside each centre's bounding box. These tests pin them against a
straightforward reference implementation that tests every voxel against every
centre, which is what the kernels replaced.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.av import (
    additive_factor_grid,
    slow_factor_grid,
    subav,
)


def _reference_masks(ng, dg, radii, centers, origin):
    """Boolean mask per centre, using the naive all-voxels-all-centres test."""
    offset = (ng - 1) // 2
    masks = []
    for center, radius in zip(centers, radii):
        # `floor`, matching `quest.core.av.grid_center_index`'s contract. This
        # said `int()` until 2026-07-28 -- a straight copy of the kernel, which
        # made this a self-comparison rather than a reference: it could not
        # detect that `int()` truncates toward zero and so rounds *up* for a
        # centre on the negative side of the origin, disagreeing by one voxel
        # per axis with every other index map in the project.
        ix0 = math.floor((center[0] - origin[0]) / dg) + offset
        iy0 = math.floor((center[1] - origin[1]) / dg) + offset
        iz0 = math.floor((center[2] - origin[2]) / dg) + offset
        radius_idx = int(radius / dg)
        grid = np.indices((ng, ng, ng))
        d2 = (grid[0] - ix0) ** 2 + (grid[1] - iy0) ** 2 + (grid[2] - iz0) ** 2
        masks.append(d2 < radius_idx * radius_idx)
    return masks


def _reference_subav(density, ng, dg, radii, centers, origin):
    masks = _reference_masks(ng, dg, radii, centers, origin)
    inside = np.zeros((ng, ng, ng), dtype=bool)
    for mask in masks:
        inside |= mask
    result = density.copy()
    result[~inside] = 0
    return result


def _reference_slow_factor_grid(density, ng, dg, radii, centers, origin, factors):
    masks = _reference_masks(ng, dg, radii, centers, origin)
    grid = np.ones((ng, ng, ng), dtype=np.float64)
    for mask, factor in zip(masks, factors):
        grid[mask] *= factor
    grid[density == 0] = 1.0
    return grid


def _reference_additive_grid(density, ng, dg, radii, centers, origin, values):
    masks = _reference_masks(ng, dg, radii, centers, origin)
    grid = np.zeros((ng, ng, ng), dtype=np.float64)
    for mask, value in zip(masks, values):
        grid[mask] += value
    grid[density == 0] = 0.0
    return grid


@pytest.fixture(params=[0.4, 0.5, 1.0], ids=lambda dg: f"dg{dg}")
def scenario(request):
    """A filled grid with centres placed at awkward positions."""
    dg = request.param
    ng = 31
    rng = np.random.default_rng(20240726)
    density = (rng.random((ng, ng, ng)) > 0.25).astype(np.uint8)
    origin = np.array([1.25, -3.5, 0.75])
    # Centres inside the grid, on the edge, and fully outside it.
    centers = np.array(
        [
            origin + np.array([0.0, 0.0, 0.0]),
            origin + np.array([2.3, -1.7, 3.1]),
            origin + np.array([-4.6, 2.2, -2.8]),
            origin + np.array([100.0, 0.0, 0.0]),
            origin + np.array([0.0, ng * dg / 2.0, 0.0]),
        ]
    )
    radii = np.array([3.0, 2.0, 4.5, 5.0, 2.5])
    return density, ng, dg, radii, centers, origin


@pytest.mark.needs_av
def test_subav_matches_reference(scenario):
    density, ng, dg, radii, centers, origin = scenario
    assert np.array_equal(
        subav(density, ng, dg, radii, centers, origin),
        _reference_subav(density, ng, dg, radii, centers, origin),
    )


def test_slow_factor_grid_matches_reference(scenario):
    density, ng, dg, radii, centers, origin = scenario
    factors = np.array([0.1, 0.5, 0.9, 0.2, 0.05])
    assert np.allclose(
        slow_factor_grid(density, ng, dg, radii, centers, origin, factors),
        _reference_slow_factor_grid(density, ng, dg, radii, centers, origin, factors),
    )


def test_additive_factor_grid_matches_reference(scenario):
    density, ng, dg, radii, centers, origin = scenario
    values = np.array([3.5, 2.0, 0.0, 1.67, 1.0])
    assert np.allclose(
        additive_factor_grid(density, ng, dg, radii, centers, origin, values),
        _reference_additive_grid(density, ng, dg, radii, centers, origin, values),
    )


def test_overlapping_centres_accumulate():
    """Overlapping quenchers add their rates; stickiness multiplies."""
    ng = 21
    dg = 0.5
    density = np.ones((ng, ng, ng), dtype=np.uint8)
    origin = np.zeros(3)
    centers = np.array([origin, origin])
    radii = np.array([2.0, 2.0])

    additive = additive_factor_grid(density, ng, dg, radii, centers, origin, np.array([1.5, 2.5]))
    assert additive[(ng - 1) // 2, (ng - 1) // 2, (ng - 1) // 2] == pytest.approx(4.0)

    multiplied = slow_factor_grid(density, ng, dg, radii, centers, origin, np.array([0.5, 0.5]))
    assert multiplied[(ng - 1) // 2, (ng - 1) // 2, (ng - 1) // 2] == pytest.approx(0.25)


def test_zero_value_centres_do_not_contribute():
    ng = 15
    dg = 0.5
    density = np.ones((ng, ng, ng), dtype=np.uint8)
    origin = np.zeros(3)
    centers = np.array([origin])
    grid = additive_factor_grid(density, ng, dg, np.array([3.0]), centers, origin, np.array([0.0]))
    assert np.count_nonzero(grid) == 0


def test_empty_voxels_are_left_untouched():
    ng = 15
    dg = 0.5
    density = np.zeros((ng, ng, ng), dtype=np.uint8)
    origin = np.zeros(3)
    centers = np.array([origin])
    assert (
        np.count_nonzero(
            additive_factor_grid(density, ng, dg, np.array([5.0]), centers, origin, np.array([2.0]))
        )
        == 0
    )
    assert np.all(
        slow_factor_grid(density, ng, dg, np.array([5.0]), centers, origin, np.array([0.1])) == 1.0
    )


class TestUnsupportedSimulationTypesFailLegibly:
    """`simulation_type="AV3"` used to raise `NameError` from inside a run.

    `calculate3R` was deleted in 7ecf209 and the call site survived, so a
    project field that a scan can set reached an undefined name eight frames
    down. Neither backend has ever implemented AV3: the IMP.bff path ignores
    `simulation_type` and `calculate1R` drives `ll.dyeDensityAV1`.
    """

    def test_av3_is_rejected_by_name(self) -> None:
        """And rejected *before* the structure is read — `structure=None` here
        would fail on any later line, so this also pins the ordering."""
        import pytest

        from chisurf.plugins.quenching_estimator.core.av import AV

        with pytest.raises(ValueError, match="AV1 only"):
            AV(None, attachment_atom_index=0, simulation_type="AV3")

    def test_av1_is_accepted_in_either_case(self) -> None:
        """The guard must not become a new way to break a valid project."""
        import pytest

        from chisurf.plugins.quenching_estimator.core.av import AV

        for value in ("AV1", "av1"):
            # Gets past the guard and fails later, on the null structure.
            with pytest.raises(Exception) as excinfo:
                AV(None, attachment_atom_index=0, simulation_type=value)
            assert "AV1 only" not in str(excinfo.value)
