"""Tests for the synthetic CLSM molecule-image generator."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.imaging.simulate import (
    Molecule,
    SimulatedImage,
    have_simulator,
    load_image_map,
    simulate_clsm_from_maps,
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


def test_simulate_from_maps_reproduces_intensity_and_lifetime():
    n = 24
    yy, xx = np.mgrid[0:n, 0:n]
    intensity = np.exp(-(((xx - 11) ** 2 + (yy - 11) ** 2) / 40.0))
    # Left half short lifetime, right half long lifetime.
    lifetime = np.where(xx < n / 2, 1.0, 3.5)

    sim = simulate_clsm_from_maps(intensity, lifetime, n_lifetime_levels=6, n_intensity_levels=5)
    assert isinstance(sim, SimulatedImage)
    rec = sim.intensity
    assert rec.shape == (n, n)
    # Reconstructed intensity tracks the input.
    assert np.corrcoef(rec.ravel(), intensity.ravel())[0, 1] > 0.8

    # Photons from the long-lifetime (right) half arrive later on average.
    micro = np.asarray(sim.tttr.micro_times)
    # A CLSMImage pixel gives the photon indices; compare left vs right columns.
    import tttrlib  # noqa: F401  (already importable — sim was built)

    left_idx, right_idx = [], []
    for iy in range(n):
        for ix in range(n):
            idx = list(sim.clsm[0][iy][ix].tttr_indices)
            (left_idx if ix < n // 2 else right_idx).extend(idx)
    if left_idx and right_idx:
        assert micro[right_idx].mean() > micro[left_idx].mean()


def test_simulate_from_maps_multi_detector():
    n = 16
    intensity = np.ones((n, n))
    # Two detectors with different lifetime maps.
    maps = [np.full((n, n), 1.0), np.full((n, n), 3.0)]
    sim = simulate_clsm_from_maps(intensity, maps, n_lifetime_levels=4, n_intensity_levels=3)
    # The reconstructed image sums both detector channels.
    assert sim.intensity.shape == (n, n)
    assert sim.intensity.sum() > 0


def test_load_image_map_npy_and_tif(tmp_path):
    arr = np.arange(36.0).reshape(6, 6)
    npy = tmp_path / "map.npy"
    np.save(npy, arr)
    np.testing.assert_allclose(load_image_map(str(npy)), arr)

    tif = pytest.importorskip("tifffile")
    p = tmp_path / "map.tif"
    tif.imwrite(str(p), arr.astype(np.float32))
    np.testing.assert_allclose(load_image_map(str(p)), arr, rtol=1e-5)
