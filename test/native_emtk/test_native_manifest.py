from chisurf.core.plugin.manifest import PluginManifest, validate_manifest_schema


def test_native_factory_entrypoint_roundtrips_without_replacing_qt_adapter():
    data = {
        "id": "example",
        "version": "1.0",
        "entrypoints": {"gui": "example.qt:Tool", "emtk": "example.native:make_app"},
    }
    manifest = PluginManifest.from_dict(data)
    assert manifest.entrypoints.emtk == "example.native:make_app"
    assert manifest.to_dict()["entrypoints"]["emtk"] == "example.native:make_app"
    assert manifest.entrypoints.gui == "example.qt:Tool"
    assert not validate_manifest_schema(data)
