"""The PSF calculator window: volume, summary and polarization overlay checked by construction; spec and layout.

The volume is a normalised peak at the lateral centre, the summary reports its interpolated half-maximum widths
beside the scalar limit 0.51 lambda/NA, and the overlay strokes follow the pupil field of the chosen polarization.
Hermetic: temporary HOME and settings.
"""

from __future__ import annotations

import json
import time

import numpy as np
import pytest

from chisurf.plugins.calculator.psf_calculator.gui.app import SETTINGS, SPEC, PSFApp, make_app

from .driving import BIG, SMALL, PSFDriver, clipped_texts, draw_clip, hermetic_env, layout_problems


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)


@pytest.fixture(autouse=True)
def no_window_failed_to_draw(caplog):
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]


@pytest.fixture
def app():
    a = make_app()
    yield a
    a.close()
    a._executor.shutdown(wait=True)


def small(app):
    """A small grid (fast), the shipped defaults otherwise."""
    app.model.nxy, app.model.nz = 24, 7


def settle(app, size=BIG):
    d = PSFDriver(app, size)
    d.settle()
    return d


# -- the volume, the summary and the overlay against what they must be by construction ------------------- #


def _half_max_width(profile, step_nm):
    """FWHM of a sampled peak by linear interpolation of both half-maximum crossings (nm)."""
    p = np.asarray(profile, float)
    half = p.max() / 2.0
    above = np.nonzero(p >= half)[0]
    lo, hi = int(above[0]), int(above[-1])
    # a peak that leaves the frame is cut at its last sample
    left = lo - (p[lo] - half) / (p[lo] - p[lo - 1]) if lo > 0 else float(lo)
    right = hi + (p[hi] - half) / (p[hi] - p[hi + 1]) if hi < p.size - 1 else float(hi)
    return (right - left) * step_nm


