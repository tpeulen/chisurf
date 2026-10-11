"""Regression tests for the manifest file boundary."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from chisurf.core.plugin.manifest import (
    PluginManifest,
    load_manifest,
    validate_manifest,
)
from chisurf.core.plugin.registry import PluginRegistry

MINIMAL = {"id": "example", "version": "1.0"}


@pytest.mark.parametrize(
    "document",
    [
        [],
        "manifest",
        None,
        {"id": [], "version": "1.0"},
        {"id": "example", "version": []},
        {"id": "example", "version": "1.0", "entrypoints": []},
        {"id": "example", "version": "1.0", "entrypoints": {"gui": []}},
        {"id": "example", "version": "1.0", "rpc_methods": None},
        {"id": "example", "version": "1.0", "rpc_methods": {}},
        {"id": "example", "version": "1.0", "rpc_methods": [[]]},
        {"id": "example", "version": "1.0", "dependencies": []},
        {"id": "example", "version": "1.0", "requires": {"missing": []}},
        {"id": "example", "version": "1.0", "optional_requires": {"x": True}},
        {"id": "example", "version": "1.0", "library": []},
        {"id": "example", "version": "1.0", "experimental": "yes"},
        {"id": "example", "version": "1.0", "menu_hidden": 1},
    ],
)
def test_load_manifest_rejects_malformed_shapes(tmp_path: Path, document, caplog):
    """Malformed JSON objects are rejected before dataclass construction."""
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert load_manifest(path) is None

    assert str(path) in caplog.text
    assert "manifest" in caplog.text.lower()


@pytest.mark.parametrize(
    "field",
    [
        "authors",
        "categories",
        "operation_types",
        "events",
        "dependencies",
        "requires",
        "optional_requires",
        "entrypoints",
        "statefulness",
        "display_name",
        "description",
        "experimental_message",
        "deprecation_message",
        "library",
        "experimental",
        "menu_hidden",
        "deprecated",
        "demo",
    ],
)
def test_load_manifest_rejects_null_non_nullable_fields(tmp_path, field):
    """An explicit null is not the same as an absent defaulted collection/flag."""
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({**MINIMAL, field: None}))
    assert load_manifest(path) is None


def test_validate_manifest_rejects_non_list_rpc_methods():
    """The semantic validator must report shape errors instead of iterating them."""
    errors = validate_manifest({**MINIMAL, "rpc_methods": None})
    assert any("rpc_methods" in error for error in errors)


@pytest.mark.parametrize(
    "field",
    ["gui", "cli", "services", "script", "emtk"],
)
def test_validate_manifest_rejects_malformed_entrypoint(field):
    """Every declared entrypoint is a nullable string."""
    errors = validate_manifest({**MINIMAL, "entrypoints": {field: []}})
    assert any("entrypoint" in error for error in errors)


def test_validate_manifest_rejects_unknown_nested_keys():
    """Nested objects are closed just like the top-level manifest."""
    errors = validate_manifest(
        {
            **MINIMAL,
            "entrypoints": {"gui": "pkg:Widget", "typo": "pkg:Other"},
            "rpc_methods": [{"name": "example.ping", "typo": True}],
        }
    )
    assert any("entrypoints" in error and "typo" in error for error in errors)
    assert any("rpc_methods" in error and "typo" in error for error in errors)


def test_load_manifest_logs_read_failure(tmp_path: Path, monkeypatch, caplog):
    """I/O failures return None and identify the unreadable path."""
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(MINIMAL), encoding="utf-8")

    def fail_read_text(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    with caplog.at_level(logging.WARNING):
        assert load_manifest(path) is None
    assert str(path) in caplog.text
    assert "permission denied" in caplog.text


def test_load_manifest_logs_invalid_utf8(tmp_path: Path, caplog):
    """Undecodable files are handled at the file boundary."""
    path = tmp_path / "manifest.json"
    path.write_bytes(b"{\xff")
    with caplog.at_level(logging.WARNING):
        assert load_manifest(path) is None
    assert str(path) in caplog.text
    assert "utf" in caplog.text.lower()


def test_missing_optional_manifest_is_quiet(tmp_path: Path, caplog):
    """An absent optional manifest is the one non-error None result."""
    path = tmp_path / "missing.json"
    with caplog.at_level(logging.WARNING):
        assert load_manifest(path) is None
    assert caplog.text == ""


def test_from_dict_remains_permissive_about_unknown_keys():
    """Direct callers retain the documented parser behavior."""
    manifest = PluginManifest.from_dict({**MINIMAL, "future_field": True})
    assert manifest.id == "example"


def test_full_roundtrip_preserves_nullable_fields_and_emtk():
    """Optional nulls, schema references, and EMTK survive serialization."""
    data = {
        **MINIMAL,
        "state_schema": None,
        "entrypoints": {"emtk": "example.gui:make_view"},
        "rpc_methods": [
            {
                "name": "example.ping",
                "params_schema": "example#/params/Ping",
                "result_schema": None,
            }
        ],
        "dependencies": {},
        "requires": {},
        "optional_requires": {},
    }
    manifest = PluginManifest.from_dict(data)
    assert PluginManifest.from_dict(manifest.to_dict()).to_dict() == manifest.to_dict()
    assert manifest.entrypoints.emtk == "example.gui:make_view"
    assert manifest.rpc_methods[0].params_schema == "example#/params/Ping"


def test_registry_discovers_healthy_sibling_after_invalid_manifest(tmp_path: Path):
    """One malformed sibling must not prevent discovery of a healthy plugin."""
    for name, contents in (
        ("broken", "[]"),
        ("healthy", json.dumps(MINIMAL)),
    ):
        plugin_dir = tmp_path / name
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("", encoding="utf-8")
        (plugin_dir / "manifest.json").write_text(contents, encoding="utf-8")

    manifests = PluginRegistry().discover(search_paths=[tmp_path])
    assert [manifest.id for manifest in manifests] == ["example"]
