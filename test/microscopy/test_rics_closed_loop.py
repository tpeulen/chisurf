"""Simulate a scan of diffusing molecules, then recover D with RICS.

This is the closed loop that makes an image-correlation result believable: a
population with a **known** diffusion coefficient is raster-scanned by the photon
simulator, and the RICS model has to read that coefficient back out of the
resulting images. Nothing else in the ICS stack checks the *physics* end to end
— the parity tests check the correlator against a reference implementation, and
the precision tests check the estimator's variance, but neither would notice if
the simulated sample never moved.

That is not hypothetical. The scan produces **bit-identical images for every
diffusion coefficient** unless the emitters are explicitly marked mobile, which
is the default nobody sets, and the failure looks exactly like a working
simulation until two of them are compared.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.experiments.ics.ics_core import compute_ics_carpet
from chisurf.core.fluorescence.imaging import have_simulator, simulate_clsm_diffusion
from chisurf.core.models.ics.models import image_correlation

pytestmark = pytest.mark.skipif(
    not have_simulator(), reason="tttrlib was built without the photon simulator"
)


def fit_rics(scan, n_lags: int = 10):
    """Fit ``N`` and ``D`` to the RICS map of *scan*.

    The zero lag is excluded: it carries the shot-noise spike, which is not part
    of the correlation model and would otherwise dominate a least-squares fit.
    """
    from scipy.optimize import curve_fit

    correlation = np.asarray(compute_ics_carpet(scan.images).correlation[0], dtype=float)
    ny, nx = correlation.shape
    cy, cx = ny // 2, nx // 2
    xi, psi = np.meshgrid(
        np.arange(-n_lags, n_lags + 1), np.arange(-n_lags, n_lags + 1), indexing="xy"
    )
    block = correlation[cy - n_lags:cy + n_lags + 1, cx - n_lags:cx + n_lags + 1]
    keep = ~((xi == 0) & (psi == 0))

    def model(_, n, d, offset):
        return image_correlation(
            xi[keep].ravel(), psi[keep].ravel(), 0.0, n=n,
            diffusion_coefficient=d, offset=offset,
            pixel_duration=scan.pixel_time * 1e6,     # us
            line_duration=scan.line_time * 1e3,       # ms
            pixel_size=scan.pixel_size * 1e3,         # nm
            w_r=scan.w_r, w_z=scan.w_z, two_d=False,
        )

    popt, _ = curve_fit(
        model, None, block[keep].ravel(), p0=[5.0, 1.0, 0.0],
        bounds=([0.01, 1e-3, -1.0], [1e5, 1e3, 1.0]), maxfev=40000,
    )
    return {"n": float(popt[0]), "diffusion_coefficient": float(popt[1])}


# ──────────────────────────────────────────────────────────────────────────────
# The simulation has to actually move
# ──────────────────────────────────────────────────────────────────────────────
def test_the_images_depend_on_the_diffusion_coefficient():
    """The regression that matters most: D must change the scan at all.

    ``add_fluorophore`` takes ``mobile=False`` by default, and an immobile
    molecule ignores ``D`` completely — so a scan built the obvious way returns
    identical images for every diffusion coefficient. Every other test here
    would still pass on such a simulation, because they only compare a fit
    against itself.
    """
    slow = simulate_clsm_diffusion(1.0, n_pixel=32, n_frames=12, n_molecules=200, seed=3)
    fast = simulate_clsm_diffusion(20.0, n_pixel=32, n_frames=12, n_molecules=200, seed=3)
    assert not np.array_equal(slow.images, fast.images)

    # And different in the specific way RICS reads. The signal is the *asymmetry*
    # between the two scan axes: neighbouring pixels are 20 us apart, neighbouring
    # lines 0.64 ms, so faster diffusion decorrelates along the slow axis while
    # leaving the fast axis almost untouched. Pixel-to-pixel variance is the wrong
    # thing to look at — it goes *up* with D, because less spatial smoothing
    # happens, which is the opposite of the naive expectation.
    def asymmetry(scan):
        correlation = np.asarray(compute_ics_carpet(scan.images).correlation[0], float)
        cy, cx = (dim // 2 for dim in correlation.shape)
        return correlation[cy + 4, cx] / correlation[cy, cx + 4]

    assert asymmetry(fast) < asymmetry(slow)


def test_the_scan_is_stationary():
    """The sample must not run out: every correlation analysis assumes it does not.

    A fixed set of emitters diffuses out of the box and dies, so the intensity
    decays through the acquisition. The open-volume population is replenished at
    the boundary, so the first and last frames have the same mean.
    """
    scan = simulate_clsm_diffusion(2.0, n_pixel=32, n_frames=20, n_molecules=300, seed=4)
    first = scan.images[:5].mean()
    last = scan.images[-5:].mean()
    assert last == pytest.approx(first, rel=0.2), (
        f"intensity drifted from {first:.2f} to {last:.2f} counts/px — "
        "the population is not stationary"
    )


def test_the_timing_is_in_real_seconds():
    """The scan timing must be the physical timing, not scanner units.

    Diffusion is nothing but the time axis: a molecule steps ``sqrt(2 D dt)``
    per integrator window, so a dwell that does not mean seconds makes ``D``
    meaningless. The line and frame times must follow from the dwell exactly.
    """
    scan = simulate_clsm_diffusion(1.0, n_pixel=32, n_frames=4, pixel_time=5e-6,
                                   n_molecules=100, seed=5)
    assert scan.pixel_time == pytest.approx(5e-6)
    assert scan.line_time == pytest.approx(32 * 5e-6)
    assert scan.frame_time == pytest.approx(32 * 32 * 5e-6)


def test_photons_and_not_scanner_markers_form_the_image():
    """A raster scan emits more markers than photons; only photons are counts.

    One pixel marker per pixel plus line and frame markers can outnumber the
    photons several times over, and binning the raw record stream would build an
    image that is mostly scanner bookkeeping — a flat, perfectly periodic
    pattern whose correlation says nothing about the sample.
    """
    scan = simulate_clsm_diffusion(1.0, n_pixel=32, n_frames=4, n_molecules=200, seed=6)
    # If markers had been counted, every pixel would carry at least one.
    assert (scan.images == 0).any()
    assert scan.n_photons == int(scan.images.sum())


def test_an_impossible_setting_is_refused():
    """Nonsense in, error out — not a scan that quietly means nothing."""
    with pytest.raises(ValueError, match="cannot be negative"):
        simulate_clsm_diffusion(-1.0, n_pixel=16, n_frames=2)
    with pytest.raises(ValueError, match="positive number of seconds"):
        simulate_clsm_diffusion(1.0, pixel_time=0.0, n_pixel=16, n_frames=2)


# ──────────────────────────────────────────────────────────────────────────────
# The loop itself
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.slow
def test_rics_recovers_the_simulated_diffusion_coefficient():
    """RICS must read back the D that was scanned, to within a factor.

    The tolerance is wide on purpose and reflects what was measured rather than
    what would be nice: over four seeds at D = 2 um^2/s the recovered value is
    biased high by about 35 % with a seed-to-seed spread of 12 %, and the bias
    does not come from the axial extent of the box (quadrupling ``box_z`` moves
    it from 1.40 to 1.31). That residual is an open question recorded in the
    known-issues list; this test pins the loop as it stands, so a change that
    breaks the recovery — or fixes the bias — is visible immediately.
    """
    scan = simulate_clsm_diffusion(
        2.0, n_pixel=64, n_frames=60, n_molecules=400, seed=1
    )
    fit = fit_rics(scan)
    assert fit["diffusion_coefficient"] == pytest.approx(2.0, rel=0.6)


@pytest.mark.slow
def test_a_faster_sample_reads_back_as_faster():
    """Ordering is the weakest useful claim, and it must hold.

    Whatever the absolute bias, a sample that diffuses four times faster has to
    produce a larger fitted D. If this fails the scan is not carrying transport
    information at all, and the absolute test above is passing by luck.
    """
    slow = fit_rics(simulate_clsm_diffusion(1.0, n_pixel=64, n_frames=60,
                                            n_molecules=400, seed=1))
    fast = fit_rics(simulate_clsm_diffusion(4.0, n_pixel=64, n_frames=60,
                                            n_molecules=400, seed=1))
    assert fast["diffusion_coefficient"] > slow["diffusion_coefficient"]


@pytest.mark.slow
def test_a_sample_too_slow_for_the_scan_is_not_resolvable():
    """RICS cannot measure a D the scan never samples, and should not pretend to.

    At 20 us per pixel a molecule with D = 0.05 um^2/s moves 2 nm between
    neighbouring pixels and 16 nm across a line, against a 250 nm waist — the
    correlation is the static focus and D is unidentifiable. The fit runs into
    its lower bound rather than returning a plausible-looking number, which is
    the honest outcome and the reason the scan-precision planner exists.
    """
    scan = simulate_clsm_diffusion(0.05, n_pixel=64, n_frames=40,
                                   n_molecules=400, seed=1)
    fit = fit_rics(scan)
    assert fit["diffusion_coefficient"] < 0.05