@pytest.mark.parametrize("model", ["airy", "vectorial"])
def test_the_volume_is_a_normalised_centred_peak_and_the_summary_reports_it(app, model):
    small(app)
    app.model.model = model
    vol = app.model.compute()
    m = app.model
    assert vol.shape == (m.nz, m.nxy, m.nxy) and vol.max() == pytest.approx(1.0)
    nz, ny, nx = vol.shape
    lateral = _half_max_width(vol[nz // 2][ny // 2], m.pixel_size_nm)
    axial = _half_max_width(vol[:, ny // 2, nx // 2], m.z_step_nm)
    scalar = 0.51 * m.wavelength_nm / m.na  # the scalar diffraction limit
    assert app.panel.summary_lines().splitlines() == [
        f"volume {nz} x {ny} x {nx} ({m.pixel_size_nm:.0f} nm px, {m.z_step_nm:.0f} nm z)",
        f"lateral FWHM {lateral:.0f} nm",
        f"axial FWHM {axial:.0f} nm",
        f"scalar 0.51 λ/NA = {scalar:.0f} nm ({lateral / scalar:.2f} x lateral)",
    ]
    if model == "airy":
        assert lateral == pytest.approx(scalar, rel=0.05)  # the Airy disc is the scalar limit


@pytest.mark.parametrize(
    "polarization, direction",
    [
        ("linear", lambda phi, a: (np.full_like(phi, np.cos(a)), np.full_like(phi, np.sin(a)))),
        ("radial", lambda phi, a: (np.cos(phi), np.sin(phi))),
        ("azimuthal", lambda phi, a: (-np.sin(phi), np.cos(phi))),
    ],
)
def test_the_polarization_overlay_strokes_follow_the_pupil_field(app, polarization, direction):
    small(app)
    app.model.polarization, app.model.angle_deg = polarization, 30.0
    app.model.compute()
    seg = app.model.polarization_segments()
    assert seg.shape == (12, 2, 3)
    phi = np.linspace(0.0, 2.0 * np.pi, 12, endpoint=False)
    stroke = seg[:, 1, :2] - seg[:, 0, :2]
    stroke /= np.linalg.norm(stroke, axis=1, keepdims=True)
    ux, uy = direction(phi, np.deg2rad(30.0))
    np.testing.assert_allclose(stroke, np.column_stack([ux, uy]), atol=1e-12)
    centre = seg.mean(axis=1)[:, :2] - app.model.nxy / 2.0  # one stroke per pupil point on a ring
    np.testing.assert_allclose(np.hypot(*centre.T), 0.38 * app.model.nxy, rtol=1e-12)
    app.model.model = "airy"
    assert app.model.polarization_segments() is None  # the scalar model has no polarization


def test_every_choice_lists_one_label_per_option_and_holds_its_value(app):
    for panel in SPEC["parameters"]["sections"]:
        for s in panel["sections"]:
            if s.get("type") == "choice":
                if s.get("labels"):
                    assert len(s["labels"]) == len(s["options"]), s["attr"]
                assert getattr(app.model, s["attr"]) in s["options"], s["attr"]


# -- spec, tooltips, no Qt import --------------------------------------------------------------------------------- #


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def test_every_section_button_and_column_of_the_spec_has_a_description():
    missing = []
    for node in walk(SPEC):
        if (
            node.get("type") in ("button_row", "toggle", "value", "choice", "info", "panel")
            and node.get("type") != "panel"
            and not node.get("description")
        ):
            missing.append((node.get("type"), node.get("attr")))
        if node.get("type") == "panel" and node.get("title") and not node.get("description"):
            missing.append(("panel", node["title"]))
        if "action" in node and not node.get("description"):
            missing.append(("button", node["action"]))
    assert not missing, missing


def test_every_control_has_a_tooltip(app):
    from test.gui.emtk_port_parity import emtk_inventory

    small(app)
    settle(app)
    inventory = emtk_inventory(app, BIG)
    assert inventory["controls_without_tooltip"] == []
    assert len(inventory["interactive"]) >= 14


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    verdict = qt_free("psf_calculator")
    assert verdict["ok"], verdict["output"]


# -- the idle state and the layout ------------------------------------------------------------------------- #


def test_controls_that_mean_nothing_in_this_state_are_greyed(app):
    p = app.panel
    assert (
        p.enabled("polarization") and not p.enabled("angle_deg") and p.enabled("show_polarization")
    )  # vectorial, circular
    app.model.polarization = "linear"
    assert p.enabled("angle_deg")
    app.model.model = "airy"
    assert (
        not p.enabled("polarization")
        and not p.enabled("angle_deg")
        and not p.enabled("show_polarization")
    )
    assert not p.enabled("export_npy") and not p.enabled("export_tif")  # nothing computed yet


@pytest.mark.parametrize("size", [BIG, SMALL])
@pytest.mark.parametrize("state", ["empty", "populated"])
def test_draws_and_the_layout_is_clean(app, size, state):
    if state == "populated":
        small(app)
        settle(app, size)
    painter = draw_clip(app, size)
    assert {"Parameters", "3-D PSF", "Orthogonal Slice", "NA", "Export .npy"} <= set(
        painter.strings
    )
    plots = [app.item_rects[k] for k in ("volume", "slice") if k in app.item_rects]
    problems = layout_problems(painter, size, ignore=plots) + clipped_texts(painter, ignore=plots)
    assert not problems, problems[:6]
    # a choice shows its whole label (emtk shortens one that does not fit)
    assert {"Vectorial (Richards-Wolf)", "Circular", "magma", "Preview (fast)", "XY"} <= set(
        painter.strings
    )


def test_settings_round_trip_clamp_and_ignore_garbage(app):
    (
        app.model.na,
        app.model.model,
        app.model.nxy,
        app.model.show_polarization,
        app.model.colormap,
    ) = 1.2, "airy", 32, False, "gray"
    app.slice_plane = "XZ"
    saved = json.loads(json.dumps(app.export_settings()))
    assert set(saved) == set(SETTINGS) | {"slice_plane"}
    other = make_app()
    try:
        other.restore_settings(saved)
        m = other.model
        assert (m.na, m.model, m.nxy, m.show_polarization, m.colormap, other.slice_plane) == (
            1.2,
            "airy",
            32,
            False,
            "gray",
            "XZ",
        )
        other.restore_settings(
            {
                "na": 99,
                "nxy": -4,
                "model": "bogus",
                "colormap": 5,
                "show_polarization": "yes",
                "slice_plane": "AB",
            }
        )
        assert (
            m.na == 1.7
            and m.nxy == 16
            and m.model == "airy"
            and m.colormap == "gray"
            and m.show_polarization is False
            and other.slice_plane == "XZ"
        )
        other.restore_settings("garbage")  # does not raise
    finally:
        other.close()
        other._executor.shutdown(wait=True)
