"""A click is a seed; the fit is the answer.

The whole reason picking runs a Gaussian rather than dropping a fixed circle
where the cursor was is that a click is a pixel or two approximate, and a region
built on the click inherits that error as a biased centroid and a brightness
measured over the wrong pixels. So the tests that matter here plant a spot at a
known place and width, click *beside* it, and demand the fit come back to the
spot — and demand that a click on nothing is refused rather than answered.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.microscopy.spot_finder.core.picking import (
    fit_gaussian_spot,
    spot_roi,
)


def _field(cy=20.0, cx=24.0, sigma_y=1.8, sigma_x=1.8, amplitude=300.0,
           background=5.0, shape=(48, 56)):
    """Return a field holding one Gaussian spot at a known place and width."""
    rows, cols = np.indices(shape)
    return background + amplitude * np.exp(
        -0.5 * (((rows - cy) / sigma_y) ** 2 + ((cols - cx) / sigma_x) ** 2)
    )


def test_a_click_beside_the_spot_still_finds_the_spot():
    """The point of fitting: the click is off by two pixels, the answer is not."""
    image = _field(cy=20.0, cx=24.0)

    spot = fit_gaussian_spot(image, 22, 26)

    assert spot.success, spot.reason
    assert spot.y == pytest.approx(20.0, abs=0.15)
    assert spot.x == pytest.approx(24.0, abs=0.15)


def test_the_fit_reports_the_width_it_measured():
    image = _field(sigma_y=1.2, sigma_x=2.6, shape=(48, 56))

    spot = fit_gaussian_spot(image, 20, 24, window=15)

    assert spot.success, spot.reason
    assert spot.sigma_y == pytest.approx(1.2, rel=0.15)
    assert spot.sigma_x == pytest.approx(2.6, rel=0.15)
    # And the single-number summary sits between them.
    assert spot.sigma_y < spot.sigma < spot.sigma_x


def test_the_amplitude_and_background_are_separated():
    image = _field(amplitude=300.0, background=17.0)

    spot = fit_gaussian_spot(image, 20, 24, window=15)

    assert spot.success, spot.reason
    assert spot.background == pytest.approx(17.0, abs=2.0)
    assert spot.amplitude == pytest.approx(300.0, rel=0.1)


def test_a_click_on_empty_background_is_refused_with_a_reason():
    """An ellipse placed where a fit failed looks like one placed where it did not."""
    image = np.full((48, 56), 5.0)

    spot = fit_gaussian_spot(image, 20, 24)

    assert not spot.success
    assert spot.reason


def test_a_click_that_locks_onto_a_different_spot_is_refused():
    """Clicking between two spots must not silently answer for the wrong one."""
    rows, cols = np.indices((48, 80))
    image = np.full((48, 80), 5.0)
    for cx in (20.0, 60.0):
        image += 300.0 * np.exp(-0.5 * (((rows - 24) / 1.8) ** 2 + ((cols - cx) / 1.8) ** 2))

    # A click far from both, with a window wide enough to see one of them.
    spot = fit_gaussian_spot(image, 24, 40, window=41, max_shift=3.0)

    assert not spot.success
    assert "locked onto something else" in spot.reason


def test_a_click_outside_the_image_is_refused():
    spot = fit_gaussian_spot(_field(), 500, 500)

    assert not spot.success
    assert "outside the image" in spot.reason


def test_a_flat_window_does_not_produce_a_region():
    """The failure mode a fixed-radius circle would have hidden."""
    image = np.full((48, 56), 5.0)
    image[40:44, 50:54] = 300.0        # a spot, but far from the click

    spot = fit_gaussian_spot(image, 10, 10, window=9)

    assert not spot.success


def test_the_region_is_the_fitted_ellipse_not_a_fixed_circle():
    image = _field(cy=20.0, cx=24.0, sigma_y=1.2, sigma_x=2.6)

    spot = fit_gaussian_spot(image, 20, 24, window=15)
    roi = spot_roi(spot, "picked 1")

    assert spot.success, spot.reason
    assert roi.name == "picked 1"
    # Elongated the way the spot is, and centred on the fit.
    assert roi.rx > roi.ry
    mask = roi.to_mask(image.shape)
    ys, xs = np.nonzero(mask)
    assert ys.mean() == pytest.approx(20.0, abs=0.5)
    assert xs.mean() == pytest.approx(24.0, abs=0.5)


def test_picking_through_the_view_model_adds_a_region(tmp_path):
    """End to end: the gesture the GUI offers, without the GUI."""
    from chisurf.plugins.microscopy.spot_finder.core.spots import SpotFinderSettings, detect
    from chisurf.plugins.microscopy.spot_finder.gui.view_model import SpotFinderViewModel

    rows, cols = np.indices((48, 56))
    image = np.full((48, 56), 3.0)
    image += 300.0 * np.exp(-0.5 * (((rows - 10) / 1.6) ** 2 + ((cols - 12) / 1.6) ** 2))
    # A second, much fainter spot the threshold will miss — the reason to pick.
    image += 25.0 * np.exp(-0.5 * (((rows - 34) / 1.6) ** 2 + ((cols - 40) / 1.6) ** 2))

    vm = SpotFinderViewModel()
    vm.results = [detect(image, SpotFinderSettings(clear_border=False))]
    found = vm.results[0].n_regions

    vm.picked_point = (0, 35, 41)          # a click beside the faint spot
    vm.pick_spot()

    assert len(vm.picked) == 1, vm.status_text
    assert vm.picked[0].y == pytest.approx(34.0, abs=0.5)

    vm.add_picked_to_detection()
    assert vm.results[0].n_regions == found + 1
    assert not vm.picked, "adding consumes the picks"


def test_a_pick_that_fails_says_so_and_adds_nothing():
    from chisurf.plugins.microscopy.spot_finder.core.spots import SpotFinderSettings, detect
    from chisurf.plugins.microscopy.spot_finder.gui.view_model import SpotFinderViewModel

    image = _field()
    vm = SpotFinderViewModel()
    vm.results = [detect(image, SpotFinderSettings(clear_border=False))]

    vm.picked_point = (0, 45, 5)           # empty corner
    vm.pick_spot()

    assert not vm.picked
    assert "No spot picked" in vm.status_text


def test_a_pick_does_not_claim_pixels_a_detected_region_already_owns():
    """A pick is a spot the detector missed, not a second claim on one it found."""
    from chisurf.plugins.microscopy.spot_finder.core.spots import SpotFinderSettings, detect
    from chisurf.plugins.microscopy.spot_finder.gui.view_model import SpotFinderViewModel

    image = _field(cy=20.0, cx=24.0)
    vm = SpotFinderViewModel()
    vm.results = [detect(image, SpotFinderSettings(clear_border=False))]
    before = vm.results[0].n_regions
    labels_before = vm.results[0].labels.copy()

    vm.picked_point = (0, 20, 24)          # right on the region already found
    vm.pick_spot()
    vm.add_picked_to_detection()

    assert vm.results[0].n_regions == before
    # The detected region keeps every pixel it had.
    assert ((labels_before > 0) & (vm.results[0].labels == 0)).sum() == 0
