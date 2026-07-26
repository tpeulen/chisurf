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


def fit_rics(scan, n_lags: int = 10, region: str = "line"):
    """Fit ``N`` and ``D`` to the RICS map of *scan*.

    ``region`` selects which lags enter the fit, and it matters more than any
    other choice here:

    ``"line"``
        The slow-axis column only (``xi = 0``, ``1 <= |psi| <= n_lags``). This is
        where the diffusion information lives — neighbouring lines are a whole
        line time apart, neighbouring pixels only a dwell.
    ``"square"``
        The full ``(2 n + 1)^2`` block, zero lag excluded. The obvious choice,
        and a bad one.

    Measured over twelve simulations spanning ``D`` = 1 to 5 µm²/s, the square
    region recovers ``D`` with mean 1.10x and **sd 0.37**, swinging from 0.62x
    at ``D`` = 1 to 1.41x at ``D`` = 2; the line region gives mean **0.99x, sd
    0.13**. The square block is dominated by points that carry no information
    about ``D`` — the ``psi = 0`` row has no time lag at all, and the far lags
    are pure noise — and 440 mostly-uninformative points outvote the few that
    matter.

    The zero lag is excluded from both: it carries the shot-noise spike, which
    is not part of the correlation model.
    """
    from scipy.optimize import curve_fit

    correlation = np.asarray(compute_ics_carpet(scan.images).correlation[0], dtype=float)
    ny, nx = correlation.shape
    cy, cx = ny // 2, nx // 2
    xi, psi = np.meshgrid(
        np.arange(-n_lags, n_lags + 1), np.arange(-n_lags, n_lags + 1), indexing="xy"
    )
    block = correlation[cy - n_lags:cy + n_lags + 1, cx - n_lags:cx + n_lags + 1]
    if region == "line":
        keep = (xi == 0) & (np.abs(psi) >= 1)
    elif region == "square":
        keep = ~((xi == 0) & (psi == 0))
    else:
        raise ValueError(f"unknown region {region!r}; use 'line' or 'square'")

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


def test_neighbouring_pixels_dominate_the_signal():
    """A molecule is excited by the beam wherever it is, not only under it.

    With a 250 nm waist and 50 nm pixels most of the excitation comes from
    *outside* the pixel being scanned, so a simulation that lit only the current
    pixel would be wrong by more than it was right. Checked on the point-spread
    function directly, since it is a property of the optics rather than of any
    one scan.
    """
    import tttrlib

    focus = tttrlib.SimGrid.analytic_gaussian3d(0.25, 1.0, 1.0)
    centre = focus.at(0.0, 0.0, 0.0)
    # One pixel away the beam still excites ~92 % as strongly as at the centre.
    assert focus.at(0.05, 0.0, 0.0) / centre > 0.9
    # Three pixels away — a different pixel entirely — it is still substantial.
    assert focus.at(0.15, 0.0, 0.0) / centre > 0.4
    # Eight pixels away it has effectively vanished, which is why a grid a few
    # waists wide loses nothing.
    assert focus.at(0.40, 0.0, 0.0) / centre < 0.01


