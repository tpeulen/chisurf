"""The colour of each kind of task in the ChiSurf window: one category, one colour, everywhere.

The palette is declared in ``task_colors.yaml`` beside this module (categories with a dark and
a light variant, which ribbon groups and docks belong to which category). This module reads
it and answers the two questions the shell asks while drawing:

* *which category* is a plugin, a ribbon group, a dock window in -- :func:`entry_category`,
  :func:`group_category`, :func:`dock_category`;
* *which colours* does a category have -- :func:`accent`, an :class:`emtk.style.ThemedAccent`
  (its dark and light variant). Drawing them -- tabs, stripes, tints, the theme pick and the
  text contrast -- is emtk's (:mod:`emtk.accents`); this module only declares and assigns.

A plugin's category comes from where the ribbon places it (``Tab:Group`` of its manifest's
``display_name``, through :func:`chisurf.emtk.shell_ribbon.plugin_tree`), so a new plugin
filed under an existing group takes the group's colour without touching the palette.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml
from emtk.style import Accent, ThemedAccent

__all__ = [
    "PALETTE_FILE",
    "accent",
    "categories",
    "dock_category",
    "entry_category",
    "group_category",
    "neutral",
    "palette",
    "plugin_categories",
]

#: The declared palette.
PALETTE_FILE = Path(__file__).with_name("task_colors.yaml")
#: The two theme variants every category declares.
THEMES = ("dark", "light")
#: The prefix of a hosted plugin's dock key (:data:`chisurf.emtk.main_app.PLUGIN_KEY`).
_PLUGIN_KEY = "plugin."


@lru_cache(maxsize=1)
def palette() -> dict[str, Any]:
    """The parsed ``task_colors.yaml``, checked: every mapping names a declared category.

    Raises
    ------
    ValueError
        A category missing a theme variant or a colour, or a group / plugin / dock mapped to
        a category that is not declared -- the file is wrong and must fail where it is read.
    """
    data = yaml.safe_load(PALETTE_FILE.read_text(encoding="utf-8")) or {}
    declared = data.get("categories") or {}
    for name, entry in {**declared, "neutral": data.get("neutral") or {}}.items():
        for theme in THEMES:
            colours = (entry or {}).get(theme) or {}
            if not {"fill", "text", "ink"} <= set(colours):
                raise ValueError(f"task colour {name!r} lacks fill/text/ink for the {theme} theme")
    for section in ("groups", "plugins", "docks"):
        for key, category in (data.get(section) or {}).items():
            if category not in declared:
                raise ValueError(f"{section}[{key!r}] names the undeclared category {category!r}")
    return data


def categories() -> dict[str, dict]:
    """``{category: entry}`` in declaration order (the order of the colour key in the docs)."""
    return dict(palette().get("categories") or {})


@lru_cache(maxsize=64)
def _accent(category: str) -> ThemedAccent | None:
    data = palette()
    entry = data.get("neutral") if category == "neutral" else categories().get(category)
    if not entry:
        return None
    return ThemedAccent(*(Accent(**entry[theme]) for theme in THEMES))


def accent(category: str | None) -> ThemedAccent | None:
    """The colours of *category* (dark and light variant); ``None`` for no category."""
    return _accent(category) if category else None


def neutral() -> ThemedAccent:
    """The quiet grey of core chrome (the Tools tree, Start)."""
    return _accent("neutral")


def group_category(tab: str, group: str) -> str | None:
    """The category of the ribbon group *group* of tab *tab* (``"Tab:Group"``, else ``"Tab:*"``)."""
    groups = palette().get("groups") or {}
    return groups.get(f"{tab}:{group}") or groups.get(f"{tab}:*")


def plugin_categories(entries: Iterable[Any]) -> dict[str, str | None]:
    """``{plugin_id: category}`` of the shell's plugins, by where the shipped ribbon layout puts them.

    The layout is the shipped one (no user ordering, experimental tools included), so a plugin
    keeps its colour whatever the user hid or reordered.
    """
    from chisurf.emtk.shell_ribbon import plugin_tree

    overrides = palette().get("plugins") or {}
    out: dict[str, str | None] = {}
    for tab, groups in plugin_tree(list(entries), settings={}, experimental=True).items():
        for group, items in groups.items():
            for entry in items:
                out[entry.plugin_id] = overrides.get(entry.plugin_id) or group_category(tab, group)
    return out


def entry_category(entry: Any, known: dict[str, str | None] | None = None) -> str | None:
    """The category of one plugin entry (*known* is :func:`plugin_categories`, made when not given)."""
    known = known if known is not None else plugin_categories([entry])
    return known.get(entry.plugin_id)


def dock_category(key: str, known: dict[str, str | None]) -> str | None:
    """The category of the shell's dock window *key*: a hosted plugin's, or the ``docks`` mapping's.

    *known* is :func:`plugin_categories` of the shell's plugins. ``None`` is core chrome.
    """
    if key.startswith(_PLUGIN_KEY):
        return known.get(key[len(_PLUGIN_KEY):])
    docks = palette().get("docks") or {}
    if key in docks:
        return docks[key]
    for prefix, category in docks.items():
        if prefix.endswith(".") and key.startswith(prefix):
            return category
    return None
