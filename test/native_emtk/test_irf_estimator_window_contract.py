"""IRF primary geometry preserves measured estimation and calibrated response data."""

import copy
import json
from pathlib import Path

import numpy as np
from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Store native preferences and metadata in scratch paths."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))


def settle(app):
    """Deliver the real estimation worker before inspecting its result."""
    app.future.result(timeout=120)
    app.poll()
    assert app.future is None
    assert not app.error
    assert app.model.result is not None


def test_raw_primary_default_reaches_real_constructor(tmp_path, monkeypatch):
    """The initial host reads primary geometry before adapting the controls."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui import app as owner

    path = Path(owner.__file__).with_name("irf_estimator_emtk.view.json")
    original = path.read_bytes()
    app = attach_native_state("irf_primary", owner.make_app())
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        Driver(app, size=app.window_size).draw(3)
        assert path.read_bytes() == original
        assert {"controls", "plot", "request_estimate"} <= app.item_rects.keys()
    finally:
        app.close()


def test_authored_primary_dimensions_are_consumed(tmp_path, monkeypatch):
    """A copied raw spec changes real factory dimensions without editing controls."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui import app as owner

    spec = owner._spec()
    spec["window"] = {"width": 960, "height": 640}
    (tmp_path / "irf_estimator_emtk.view.json").write_text(json.dumps(spec))
    monkeypatch.setattr(owner, "HERE", tmp_path)
    app = owner.make_app()
    try:
        assert app.window_size == (960, 640)
        Driver(app, size=app.window_size).draw(3)
    finally:
        app.close()


def test_missing_declaration_uses_family_fallback(tmp_path, monkeypatch):
    """An older primary spec still receives the family fallback."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui import app as owner

    spec = owner._spec()
    spec.pop("window")
    (tmp_path / "irf_estimator_emtk.view.json").write_text(json.dumps(spec))
    monkeypatch.setattr(owner, "HERE", tmp_path)
    app = owner.make_app()
    try:
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_saved_geometry_wins_without_claiming_analysis_restoration(tmp_path, monkeypatch):
    """Native dimensions persist; the existing app rebuilds analysis after loading data."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import make_app

    first = attach_native_state("irf_saved", make_app())
    first.window_resized(1330, 870)
    first.close()
    other = attach_native_state("irf_saved", make_app())
    try:
        assert other.window_size == (1330, 870)
        assert other.model.result is None
        assert other.model.decay_data_original is None
        other.draw(RecordingPainter(), 0, 0, 900, 650)
        assert other.window_size == (1330, 870)
    finally:
        other.close()


def test_real_estimate_and_export_survive_every_dock_and_narrow_view(tmp_path, monkeypatch):
    """Viewport changes preserve loaded counts, background, selected range and worker result."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import make_app

    repo = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
    source = repo / "test/data/tcspc/Jordi_FRETsens/Donor/D0_14_TAC1024_DexDem.dat"
    app = make_app()
    try:
        assert app.files_dropped([str(source)])
        assert not app.error
        app.model.rl_iterations = 100
        app.model.use_range_selection = True
        app.model.range_bounds = [30.0, 900.0]
        assert app.start_estimate()
        settle(app)
        measured = app.model.decay_data_original.copy()
        axis = app.model.channel_axis.copy()
        settings = copy.deepcopy(vars(app.model.settings()))
        result = copy.deepcopy(vars(app.model.result))
        app.model.save(tmp_path / "before.dat")
        for size in ((1100, 720), (900, 650), (736, 650)):
            driver = Driver(app, size=size)
            for key in ("settings", "plot", "results"):
                app.docks.focus(key)
                driver.draw(3)
            x0, y0, w0, h0 = app.item_rects["controls"]
            for name in ("dt", "manual_background", "first_channel", "last_channel",
                         "request_estimate", "request_load", "request_save"):
                x, y, width, height = app.item_rects[name]
                assert x >= x0 and x + width <= x0 + w0 + 0.5, name
                assert y >= y0 and y + height <= y0 + h0 + 0.5, name
            np.testing.assert_array_equal(app.model.decay_data_original, measured)
            np.testing.assert_array_equal(app.model.channel_axis, axis)
            assert vars(app.model.settings()) == settings
            assert vars(app.model.result) == result
            app.model.save(tmp_path / "after.dat")
            assert (tmp_path / "after.dat").read_bytes() == (tmp_path / "before.dat").read_bytes()
        assert len(measured) == 1024
    finally:
        app.close()


def test_calibrated_independent_convolution_keeps_response_peak(tmp_path, monkeypatch):
    """A Gaussian response on a known nanosecond grid retains its peak after rendering."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import make_app

    time = np.arange(500) * 0.1002
    response = np.exp(-0.5 * ((time - 5.0) / 0.5) ** 2)
    response /= response.sum()
    reconvolved = np.convolve(np.exp(-time / 4.0), response)[:len(time)]
    counts = np.random.default_rng(5).poisson(4e4 * reconvolved / reconvolved.max() + 8).astype(float)
    app = make_app()
    try:
        app.model.load_data(counts, time_axis=time)
        app.model.manual_background = 8.0
        assert app.start_estimate()
        settle(app)
        before = copy.deepcopy(vars(app.model.result))
        peak_ns = time[np.argmax(app.model.result.irf)]
        assert abs(peak_ns - 5.0) < 3 * 0.1002
        assert abs(app.model.result.decay_rate_ns * app.model.result.lifetime_ns - 1) < 1e-12
        Driver(app, size=(1100, 720)).draw(4)
        assert vars(app.model.result) == before
        np.testing.assert_array_equal(app.model.channel_axis, time)
        np.testing.assert_array_equal(app.model.decay_data_original, counts)
    finally:
        app.close()
