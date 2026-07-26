"""List-valued settings must stay lists across a settings save/load round-trip.

The plugin settings (``toolbar_plugins``, ``disabled_plugins``,
``disabled_models``) are consumed by iteration — ``Main.load_toolbar_plugins``
walks ``plugins.toolbar_plugins`` element by element. If such a value is ever
flattened into a comma-joined scalar the iteration does not fail, it silently
walks *characters*, so the toolbar comes up empty instead of raising. These
tests pin the list-ness at the two places it can be lost: the shipped defaults
and the settings loader/writer round-trip.

This file replaces four prototyping scripts (``test/settings/test_yaml.py``,
``test/settings/test_real_settings.py``, ``test/plugins/test_plugins_list_format.py``,
``test/gui/test_list_editor_fix.py``) that asked the same question of a
``chisurf.gui.widgets.yaml_utils.dump_yaml`` which has never existed — they
failed at collection and took three test packages down with them.
"""

from __future__ import annotations

import pathlib

import yaml

from chisurf.core.settings import settings_utils

#: Plugin settings whose value is a sequence the GUI iterates over.
PLUGIN_LIST_KEYS = ("toolbar_plugins", "disabled_plugins", "disabled_models")

PACKAGED_SETTINGS = pathlib.Path(settings_utils.__file__).parent / "settings_chisurf.yaml"


def packaged_plugin_settings() -> dict:
    """Return the ``plugins`` section of the packaged settings file."""
    return yaml.safe_load(PACKAGED_SETTINGS.read_text(encoding="utf-8"))["plugins"]


def test_shipped_settings_store_plugin_lists_as_sequences() -> None:
    """The packaged ``settings_chisurf.yaml`` stores plugin lists as sequences."""
    plugins = packaged_plugin_settings()
    for key in PLUGIN_LIST_KEYS:
        value = plugins[key]
        assert isinstance(value, list), f"plugins.{key} is {type(value).__name__}, not a list"
        assert all(isinstance(entry, str) for entry in value)


def test_user_plugin_list_replaces_packaged_default_wholesale(tmp_path) -> None:
    """A user list overrides the packaged one entirely; sibling defaults survive.

    ``_deep_merge`` merges dicts key-by-key but replaces every other value —
    a user's shortened toolbar must not be back-filled with packaged entries.
    """
    user_file = tmp_path / "settings_chisurf.yaml"
    user_file.write_text(
        yaml.safe_dump({"plugins": {"toolbar_plugins": ["Tools:Only"]}}),
        encoding="utf-8",
    )

    merged = settings_utils.get_chisurf_settings(user_file)

    assert merged["plugins"]["toolbar_plugins"] == ["Tools:Only"]
    # Keys the user file does not mention still resolve to the packaged defaults.
    assert isinstance(merged["plugins"]["disabled_plugins"], list)
    packaged = packaged_plugin_settings()
    assert merged["plugins"]["disabled_plugins"] == packaged["disabled_plugins"]


def test_plugin_lists_survive_a_settings_write_read_round_trip(tmp_path) -> None:
    """Writing settings the way the writers do keeps lists as YAML sequences."""
    toolbar = [
        "Tools:Histogram-Microtime",
        "FCS:Correlator",
        "Single-Molecule:Burst-Selection",
    ]
    user_file = tmp_path / "settings_chisurf.yaml"
    with user_file.open("w", encoding="utf-8") as fh:
        yaml.safe_dump({"plugins": {"toolbar_plugins": toolbar}}, fh, default_flow_style=False)

    text = user_file.read_text(encoding="utf-8")
    assert "- Tools:Histogram-Microtime" in text, "block-style sequence expected"
    assert "Tools:Histogram-Microtime, FCS:Correlator" not in text, "list was comma-joined"

    reloaded = settings_utils.get_chisurf_settings(user_file)["plugins"]["toolbar_plugins"]
    assert reloaded == toolbar
