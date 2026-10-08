"""Declared settings-tool geometry preserves saved layouts and provider/preset data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.ai_settings.gui.app import make_ai_settings_app
from chisurf.plugins.fcs.fcs_channel_preset.gui.app import create_app


@pytest.fixture
def settings_tools(tmp_path, monkeypatch):
    """Use real configuration files in an isolated settings directory."""
    from chisurf.core.settings import ai_settings
    from chisurf.core.support import http

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))
    for key in ("MISTRAL_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    def forbid_network(*args, **kwargs):
        """A geometry test must never initiate an endpoint request."""
        raise AssertionError("Unexpected network request")

    monkeypatch.setattr(http, "get", forbid_network)
    monkeypatch.setattr(ai_settings, "_get_settings_path", lambda: tmp_path / "ai.json")
    ai_settings.save_api_settings(
        {
            "base_url": "http://localhost:11434/v1",
            "text_model": "lab-chat",
            "image_model": "lab-image",
            "api_key": "",
            "temperature": 0.4,
            "top_p": 0.85,
            "max_tokens": 2048,
        },
        provider="local",
    )
    detectors = tmp_path / "detectors.json"
    presets = tmp_path / "presets.json"
    setup = {
        "windows": {"prompt": [0, 64]},
        "detectors": {
            "green": {"chs": [0], "micro_time_ranges": [[0, 32]]},
            "red": {"chs": [1], "micro_time_ranges": [[0, 32]]},
        },
    }
    detectors.write_text(json.dumps({"setups": {"bench": setup}}))
    presets.write_text(json.dumps({
        "last_used_setup": "bench",
        "setups": {"bench": {"pairs": [{
            "name": "GR", "channel_a": "green", "channel_b": "red",
            "n_bins": 8, "n_casc": 12, "make_fine": False,
        }]}},
    }))
    return {
        "ai_settings": make_ai_settings_app,
        "fcs_channel_preset": lambda: create_app(detector_file=detectors, preset_file=presets),
    }, [tmp_path / "ai.json", detectors, presets]


@pytest.mark.parametrize("plugin_id", ["ai_settings", "fcs_channel_preset"])
def test_declared_factory_default_reaches_state_and_preserves_configuration(settings_tools, plugin_id):
    """Standalone construction and persistence use the declared tool-family size."""
    factories, paths = settings_tools
    before = [path.read_bytes() for path in paths]
    app = factories[plugin_id]()
    try:
        assert app.window_size == (1100, 720)
        attach_native_state(plugin_id, app)
        assert app.window_size == (1100, 720)
        Driver(app, app.window_size).draw(3)
        if plugin_id == "ai_settings":
            assert app.model.provider == "local"
            assert app.model.text_model == "lab-chat"
            assert app.model.temperature == 0.4
        else:
            assert app.model.current_setup == "bench"
            assert app.model.channel_names == ["green", "red"]
            assert app.model.pairs[0]["name"] == "GR"
        assert [path.read_bytes() for path in paths] == before
    finally:
        app.close()
    assert [path.read_bytes() for path in paths] == before


@pytest.mark.parametrize("plugin_id", ["ai_settings", "fcs_channel_preset"])
def test_saved_geometry_and_dock_configuration_override_factory_defaults(settings_tools, plugin_id):
    """A real close/reopen cycle keeps user geometry and meaningful dock state."""
    factories, paths = settings_tools
    before = [path.read_bytes() for path in paths]
    first = attach_native_state(plugin_id, factories[plugin_id]())
    Driver(first, (1100, 720)).draw(3)
    window = next(iter(first.docks.windows))
    first.docks.undock(window, (40, 50, 440, 400))
    first.window_resized(1390, 910)
    saved = first.docks.state()
    first.close()
    reopened = attach_native_state(plugin_id, factories[plugin_id]())
    try:
        assert reopened.window_size == (1390, 910)
        assert reopened.docks.state()["layout"] == saved["layout"]
        assert reopened.docks.state()["windows"] == saved["windows"]
        Driver(reopened, reopened.window_size).draw(3)
        assert [path.read_bytes() for path in paths] == before
    finally:
        reopened.close()


@pytest.mark.parametrize("plugin_id,spec", [
    ("ai_settings", "ai_settings/gui/ai_settings_emtk.view.json"),
    ("fcs_channel_preset", "fcs/fcs_channel_preset/gui/fcs_channel_preset.view.json"),
])
def test_existing_primary_spec_drives_factory_size(settings_tools, monkeypatch, plugin_id, spec):
    """Changing the loaded declaration changes construction without a new literal default."""
    import chisurf.plugins.ai_settings.gui.app as ai_app
    import chisurf.plugins.fcs.fcs_channel_preset.gui.app as fcs_app

    factories, _ = settings_tools
    module = ai_app if plugin_id == "ai_settings" else fcs_app
    original = module.window_size
    observed = []

    def declared(loaded, default):
        """Record the actual primary spec and exercise the shared reader."""
        observed.append((loaded["window"], default))
        return original({**loaded, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", declared)
    app = factories[plugin_id]()
    try:
        assert app.window_size == (1234, 789)
        assert observed == [({"width": 1100, "height": 720}, (1100, 720))]
        primary = Path(__file__).parents[2] / "chisurf/plugins" / spec
        assert json.loads(primary.read_text())["window"] == {"width": 1100, "height": 720}
    finally:
        app.close()
