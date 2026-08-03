"""Headless tests for the Qt-free :class:`PsfViewModel` (no Qt/pyqtgraph)."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.microscopy.psf_determination.gui.view_model import PsfViewModel


def _synthetic_stack(nz=21, ny=40, nx=40, sigma_xy=2.0, sigma_z=4.0):
    """Return a single 3D Gaussian bead centred in the stack on a small offset."""
    z, y, x = np.meshgrid(np.arange(nz), np.arange(ny), np.arange(nx), indexing="ij")
    zc, yc, xc = nz / 2, ny / 2, nx / 2
    bead = 1000.0 * np.exp(
        -0.5 * (((x - xc) / sigma_xy) ** 2 + ((y - yc) / sigma_xy) ** 2 + ((z - zc) / sigma_z) ** 2)
    )
    return (bead + 5.0).astype(np.float32)


def test_detection_finds_the_bead_centre_and_ignores_a_hot_pixel():
    """Candidates are regions, which is what separates a bead from a dead pixel.

    A bead covers several pixels and its candidate should sit at the centre of
    that spot; a single blazing pixel is a camera defect and must not become a
    bead, however bright it is.
    """
    from chisurf.plugins.microscopy.psf_determination.api.psf import detect_beads

    stack = _synthetic_stack()
    stack[:, 8, 30] = 5000.0  # a hot pixel column, brighter than the bead

    beads = detect_beads(stack, roi_xy=15, roi_z=15, pixels_per_frame=40)
    assert beads
    for _, y, x in beads:
        assert (y, x) != (8, 30)
        # every candidate sits on the bead, whose centre is (20, 20)
        assert abs(y - 20) <= 1 and abs(x - 20) <= 1

    # ... and asking for single-pixel spots brings the defect back.
    permissive = detect_beads(stack, roi_xy=15, roi_z=15, pixels_per_frame=40, min_area=1)
    assert any((y, x) == (8, 30) for _, y, x in permissive)


def test_load_detect_fit_roundtrip():
    model = PsfViewModel()
    events: list[str] = []
    model.add_observer(events.append)

    stack = _synthetic_stack()
    model.set_stack(stack)
    assert model.stack is not None
    assert "stack" in events

    n = model.detect_beads()
    assert n >= 1
    assert "beads" in events
    assert model.selected_bead is not None

    fit = model.fit_selected()
    assert fit is not None and fit["success"]
    # Fitted lateral sigma should be close to the ground-truth 2.0 px.
    _, _, _, sigma_z, sigma_y, sigma_x, _, _ = fit["params"]
    assert abs(sigma_x - 2.0) < 1.0
    assert abs(sigma_y - 2.0) < 1.0
    assert sigma_z > sigma_x  # axial worse than lateral

    # Profiles and overlay accessors are populated.
    assert len(model.x_profile_series()) == 2
    assert len(model.z_profile_series()) == 2
    assert model.fit_circle() is not None
    assert "PSF Fit Results" in model.results_text


def test_fit_all_and_export(tmp_path):
    model = PsfViewModel()
    model.set_stack(_synthetic_stack())
    model.detect_beads()
    results = model.fit_all()
    assert results
    assert "Batch PSF fits" in model.results_text

    out = tmp_path / "psf.csv"
    model.export_csv(str(out))
    assert out.exists()
    assert out.read_text().splitlines()[0].startswith("index,")


def test_the_fitted_psf_width_is_available_as_a_region():
    """The measured lateral FWHM, as a region like every other in ChiSurf.

    The circle drawn on screen is a *descriptor* — it carries the z slice so the
    overlay sits beside the picked bead, and a region carries no third axis. The
    region is the same circle in the frame's coordinates, so a fitted PSF can be
    measured against an image, combined with another region, or stored.
    """
    from chisurf.core.roi import EllipseROI

    model = PsfViewModel()
    assert model.fit_region() is None, "nothing fitted yet"

    model.set_stack(_synthetic_stack())
    model.detect_beads()
    fit = model.fit_selected()
    assert fit is not None and fit["success"]

    region = model.fit_region()
    circle = model.fit_circle()
    assert isinstance(region, EllipseROI)
    assert (region.cx, region.cy) == (circle["x"], circle["y"])
    assert region.rx == region.ry == circle["r"]
    assert f"z={int(circle['z'])}" in region.name

    # The radius is the lateral FWHM/2 of the fitted Gaussian.
    _, _, _, _, sigma_y, sigma_x, _, _ = fit["params"]
    assert region.rx == pytest.approx(2.355 * (sigma_x + sigma_y) / 2.0 / 2.0)

    # And it behaves as a region: it covers the bead centre and can be measured.
    assert region.contains(np.array([[region.cx, region.cy]])).tolist() == [True]
    props = region.properties(model.stack.shape[1:])
    assert props.area > 0
