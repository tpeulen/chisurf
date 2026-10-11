"""Primary native generator geometry preserves counts, polarization and settings."""

from __future__ import annotations

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.app import make_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Construct the real generator with scratch native settings."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    instance = make_app()
    yield instance
    close = getattr(instance, "close", None)
    if close:
        close()


def test_primary_metadata_reaches_constructor_before_control_spec_slicing(app):
    """The raw declaration determines the standalone host before controls are filtered."""
    assert app.window_size == (1100, 720)
    assert "window" not in app.spec
    attach_native_state("synthetic-decay", app)
    assert app.window_size == (1100, 720)
    assert (
        "generate" in Driver(app, app.window_size).draw(3).strings or "generate" in app.item_rects
    )


def test_primary_reader_uses_raw_declaration(app, monkeypatch):
    """The shared reader sees the primary file rather than the controls-only reconstruction."""
    import chisurf.plugins.fluorescence_decay.synthetic_decay.gui.app as module

    original = module.window_size
    declarations = []

    def changed(spec, default):
        """Record raw metadata and exercise a different authored default."""
        declarations.append((spec["window"], default))
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", changed)
    other = make_app()
    assert other.window_size == (1234, 789)
    assert declarations == [({"width": 1100, "height": 720}, (1100, 720))]


def test_saved_geometry_inputs_and_layout_restore_without_generated_results(app):
    """An actual native close/reopen restores definitions while generated curves rebuild."""
    attach_native_state("synthetic-decay", app)
    app.model.n_bins = 512
    app.model.bin_width = 0.02
    app.model.seed = 17
    app.model.polarization = "vv/vh"
    app.model.shot_noise = True
    app.model.generate()
    settings = app.export_settings()
    expected = (np.array(app.model._vv), np.array(app.model._vh))
    Driver(app, (1100, 720)).draw(3)
    app.docks.undock("anisotropy", (20, 30, 420, 360))
    layout = app.docks.state()
    app.window_resized(1330, 870)
    app.close()
    reopened = attach_native_state("synthetic-decay", make_app())
    try:
        assert reopened.window_size == (1330, 870)
        assert reopened.export_settings() == settings
        assert reopened.docks.state()["windows"] == layout["windows"]
        assert reopened.model.decay_series() == []
        reopened.model.generate()
        np.testing.assert_array_equal(reopened.model._vv, expected[0])
        np.testing.assert_array_equal(reopened.model._vh, expected[1])
    finally:
        reopened.close()


def test_clamped_host_keeps_full_polarization_option_reachable(app):
    """The actual long mode caption fits its settings dock and a real press changes mode."""
    driver = Driver(app, (736, 552))
    painter = driver.draw(3)
    caption = next(record for record in painter.texts if record[5] == "VV/VH (polarized)")
    x, y, _, height, _, text, *_ = caption
    dock = app.docks.region_boxes["settings"]
    assert x + painter.text_width(text) <= dock[0] + dock[2]
    driver.click((x + 6, y + height / 2))
    assert app.model.is_vv_vh()
    for _ in range(12):
        driver.wheel(-2, at=(120, 420))
    rotation = app.form.tables["rotation_records"].control
    assert rotation is not None
    _, y, _, height = app.form.rects["rotation_records"]
    assert 0 <= y < y + height <= 552


@pytest.mark.parametrize("mode", ["vm", "vv/vh"])
def test_real_measured_irf_physical_outputs_survive_resize(app, mode):
    """A measured response and seeded photons retain their axes, rotation and calibration."""
    from pathlib import Path

    from chisurf.core.fluorescence.decay import synthetic_aniso_decay, synthetic_decay

    path = Path(__file__).resolve().parents[2] / "test/data/tcspc/EasyTau300/215-268 D0 irf.dat"
    measured = np.loadtxt(path)
    model = app.model
    model.n_bins = len(measured)
    model.bin_width = 0.008
    model.irf_path = str(path)
    model.polarization = mode
    model.shot_noise = True
    model.photon_count = 120000
    model.seed = 17
    model.g_factor, model.l1, model.l2 = 1.3, 0.02, 0.05
    model.rotation_rows = [{"b": 0.22, "rho": 1.4}, {"b": 0.08, "rho": 8.0}]
    driver = Driver(app, (1100, 720))
    driver.draw(3)
    driver.click("generate")
    settings = model.export_settings()
    arrays = {name: np.array(getattr(model, name)) for name in ("_x", "_y", "_vv", "_vh", "_r")}
    common = dict(
        amplitudes=[1, 1],
        bin_width=0.008,
        irf=measured[:, -1],
        normalize=False,
        photon_count=120000,
        seed=17,
    )
    if mode == "vm":
        expected = synthetic_decay(len(measured), [1.2, 4.0], **common)
        np.testing.assert_array_equal(model._y, expected)
        count = np.sum(model._y)
    else:
        expected = synthetic_aniso_decay(
            len(measured),
            [1.2, 4.0],
            anisotropy_spectrum=[0.22, 1.4, 0.08, 8.0],
            g_factor=1.3,
            l1=0.02,
            l2=0.05,
            **common,
        )
        np.testing.assert_array_equal(model._vv, expected[0])
        np.testing.assert_array_equal(model._vh, expected[1])
        count = np.sum(model._vv) + np.sum(model._vh)
    assert abs(count - 120000) < 6 * np.sqrt(120000)
    time = np.arange(len(measured)) * 0.008
    np.testing.assert_array_equal(model._x, time)
    np.testing.assert_allclose(model._r, 0.22 * np.exp(-time / 1.4) + 0.08 * np.exp(-time / 8))
    for size in ((736, 552), (800, 600), (1330, 870)):
        driver.draw(3, size=size)
    assert model.export_settings() == settings
    for name, expected in arrays.items():
        np.testing.assert_array_equal(getattr(model, name), expected)


@pytest.mark.parametrize(
    "option,expected",
    [
        ("polarization.0", "Magic-angle decay; carries no anisotropy."),
        (
            "polarization.1",
            "Parallel and perpendicular channels generated from the rotation spectrum.",
        ),
    ],
)
def test_mode_options_expose_real_scientific_tooltips(app, option, expected):
    """Both native radio options reveal their own physical description on actual hover."""
    import time

    driver = Driver(app, (736, 552))
    driver.draw(3)
    driver.hover(option)
    driver.draw(2)
    time.sleep(0.65)
    text = " ".join(driver.draw(2).strings)
    assert expected in text
