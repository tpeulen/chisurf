"""A demo plugin ships with the application but does not compete for menu space.

The built-in games (`chisurf/plugins/misc/games`) sat in the generated menus
beside the analysis tools with nothing distinguishing them, which is the open
half of INC-07 ("gate demo plugins behind a flag"). A plugin now declares
``"demo": true`` in its manifest, and plugin discovery — the one place every
menu host reads — turns that into ``menu_hidden`` unless the user opts in with
``plugins.show_demo_plugins``.

These tests pin both halves: the flag is declared where a host can read it, and
the gate is applied at discovery rather than in each of the four menu builders.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from chisurf.core.plugin.manifest import PluginManifest, load_manifest, validate_manifest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "chisurf" / "plugins"
GAMES_ROOT = PLUGIN_ROOT / "misc" / "games"


def _game_manifests() -> list[pathlib.Path]:
    """Return the games hub manifest and every game manifest inside it."""
    return sorted(GAMES_ROOT.rglob("manifest.json"))


def test_demo_is_a_declared_manifest_key():
    """An undeclared key is dropped in silence — the closed key set must know ``demo``."""
    assert "demo" in PluginManifest.__dataclass_fields__
    assert not validate_manifest({"id": "x", "version": "1", "demo": True})


def test_demo_round_trips_through_the_manifest():
    """``to_dict`` must carry the flag, or a rewritten manifest loses it."""
    manifest = PluginManifest.from_dict({"id": "x", "version": "1", "demo": True})
    assert manifest.demo is True
    assert PluginManifest.from_dict(manifest.to_dict()).demo is True
    assert PluginManifest.from_dict({"id": "x", "version": "1"}).demo is False


def test_every_game_declares_itself_a_demo():
    """The games are the demos; a game that forgets the flag is back in the menus."""
    manifests = _game_manifests()
    assert manifests, "no games found — did the demo plugins move?"
    undeclared = [
        str(path.relative_to(REPO_ROOT))
        for path in manifests
        if not (load_manifest(path) or PluginManifest(id="", version="")).demo
    ]
    assert not undeclared, f"these demo plugins do not declare 'demo': {undeclared}"


def test_game_manifests_stay_valid_json_and_schema():
    """The flag is added by hand; a trailing comma there breaks discovery silently."""
    for path in _game_manifests():
        data = json.loads(path.read_text(encoding="utf-8"))
        assert not validate_manifest(data), f"{path.relative_to(REPO_ROOT)} is invalid"


def test_the_default_settings_declare_the_opt_in():
    """The gate is user-facing, so the key must exist for the settings editor to show."""
    import yaml

    settings_path = REPO_ROOT / "chisurf" / "core" / "settings" / "settings_chisurf.yaml"
    settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    assert settings["plugins"]["show_demo_plugins"] is False


def _records(monkeypatch: pytest.MonkeyPatch, *, show_demos: bool) -> dict[str, dict]:
    """Run an uncached discovery pass with the demo gate forced open or shut."""
    import chisurf.plugins as plugins

    monkeypatch.setattr(plugins, "demo_plugins_enabled", lambda: show_demos)
    return {str(record["package_dir"]): record for record in plugins._iter_plugins_uncached()}


def test_a_demo_is_hidden_from_every_menu_by_default(monkeypatch: pytest.MonkeyPatch):
    """Discovery, not the four menu builders, is what keeps a demo out."""
    records = _records(monkeypatch, show_demos=False)
    demos = [record for record in records.values() if record["demo"]]
    assert demos, "plugin discovery reported no demo plugins at all"
    visible = [record["plugin_name"] for record in demos if not record["menu_hidden"]]
    assert not visible, f"demo plugins reachable from the menus by default: {visible}"


def test_opting_in_brings_the_demo_hub_back(monkeypatch: pytest.MonkeyPatch):
    """The setting must actually change the answer, not only exist."""
    records = _records(monkeypatch, show_demos=True)
    hub = records[str(GAMES_ROOT)]
    assert hub["demo"] is True
    assert hub["menu_hidden"] is False


def test_the_gate_hides_only_demos(monkeypatch: pytest.MonkeyPatch):
    """A non-demo plugin's menu visibility is unchanged by the setting."""
    hidden_off = {
        path: record["menu_hidden"]
        for path, record in _records(monkeypatch, show_demos=False).items()
        if not record["demo"]
    }
    hidden_on = {
        path: record["menu_hidden"]
        for path, record in _records(monkeypatch, show_demos=True).items()
        if not record["demo"]
    }
    assert hidden_off == hidden_on


def test_discovery_record_always_carries_the_flag(monkeypatch: pytest.MonkeyPatch):
    """A host must never have to guess that a missing key means "not a demo"."""
    for record in _records(monkeypatch, show_demos=False).values():
        assert isinstance(record["demo"], bool), record["package_dir"]
