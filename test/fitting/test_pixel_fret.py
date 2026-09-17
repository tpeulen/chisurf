"""Per-pixel (FLIM) FRET calibration on synthetic images.

A synthetic two-colour PIE image with a known per-pixel efficiency gradient and a
photon-starved border is corrected back to the ground-truth efficiency map, with
masking, stable un-mixing and integer photon-preserving per-source images checked.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.fret.pixel import corrected_es_image, pixel_source_photons


def _synthetic_flim(h=16, w=20, tot=800.0, alpha=0.08, delta=0.05, gamma=1.4):
    """Return (intensity[2,2,H,W], true_E[H,W]) for a left-to-right E gradient."""
    x = np.linspace(0.1, 0.8, w)[None, :] * np.ones((h, 1))  # E gradient across W
    e_true = x
    emission = np.array([[1.0, alpha], [0.0, gamma]])  # source x detector
    excitation = np.array([[1.0, delta], [0.0, 1.0]])  # laser x source

    # per-pixel true emission, then apply the emission matrix
    e_emit = np.zeros((2, 2, h, w))
    e_emit[0, 0] = (1 - e_true) * tot
    e_emit[0, 1] = e_true * tot + delta * tot
    e_emit[1, 1] = tot
    intensity = np.einsum("lkhw,km->lmhw", e_emit, emission)
    return intensity, e_true, excitation, emission


def test_pixel_efficiency_map_recovers_ground_truth():
    intensity, e_true, excitation, emission = _synthetic_flim()
    res = corrected_es_image(intensity, excitation, emission)
    e_img = np.asarray(res[(0, 1)]["E"])
    assert e_img.shape == e_true.shape
    assert np.allclose(e_img, e_true, atol=1e-9)


def test_min_counts_masks_photon_starved_pixels():
    intensity, e_true, excitation, emission = _synthetic_flim()
    # zero out a border region -> those pixels are photon-starved
    intensity[:, :, :, :3] = 0.0
    res = corrected_es_image(intensity, excitation, emission, min_counts=10.0)
    e_img = np.asarray(res[(0, 1)]["E"])
    assert np.all(np.isnan(e_img[:, :3]))  # starved border masked
    assert np.all(np.isfinite(e_img[:, 3:]))  # rest intact
    assert np.allclose(e_img[:, 3:], e_true[:, 3:], atol=1e-9)


def test_stable_unmix_bounded_on_noisy_illconditioned_image():
    """Ill-conditioned emission + shot noise: stable stays in range more than naive."""
    h, w = 12, 12
    excitation = np.array([[1.0, 0.04, 0.03], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    emission = np.array(
        [
            [1.0, 0.05, 0.05],
            [0.0, 1.00, 0.98],
            [0.0, 0.98, 1.00],
        ]
    )
    e01 = np.full((h, w), 0.35)
    e02 = np.full((h, w), 0.35)
    tot = 900.0
    e_emit = np.zeros((3, 3, h, w))
    e_emit[0, 0] = (1 - e01 - e02) * tot
    e_emit[0, 1] = e01 * tot + excitation[0, 1] * tot
    e_emit[0, 2] = e02 * tot + excitation[0, 2] * tot
    e_emit[1, 1] = tot
    e_emit[2, 2] = tot
    clean = np.einsum("lkhw,km->lmhw", e_emit, emission)
    rng = np.random.default_rng(0)
    noisy = clean + rng.normal(0.0, 25.0, size=clean.shape)

    naive = np.asarray(corrected_es_image(noisy, excitation, emission, pairs=[(0, 1)])[(0, 1)]["E"])
    stable = np.asarray(
        corrected_es_image(noisy, excitation, emission, pairs=[(0, 1)], unmix="stable")[(0, 1)]["E"]
    )

    def frac_out(e):
        return np.mean((e < -0.05) | (e > 1.05))

    assert frac_out(stable) < frac_out(naive)


def test_pixel_source_photons_shuffle_is_integer_and_preserving():
    d = np.array([[1.0, 0.1], [0.0, 1.0]])
    rng = np.random.default_rng(1)
    counts = rng.integers(0, 300, size=(2, 8, 9))  # (n_det, H, W)
    src = pixel_source_photons(counts, d, unmix="shuffle", seed=2)
    assert src.shape == (2, 8, 9)
    assert np.array_equal(src, np.rint(src))  # integer
    assert np.array_equal(src.sum(axis=0), counts.sum(axis=0))  # counts preserved per pixel

    stable = pixel_source_photons(counts, d, unmix="stable")
    assert np.all(stable >= 0)
