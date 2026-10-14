"""Regression tests for shared plugin discovery and cache behavior."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys

import pytest

from chisurf.core.plugin.registry import PluginRegistry


def _plugin(root, folder, plugin_id, version="1.0.0", *, entrypoints=None):
    """Create an importable plugin package without executing its code."""
    directory = root / folder
    directory.mkdir(parents=True)
    (directory / "__init__.py").write_text('raise RuntimeError("discovery imported plugin")\n')
    (directory / "manifest.json").write_text(
        json.dumps({"id": plugin_id, "version": version, "entrypoints": entrypoints or {}})
    )
    return directory


def test_registry_discovers_plugins_below_hidden_search_root(tmp_path):
    """The default ~/.chisurf/plugins location must be searchable."""
    root = tmp_path / ".chisurf" / "plugins"
    _plugin(root, "visible", "visible")
    _plugin(root, ".disabled", "disabled")
    _plugin(root, "{{template}}", "template")

    manifests = PluginRegistry().discover([root])

    assert [manifest.id for manifest in manifests] == ["visible"]


def test_registry_duplicate_ids_use_first_search_path(tmp_path, caplog):
    """Returned metadata and registration must refer to the same source."""
    preferred = _plugin(tmp_path / "first", "z_plugin", "shared", "1.0.0")
    shadowed = _plugin(tmp_path / "second", "a_plugin", "shared", "2.0.0")
    registry = PluginRegistry()

    manifests = registry.discover([preferred.parent, shadowed.parent])

    assert [(manifest.id, manifest.version) for manifest in manifests] == [("shared", "1.0.0")]
    assert registry.all_manifests == manifests
    assert registry.get_manifest("shared") is manifests[0]
    assert str(preferred) in caplog.text
    assert str(shadowed) in caplog.text
    assert "shared" in caplog.text


def test_registry_duplicate_modules_do_not_advertise_shadowed_manifest(tmp_path, caplog):
    """Different IDs at the same module path still import from the first root."""
    first = _plugin(tmp_path / "first", "original", "shared")
    second = _plugin(tmp_path / "second", "original", "shadowed")
    registry = PluginRegistry()

    manifests = registry.discover([first.parent, second.parent])

    assert [manifest.id for manifest in manifests] == ["shared"]
    assert registry.get_manifest("shadowed") is None
    assert str(first) in caplog.text
    assert str(second) in caplog.text


def _mixed_identity_pair(tmp_path, first_kind):
    """An earlier package shadows a later one, even without valid metadata."""
    first = _plugin(tmp_path / "first", "original", "first")
    second = _plugin(tmp_path / "second", "original", "second")
    if first_kind == "manifest":
        (second / "manifest.json").unlink()
        (second / "__init__.py").write_text(
            'name = "Second legacy"\nraise RuntimeError("imported")\n'
        )
    else:
        (first / "manifest.json").unlink()
        prefix = 'name = "First legacy"\n' if first_kind == "legacy" else ""
        (first / "__init__.py").write_text(prefix + 'raise RuntimeError("imported")\n')
    return first, second


@pytest.mark.parametrize("first_kind", ["legacy", "manifest", "unnamed"])
def test_registry_collisions_cover_all_package_kinds(tmp_path, caplog, first_kind):
    first, second = _mixed_identity_pair(tmp_path, first_kind)
    registry = PluginRegistry()
    manifests = registry.discover([first.parent, second.parent])
    assert [manifest.id for manifest in manifests] == (
        ["first"] if first_kind == "manifest" else []
    )
    assert len(registry._legacy_plugins) == (1 if first_kind == "legacy" else 0)
    assert str(first) in caplog.text
    assert str(second) in caplog.text


@pytest.mark.parametrize("first_kind", ["legacy", "manifest", "unnamed"])
def test_menu_collisions_cover_all_package_kinds(tmp_path, monkeypatch, caplog, first_kind):
    from chisurf import plugins

    first, second = _mixed_identity_pair(tmp_path, first_kind)
    monkeypatch.setattr(plugins, "__path__", [str(first.parent), str(second.parent)])
    monkeypatch.setattr(plugins, "user_plugins_dir", second.parent)
    records = list(plugins._iter_plugins_uncached())
    assert len(records) == (0 if first_kind == "unnamed" else 1)
    if records:
        assert records[0]["package_dir"] == first.resolve()
        assert records[0]["manifest_id"] == ("first" if first_kind == "manifest" else None)
    assert str(first) in caplog.text
    assert str(second) in caplog.text


@pytest.mark.parametrize("scanner", ["registry", "menu"])
@pytest.mark.parametrize("parent_kind", ["regular-first", "namespace-first", "namespaces"])
def test_nested_discovery_matches_python_package_precedence(
    tmp_path, monkeypatch, scanner, parent_kind
):
    from chisurf import plugins

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    early = _plugin(first_root / "group", "early", "early")
    late = _plugin(second_root / "group", "late", "late")
    if parent_kind == "regular-first":
        (early.parent / "__init__.py").write_text('raise AssertionError("parent imported")\n')
    if parent_kind != "namespaces":
        (late.parent / "__init__.py").write_text('raise AssertionError("parent imported")\n')
    expected = {
        "regular-first": ["early"],
        "namespace-first": ["late"],
        "namespaces": ["early", "late"],
    }[parent_kind]

    if scanner == "registry":
        records = PluginRegistry().discover([first_root, second_root])
        assert [manifest.id for manifest in records] == expected
    else:
        monkeypatch.setattr(plugins, "__path__", [str(first_root), str(second_root)])
        monkeypatch.setattr(plugins, "user_plugins_dir", second_root)
        records = list(plugins._iter_plugins_uncached())
        assert [record["manifest_id"] for record in records] == expected


@pytest.mark.parametrize("scanner", ["registry", "menu"])
def test_fresh_discovery_refreshes_stale_package_finders(tmp_path, monkeypatch, scanner):
    from importlib.machinery import PathFinder

    from chisurf import plugins

    root = tmp_path / "plugins"
    root.mkdir()
    timestamp = root.stat()
    assert PathFinder.find_spec("installed", [str(root)]) is None
    _plugin(root, "installed", "installed")
    os.utime(root, ns=(timestamp.st_atime_ns, timestamp.st_mtime_ns))
    assert PathFinder.find_spec("installed", [str(root)]) is None

    if scanner == "registry":
        assert [manifest.id for manifest in PluginRegistry().discover([root])] == ["installed"]
    else:
        monkeypatch.setattr(plugins, "__path__", [str(root)])
        monkeypatch.setattr(plugins, "user_plugins_dir", root)
        assert [record["manifest_id"] for record in plugins._iter_plugins_uncached()] == [
            "installed"
        ]


def test_menu_discovery_ignores_invalid_root_entries(tmp_path, monkeypatch):
    from chisurf import plugins

    _plugin(tmp_path, "healthy", "healthy")
    monkeypatch.setattr(plugins, "__path__", [None, str(tmp_path)])
    monkeypatch.setattr(plugins, "user_plugins_dir", tmp_path)
    assert [record["manifest_id"] for record in plugins._iter_plugins_uncached()] == ["healthy"]


def test_registry_rescan_replaces_legacy_snapshot(tmp_path):
    """Repeated discovery must not retain deleted legacy plugin records."""
    directory = tmp_path / "legacy"
    directory.mkdir()
    init_py = directory / "__init__.py"
    init_py.write_text('name = "Legacy Tool"\n')
    registry = PluginRegistry()
    registry.discover([tmp_path])
    registry.discover([tmp_path])

    assert len(registry._legacy_plugins) == 1

    init_py.unlink()
    registry.discover([tmp_path])
    assert registry._legacy_plugins == []


def test_emtk_only_plugin_is_not_cli_only(tmp_path):
    """Native-only factories must be offered by GUI discovery."""
    from chisurf.plugins import _read_manifest_metadata

    directory = _plugin(tmp_path, "native", "native", entrypoints={"emtk": "example:make_app"})

    metadata = _read_manifest_metadata(directory)
    assert metadata is not None
    assert metadata["cli_only"] is False


def test_contract_collection_does_not_pollute_import_paths():
    """Collecting static contract tests must not shadow editable dependencies."""
    import pathlib
    import subprocess

    contract = pathlib.Path(__file__).resolve().parents[1] / "plugins" / "test_plugin_contracts.py"
    program = (
        "import runpy, sys\n"
        "import chisurf.plugins\n"
        "before = list(sys.path)\n"
        f"runpy.run_path({str(contract)!r})\n"
        "assert sys.path == before, (before, sys.path)\n"
    )
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_plugin_invalidation_refreshes_python_import_finders(tmp_path, monkeypatch):
    """An installed module must import even within the filesystem mtime race."""
    from chisurf import plugins

    monkeypatch.syspath_prepend(str(tmp_path))
    module_name = "chisurf_test_installed_module"
    assert importlib.util.find_spec(module_name) is None
    directory_state = tmp_path.stat()
    (tmp_path / f"{module_name}.py").write_text("VALUE = 42\n")
    os.utime(tmp_path, ns=(directory_state.st_atime_ns, directory_state.st_mtime_ns))
    assert importlib.util.find_spec(module_name) is None
    monkeypatch.setattr(plugins, "_PLUGIN_CACHE", [{"sentinel": True}])

    try:
        plugins.invalidate_plugin_cache()
        installed = importlib.import_module(module_name)
        assert installed.VALUE == 42
        assert plugins._PLUGIN_CACHE is None
    finally:
        sys.modules.pop(module_name, None)
        sys.path_importer_cache.pop(str(tmp_path), None)


@pytest.mark.parametrize("same_module", [False, True], ids=["duplicate-id", "duplicate-module"])
def test_menu_discovery_keeps_first_importable_identity(tmp_path, monkeypatch, caplog, same_module):
    """Menus must not advertise metadata from a shadowed plugin source."""
    from chisurf import plugins

    first = _plugin(tmp_path / "first", "original", "shared", "1.0.0")
    second = _plugin(
        tmp_path / "second",
        "original" if same_module else "different",
        "different" if same_module else "shared",
        "2.0.0",
    )
    monkeypatch.setattr(plugins, "__path__", [str(first.parent), str(second.parent)])
    monkeypatch.setattr(plugins, "user_plugins_dir", second.parent)

    records = list(plugins._iter_plugins_uncached())

    assert [(record["manifest_id"], record["manifest_version"]) for record in records] == [
        ("shared", "1.0.0")
    ]
    assert records[0]["package_dir"] == first.resolve()
    assert str(first) in caplog.text
    assert str(second) in caplog.text


def test_menu_discovery_excludes_hidden_and_template_packages(tmp_path, monkeypatch):
    """Unimportable scaffolds are not plugins, even below a hidden search root."""
    from chisurf import plugins

    root = tmp_path / ".chisurf" / "plugins"
    _plugin(root, "visible", "visible")
    _plugin(root, ".disabled", "disabled")
    _plugin(root, "{{template}}", "template")
    monkeypatch.setattr(plugins, "__path__", [str(root)])
    monkeypatch.setattr(plugins, "user_plugins_dir", root)

    records = list(plugins._iter_plugins_uncached())

    assert [record["manifest_id"] for record in records] == ["visible"]
    assert records[0]["source"] == "user"
