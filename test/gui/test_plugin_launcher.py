"""A menu entry must open a window, and a manifest is how a plugin says which.

Every shipped manifest's ``entrypoints.emtk`` must resolve to something callable; the
declaration itself is checked in ``test/core/test_plugin_menu_opens.py``. A menu entry naming a
factory that is not there is a button that does nothing.
"""

from __future__ import annotations

import importlib
import json
import pathlib

import pytest

PLUGINS = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "plugins"


def _emtk_entrypoints() -> list[tuple[str, str]]:
    """Return ``(plugin id, entrypoint)`` for every shipped manifest with an emtk app."""
    out = []
    for path in sorted(PLUGINS.rglob("manifest.json")):
        if "{{" in str(path):  # the cookiecutter template
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        entry = (data.get("entrypoints") or {}).get("emtk")
        if entry:
            out.append((data.get("id", path.parent.name), entry))
    return out


@pytest.mark.parametrize("plugin_id,entry", _emtk_entrypoints(), ids=lambda v: str(v)[:40])
def test_every_declared_emtk_entry_point_resolves(plugin_id: str, entry: str):
    """The module imports and the named attribute is callable."""
    module_path, _, attr = entry.partition(":")
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        pytest.skip(f"{plugin_id}: optional dependency missing ({exc})")
    target = getattr(module, attr) if attr else module
    assert callable(target), f"{plugin_id}: {entry} is not callable"
