"""Burst MLE primary geometry and readable status preserve real pooled fitting."""

import copy
import json
from pathlib import Path

import numpy as np
from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep native preferences, demo photons and metadata in scratch storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))


def test_raw_primary_default_reaches_real_native_factory(tmp_path, monkeypatch):
    """Host geometry is read before the toolkit adapts the control sections."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_mle_analysis.gui import native as owner

    path = Path(owner.__file__).with_name("mle_native.view.json")
    original = path.read_bytes()
    app = attach_native_state("mle_primary", owner.create_app())
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        Driver(app, size=app.window_size).draw(3)
        assert path.read_bytes() == original
        assert {"auto", "toolAction_run", "fit_model"} <= app.item_rects.keys()
    finally:
        app.close()


def test_authored_primary_dimensions_reach_constructor(tmp_path, monkeypatch):
    """The raw declaration controls dimensions instead of a repeated fixed constant."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_mle_analysis.gui import native as owner

    primary = json.loads((owner.HERE / "mle_native.view.json").read_text())
    primary["window"] = {"width": 960, "height": 640}
    (tmp_path / "mle_native.view.json").write_text(json.dumps(primary))
    monkeypatch.setattr(owner, "HERE", tmp_path)
    app = owner.create_app()
    try:
        assert app.window_size == (960, 640)
        Driver(app, size=app.window_size).draw(3)
    finally:
        app.close()


def test_missing_primary_declaration_uses_family_fallback(tmp_path, monkeypatch):
    """Older control specifications retain a deterministic family default."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_mle_analysis.gui import native as owner

    primary = json.loads((owner.HERE / "mle_native.view.json").read_text())
    primary.pop("window")
    (tmp_path / "mle_native.view.json").write_text(json.dumps(primary))
    monkeypatch.setattr(owner, "HERE", tmp_path)
    app = owner.create_app()
    try:
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_saved_native_geometry_wins_without_claiming_analysis_persistence(tmp_path, monkeypatch):
    """Native dimensions/docks reopen; analysis uses the explicit settings file contract."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    first = attach_native_state("mle_saved", create_app())
    first.window_resized(1330, 870)
    first.close()
    other = attach_native_state("mle_saved", create_app())
    try:
        assert other.window_size == (1330, 870)
        assert other.model.session.df_bursts is None
        assert other.model.session.outcome is None
        other.draw(RecordingPainter(), 0, 0, 900, 650)
        assert other.window_size == (1330, 870)
    finally:
        other.close()


def test_long_permission_error_and_readiness_text_fit_inside_narrow_dock(tmp_path, monkeypatch):
    """Presentation-only error text keeps full glyphs and severity, without simulating any fit."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    app = create_app()
    try:
        app.job.error = str(PermissionError(1, "Operation not permitted", "/psm_0123456789abcdef"))
        driver = Driver(app, size=(900, 650))
        painter = driver.draw(3)
        colored = [(text, meta) for text, meta in zip(painter.texts, painter.text_metadata)
                   if text[6][0] > text[6][1] * 1.5]
        assert colored
        assert "".join(text[5].replace(" ", "") for text, _ in colored) == app.job.error.replace(" ", "")
        for _, meta in colored:
            assert meta["visible_bounds"][2] >= meta["measured_bounds"][2] - 0.5
            assert meta["visible_bounds"][3] >= meta["measured_bounds"][3] - 0.5
        # A long real detector name exercises the unavailable-input readiness branch.
        app.job.error = ""
        app.model.session.set_detectors({"a_detector_with_a_long_measurement_name": {
            "chs": [0, 1], "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0, "l2": 0.0,
        }}, "PTU")
        painter = driver.draw(3)
        yellow = [(text, meta) for text, meta in zip(painter.texts, painter.text_metadata)
                  if text[6][0] == text[6][1] and text[6][0] > text[6][2]]
        assert yellow
        for _, meta in yellow:
            assert meta["visible_bounds"][2] >= meta["measured_bounds"][2] - 0.5
    finally:
        app.close()


def test_real_demo_pooled_fit_preserves_photons_models_and_settings(tmp_path, monkeypatch):
    """The real snapshot worker fits shipped photons; viewport changes preserve computed arrays."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    app = create_app()
    try:
        app.model.load_example()
        assert app.model.n_bursts == 16
        app.auto_extract()
        app.job.thread.join(timeout=120)
        app.job.poll()
        assert not app.job.busy and not app.job.error
        assert app.model.fit_curves is not None
        # The first view consumes the queued detector-definition normalization once.
        Driver(app, size=(1100, 720)).draw(3)
        session = app.model.session
        photons = {key: (np.asarray(raw.micro_times).copy(), np.asarray(raw.routing_channels).copy())
                   for key, raw in session.tttrs.items()}
        baseline = copy.deepcopy(session.outcome)
        settings = copy.deepcopy(session.settings_payload())
        for size in ((1100, 720), (900, 650)):
            driver = Driver(app, size=size)
            for key in ("controls", "irf", "detectors", "decay", "inspect", "lifetimes", "results"):
                app.docks.focus(key)
                driver.draw(3)
            np.testing.assert_array_equal(session.outcome.x, baseline.x)
            np.testing.assert_array_equal(session.outcome.model, baseline.model)
            assert session.settings_payload() == settings
            for key, (micro, channels) in photons.items():
                np.testing.assert_array_equal(session.tttrs[key].micro_times, micro)
                np.testing.assert_array_equal(session.tttrs[key].routing_channels, channels)
        assert app.model.fit_model_options() == ["fit23", "fit24", "fit25"]
        assert 1.5 < app.model.tau_result < 2.5
    finally:
        app.close()
