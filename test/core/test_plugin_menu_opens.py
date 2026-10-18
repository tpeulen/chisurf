"""A plugin that appears in the menu must have something for the click to do.

The emtk shell opens a plugin from its manifest: ``entrypoints.action`` runs as
an action, ``entrypoints.emtk`` builds the app. A plugin with neither has a
**dead menu entry, silently**: nothing opens and nothing is logged.

Static: no Qt, no plugin import.
"""

from __future__ import annotations

import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "chisurf" / "plugins"


def _menu_plugins() -> list[pathlib.Path]:
    """Return the directory of every plugin the menu offers."""
    out = []
    for manifest_path in sorted(PLUGIN_ROOT.rglob("manifest.json")):
        if any("{{" in part for part in manifest_path.parts):
            continue  # cookiecutter scaffold, not a real plugin
        if any(part in ("test", "tests") for part in manifest_path.parts):
            continue  # a fixture's manifest (chimol's render baselines), not a plugin
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if manifest.get("menu_hidden") or not manifest.get("id"):
            continue
        out.append(manifest_path.parent)
    return out


@pytest.mark.parametrize("plugin_dir", _menu_plugins(), ids=lambda p: p.name)
def test_a_menu_plugin_can_be_opened(plugin_dir: pathlib.Path):
    """A menu plugin declares an ``entrypoints.emtk`` app or an ``entrypoints.action``."""
    manifest = json.loads((plugin_dir / "manifest.json").read_text(encoding="utf-8"))
    entrypoints = manifest.get("entrypoints") or {}
    assert any(entrypoints.get(kind) for kind in ("action", "emtk")), (
        f"{plugin_dir.relative_to(REPO_ROOT)} is offered in the plugins menu but "
        "has no way to open: declare `entrypoints.emtk` (or `.action`) in its manifest."
    )
