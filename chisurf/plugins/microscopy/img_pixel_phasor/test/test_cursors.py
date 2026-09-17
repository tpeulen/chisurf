"""Phasor cursors, and the orientation of the cloud they are drawn on.

A phasor cursor is a region: an ellipse round a lifetime cluster, a polygon
round one that is neither round nor elliptical, several combined. Until the
shared region GUI existed this tool had **no interactive cursor at all** — the
ellipse lived in the analysis API and nothing could draw one.

The orientation test is the more important of the two. ``np.histogram2d`` puts
its first argument on axis 0 while images are drawn row-major, so without a
transpose the density is mirrored about the diagonal. A phasor cloud mirrored
that way still looks like a phasor cloud — but it no longer sits on the
universal semicircle, and every lifetime read off it is wrong.
"""

from __future__ import annotations

import numpy as np
import pytest


def _two_lifetime_model(frequency_mhz=80.0, tau_a=3.2, tau_b=1.6):
    """A frame whose pixels carry one of two lifetimes, plus the true phasors."""
    from chisurf.plugins.microscopy.img_pixel_phasor.gui.view_model import (
        PhasorImgViewModel,
    )

    rng = np.random.default_rng(7)
    ny = nx = 64
    yy, xx = np.mgrid[0:ny, 0:nx]
    left = xx < nx // 2
    tau = np.where(left, tau_a, tau_b)
    photons = rng.poisson(400.0, (ny, nx)).astype(float)

    omega = 2.0 * np.pi * frequency_mhz * 1e-3  # rad/ns
    wt = omega * tau
    g = 1.0 / (1.0 + wt**2)
    s = wt / (1.0 + wt**2)
    noise = 0.005
    g = g + rng.normal(0, noise, (ny, nx))
    s = s + rng.normal(0, noise, (ny, nx))

    vm = PhasorImgViewModel()
    vm._by_window = {"": {"g": g, "s": s, "n_photons": photons, "intensity": photons}}
    vm.display_window = ""

    def phasor_of(t):
        w = omega * t
        return 1.0 / (1.0 + w**2), w / (1.0 + w**2)

    return vm, phasor_of(tau_a), phasor_of(tau_b), left


def _peak_coordinates(density, g_range, s_range):
    """Return the ``(g, s)`` of the densest bin, read row-major."""
    rows, cols = density.shape
    j, i = np.unravel_index(int(np.argmax(density)), density.shape)
    g = g_range[0] + (i + 0.5) * (g_range[1] - g_range[0]) / cols
    s = s_range[0] + (j + 0.5) * (s_range[1] - s_range[0]) / rows
    return g, s


def test_the_density_is_drawn_with_g_horizontal_and_lands_on_the_semicircle():
    """The cloud of a single-exponential sample must sit on the universal circle.

    That is the check with teeth: a transposed density still looks like a
    phasor cloud, but it leaves the semicircle — the one curve every phasor
    plot is read against.
    """
    vm, (ga, sa), (gb, sb), _ = _two_lifetime_model()
    density = vm.phasor_histogram_map(bins=200)

    g, s = _peak_coordinates(density, vm.PHASOR_G_RANGE, vm.PHASOR_S_RANGE)
    assert (g, s) == pytest.approx((ga, sa), abs=0.02) or (g, s) == pytest.approx(
        (gb, sb), abs=0.02
    )

    # On the semicircle of centre (0.5, 0) and radius 0.5, to within a bin.
    assert np.hypot(g - 0.5, s) == pytest.approx(0.5, abs=0.02)


def test_the_movie_frames_use_the_same_orientation_as_the_static_map():
    """Two sources for one plot; disagreeing about axes is how one rots."""
    import inspect

    from chisurf.plugins.microscopy.img_pixel_phasor.gui.view_model import (
        PhasorImgViewModel,
    )

    source = inspect.getsource(PhasorImgViewModel.phasor_histogram_frames)
    assert "hist.T" in source, "the movie stack must transpose like the static map"


# --- the cursors --------------------------------------------------------------
def test_a_cursor_selects_the_pixels_of_its_lifetime():
    """The phasor plane and the image are two views of the same pixels."""
    from chisurf.core.roi import EllipseROI

    vm, (ga, sa), _, left = _two_lifetime_model()
    vm.cursors.add(EllipseROI(ga, sa, 0.03, 0.03, name="unquenched"))

    mask = vm.cursor_mask()
    assert mask.shape == left.shape
    # Almost all of the long-lifetime half, and almost none of the other.
    assert mask[left].mean() > 0.95
    assert mask[~left].mean() < 0.05


def test_two_cursors_combine_and_one_can_be_switched_off():
    from chisurf.core.roi import EllipseROI

    vm, (ga, sa), (gb, sb), left = _two_lifetime_model()
    vm.cursors.add(EllipseROI(ga, sa, 0.03, 0.03, name="unquenched"))
    vm.cursors.add(EllipseROI(gb, sb, 0.03, 0.03, name="FRET"))

    assert vm.cursor_mask().mean() > 0.95  # union covers both halves
    vm.cursors.set_enabled("FRET", False)
    assert vm.cursor_mask()[~left].mean() < 0.05  # and drops one when unticked


def test_inverting_a_cursor_selects_everything_else():
    from chisurf.core.roi import EllipseROI

    vm, (ga, sa), _, left = _two_lifetime_model()
    vm.cursors.add(EllipseROI(ga, sa, 0.03, 0.03, name="unquenched"), invert=True)
    assert vm.cursor_mask()[left].mean() < 0.05
    assert vm.cursor_mask()[~left].mean() > 0.95


def test_no_cursor_means_every_pixel_not_none():
    """An empty cursor list is "no restriction", not "nothing selected"."""
    vm, *_ = _two_lifetime_model()
    assert vm.cursors.combined() is None
    assert vm.cursor_mask().all()


def test_the_gated_image_is_the_intensity_of_the_selected_pixels():
    from chisurf.core.roi import EllipseROI

    vm, (ga, sa), _, left = _two_lifetime_model()
    vm.cursors.add(EllipseROI(ga, sa, 0.03, 0.03, name="unquenched"))

    gated = vm.masked_intensity_map()
    intensity = np.asarray(vm._disp("n_photons"))
    assert gated[~left].sum() < 0.05 * intensity.sum()
    assert gated[left].sum() == pytest.approx(intensity[left].sum(), rel=0.05)


def test_the_summary_reports_how_much_was_picked():
    from chisurf.core.roi import EllipseROI

    vm, (ga, sa), _, _ = _two_lifetime_model()
    vm.cursors.add(EllipseROI(ga, sa, 0.03, 0.03, name="unquenched"))
    summary = vm.cursor_summary()
    assert "px" in summary and "%" in summary


def test_a_cursor_is_placed_inside_the_phasor_plane():
    """A new cursor must land where the clusters are, not off the plot."""
    vm, *_ = _two_lifetime_model()
    g0, g1, s0, s1 = vm.cursor_extent()
    assert (g0, g1) == vm.PHASOR_G_RANGE
    assert (s0, s1) == vm.PHASOR_S_RANGE
