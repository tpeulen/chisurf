"""Region MLE keeps primary host geometry while saved user dimensions win."""

import copy
import json

from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep preferences and metadata in the temporary settings tree."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))


def test_primary_geometry_survives_window_section_slicing(tmp_path, monkeypatch):
    """The real factory reads composite geometry before preparing its three docks."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.microscopy.region_mle.gui.app import HERE, make_app

    source = (HERE / "region_mle_emtk.view.json").read_bytes()
    app = make_app()
    try:
        assert json.loads(source)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        assert len(app.windows) == 3
        Driver(app, size=(1100, 720)).draw()
        assert (HERE / "region_mle_emtk.view.json").read_bytes() == source
    finally:
        app.close()


def test_saved_resize_and_fit_settings_win_on_reopen(tmp_path, monkeypatch):
    """Stored geometry and scientific parameters remain authoritative through rendering."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.microscopy.region_mle.gui.app import make_app

    first = attach_native_state("region_mle", make_app())
    first.model.settings.detector_chs = [0, 1]
    first.model.settings.micro_time_range = (0, 128)
    first.model.settings.min_photons = 123
    first.window_resized(1340, 900)
    state = copy.deepcopy(first.export_settings())
    first.close()
    reopened = attach_native_state("region_mle", make_app())
    try:
        assert reopened.window_size == (1340, 900)
        assert reopened.export_settings() == state
        reopened.draw(RecordingPainter(), 0, 0, 900, 650)
        assert reopened.window_size == (1340, 900)
        assert reopened.export_settings() == state
    finally:
        reopened.close()


def test_default_preserves_analysis_regions_and_decay_addresses(tmp_path, monkeypatch):
    """All three docks and genuine workflow controls remain available at the default."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.microscopy.region_mle.gui.app import make_app

    app = make_app()
    try:
        drv = Driver(app, size=(1100, 720))
        drv.draw(3)
        assert all(app.docks.window(key) is not None for key in ("analysis", "regions", "decay"))
        assert {"request_demo", "request_preview", "request_run"} <= app.form.rects.keys()
        for key in ("regions", "decay", "analysis"):
            app.docks.focus(key)
            drv.draw(2)
    finally:
        app.close()


def test_region_filter_and_selector_labels_fit_the_dock(tmp_path, monkeypatch):
    """Real demo controls reserve room for their labels in the initial region dock."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.microscopy.region_mle.gui.app import make_app

    app = make_app()
    try:
        app.model.load_demo()
        app.model.preview_regions()
        driver = Driver(app, size=(1100, 720))
        driver.draw(3)
        for label in ("Filter regions", "Region"):
            records = [
                metadata
                for text, metadata in zip(
                    driver.painter.texts, driver.painter.text_metadata, strict=True
                )
                if text[5] == label
            ]
            assert records, label
            assert all(r["visible_bounds"] == r["measured_bounds"] for r in records), label
    finally:
        app.close()