def test_coasting_must_stay_off_for_a_scan():
    """``per_molecule_skip`` is valid for a fixed focus and wrong for a raster.

    The optimisation decides a molecule is too far from the focus to matter and
    fast-forwards it. That holds when the focus stands still; in a scan the beam
    travels **to** the molecule, so the ones it skips are exactly the ones about
    to be scanned. This pins the damage — it is the kind of setting that looks
    like free speed and silently removes much of the signal.

    How much it removes depends on the configuration, so the assertion below
    is deliberately loose: measured at 11x fewer photons with a wide analytic
    focus, and 1.85x with the focus-sized voxel grid this function uses. The
    claim worth pinning is that coasting is *not* free, not a given factor.
    """
    import tttrlib

    from chisurf.core.fluorescence.imaging.simulate import simulate_clsm_diffusion

    honest = simulate_clsm_diffusion(2.0, n_pixel=32, n_frames=8,
                                     n_molecules=300, seed=7)

    # Build the same scan by hand, with coasting switched on.
    w_r, w_z, pixel_time, pixel_size = 0.25, 1.0, 2e-5, 0.05
    scanned = 32 * pixel_size
    box_xy = 0.5 * scanned * np.sqrt(2.0) + 4.0 * w_r
    sample = tttrlib.SimSystem()
    species = tttrlib.SimSpecies()
    species.D = 2.0
    species.q = tttrlib.VectorDouble([2e6])
    species.r0 = 0.0
    sample.add_species(species)
    sample.set_background([0.0])
    sample.set_box(box_xy, 4.0)
    sample.set_population(0, 300.0)
    settings = tttrlib.SimIntegrator()
    settings.dt = pixel_time
    settings.n_channels = 1
    settings.n_ph_max = 10 ** 12
    settings.seed_diffusion = 7
    settings.seed_emission = 8
    settings.per_molecule_skip = True
    engine = tttrlib.SimEngine(
        sample, tttrlib.SimGrid.gaussian3d(w_r, w_z, 4.0 * w_r, 4.0, 0.05, 1.0),
        tttrlib.VectorSimGrid([]), settings,
    )
    scanner = tttrlib.SimScanner.uniform(
        32, 32, pixel_time, pixel_size, pixel_size,
        -0.5 * scanned, -0.5 * scanned, tttrlib.SimMarkerConfig(), False,
    )
    for _ in range(8):
        engine.run_scan(scanner)
    event_type = np.asarray(engine.event_type())
    coasted = int((event_type == 0).sum())

    # Coasting throws photons away; the honest scan must collect materially
    # more. If this ever stops holding, coasting has been taught about the
    # scanner and the warning in simulate_clsm_diffusion can be revisited.
    assert honest.n_photons > 1.4 * coasted


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
    """RICS must read back the D that was scanned.

    Fitted over the line axis, recovery is essentially unbiased: mean 0.99x with
    sd 0.13 over twelve simulations spanning D = 1 to 5 um^2/s. The tolerance
    here covers that scatter with margin rather than papering over a systematic.
    """
    scan = simulate_clsm_diffusion(
        2.0, n_pixel=64, n_frames=60, n_molecules=400, seed=1
    )
    fit = fit_rics(scan)
    assert fit["diffusion_coefficient"] == pytest.approx(2.0, rel=0.35)


@pytest.mark.slow
def test_the_fit_region_is_what_decided_the_old_bias():
    """Including lags that carry no information about D corrupts the answer.

    The obvious fit region — the whole square block of lags — is dominated by
    points that say nothing about diffusion: the ``psi = 0`` row spans one pixel
    dwell, and the far lags have no correlation left. They outvote the line-axis
    column that does carry it, and the result swings with D (0.62x at D = 1,
    1.41x at D = 2) in a way that looks like a systematic bias when measured at
    a single D. This pins the difference so the region cannot quietly revert.
    """
    scan = simulate_clsm_diffusion(1.0, n_pixel=64, n_frames=60,
                                   n_molecules=400, seed=2)
    line = fit_rics(scan, region="line")["diffusion_coefficient"]
    square = fit_rics(scan, region="square")["diffusion_coefficient"]
    assert abs(line - 1.0) < abs(square - 1.0)


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
    """RICS cannot measure a D the scan never samples — and it does not say so.

    At 20 us per pixel a molecule with D = 0.05 um^2/s moves 2 nm between
    neighbouring pixels and 16 nm across a line, against a 250 nm waist, so the
    correlation is essentially the static focus and D is unidentifiable.

    **The failure is silent, and that is worth knowing.** Fitted over the line
    axis the result is not a refusal but a confident wrong number: 2.6x the
    truth at D = 0.05, and 15x at D = 0.02. (The old square region collapsed to
    its lower bound instead, which was less accurate everywhere else but at
    least looked broken.) Nothing in the fit announces this, which is precisely
    why the scan-precision planner exists — the working range has to be checked
    before the measurement, not after.
    """
    truth = 0.05
    scan = simulate_clsm_diffusion(truth, n_pixel=64, n_frames=40,
                                   n_molecules=400, seed=1)
    recovered = fit_rics(scan)["diffusion_coefficient"]
    # Wrong by more than a factor of two, while a resolvable D lands within ~15 %.
    assert recovered > 2.0 * truth

    resolvable = simulate_clsm_diffusion(5.0, n_pixel=64, n_frames=40,
                                         n_molecules=400, seed=1)
    assert fit_rics(resolvable)["diffusion_coefficient"] == pytest.approx(5.0, rel=0.35)
