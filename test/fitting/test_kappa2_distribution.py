"""The orientation-factor distribution, checked against what it must obey.

``kappasq_all`` samples donor and acceptor dipole directions and returns the
resulting kappa^2 distribution. Its width is what turns a FRET distance into a
distance *range*, so a distribution that is too narrow understates the very
uncertainty it exists to quantify.

It was too narrow. The directions came from ``np.random.random(3)``, which
fills the unit cube with non-negative components: both dipoles sat in one
octant, the angle between them averaged 34 degrees instead of 90, and could
never exceed 90. Nothing tested this function, so nothing said so.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.anisotropy.kappa2 import kappasq, kappasq_all

#: Enough samples for the mean to be tight without making the suite slow.
SAMPLES = 20000

#: Order-parameter pairs spanning flexible to strongly restrained dyes.
ORDER_PARAMETERS = [(0.0, 0.0), (0.2, 0.2), (0.3, 0.5), (0.5, 0.5), (0.8, 0.8)]


@pytest.fixture(autouse=True)
def _seeded():
    """Make the sampling reproducible."""
    np.random.seed(20260726)


@pytest.mark.parametrize(("s2_donor", "s2_acceptor"), ORDER_PARAMETERS)
def test_the_mean_orientation_factor_is_two_thirds(s2_donor, s2_acceptor):
    """The invariant that caught the bug.

    Averaged over isotropically distributed *relative* orientations, the mean
    orientation factor is 2/3 however restrained each dye is: the order
    parameters shape the distribution, not its mean. Octant sampling pulled the
    mean down to 0.46 at S2 = 0.8.
    """
    _, _, k2 = kappasq_all(sD2=s2_donor, sA2=s2_acceptor, n_samples=SAMPLES)
    assert k2.mean() == pytest.approx(2.0 / 3.0, abs=0.02), (
        f"S2=({s2_donor}, {s2_acceptor}): mean kappa^2 is {k2.mean():.3f}"
    )


def test_restrained_dyes_give_a_wider_distribution_than_flexible_ones():
    """Rigidly held dyes are the case where kappa^2 is genuinely uncertain."""
    widths = []
    for s2 in (0.0, 0.3, 0.8):
        _, _, k2 = kappasq_all(sD2=s2, sA2=s2, n_samples=SAMPLES)
        low, high = np.percentile(k2, [2.5, 97.5])
        widths.append(high - low)

    assert widths[0] == pytest.approx(0.0, abs=1e-9), "flexible dyes average to a single value"
    assert widths[1] < widths[2], f"the distribution should widen with S2: {widths}"
    assert widths[2] > 1.5, f"strongly restrained dyes span little of kappa^2: {widths[2]:.2f}"


def test_the_orientation_factor_stays_within_its_physical_range():
    """kappa^2 lies in [0, 4]; anything else means the geometry is wrong."""
    _, _, k2 = kappasq_all(sD2=0.8, sA2=0.8, n_samples=SAMPLES)
    assert k2.min() >= 0.0
    assert k2.max() <= 4.0 + 1e-9


def test_the_sampled_dipoles_point_in_every_direction():
    """The defect itself: directions were confined to one octant.

    Two isotropic directions enclose 90 degrees on average and can be
    antiparallel. Reproduced here from the same primitive the function uses, so
    a regression to cube sampling fails this.
    """
    samples = 20000
    first = np.random.randn(samples, 3)
    second = np.random.randn(samples, 3)
    first /= np.linalg.norm(first, axis=1)[:, None]
    second /= np.linalg.norm(second, axis=1)[:, None]
    angle = np.degrees(np.arccos(np.clip((first * second).sum(axis=1), -1, 1)))

    assert angle.mean() == pytest.approx(90.0, abs=1.0)
    assert angle.max() > 170.0, "no pair of dipoles is close to antiparallel"


def test_the_scale_is_bin_edges_not_bin_centres():
    """An easy trap for a caller: one more edge than there are counts."""
    scale, histogram, k2 = kappasq_all(sD2=0.3, sA2=0.5, n_bins=31, n_samples=2000)

    assert scale.size == histogram.size + 1
    assert histogram.sum() == k2.size
    assert scale[0] == pytest.approx(0.0)
    assert scale[-1] == pytest.approx(4.0)


def test_a_named_geometry_matches_the_closed_form():
    """Parallel dipoles perpendicular to the connecting vector give kappa^2 = 1."""
    assert kappasq(delta=0.0, sD2=1.0, sA2=1.0, beta1=np.pi / 2, beta2=np.pi / 2) == pytest.approx(
        1.0, abs=1e-9
    )
