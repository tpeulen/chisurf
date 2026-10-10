"""ALEX and Burst MLE cache actual demonstration payloads by full settings."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from chisurf.plugins.burst.alex_suite import demo as alex
from chisurf.plugins.emtk_layout import action_caption
from chisurf.plugins.burst.burst_mle_analysis import demo as mle


@pytest.mark.parametrize("module,plugin_id", [(alex, "alex_suite"), (mle, "burst_mle_analysis")])
def test_default_folder_is_plugin_owned(module, plugin_id, tmp_path, monkeypatch):
    """The current settings override selects the dedicated generated-data folder."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    assert module.demo_folder() == tmp_path / "demos" / plugin_id


@pytest.mark.parametrize("module", [alex, mle])
def test_cache_settings_integrity_and_overwrite(module, tmp_path):
    """Changed seeds and corrupt files produce new real photons; reuse keeps complete files."""
    import tttrlib

    primary = module.make_demo(tmp_path)
    raw = primary if module is alex else tmp_path / "synthetic_mle.ptu"
    baseline = raw.read_bytes()
    timestamp = raw.stat().st_mtime_ns
    assert module.make_demo(tmp_path) == primary
    assert raw.stat().st_mtime_ns == timestamp
    changed = module.make_demo(tmp_path, seed=17)
    assert changed == primary and raw.read_bytes() != baseline
    stream = tttrlib.TTTR(str(raw), "SPC-130" if module is alex else "PTU")
    if module is alex:
        macro, routing, _ = module.photon_stream(seed=17)
        np.testing.assert_array_equal(stream.macro_times, macro)
        np.testing.assert_array_equal(stream.routing_channels, routing)
    else:
        assert len(stream) == 4096 + 1024 + 16 * 1000
        assert stream.header.micro_time_resolution == 32e-12
    raw.write_bytes(b"corrupted generated stream")
    module.make_demo(tmp_path, seed=17)
    assert raw.read_bytes() != b"corrupted generated stream"
    module.make_demo(tmp_path, overwrite=True)
    assert raw.read_bytes() == baseline
    manifest = tmp_path / ("alex_demo.json" if module is alex else "demo.json")
    metadata = json.loads(manifest.read_text())
    assert metadata["settings"]["seed"] == module.DEMO["seed"]
    assert metadata["files"][str(raw.relative_to(tmp_path))] == hashlib.sha256(baseline).hexdigest()


def test_alex_tour_starts_with_real_example_and_leaves_analysis_to_user(tmp_path, monkeypatch):
    """The first actionable guide step exposes Files and awaits the real example release."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    from emtk.testing import Driver

    from chisurf.plugins.burst.alex_suite.gui.native import make_app

    app = make_app()
    try:
        driver = Driver(app, (1400, 900))
        app.tour.start(1)
        driver.draw(3)
        assert app.selected == "data"
        assert app.tour.steps[1]["target"]["name"] == "load_example"
        assert app.tour.awaiting
        child = app.children["data"]
        assert not child.model.paths()
        driver.click(action_caption("example"))
        driver.draw(3)
        assert not app.tour.awaiting
        assert child.model.paths() == [alex.demo_folder() / alex.STREAM_NAME]
        assert "alternation" not in app.children
    finally:
        app.close()


@pytest.mark.parametrize("module", [alex, mle])
def test_failed_writer_preserves_all_previous_payloads(module, tmp_path, monkeypatch):
    """Generation failure publishes neither partial photons nor mismatched truth metadata."""
    import tttrlib

    module.make_demo(tmp_path)
    before = {
        str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }
    original = tttrlib.TTTR.write

    def failed_write(stream, path, *args):
        from pathlib import Path

        Path(path).write_bytes(b"partial photons")
        return False

    monkeypatch.setattr(tttrlib.TTTR, "write", failed_write)
    with pytest.raises(OSError, match="could not write|Could not write"):
        module.make_demo(tmp_path, seed=17)
    after = {
        str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    }
    assert after == before
    assert not list(tmp_path.glob(".*-demo-*"))
    monkeypatch.setattr(tttrlib.TTTR, "write", original)


@pytest.mark.parametrize("module", [alex, mle])
def test_declared_demo_settings_drive_regeneration(module, tmp_path, monkeypatch):
    """Changing the declared fixture changes real events rather than metadata alone."""
    import tttrlib

    primary = module.make_demo(tmp_path)
    raw = primary if module is alex else tmp_path / "synthetic_mle.ptu"
    initial = raw.read_bytes()
    if module is alex:
        monkeypatch.setitem(module.DEMO, "seconds", 1.0)
    else:
        monkeypatch.setitem(module.DEMO, "burst_count", 3)
    module.make_demo(tmp_path)
    assert raw.read_bytes() != initial
    stream = tttrlib.TTTR(str(raw), "SPC-130" if module is alex else "PTU")
    if module is alex:
        expected, _, _ = module.photon_stream(seconds=1.0)
        np.testing.assert_array_equal(stream.macro_times, expected)
    else:
        assert len(stream) == 4096 + 1024 + 3 * 1000
