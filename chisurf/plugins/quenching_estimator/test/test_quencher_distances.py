"""Distance and contact oracles for QuEst's legacy atom-contact trajectory."""

from __future__ import annotations

import math
import os
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pytest


def _simulation(trajectory):
    """Provide a defined walk without constructing an accessible volume."""
    from chisurf.plugins.quenching_estimator.core.dye_diffusion import SimulateDiffusion

    simulation = SimulateDiffusion.__new__(SimulateDiffusion)
    simulation._traj = trajectory
    simulation.verbose = False
    simulation._k_quench_grid_trace = None
    simulation._quencher = OrderedDict(TRP={"kQ": 2.0}, TYR={"kQ": 3.0})
    simulation._quencher_row_ranges = {"TRP": (0, 1), "TYR": (1, 2)}
    return simulation


def test_domain_import_does_not_require_numexpr():
    """Removing the accelerator restores imports even when it is unavailable."""
    environment = os.environ.copy()
    source = str(Path(__file__).resolve().parents[1])
    environment["PYTHONPATH"] = source + os.pathsep + environment.get("PYTHONPATH", "")
    script = """
import sys
sys.modules['numexpr'] = None
import numpy as np
from chisurf.plugins.quenching_estimator.core.dye_diffusion import SimulateDiffusion
simulation = SimulateDiffusion.__new__(SimulateDiffusion)
simulation._traj = np.array([[3.0, 4.0, 0.0]])
simulation.verbose = False
np.testing.assert_array_equal(simulation.get_quencher_distance2(np.zeros((1, 3))), [[25]])
"""
    result = subprocess.run(
        [sys.executable, "-c", script], env=environment, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_pythagorean_walk_preserves_squared_distances_and_contact_boundary(dtype):
    """Known 3–4–5 contacts distinguish squared distances and strict thresholds."""
    trajectory = np.array(
        [
            [0, 0, 0],
            [3, 4, 0],
            [3, 4, 12],
            [-3, 0, 4],
            [3, 3.999, 0],
            [3, 4.001, 0],
            [0, 0, 12],
        ],
        dtype=dtype,
    )
    quenchers = np.array([[0, 0, 0], [0, 0, 12]], dtype=dtype)
    expected = np.array(
        [
            [0, 25, 169, 25, 24.992001, 25.008001, 144],
            [144, 169, 25, 73, 168.992001, 169.008001, 0],
        ],
        dtype=np.float16,
    )
    simulation = _simulation(trajectory)
    distances = simulation.get_quencher_distance2(quenchers)
    assert distances.shape == (2, 7)
    assert distances.dtype == np.float16
    np.testing.assert_array_equal(distances, expected)
    simulation._quencher_distances = distances
    simulation.critical_distance = 5.0
    np.testing.assert_array_equal(
        simulation.quenched, [True, False, False, False, True, False, True]
    )
    np.testing.assert_array_equal(simulation.k_quench, [2, 0, 0, 0, 2, 0, 3])


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_brownian_walk_agrees_with_independent_scalar_distance_oracle(dtype):
    """A fixed diffusion walk keeps the stored half precision and contact mask."""
    diffusion, time_step = 0.15, 0.01
    rng = np.random.default_rng(20261006)
    trajectory = np.cumsum(rng.normal(0, math.sqrt(2 * diffusion * time_step), (512, 3)), axis=0)
    trajectory = trajectory.astype(dtype)
    quenchers = np.array([[0, 0, 0], [2, 1, -1]], dtype=dtype)
    # math.dist is an independent scalar Euclidean-distance implementation.
    oracle = np.array(
        [[math.dist(point, position) ** 2 for position in trajectory] for point in quenchers],
        dtype=np.float64,
    )
    simulation = _simulation(trajectory)
    distances = simulation.get_quencher_distance2(quenchers)
    np.testing.assert_array_equal(distances, oracle.astype(np.float16))
    quantization = np.abs(distances.astype(np.float64) - oracle)
    half_ulp = np.spacing(distances).astype(np.float64) / 2
    assert np.all(quantization <= half_ulp + 1e-7)
    simulation._quencher_distances = distances
    simulation.critical_distance = 1.75
    expected = np.sum(oracle.astype(np.float16) < 1.75**2, axis=0).astype(np.uint8)
    np.testing.assert_array_equal(simulation.quenched, expected)
    assert np.any(expected > 0) and np.any(expected == 0)


@pytest.mark.parametrize(("frames", "quenchers"), [(0, 2), (3, 0), (0, 0)])
def test_empty_distance_axes_keep_the_matrix_contract(frames, quenchers):
    """Empty frame or quencher inputs still return a correctly shaped matrix."""
    simulation = _simulation(np.zeros((frames, 3)))
    distances = simulation.get_quencher_distance2(np.zeros((quenchers, 3)))
    assert distances.shape == (quenchers, frames)
    assert distances.dtype == np.float16
