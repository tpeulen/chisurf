"""Tests for the Burstwise → PTO converter plugin."""

from __future__ import annotations

import pathlib
from pathlib import Path

import pytest
from emtk.app import ImApp
from emtk.testing import RecordingPainter

from chisurf.core.plugin import load_manifest
from chisurf.plugins.burst.burstwise_import import (
    create_beside_resolver,
    create_mti_resolver,
    scan_folder,
)
from chisurf.plugins.burst.burstwise_import.gui.app import create_app
from chisurf.plugins.burst.burstwise_import.gui.view_model import BurstwiseImportViewModel

SAMPLE = (
    pathlib.Path.home()
    / ".hermes"
    / "cache"
    / "scratch"
    / "burstwise_samples"
    / "burstwise_All 0.1066#60"
)


def test_manifest_loads():
    """Verify plugin manifest fields and entrypoints."""
    manifest_path = Path(__file__).parents[1] / "manifest.json"
    manifest = load_manifest(manifest_path)
    assert manifest is not None
    assert manifest.id == "burstwise_import"
    assert manifest.version == "0.1.0"
    assert manifest.display_name == "File:Data:Burstwise→PTO"
    assert manifest.icon == "📦"
    assert manifest.categories == ["File", "Data"]
    assert manifest.authors == ["Thomas-Otavio Peulen"]
    assert manifest.entrypoints.emtk == "chisurf.plugins.burst.burstwise_import.gui.app:create_app"


def test_create_app_returns_imapp():
    """The factory creates an ImApp instance with an attached view model."""
    app = create_app()
    try:
        assert isinstance(app, ImApp)
        assert isinstance(app.model, BurstwiseImportViewModel)
        assert app.window_size == (1100, 720)
    finally:
        app.close()


def test_scan_wired_to_view_model(tmp_path):
    """Scan action invokes scan_folder and updates view model and observers."""
    # Create minimal mock burstwise folder
    bw = tmp_path / "burstwise_Test 0.5#40"
    (bw / "bi4_bur").mkdir(parents=True)
    (bw / "bi4_bur" / "stem0_0.bur").write_text("ColA\tColB\n1.0\t2.0\n")

    app = create_app()
    try:
        events = []
        app.model.add_observer(lambda ev: events.append(ev))

        inv = app.scan(bw)
        assert inv is not None
        assert "stem0" in inv["tables"]
        assert inv["parameters"]["threshold"] == pytest.approx(0.5)
        assert inv["parameters"]["min_photons"] == 40
        assert app.model.inventory == inv
        assert "1 measurement stem(s) found" in app.model.status_text
        assert "scan" in events
    finally:
        app.close()


def test_headless_draw_recording_painter(tmp_path):
    """Headless draw renders UI controls, tables, and dialogs without error."""
    app = create_app()
    try:
        # Initial empty state
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1100, 720)
        assert painter.strings, "nothing was drawn on the canvas"

        # Simulate scanned state with a mock folder
        bw = tmp_path / "burstwise_All 0.1066#60"
        (bw / "bi4_bur").mkdir(parents=True)
        (bw / "bi4_bur" / "test_meas_0.bur").write_text(
            "First Photon\tTau (green)\n0\t0\n100\t2.5\n"
        )
        app.scan(bw)

        painter2 = RecordingPainter()
        app.draw(painter2, 0, 0, 1100, 720)
        drawn_text = " ".join(painter2.strings)
        assert "test_meas" in drawn_text or "Found 1 measurement stems" in drawn_text

        # Narrow viewport to exercise same_line / wrapping guards
        painter_narrow = RecordingPainter()
        app.draw(painter_narrow, 0, 0, 600, 400)
        assert painter_narrow.strings

        # Preferences export / restore
        settings = app.export_settings()
        assert settings["folder"] == str(bw)
        restored = create_app()
        try:
            restored.restore_settings(settings)
            assert restored.model.folder == str(bw)
        finally:
            restored.close()
    finally:
        app.close()


@pytest.mark.skipif(not SAMPLE.is_dir(), reason="burstwise sample not present")
def test_integration_sample_scan_and_dry_run(tmp_path):
    """Integration test against the real legacy burstwise sample."""
    inv = scan_folder(SAMPLE)
    assert len(inv["tables"]) == 87
    assert inv["parameters"]["min_photons"] == 60
    assert inv["parameters"]["threshold"] == pytest.approx(0.1066)

    app = create_app()
    try:
        app.scan(SAMPLE)
        assert len(app.model.inventory["tables"]) == 87
        assert app.model.mti_entries

        # Dry run conversion with beside resolver
        app.model.resolver_mode = "beside"
        app.model.dry_run = True
        rep = app.model.convert(out_dir=tmp_path)
        assert len(rep.stems) == 87
        # parameters are per analysis tree now (a measurement has several)
        params = next(iter(rep.parameters.values()))
        assert params["min_photons"] == 60

        # Draw with results populated
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1100, 720)
        assert painter.strings
    finally:
        app.close()


def test_resolvers_logic(tmp_path):
    """Verify source resolution logic for mti prefix mapping and beside resolver."""
    # Test beside resolver
    raw_file = tmp_path / "meas_001.ptu"
    raw_file.write_text("dummy")
    bw_dir = tmp_path / "burstwise_All 0.1#50"
    bw_dir.mkdir()

    beside = create_beside_resolver(bw_dir)
    found = beside("meas_001", {})
    assert found == raw_file
    assert beside("missing_meas", {}) is None

    # Test mti resolver
    local_data = tmp_path / "local_mirror"
    sub = local_data / "exp"
    sub.mkdir(parents=True)
    mti_target = sub / "meas_002.ht3"
    mti_target.write_text("dummy")

    mti_dict = {
        "N:\\exp\\meas_002.ht3": 120.0,
    }
    mti_resolver = create_mti_resolver("N:\\", str(local_data))
    resolved = mti_resolver("meas_002", mti_dict)
    assert resolved == mti_target
    assert mti_resolver("non_existent", mti_dict) is None
