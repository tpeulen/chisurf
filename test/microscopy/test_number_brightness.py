"""Number & Brightness: A/B against the reference implementation and known-answer simulations.

Two kinds of evidence:

* **A/B against PAM's MIA N&B** (``Do_NB.m``), run under Octave with the
  arithmetic extracted verbatim from the reference file and frozen in
  ``test/data/nb/pam_nb_reference.npz``; ``gen_pam_nb_reference.py`` beside it
  names the upstream revision and regenerates it. Covers the dead-time
  correction, the PCH, the γ-corrected ε and n, the three moment filters, the
  median filter, cross N&B and the starting histogram ranges.
* **Known answers on simulated stacks**: brightness and number recovered for a
  photon-counting and an analog detector, the cross brightness without its
  ``−1``, segmented detrending on a bleaching stack, NaN-aware smoothing, and a
  gate drawn on the brightness plane back-mapped onto pixels.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fluorescence.imaging import number_brightness as nbm

REFERENCE = pathlib.Path(__file__).resolve().parents[1] / "data" / "nb" / "pam_nb_reference.npz"
SMOOTHING = {1: "none", 2: "average", 3: "disk", 4: "gaussian"}


@pytest.fixture(scope="module")
def ref():
    """The frozen PAM N&B reference outputs."""
    return np.load(REFERENCE)


def _auto_case(ref, name, stack_key, index):
    nb_type, avg, radius, median, dead, pixel = ref[f"{name}__settings"]
    stack = ref[stack_key].astype(float)
    maps = nbm.nb_maps(
        stack,
        ddof=1,
        gamma=nbm.GAMMA_3D_GAUSSIAN,
        dead_time=dead,
        pixel_dwell=pixel * 1000.0,  # ns and µs -> ns
        smoothing=SMOOTHING[int(avg)],
        radius=radius,
        median=bool(median),
    )
    return maps, stack, (dead, pixel), index


@pytest.mark.parametrize(
    "name, stack_key, index",
    [
        ("top_plain", "ch1", 1),
        ("top_average_deadtime", "ch1", 1),
        ("bottom_disk_median_deadtime", "ch2", 3),
        ("cross_gaussian", "ch1", 1),
        ("cross_gaussian", "ch2", 3),
        ("top_radius_one", "ch1", 1),
    ],
)
def test_auto_nb_matches_pam(ref, name, stack_key, index):
    """Mean, σ², ε, n and the PCH equal PAM's for every filter / dead-time setting."""
    maps, stack, (dead, pixel), i = _auto_case(ref, name, stack_key, index)
    np.testing.assert_allclose(maps["mean"], ref[f"{name}__Int{i}"], rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(
        maps["variance"], ref[f"{name}__Std{i}"] ** 2, rtol=1e-11, atol=1e-11
    )
    np.testing.assert_allclose(maps["n"], ref[f"{name}__Num{i}"], rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(maps["epsilon"], ref[f"{name}__Eps{i}"], rtol=1e-10, atol=1e-10)
    corrected = nbm.dead_time_correct(stack, dead, pixel * 1000.0)
    np.testing.assert_array_equal(nbm.photon_counting_histogram(corrected), ref[f"{name}__PCH{i}"])


@pytest.mark.parametrize(
    "name, stack_key, index",
    [
        ("top_plain", "ch1", 1),
        ("top_average_deadtime", "ch1", 1),
        ("bottom_disk_median_deadtime", "ch2", 3),
    ],
)
def test_default_ranges_match_pams_starting_thresholds(ref, name, stack_key, index):
    """The outlier-trimmed ranges equal the thresholds PAM starts the histograms with.

    PAM shows intensity and brightness in kHz (counts per µs dwell × 10³), the
    number unscaled.
    """
    maps, _, (_, pixel), _ = _auto_case(ref, name, stack_key, index)
    ranges = nbm.nb_default_ranges(maps)
    hist = ref[f"{name}__Hist"]
    khz = 1e3 / pixel
    np.testing.assert_allclose(np.array(ranges["mean"]) * khz, hist[:2, 0], rtol=1e-10)
    np.testing.assert_allclose(ranges["n"], hist[:2, 1], rtol=1e-9)
    np.testing.assert_allclose(np.array(ranges["epsilon"]) * khz, hist[:2, 2], rtol=1e-9)


def test_cross_nb_matches_pam_without_filter(ref):
    """B_cross = C/√(⟨a⟩⟨b⟩) and N_cross = ⟨a⟩⟨b⟩/C equal PAM's cross channel.

    PAM's covariance divides by K (``ddof=0``) while its auto variance divides by
    K−1; ChiSurf uses one ``ddof`` for both, so the A/B sets it to PAM's cross
    choice. With a moment filter PAM smooths √C (complex where C < 0) and smooths
    the already smoothed means a second time — not reproduced, see the module.
    """
    a, b = ref["ch1"].astype(float), ref["ch2"].astype(float)
    cross = nbm.ccnb_maps(a, b, ddof=0)
    np.testing.assert_allclose(cross["mean"], ref["cross_plain__Int2"], rtol=1e-12)
    np.testing.assert_allclose(
        cross["covariance"], np.real(ref["cross_plain__Std2"] ** 2), rtol=1e-10, atol=1e-12
    )
    np.testing.assert_allclose(cross["N_cross"], ref["cross_plain__Num2"], rtol=1e-9)
    np.testing.assert_allclose(cross["B_cross"], ref["cross_plain__Eps2"], rtol=1e-10, atol=1e-12)


@pytest.mark.parametrize("px", [3, 4])
def test_moving_average_matches_the_reference_box_filter(ref, px):
    """The stack-correction box average centres an even box like the reference."""
    stack = ref["ch1"].astype(float)
    np.testing.assert_allclose(
        nbm.moving_average(stack, px, 1), ref[f"moving_average__{px}"], rtol=1e-12, atol=1e-12
    )


# --------------------------------------------------------------------------- simulations
def _simulate(rng, number, brightness, frames):
    """Photon counts of fluctuating molecule numbers: n ~ Poisson(N), k ~ Poisson(ε n)."""
    n = rng.poisson(number, size=(frames, *np.shape(number)))
    return rng.poisson(brightness * n).astype(float), n


def test_recovers_known_brightness_and_number():
    """Photon counting: ε = B − 1 and n = ⟨k⟩/ε recover the simulated values."""
    rng = np.random.default_rng(1)
    number, brightness = 4.0, 0.8
    stack, _ = _simulate(rng, np.full((48, 48), number), brightness, 400)
    maps = nbm.nb_maps(stack)
    assert np.median(maps["epsilon"]) == pytest.approx(brightness, rel=0.03)
    assert np.median(maps["n"]) == pytest.approx(number, rel=0.05)
    assert np.median(maps["B"]) == pytest.approx(1.0 + brightness, rel=0.02)
    # a Poisson-only (immobile) pixel has B = 1 and ε = 0
    flat = rng.poisson(5.0, size=(400, 48, 48)).astype(float)
    assert np.median(nbm.nb_maps(flat)["epsilon"]) == pytest.approx(0.0, abs=0.01)


def test_unbiased_variance_is_the_default():
    """With few frames the population variance biases B low by (K−1)/K."""
    rng = np.random.default_rng(2)
    frames = 10
    stack = rng.poisson(20.0, size=(frames, 200, 200)).astype(float)
    unbiased = nbm.nb_maps(stack)["B"].mean()
    biased = nbm.nb_maps(stack, ddof=0)["B"].mean()
    assert unbiased == pytest.approx(1.0, abs=0.01)
    assert biased == pytest.approx((frames - 1) / frames, abs=0.01)


def test_gamma_scales_brightness_and_number_inversely():
    """γ divides ε and multiplies n; their product stays ⟨k⟩."""
    rng = np.random.default_rng(3)
    stack, _ = _simulate(rng, np.full((16, 16), 3.0), 1.2, 200)
    plain = nbm.nb_maps(stack)
    corrected = nbm.nb_maps(stack, gamma=nbm.GAMMA_3D_GAUSSIAN)
    np.testing.assert_allclose(corrected["epsilon"], plain["epsilon"] * np.sqrt(8.0))
    np.testing.assert_allclose(corrected["n"], plain["n"] / np.sqrt(8.0))
    np.testing.assert_allclose(corrected["epsilon"] * corrected["n"], plain["mean"], rtol=1e-12)


def test_analog_detector_with_gradient_calibration():
    """Gain and offset come from a static gradient; then ε is recovered on analog data."""
    rng = np.random.default_rng(4)
    gain, offset, read_sd = 12.0, 100.0, 4.0

    def detect(photons):
        return gain * photons + offset + rng.normal(0.0, read_sd, size=photons.shape)

    gradient = np.tile(np.linspace(1.0, 30.0, 64), (32, 1))
    calibration = detect(rng.poisson(gradient, size=(300, 32, 64)).astype(float))
    cal_maps = nbm.nb_maps(calibration)
    cal = nbm.analog_calibration(cal_maps["mean"], cal_maps["variance"], read_variance=read_sd**2)
    assert cal["gain"] == pytest.approx(gain, rel=0.03)
    assert cal["offset"] == pytest.approx(offset, abs=3.0)

    brightness, number = 0.7, 5.0
    photons, _ = _simulate(rng, np.full((40, 40), number), brightness, 400)
    maps = nbm.nb_maps(
        detect(photons), gain=cal["gain"], offset=cal["offset"], read_variance=read_sd**2
    )
    assert np.median(maps["epsilon"]) == pytest.approx(brightness, rel=0.08)
    assert np.median(maps["n"]) == pytest.approx(number, rel=0.1)
    # the photon-counting formula on analog data is nowhere near
    assert np.median(nbm.nb_maps(detect(photons))["epsilon"]) > 5.0


def test_cross_brightness_has_no_minus_one():
    """Uncorrelated channels give B_cross ≈ 0, a doubly labelled species √(ε_a ε_b)."""
    rng = np.random.default_rng(5)
    shape, frames = (40, 40), 400
    a = rng.poisson(6.0, size=(frames, *shape)).astype(float)
    b = rng.poisson(4.0, size=(frames, *shape)).astype(float)
    independent = nbm.ccnb_maps(a, b)
    assert np.median(independent["B_cross"]) == pytest.approx(0.0, abs=0.02)
    # the auto brightness of the same channels is 1, the shot-noise floor
    assert np.median(nbm.nb_maps(a)["B"]) == pytest.approx(1.0, abs=0.02)

    eps_a, eps_b, number = 0.9, 0.4, 5.0
    n = rng.poisson(number, size=(frames, *shape))
    shared = nbm.ccnb_maps(
        rng.poisson(eps_a * n).astype(float), rng.poisson(eps_b * n).astype(float)
    )
    assert np.median(shared["B_cross"]) == pytest.approx(np.sqrt(eps_a * eps_b), rel=0.06)
    assert np.median(shared["N_cross"]) == pytest.approx(number, rel=0.1)


def _bleaching_stack(rng, brightness=1.0, number=20.0, frames=600, tau=400.0, shape=(24, 24)):
    t = np.arange(frames, dtype=float)
    numbers = number * np.exp(-t / tau)
    n = rng.poisson(numbers[:, None, None] * np.ones(shape))
    return rng.poisson(brightness * n).astype(float)


def test_detrending_recovers_brightness_on_a_bleaching_stack():
    """Only segmented detrending *with* mean restoration gives back ε.

    The raw stack's bleaching decay inflates σ²; the ICS immobile filter
    (subtract the pixel mean, add the total mean) does not touch a trend shared
    by all pixels; and detrending that drops the mean leaves ⟨k⟩ ≈ 0, which
    ``B = σ²/⟨k⟩`` cannot survive.
    """
    rng = np.random.default_rng(6)
    brightness = 1.0
    stack = _bleaching_stack(rng, brightness=brightness)
    raw = np.median(nbm.nb_maps(stack)["epsilon"])
    immobile = np.median(
        nbm.nb_maps(nbm.correct_stack(stack, subtract="pixel_mean", add="total_mean"))["epsilon"]
    )
    detrended = np.median(nbm.nb_maps(nbm.detrend_segmented(stack, 10))["epsilon"])
    no_mean = nbm.nb_maps(nbm.detrend_segmented(stack, 10, maintain_intensity=False))

    assert raw > 2.0 * brightness
    assert immobile > 2.0 * brightness
    assert detrended == pytest.approx(brightness, rel=0.1)
    assert abs(np.median(no_mean["mean"])) < 1e-9
    assert not np.isclose(np.median(no_mean["epsilon"]), brightness, rtol=0.5)


def test_stack_trends_is_the_per_pixel_least_squares_line():
    """The closed-form trend equals numpy.polyfit per pixel."""
    rng = np.random.default_rng(7)
    stack = rng.normal(size=(15, 3, 4)) + np.arange(15)[:, None, None] * rng.normal(size=(3, 4))
    slopes, intercepts = nbm.stack_trends(stack)
    for i in range(3):
        for j in range(4):
            p = np.polyfit(np.arange(15), stack[:, i, j], 1)
            assert slopes[i, j] == pytest.approx(p[0])
            assert intercepts[i, j] == pytest.approx(p[1])


def test_nan_aware_smoothing_does_not_leak_across_the_mask():
    """A thresholded map smooths inside its mask without darkening the edge."""
    image = np.full((40, 40), 5.0)
    image[:, 20:] = np.nan  # masked half (e.g. below an intensity threshold)
    smooth = nbm.gaussian_filter_nan(image, 2.0)
    assert np.all(np.isnan(smooth[:, 20:]))
    np.testing.assert_allclose(smooth[:, :20], 5.0, rtol=1e-12)
    # zero-filling first (the naive way) pulls the edge towards zero
    from scipy.ndimage import gaussian_filter

    naive = gaussian_filter(np.nan_to_num(image), 2.0)
    assert naive[20, 19] < 4.0


def test_gate_on_the_brightness_plane_back_maps_to_pixels():
    """A rectangle round the bright population selects exactly its pixels."""
    from chisurf.core.roi import RectangleROI

    rng = np.random.default_rng(8)
    brightness = np.where(np.arange(32)[None, :] < 16, 0.3, 1.5) * np.ones((32, 1))
    stack, _ = _simulate(rng, np.full((32, 32), 5.0), brightness, 300)
    maps = nbm.nb_maps(stack)
    gate = RectangleROI(0.0, 1.9, maps["mean"].max() + 1.0, 4.0)
    mask = nbm.nb_gate_mask(maps["mean"], maps["B"], gate)
    assert mask[:, 16:].mean() > 0.95
    assert mask[:, :16].mean() < 0.02
    hist = nbm.nb_histogram_2d(maps["mean"], maps["B"], (0.0, 12.0), (0.0, 4.0), bins=(24, 16))
    assert hist.shape == (16, 24)
    assert hist.sum() == pytest.approx(np.sum((maps["mean"] <= 12.0) & (maps["B"] <= 4.0)))
    thresholds = nbm.nb_threshold_mask(maps, {"B": (1.9, 4.0)})
    np.testing.assert_array_equal(thresholds, mask)


def test_pipeline_applies_corrections_then_nb():
    """``nb_pipeline`` = ``prepare_stack`` then ``nb_maps`` with the detrending degrees of freedom."""
    rng = np.random.default_rng(9)
    stack = _bleaching_stack(rng, frames=200, shape=(8, 8))
    params = {
        "detrend_segments": 5,
        "subtract": "moving_average",
        "add": "pixel_mean",
        "box_pixels": 1,
        "box_frames": 1,
        "gamma": 0.5,
    }
    expected = nbm.nb_maps(
        nbm.detrend_segmented(
            nbm.correct_stack(
                stack,
                subtract="moving_average",
                add="pixel_mean",
                subtract_box=(1, 1),
                add_box=(1, 1),
            ),
            5,
        ),
        gamma=0.5,
        ddof=10,  # two per detrending segment
    )
    got = nbm.nb_pipeline(stack, params)
    for key in expected:
        np.testing.assert_allclose(got[key], expected[key])


def test_pipeline_detrending_keeps_b_unbiased():
    """Segmented detrending costs two degrees of freedom per segment; the pipeline pays them.

    On a stationary Poisson stack (B = 1) ten-frame segments fitted with a line
    leave residuals whose K − 1 variance is (K − 2·segments)/(K − 1) ≈ 0.8 of the
    truth; dividing by K − 2·segments restores B = 1.
    """
    rng = np.random.default_rng(10)
    stack = rng.poisson(8.0, size=(40, 64, 64)).astype(float)
    naive = nbm.nb_maps(nbm.detrend_segmented(stack, 4))["B"].mean()
    corrected = nbm.nb_pipeline(stack, {"detrend_segments": 4})["B"].mean()
    assert naive == pytest.approx((40 - 8) / 39, abs=0.02)
    assert corrected == pytest.approx(1.0, abs=0.02)


def test_demo_photon_stream_round_trips_and_carries_its_truth(tmp_path):
    """The demo PTU reads back to exactly the simulated counts and gives the stated ε."""
    tttrlib = pytest.importorskip("tttrlib")
    from chisurf.core.fluorescence.imaging.pixel_maps import build_clsm_windowed
    from chisurf.plugins.microscopy.img_pixel_nb import demo

    cfg = {"n_pixel": 16, "n_frames": 400}
    info = demo.create_demo(tmp_path / "nb_demo.ptu", **cfg)
    counts = demo.simulate_counts({**demo.DEMO, **cfg})
    clsm = build_clsm_windowed(tttrlib.TTTR(info["path"]), [0], [])
    stack = np.asarray(clsm.get_intensity(), dtype=float)
    np.testing.assert_array_equal(stack, counts)
    maps = nbm.nb_maps(stack)
    assert maps["epsilon"][:, :8].mean() == pytest.approx(info["monomer"]["epsilon"], rel=0.1)
    assert maps["epsilon"][:, 8:].mean() == pytest.approx(info["dimer"]["epsilon"], rel=0.1)
    # same intensity on both halves: the intensity image cannot tell them apart
    assert maps["mean"][:, :8].mean() == pytest.approx(maps["mean"][:, 8:].mean(), rel=0.05)


def test_view_model_gates_back_map_the_dimers(tmp_path):
    """Run the tool's view-model on the demo, gate high brightness, get the dimer half."""
    pytest.importorskip("tttrlib")
    from chisurf.core.roi import RectangleROI
    from chisurf.plugins.microscopy.img_pixel_nb import demo
    from chisurf.plugins.microscopy.img_pixel_nb.gui.view_model import NBViewModel

    info = demo.create_demo(tmp_path / "nb_demo.ptu", n_pixel=16, n_frames=300)
    vm = NBViewModel()
    vm.filename = info["path"]
    vm.run()
    assert "median ε" in vm.results_text
    assert set(vm._by_window["ch0"]) >= {"B", "N", "epsilon", "n", "mean", "variance"}
    x0, x1, y0, y1 = vm.plane_extent()
    assert x1 > x0 and y1 > y0
    assert vm.plane_histogram().shape == (vm.plane_bins, vm.plane_bins)
    vm.gates.add(RectangleROI(0.0, 1.75, 100.0, 10.0, name="dimer"))
    mask = vm.gate_mask()
    assert mask[:, 8:].mean() > 0.8 and mask[:, :8].mean() < 0.2
    assert "Gates:" in vm.results_html()
    params = vm._window_params()
    assert params["pixel_dwell"] == 0.0 and params["gamma"] == 1.0
