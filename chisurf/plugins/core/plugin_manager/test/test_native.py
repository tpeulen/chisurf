from emtk.testing import RecordingPainter

from chisurf.plugins.core.plugin_manager.api.records import collect_rows
from chisurf.plugins.core.plugin_manager.gui.model import PluginManagerModel


def _model(tmp_path):
    package = tmp_path / "alpha"
    package.mkdir()
    (package / "manifest.json").write_text(
        '{"id":"alpha","version":"1.0","display_name":"Tools:Alpha","description":"Test plugin"}'
    )
    model = PluginManagerModel(settings_block={"disabled_plugins": [], "hide_disabled_plugins": True})
    model._rows = collect_rows([{
        "manifest_id": "alpha", "manifest_version": "1.0", "plugin_name": "Tools:Alpha",
        "description": "Test plugin", "module_path": "chisurf.plugins.alpha",
        "package_dir": str(package), "source": "user", "requires": {"base": "*"},
        "optional_requires": {},
    }])
    model.select_row({"id": "alpha"})
    return model, package


def test_gui_runtime_selection_is_deterministic():
    from types import SimpleNamespace

    from chisurf.core.plugin.registry import select_gui_entrypoint

    manifest = SimpleNamespace(id="demo", entrypoints=SimpleNamespace(gui="pkg:Qt", emtk="pkg:Native"))
    assert select_gui_entrypoint(manifest, "emtk") == ("emtk", "pkg:Native")
    assert select_gui_entrypoint(manifest, "qt") == ("qt", "pkg:Qt")
    assert select_gui_entrypoint(manifest, "auto") == ("emtk", "pkg:Native")
    only_qt = SimpleNamespace(id="qt", entrypoints=SimpleNamespace(gui="pkg:Qt", emtk=None))
    assert select_gui_entrypoint(only_qt, "emtk") == ("qt", "pkg:Qt")


def test_native_manager_renders_dependencies_and_preference_controls(tmp_path):
    from chisurf.plugins.core.plugin_manager.gui.app import PluginManagerApp

    model, _ = _model(tmp_path)
    app = PluginManagerApp(model)
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 1200, 800)
    rendered = " ".join(painter.strings)
    assert "Alpha" in rendered
    assert "Dependencies" in rendered
    assert "Help" in rendered
    assert "Disabled" in rendered
    assert "Remember window state" in rendered
    assert "GUI runtime" in rendered
    assert "base" in rendered
    app.close()


def test_native_manager_preferences_and_rename_use_existing_model(tmp_path, monkeypatch):
    model, package = _model(tmp_path)
    import chisurf.plugins as plugins

    monkeypatch.setattr(plugins, "iter_plugins", lambda: [{
        "manifest_id": "alpha", "manifest_version": "1.0", "plugin_name": "Tools:Alpha",
        "description": "Test plugin", "module_path": "chisurf.plugins.alpha",
        "package_dir": str(package), "source": "user", "requires": {"base": "*"},
        "optional_requires": {},
    }])
    model.set_disabled(True)
    model.gui_mode = "emtk"
    assert model.gui_mode == "emtk"
    assert model.settings.disabled == ["alpha"]
    assert model.selected_disabled
    model.set_show_disabled(True)
    assert model.visible_rows()[0].disabled
    assert model.settings.hide_disabled is False
    assert model.rename_selected("Renamed") == ""
    assert '"display_name": "Tools:Renamed"' in (package / "manifest.json").read_text()
    model.revert()
    assert model.settings.disabled == []
    assert model.show_disabled is False


def test_native_icon_import_centers_and_declares_png(tmp_path):
    """A non-PNG image is put on a square 256 px canvas (the Qt panel's size) and declared."""
    from PIL import Image

    model, package = _model(tmp_path)
    source = tmp_path / "mark.jpg"
    Image.new("RGB", (20, 40), (40, 80, 120)).save(source)
    model.icon_path_text = str(source)
    model.icon_use()
    with Image.open(package / "icon.png") as icon:
        assert icon.size == (256, 256)
        # 20x40 scaled to fit 256 keeps the aspect ratio and is centred: 128 wide
        assert icon.getbbox() == (64, 0, 192, 256)
    assert '"icon": "icon.png"' in (package / "manifest.json").read_text()


def test_native_install_asks_before_replacing_an_existing_plugin(tmp_path, monkeypatch):
    from chisurf.plugins.core.plugin_manager.api import install as installer
    from chisurf.plugins.core.plugin_manager.api.install import InstallPlan

    model, _ = _model(tmp_path)
    destination = tmp_path / "plugins" / "alpha"
    plan = InstallPlan(tmp_path / "alpha.zip", "alpha", destination, overwrites=True)
    monkeypatch.setattr(installer, "inspect_source", lambda source: plan)
    installed = []
    monkeypatch.setattr(installer, "install", lambda selected: installed.append(selected) or destination)
    monkeypatch.setattr(model, "reload", lambda **kwargs: None)

    model.choose_install_source(tmp_path / "alpha.zip")
    assert model.dialog == "confirm_install" and "replaces the plugin" in model.dialog_text
    assert installed == []
    model.dialog_ok()
    assert installed == [plan]
    assert model.install_plan is None
