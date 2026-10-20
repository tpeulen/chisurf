"""A demo plugin ships with the application but does not compete for menu space.

INC-07 asked to "gate demo plugins behind a flag": a plugin declares
``"demo": true`` in its manifest, and plugin discovery — the one place every
menu host reads — turns that into ``menu_hidden`` unless the user opts in with
``plugins.show_demo_plugins``.

These tests pin both halves: the flag is declared where a host can read it, and
the gate is applied at discovery rather than in each of the four menu builders.
The built-in games were the gate's first users while the Games hub listed them;
since the hub went (every game its own Tools › Games button), they are not
demo-gated — a gated game with no hub is a game nobody can find.
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
    """Return every game's manifest (the games package itself has none)."""
    return sorted(p for p in GAMES_ROOT.rglob("manifest.json") if p.parent != GAMES_ROOT)


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


def test_no_shipped_game_is_demo_gated():
    """With no hub in front of them, a demo-gated game is unreachable by default (BUGS 2026-08-08)."""
    manifests = _game_manifests()
    assert manifests, "no games found — did the games move?"
    gated = [
        str(path.relative_to(REPO_ROOT))
        for path in manifests
        if (load_manifest(path) or PluginManifest(id="", version="")).demo
    ]
    assert not gated, f"these games would vanish from the default ribbon: {gated}"


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


def _probe(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A demo plugin that is not hidden otherwise, on the plugin path; its record key."""
    import chisurf.plugins as plugins

    package = tmp_path / "gating_probe_demo"
    package.mkdir()
    (package / "__init__.py").write_text('name = "Gating probe"\n', encoding="utf-8")
    (package / "manifest.json").write_text(
        json.dumps({"id": "gating_probe_demo", "version": "1", "demo": True, "menu_hidden": False}),
        encoding="utf-8",
    )
    monkeypatch.setattr(plugins, "__path__", [*plugins.__path__, str(tmp_path)])
    return str(package.resolve())


def test_a_demo_is_hidden_from_every_menu_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Discovery, not the four menu builders, is what keeps a demo out."""
    key = _probe(tmp_path, monkeypatch)
    records = _records(monkeypatch, show_demos=False)
    demos = [record for record in records.values() if record["demo"]]
    assert [str(record["package_dir"]) for record in demos] == [key]
    visible = [record["plugin_name"] for record in demos if not record["menu_hidden"]]
    assert not visible, f"demo plugins reachable from the menus by default: {visible}"


def test_opting_in_brings_a_demo_back(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """The setting must actually change the answer, not only exist."""
    key = _probe(tmp_path, monkeypatch)
    assert _records(monkeypatch, show_demos=False)[key]["menu_hidden"] is True
    shown = _records(monkeypatch, show_demos=True)[key]
    assert shown["demo"] is True
    assert shown["menu_hidden"] is False


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
