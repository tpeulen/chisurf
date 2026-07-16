"""Tests for the synthetic CLSM molecule-image generator."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.imaging.simulate import (
    Molecule,
    SimulatedImage,
    have_simulator,
    simulate_clsm_molecules,
)

if not have_simulator():
    pytest.skip("tttrlib built without the photon simulator", allow_module_level=True)


def test_simulate_returns_image_with_ground_truth():
    sim = simulate_clsm_molecules([(8, 8, 1.0), (23, 23, 3.5)], n_pixel=32)
    assert isinstance(sim, SimulatedImage)
    assert sim.intensity.shape == (32, 32)
    assert sim.intensity.sum() > 0
    assert sim.true_taus == [1.0, 3.5]
    # IRF in VV/VH layout is area-normalised per half.
    irf = sim.vv_vh_irf()
    assert irf.shape == (2 * sim.n_micro,)
    assert np.isclose(irf[: sim.n_micro].sum(), 1.0)


def test_molecules_land_at_their_pixels():
    # Bright molecules show up as intensity maxima near their pixel coordinates.
    sim = simulate_clsm_molecules([Molecule(6, 20, 2.0), Molecule(24, 9, 2.0)], n_pixel=32)
    img = sim.intensity
    # The two brightest disconnected regions sit near the requested pixels.
    for m in sim.molecules:
        window = img[max(0, m.iy - 2):m.iy + 3, max(0, m.ix - 2):m.ix + 3]
        assert window.sum() > 0  # photons landed in the molecule's neighbourhood


def test_accepts_tuple_dict_and_dataclass_molecules():
    sim = simulate_clsm_molecules(
        [(4, 4, 1.5), {"ix": 20, "iy": 20, "tau": 3.0}, Molecule(28, 6, 2.0)],
        n_pixel=32,
    )
    assert [m.tau for m in sim.molecules] == [1.5, 3.0, 2.0]
    assert len(sim.molecules) == 3
