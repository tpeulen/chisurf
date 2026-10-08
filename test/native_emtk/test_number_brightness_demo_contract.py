"""The N&B example uses the shared disk location and preserves its simulation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chisurf.plugins.microscopy.img_pixel_nb import demo


def test_default_example_folder_respects_settings_override(tmp_path, monkeypatch):
    """Each plugin stores its generated files in its own settings subfolder."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    assert demo.demo_folder() == tmp_path / "demos" / "img_pixel_nb"


def test_example_returns_primary_path_and_reuses_matching_settings(tmp_path):
    """Cache reuse retains bytes; every regeneration writes the actual configured scan."""
    import numpy as np
    import tttrlib

    from chisurf.core.fluorescence.imaging.pixel_maps import build_clsm_windowed

    def read_counts(path):
        stream = tttrlib.TTTR(str(path))
        return np.asarray(build_clsm_windowed(stream, [0], []).get_intensity())

    cfg = {"n_pixel": 4, "n_frames": 5}
    target = demo.make_demo(tmp_path, **cfg)
    assert isinstance(target, Path) and target.parent == tmp_path
    sidecar = target.with_suffix(".json")
    assert json.loads(sidecar.read_text()) == demo.truth(cfg)
    np.testing.assert_array_equal(read_counts(target), demo.simulate_counts(cfg))
    initial = target.stat().st_mtime_ns
    original = target.read_bytes()
    assert demo.make_demo(tmp_path, **cfg) == target
    assert target.stat().st_mtime_ns == initial
    assert target.read_bytes() == original
    target.write_bytes(b"corrupted cache")
    demo.make_demo(tmp_path, overwrite=True, **cfg)
    assert target.read_bytes() == original
    np.testing.assert_array_equal(read_counts(target), demo.simulate_counts(cfg))
    changed = {"n_pixel": 6, "n_frames": 9, "seed": 12, "pixel_dwell_s": 40e-6}
    demo.make_demo(tmp_path, **changed)
    assert target.read_bytes() != original
    np.testing.assert_array_equal(read_counts(target), demo.simulate_counts(changed))
    assert tttrlib.TTTR(str(target)).header.macro_time_resolution == 20e-6
    assert json.loads(sidecar.read_text()) == demo.truth(changed)
    sidecar.write_text("broken")
    demo.make_demo(tmp_path, **cfg)
    assert target.read_bytes() == original
    np.testing.assert_array_equal(read_counts(target), demo.simulate_counts(cfg))
    assert json.loads(sidecar.read_text()) == demo.truth(cfg)


def test_regeneration_writes_to_a_new_file_even_when_writer_refuses_existing_paths(
    tmp_path, monkeypatch
):
    """A provider that reports success without replacing files cannot retain stale data."""
    import numpy as np
    import tttrlib

    from chisurf.core.fluorescence.imaging.pixel_maps import build_clsm_windowed

    original = demo.counts_to_tttr

    class ExistingFileRefusal:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def write(self, path, kind):
            if Path(path).exists():
                return True
            return self.wrapped.write(path, kind)

    monkeypatch.setattr(demo, "counts_to_tttr", lambda *args: ExistingFileRefusal(original(*args)))
    target = demo.make_demo(tmp_path, n_pixel=4, n_frames=5)
    cfg = {"n_pixel": 4, "n_frames": 9, "seed": 12}
    demo.make_demo(tmp_path, **cfg)
    stream = tttrlib.TTTR(str(target))
    counts = np.asarray(build_clsm_windowed(stream, [0], []).get_intensity())
    np.testing.assert_array_equal(counts, demo.simulate_counts(cfg))
    assert not list(tmp_path.glob(".nb-demo-*"))


def test_failed_regeneration_preserves_the_previous_complete_cache(tmp_path, monkeypatch):
    """A failed writer cannot publish new metadata over an old photon stream."""
    target = demo.make_demo(tmp_path, n_pixel=4, n_frames=5)
    sidecar = target.with_suffix(".json")
    before = target.read_bytes(), sidecar.read_bytes()

    class FailedWriter:
        def write(self, path, kind):
            Path(path).write_bytes(b"partial stream")
            return False

    monkeypatch.setattr(demo, "counts_to_tttr", lambda *args: FailedWriter())
    with pytest.raises(RuntimeError, match="could not write"):
        demo.make_demo(tmp_path, n_pixel=4, n_frames=9)
    assert (target.read_bytes(), sidecar.read_bytes()) == before
    assert not list(tmp_path.glob(".nb-demo-*"))


def test_native_example_button_and_tour_use_real_release(tmp_path, monkeypatch):
    """The tour awaits a real declared action; its worker loads the cached scan."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    from emtk.testing import Driver

    from chisurf.plugins.microscopy.img_pixel_nb.gui.app import make_app

    primary = demo.make_demo(tmp_path / "demo", n_pixel=8, n_frames=40)
    monkeypatch.setattr(demo, "demo_folder", lambda: primary.parent)
    # The ordinary default request must reuse this full contract fixture.
    monkeypatch.setitem(demo.DEMO, "n_pixel", 8)
    monkeypatch.setitem(demo.DEMO, "n_frames", 40)
    app = make_app()
    try:
        driver = Driver(app, (1200, 800))
        driver.draw()
        assert "load_example" in driver.ids()
        step = app.tour.steps[1]
        assert step["target"]["name"] == "load_example" and step.get("await")
        assert not any(s.get("action") for s in app.tour.steps)
        app.tour.start(1)
        driver.draw()
        assert app.tour.get_target_rect("load_example") is not None
        assert not app.job.busy and not app.model.filename
        # Press/release the highlighted real button while its tour awaits it.
        driver.click("load_example")
        assert app.tour._step_used
        driver.settle(timeout=120)
        assert not app.job.error
        assert Path(app.model.filename) == primary
        assert app.model.intensity_map().shape == (8, 8)
    finally:
        app.close()
