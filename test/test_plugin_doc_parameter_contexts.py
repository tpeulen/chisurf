"""Model-specific parameter contexts cannot collapse reused adapter attributes."""

import json

from build_tools.docs.generate_plugin_docs import _plugin_page


def test_reused_attribute_names_retain_their_model_context(tmp_path, monkeypatch):
    """A fit23 lifetime and a fit24 lifetime retain their own labels and meanings."""
    import build_tools.docs.generate_plugin_docs as docs

    monkeypatch.setattr(docs, "PLUGIN_ROOT", tmp_path)
    monkeypatch.setattr(docs, "REPO_ROOT", tmp_path)
    plugin = tmp_path / "example"
    plugin.mkdir()
    manifest = {"id": "example", "display_name": "Test:Example", "description": "Example"}
    spec = {
        "sections": [
            {
                "type": "panel",
                "title": "Fit23",
                "sections": [
                    {
                        "type": "value",
                        "attr": "p0_value",
                        "label": "τ",
                        "kind": "float",
                        "description": "Single lifetime.",
                    }
                ],
            },
            {
                "type": "panel",
                "title": "Fit24",
                "sections": [
                    {
                        "type": "value",
                        "attr": "p0_value",
                        "label": "τ1",
                        "kind": "float",
                        "description": "First lifetime.",
                    }
                ],
            },
        ]
    }
    for name in ["legacy.view.json", "native.view.json"]:
        (plugin / name).write_text(json.dumps(spec))
    page = _plugin_page(manifest, plugin, {})
    assert "### Fit23" in page and "### Fit24" in page
    assert page.count("Single lifetime.") == 1
    assert page.count("First lifetime.") == 1
