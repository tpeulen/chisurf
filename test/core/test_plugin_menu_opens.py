"""A plugin that appears in the menu must have something for the click to do.

The plugins menu opens a plugin through
:func:`chisurf.gui.misc_helpers.run_plugin_from_dir`, which tries two things in
order: the manifest's ``entrypoints.gui``, and — failing that — executing
``wizard.py`` or ``__init__.py`` as a macro with ``__name__`` set to
``"plugin"``.

A plugin with neither has a **dead menu entry, silently**: the launcher runs the
file, the file only imports and documents, nothing opens, and nothing is logged.
That is how the ALEX Suite shipped with a button that did nothing until its
``__init__`` grew the launch block.

Static: no Qt, no plugin import.
"""

from __future__ import annotations

import ast
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


def _has_plugin_launch_block(path: pathlib.Path) -> bool:
    """Whether *path* runs something under ``if __name__ == "plugin"``."""
    if not path.is_file():
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        for value in ast.walk(node.test):
            if isinstance(value, ast.Constant) and value.value == "plugin":
                return True
    return False


@pytest.mark.parametrize("plugin_dir", _menu_plugins(), ids=lambda p: p.name)
def test_a_menu_plugin_can_be_opened(plugin_dir: pathlib.Path):
    """Either a manifest GUI entry point, or a ``__name__ == "plugin"`` block."""
    manifest = json.loads((plugin_dir / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("entrypoints") or {}).get("gui"):
        return
    launchable = any(
        _has_plugin_launch_block(plugin_dir / name) for name in ("wizard.py", "__init__.py")
    )
    assert launchable, (
        f"{plugin_dir.relative_to(REPO_ROOT)} is offered in the plugins menu but "
        "has no way to open: declare `entrypoints.gui` in its manifest (the "
        "current standard), or give its __init__.py an "
        '`if __name__ == "plugin":` block. Without one the menu entry runs the '
        "file and opens nothing, without an error."
    )
