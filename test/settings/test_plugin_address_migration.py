"""Moving menu addresses preserves explicitly stored plugin preferences."""

from copy import deepcopy

from chisurf.core.settings.settings_utils import _migrate_plugin_addresses


def test_full_address_preferences_migrate_and_explicit_current_values_win():
    old = "Imaging:Lifetime:Pixel-wise MLE"
    current = "Spectroscopy:Imaging:Lifetime:Pixel-wise MLE"
    settings = {
        "plugins": {
            "disabled_plugins": [old, "stable_plugin_id"],
            "toolbar_plugins": ["Spectroscopy:Fluorescence decay:Histogram-Microtime"],
            "plugin_order": {old: 7, current: 3, "stable_plugin_id": 5},
            "statefulness": {"per_plugin": {old: False, "stable_plugin_id": True}},
        },
        "other": {"unchanged": 1},
    }
    result = _migrate_plugin_addresses(deepcopy(settings))
    assert result["plugins"]["disabled_plugins"] == [current, "stable_plugin_id"]
    assert result["plugins"]["toolbar_plugins"] == ["Spectroscopy:Decay:Histogram-Microtime"]
    assert result["plugins"]["plugin_order"] == {current: 3, "stable_plugin_id": 5}
    assert result["plugins"]["statefulness"]["per_plugin"] == {
        current: False,
        "stable_plugin_id": True,
    }
    assert result["other"] == settings["other"]
    assert _migrate_plugin_addresses(deepcopy(result)) == result


def test_correlation_address_and_unknown_preferences_are_preserved():
    settings = {
        "plugins": {
            "disabled_plugins": [
                "Spectroscopy:Fluorescence Correlation Spectroscopy:Correlator",
                "Unrelated:Custom Tool",
            ],
            "plugin_order": {"Spectroscopy:Fluorescence decay:IRF Estimation": 2},
        }
    }
    result = _migrate_plugin_addresses(settings)
    assert result["plugins"]["disabled_plugins"] == [
        "Spectroscopy:Correlation:Correlator",
        "Unrelated:Custom Tool",
    ]
    assert result["plugins"]["plugin_order"] == {"Spectroscopy:Decay:IRF Estimation": 2}


def test_existing_loader_rewrites_only_known_addresses_and_preserves_choices(tmp_path):
    import yaml

    from chisurf.core.settings.settings_utils import get_chisurf_settings

    path = tmp_path / "settings_chisurf.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "plugins": {
                    "disabled_plugins": ["Imaging:Image Tools"],
                    "plugin_order": {"Spectroscopy:Fluorescence decay:Histogram-Microtime": 4},
                    "statefulness": {"per_plugin": {"Imaging:Image Tools": False}},
                },
                "custom": {"keep": 17},
            }
        )
    )
    loaded = get_chisurf_settings(path)
    assert loaded["plugins"]["disabled_plugins"] == ["Spectroscopy:Imaging:Image Tools"]
    assert loaded["plugins"]["plugin_order"]["Spectroscopy:Decay:Histogram-Microtime"] == 4
    assert (
        loaded["plugins"]["statefulness"]["per_plugin"]["Spectroscopy:Imaging:Image Tools"] is False
    )
    assert loaded["custom"] == {"keep": 17}
    persisted = yaml.safe_load(path.read_text())
    assert persisted["plugins"]["disabled_plugins"] == loaded["plugins"]["disabled_plugins"]
    assert get_chisurf_settings(path) == loaded
