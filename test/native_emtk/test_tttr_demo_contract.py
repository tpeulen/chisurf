"""Standard TTTR demonstrations retain physical streams and reject incomplete caches."""

import importlib
import json

import numpy as np
import pytest

PLUGINS = (
    "intensity_trace",
    "microtime_histogram",
    "audifier",
    "photon_table",
    "ptu_alex_creator",
    "tttr_count_rate_analysis",
    "tttr_header_edit",
    "tttr_lut_tools",
    "tttr_microtime_shifter",
    "tttr_splitter",
    "tttr_time_windows",
)


@pytest.mark.parametrize("plugin", PLUGINS)
def test_default_folder_and_declared_parameter_sidecar(tmp_path, monkeypatch, plugin):
    """The primary stream lives in the plugin's settings-owned demo folder."""
    demo = importlib.import_module(f"chisurf.plugins.tttr.{plugin}.demo")
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    assert demo.demo_folder() == tmp_path / "demos" / plugin
    path = demo.make_demo()
    assert path.parent == demo.demo_folder()
    assert json.loads(path.with_suffix(".json").read_text()) == demo.DEMO
    assert demo._cache_is_good(path)


@pytest.mark.parametrize("plugin", PLUGINS)
@pytest.mark.parametrize(
    "damage",
    ("stream", "partial", "same_size", "sidecar", "checksum", "seed", "version", "overwrite"),
)
def test_cache_reuse_and_repair_retain_a_complete_photon_stream(
    tmp_path, monkeypatch, plugin, damage
):
    """A stale parameter set or incomplete cached file must regenerate, not silently load."""
    demo = importlib.import_module(f"chisurf.plugins.tttr.{plugin}.demo")
    path = demo.make_demo(tmp_path)
    original_data = path.read_bytes()
    original_mtime = path.stat().st_mtime_ns
    assert demo.make_demo(tmp_path) == path
    assert path.read_bytes() == original_data
    assert path.stat().st_mtime_ns == original_mtime
    if damage == "stream":
        path.unlink()
    elif damage == "partial":
        path.write_bytes(original_data[: len(original_data) // 2])
    elif damage == "same_size":
        altered = bytearray(original_data)
        altered[-1] ^= 1
        path.write_bytes(altered)
    elif damage == "sidecar":
        path.with_suffix(".json").write_text("{unfinished")
    elif damage == "checksum":
        path.with_suffix(".sha256").unlink()
    elif damage == "seed":
        monkeypatch.setitem(demo.DEMO, "seed", demo.DEMO["seed"] + 1)
    elif damage == "version":
        monkeypatch.setitem(demo.DEMO, "version", demo.DEMO["version"] + 1)
    assert demo.make_demo(tmp_path, overwrite=damage == "overwrite") == path
    assert demo._cache_is_good(path)
    assert path.stat().st_mtime_ns != original_mtime
    assert json.loads(path.with_suffix(".json").read_text()) == demo.DEMO
    if damage != "seed":
        assert path.read_bytes() == original_data
    else:
        assert path.read_bytes() != original_data


def test_microtime_default_stream_keeps_exact_counts_and_header(tmp_path):
    """The known 3000/1500-count demonstration keeps its original physical clocks."""
    import tttrlib

    from chisurf.plugins.tttr.microtime_histogram import demo

    stream = tttrlib.TTTR(str(demo.make_demo(tmp_path)), "PTU")
    assert len(stream) == 4500
    assert stream.header.micro_time_resolution == 32e-12
    assert stream.header.macro_time_resolution == 25e-9
    assert np.count_nonzero(stream.routing_channels == 0) == 3000
    assert np.count_nonzero(stream.routing_channels == 1) == 1500


def test_intensity_default_stream_keeps_original_events_and_header(tmp_path):
    """The deterministic molecule retains every original macro/micro/route event."""
    import hashlib

    import tttrlib

    from chisurf.plugins.tttr.intensity_trace import demo

    path = demo.make_demo(tmp_path)
    stream = tttrlib.TTTR(str(path), "SPC-130")
    assert len(stream) == 408885
    assert stream.header.macro_time_resolution == 13.5e-9
    assert stream.header.micro_time_resolution == 3.2958984375e-12
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "361ae8f48ce1f30fdfff4268efadff3b101c6d2768b41cd2a646cda9a1e66470"
    )


def test_intensity_guide_loads_example_only_after_actual_user_click(tmp_path, monkeypatch):
    """The declared action releases its awaited step and opens the real photon input."""
    from emtk.testing import Driver

    from chisurf.plugins.tttr.intensity_trace.gui.app import make_app

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    app = make_app()
    driver = Driver(app, (1200, 800))
    try:
        driver.frame(3)
        assert "load_example" in driver.ids()
        assert "request_example" not in driver.ids()
        assert app.tour.steps[1]["target"] == {"name": "load_example"}
        app.tour.start(1)
        driver.frame(3)
        assert app.tour.awaiting
        assert not app.model.loaded
        driver.click("load_example")
        if app._worker:
            app._worker.join(20)
        driver.frame(3)
        assert app.model.loaded
        assert not app.tour.awaiting
        assert app.model.window_ms == 2.0
        assert app.model.n_states == 2
        assert str(app.model.path).startswith(str(tmp_path / "demos" / "intensity_trace"))
        assert app.model.counts.sum() == 408885
    finally:
        app.close()
