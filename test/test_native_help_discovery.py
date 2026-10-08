"""Native-only plugin manifests must remain in the shared help/tour gate."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def seam():
    """Load the existing guard without importing any plugin GUI."""
    spec = importlib.util.spec_from_file_location(
        "help_guard", ROOT / "test/test_plugin_help_guide_seam.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_plugin(root, name, entries):
    """Declare a source package whose imports would fail if discovery executed it."""
    directory = root / "chisurf/plugins" / name
    directory.mkdir(parents=True)
    (directory / "app.py").write_text('raise RuntimeError("discovery imported GUI")')
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps({"id": name, "version": "1", "entrypoints": entries}))
    return manifest


def test_native_only_plugin_is_discovered_without_importing(tmp_path, monkeypatch):
    """Removing a Qt entry cannot remove the plugin from release checks."""
    guard = seam()
    write_plugin(tmp_path, "native", {"emtk": "chisurf.plugins.native.app:make_app"})
    monkeypatch.setattr(guard, "_ROOT", tmp_path)
    monkeypatch.setattr(guard, "_PLUGINS", tmp_path / "chisurf/plugins")
    plugins = guard.gui_plugins(revision=None)
    assert [p.id for p in plugins] == ["native"]
    assert plugins[0].directory == tmp_path / "chisurf/plugins/native"


def test_dual_surface_keeps_existing_resource_directory(tmp_path, monkeypatch):
    """A native factory does not move existing Qt help resources."""
    guard = seam()
    manifest = write_plugin(
        tmp_path,
        "dual",
        {"gui": "chisurf.plugins.dual.app:Tool", "emtk": "chisurf.plugins.dual.native:make_app"},
    )
    monkeypatch.setattr(guard, "_ROOT", tmp_path)
    plugin = guard.GuiPlugin(manifest, json.loads(manifest.read_text()))
    assert plugin.directory == manifest.parent


def test_native_parent_resources_are_kept_when_declared_at_plugin_root(tmp_path, monkeypatch):
    """Several native tools consume plugin-root help beside a gui package."""
    guard = seam()
    manifest = write_plugin(tmp_path, "parent", {"emtk": "chisurf.plugins.parent.gui.app:make_app"})
    gui = manifest.parent / "gui"
    gui.mkdir()
    (gui / "app.py").write_text("raise RuntimeError('must not import')")
    (manifest.parent / "help.md").write_text("Existing parent help")
    (manifest.parent / "guide.json").write_text("[]")
    monkeypatch.setattr(guard, "_ROOT", tmp_path)
    plugin = guard.GuiPlugin(manifest, json.loads(manifest.read_text()))
    assert plugin.help_file == manifest.parent / "help.md"
    assert plugin.guide_file == manifest.parent / "guide.json"


def test_committed_enrollment_ignores_foreign_live_native_manifest(tmp_path, monkeypatch):
    """A local uncommitted native port cannot become a release claim."""
    import subprocess

    guard = seam()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    manifest = write_plugin(tmp_path, "prototype", {"script": "__init__.py"})
    subprocess.run(["git", "-C", str(tmp_path), "add", "chisurf/plugins/prototype"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Fixture",
        ],
        check=True,
    )
    manifest.write_text(
        json.dumps(
            {
                "id": "prototype",
                "version": "1",
                "entrypoints": {"emtk": "chisurf.plugins.prototype.app:make_app"},
            }
        )
    )
    monkeypatch.setattr(guard, "_ROOT", tmp_path)
    monkeypatch.setattr(guard, "_PLUGINS", tmp_path / "chisurf/plugins")
    assert guard.gui_plugins() == []
    assert [p.id for p in guard.gui_plugins(revision=None)] == ["prototype"]
