import json

import pytest

from chisurf.emtk.plugins import manifests, native_factory


def test_native_discovery_keeps_pending_ports_explicit(tmp_path):
    for key, entrypoints in [("native", {"emtk": "demo:make_app"}), ("qt", {"gui": "demo:Tool"})]:
        directory = tmp_path / key
        directory.mkdir()
        (directory / "manifest.json").write_text(json.dumps({"id": key, "version": "1", "entrypoints": entrypoints}))
    assert set(manifests(tmp_path)) == {"native", "qt"}
    assert native_factory("native", tmp_path) == "demo:make_app"
    with pytest.raises(ValueError, match="no verified native factory"):
        native_factory("qt", tmp_path)
    with pytest.raises(KeyError, match="Unknown plugin"):
        native_factory("missing", tmp_path)


def test_factory_initialization_does_not_override_selected_language():
    from emtk import i18n as toolkit_i18n

    from chisurf.emtk import i18n

    try:
        i18n.install("de")
        i18n.install()
        assert toolkit_i18n.get_locale() == "de"
        assert toolkit_i18n.tr("💾 Export CSV") == "💾 CSV exportieren"
    finally:
        i18n.set_locale("en")
