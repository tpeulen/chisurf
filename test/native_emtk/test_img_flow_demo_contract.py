"""Flow demonstration cache and actual native user actions share one contract."""

import hashlib
from pathlib import Path

from emtk.testing import Driver

from chisurf.plugins.microscopy.img_flow import demo
from chisurf.plugins.microscopy.img_flow.gui.app import make_app


def test_folder_is_owned_by_plugin_and_settings(tmp_path, monkeypatch):
    """A redirected settings tree owns the demonstration cache."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    assert demo.demo_folder() == tmp_path / "demos" / "img_flow"


def test_cache_checks_configuration_completion_and_bytes(tmp_path):
    """Incomplete, changed and corrupted caches are never silently reused."""
    path = tmp_path / "flow_demo_poiseuille.ptu"
    path.write_bytes(b"real completed file" * 1000)
    info = demo._truth(demo.DEMO, path)
    demo._write_sidecar(path, demo.DEMO, info)
    assert demo._cache_is_good(path, demo.DEMO)
    assert not demo._cache_is_good(path, {**demo.DEMO, "seed": 8})
    path.write_bytes(b"corrupted content" * 1000)
    assert not demo._cache_is_good(path, demo.DEMO)
    path.with_suffix(".json").unlink()
    assert not demo._cache_is_good(path, demo.DEMO)


def test_real_producer_reuse_and_overwrite(tmp_path):
    """A real small scan preserves file identity on reuse and records its clock."""
    cfg = dict(n_pixel=16, n_frames=4)
    path = demo.make_demo(tmp_path, **cfg)
    assert path == tmp_path / "flow_demo_poiseuille.ptu"
    stat = path.stat()
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    assert demo.make_demo(tmp_path, **cfg) == path
    assert path.stat().st_mtime_ns == stat.st_mtime_ns
    assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
    assert demo.demo_info(path)["settings"] == {**demo.DEMO, **cfg}
    assert demo.demo_info(path)["timing"]["frame_duration_ms"] == 5.12
    assert demo.make_demo(tmp_path, overwrite=True, **cfg) == path
    assert path.stat().st_mtime_ns != stat.st_mtime_ns
    assert demo._cache_is_good(path, {**demo.DEMO, **cfg})
    assert demo.make_demo(tmp_path, n_pixel=16, n_frames=5) == path
    assert demo.demo_info(path)["settings"]["n_frames"] == 5
    import tttrlib

    stream = tttrlib.TTTR(str(path))
    assert int((stream.routing_channels == 4).sum()) == 5
    assert demo._cache_is_good(path, {**demo.DEMO, "n_pixel": 16, "n_frames": 5})


def test_real_demo_button_releases_only_its_await(tmp_path, monkeypatch):
    """The tour waits for the declared action and its actual worker completion."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_CONFIG_DIR", str(tmp_path / "mmfdb"))
    folder = tmp_path / "demo"
    demo.make_demo(folder)
    monkeypatch.setattr(demo, "demo_folder", lambda: folder)
    app = make_app()
    driver = Driver(app, (1200, 800))
    try:
        driver.frame(3)
        assert "load_example" in driver.ids()
        driver.click("guide")
        assert app.tour.active
        app.tour.next()
        driver.frame(2)
        assert app.tour.step_idx == 1 and app.tour.awaiting
        assert app.tour.steps[1]["target"]["name"] == "load_example"
        driver.click("load_example")
        driver.settle()
        assert not app.tour.awaiting
        assert Path(app.model.filename) == folder / "flow_demo_poiseuille.ptu"
        assert app.model.demo_truth == demo.demo_info(app.model.filename)["truth"]
        assert app.model.result is None
        app.tour.stop()
        driver.click("map_flow")
        driver.settle()
        summary = app.model.result.summary(0.5)
        assert app.model.result.n_escaped == 0
        assert summary["n_kept"] >= 0.8 * summary["n_tiles"]
        assert summary["mean_vx"] > 0
        assert abs(summary["mean_vy"]) < 0.3 * summary["mean_vx"]
    finally:
        app.close()
