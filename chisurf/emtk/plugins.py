"""Native plugin discovery that does not import the Qt application or plugins."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

_launch_options: dict = {}


def manifests(root: str | Path | None = None) -> dict[str, dict]:
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1] / "plugins"
    found = {}
    for path in sorted(root.rglob("manifest.json")):
        if "cookiecutter" in str(path):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("id") or not data.get("version"):
            continue
        key = data["id"]
        if key in found:
            raise ValueError(f"Duplicate plugin id: {key}")
        found[key] = data
    return found


def native_factory(plugin_id: str, root: str | Path | None = None) -> str:
    catalog = manifests(root)
    if plugin_id not in catalog:
        raise KeyError(f"Unknown plugin: {plugin_id}")
    spec = catalog[plugin_id].get("entrypoints", {}).get("emtk")
    if not spec:
        raise ValueError(f"Plugin {plugin_id!r} has no verified native factory declaration yet")
    return spec


def load_plugin(plugin_id: str, *, locale: str | None = None, root: str | Path | None = None,
                persist: bool = True):
    """Construct a declared EMTK control, preserving source identities in translation."""
    from .i18n import install

    spec = native_factory(plugin_id, root)
    install(locale)
    module, attribute = spec.split(":", 1)
    app = getattr(importlib.import_module(module), attribute)()
    if persist:
        from .state import attach_native_state

        attach_native_state(plugin_id, app)
    return app


def configure_launch(plugin_id: str, locale: str | None = None,
                     path: str | None = None, anchor: str | None = None) -> None:
    _launch_options.update(plugin_id=plugin_id, locale=locale, path=path, anchor=anchor)


def make_selected_app():
    app = load_plugin(_launch_options["plugin_id"], locale=_launch_options.get("locale"))
    path = _launch_options.get("path")
    if path:
        model = app.model
        if _launch_options["plugin_id"] == "help":
            if not model.open_page(path, anchor=_launch_options.get("anchor")):
                raise ValueError(f"Could not open document: {path}")
        elif _launch_options["plugin_id"] == "code_editor":
            anchor = _launch_options.get("anchor")
            line = int(anchor) if anchor and anchor.isdecimal() else None
            if model.open_file(path, line=line) is None:
                raise ValueError(f"Could not open source: {path}")
        else:
            raise ValueError("--path is supported for help and code_editor")
    return app
