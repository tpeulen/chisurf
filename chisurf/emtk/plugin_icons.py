"""The icon a hub draws in front of a sub-tool's row: the sub-tool's own manifest icon.

A hub (TTTR Tools, Image Tools, the calculators, ...) lists other plugins. Each
of those already declares its pictogram once, in its ``manifest.json``; reading
it from there keeps a hub's list and the main menu showing the same picture,
and means a hub's registry only names an ``icon`` where it wants a different one.
"""

from __future__ import annotations

import ast
import json
from functools import cache
from pathlib import Path

__all__ = ["plugin_icon", "entry_icon"]

#: ``chisurf/plugins``: every manifest lives below it.
PLUGINS = Path(__file__).resolve().parents[1] / "plugins"


@cache
def _manifest_icon(directory: str) -> str:
    """The plugin's icon in the menu's order: manifest ``icon``, then the package's ``icon``.

    The package attribute is read from the source, not imported: a hub lists
    its children before any of them is opened, and importing one to learn its
    icon would load its whole dependency tree for a single character.
    """
    try:
        icon = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8")).get(
            "icon", ""
        )
    except (OSError, ValueError):
        icon = ""
    return icon or _module_icon(Path(directory) / "__init__.py")


def _module_icon(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return ""
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "icon" for t in node.targets)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and not node.value.value.endswith((".png", ".svg"))
        ):
            return node.value.value
    return ""


def plugin_icon(ref: str | None) -> str:
    """The manifest icon of the plugin *ref* names, or ``""``.

    Parameters
    ----------
    ref : str or None
        Any of the spellings hubs use for a child: an entrypoint
        (``"chisurf.plugins.tttr.photon_table.gui.app:make_app"``), a plugin
        path relative to ``chisurf/plugins`` (``"microscopy/img_drift"``), or a
        bare plugin id (``"irf_estimator"``). The nearest enclosing directory
        with a ``manifest.json`` is the plugin.

    Returns
    -------
    str
        The manifest's ``icon``; empty when no manifest is found.
    """
    if not ref:
        return ""
    module = ref.split(":", 1)[0]
    if module.startswith("chisurf.plugins."):
        parts = module.split(".")[2:]
    elif "/" in module:
        parts = [p for p in module.split("/") if p]
    else:
        return _icon_by_id(module)
    for end in range(len(parts), 0, -1):
        directory = PLUGINS.joinpath(*parts[:end])
        if (directory / "manifest.json").is_file():
            return _manifest_icon(str(directory))
    return ""


@cache
def _icon_by_id(plugin_id: str) -> str:
    candidates = [PLUGINS / plugin_id / "manifest.json"]
    candidates += PLUGINS.glob("*/" + plugin_id + "/manifest.json")
    for manifest in candidates:
        if not manifest.is_file():
            continue
        return _manifest_icon(str(manifest.parent))
    return ""


def entry_icon(entry, *refs: str | None) -> str:
    """A hub entry's own ``icon`` if it names one, else the first manifest icon among *refs*.

    *entry* may be a mapping (``panels.json`` rows) or an object with an
    ``icon`` attribute (the registries' dataclasses).
    """
    own = entry.get("icon") if isinstance(entry, dict) else getattr(entry, "icon", "")
    if own:
        return own
    return next((icon for icon in map(plugin_icon, refs) if icon), "")
