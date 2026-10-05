"""Where a plugin's button lands in the ribbon: tab, group, label. Qt-free.

A plugin's manifest ``display_name`` is its address, ``"Tab:Group:Name"``. The
first segment is the ribbon tab, the last is the button, and everything between
is the group. Hubs (TTTR Tools, Image Tools, ...) are ordinary plugins with an
address; the tools a hub hosts are ``menu_hidden`` and reach the user through it.

The ribbon builds its plugin tabs from :func:`plugin_layout`, and the layout test
reads the same function, so the rules exist once.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

__all__ = [
    "split_address",
    "is_listed",
    "group_records",
    "ordered_tabs",
    "plugin_layout",
    "GROUP_SEPARATOR",
    "TAB_ORDER",
    "GROUP_ORDER",
]

#: Joins the middle segments of a deep address into one group title.
GROUP_SEPARATOR = " › "

#: The domain tabs, left to right. A tab not named here follows them alphabetically,
#: and ``Dev`` is always last.
TAB_ORDER = ("File", "Main", "Spectroscopy", "Imaging", "Structure", "Tools")

#: Groups inside a tab, left to right: the order work happens in, not the alphabet.
#: A group not named here follows the named ones in order of first appearance.
GROUP_ORDER = {
    "File": ("Setup", "Data"),
    "Spectroscopy": ("Decay", "Correlation", "Single-Molecule", "Kinetics"),
    "Tools": ("Photon data", "Calculators", "Views", "System"),
}

#: Tabs the ribbon builds itself; their ``Setup:`` and ``Help:`` plugins land in groups
#: of those tabs rather than in tabs of their own.
SPECIAL_TABS = {"Setup": "File", "Help": "Main"}


def split_address(display_name: str) -> tuple[str, str, str]:
    """``(tab, group, label)`` of a ``display_name``.

    ``"Tab:Name"`` lands in a group named after its tab; ``"Tab:A:B:Name"`` in
    the group ``"A › B"`` (any depth). A name without ``:`` lands on ``Main``.
    """
    parts = [part.strip() for part in display_name.split(":")]
    if len(parts) == 1:
        return "Main", "Main", parts[0]
    tab, label = parts[0], parts[-1]
    middle = parts[1:-1]
    group = GROUP_SEPARATOR.join(middle) if middle else tab
    return tab, group, label


def is_listed(info: Mapping, settings: Mapping, experimental: bool = False) -> bool:
    """Whether the ribbon shows a button for this plugin record.

    Hidden plugins never get one; disabled (broken) and CLI-only plugins only in
    experimental mode, and not even then when ``hide_disabled_plugins`` is set.
    """
    if info.get("menu_hidden"):
        return False
    name = info.get("plugin_name") or info.get("module_name") or ""
    label = split_address(name)[2]
    disabled = set(settings.get("disabled_plugins", []) or [])
    broken = bool({name, info.get("module_name") or "", label} & disabled)
    if (broken or info.get("cli_only")) and not experimental:
        return False
    if broken and experimental and settings.get("hide_disabled_plugins", True):
        return False
    return True


def ordered_tabs(tabs: Iterable[str]) -> list[str]:
    """*tabs* in ribbon order: :data:`TAB_ORDER`, then the rest alphabetically, ``Dev`` last."""

    def rank(tab: str) -> tuple:
        if tab in TAB_ORDER:
            return (0, TAB_ORDER.index(tab), "")
        return (2 if tab == "Dev" else 1, 0, tab)

    return sorted(set(tabs), key=rank)


def group_records(records: Iterable[Mapping]) -> dict[str, dict[str, list[Mapping]]]:
    """``{tab: {group: [record, ...]}}`` of already-listed, already-ordered records.

    Tabs come in :func:`ordered_tabs` order. Groups follow :data:`GROUP_ORDER`
    where the tab has one; the group named after its tab comes first, and any
    other group follows in the order of its first record.
    ``Setup:`` and ``Help:`` plugins are placed in the ``File`` and ``Main`` tabs
    under a group of that name.
    """
    layout: dict[str, dict[str, list[Mapping]]] = {}
    for record in records:
        tab, group, _label = split_address(
            record.get("plugin_name") or record.get("module_name") or ""
        )
        if tab in SPECIAL_TABS:
            tab, group = SPECIAL_TABS[tab], tab
        layout.setdefault(tab, {}).setdefault(group, []).append(record)
    ordered = {}
    for tab in ordered_tabs(layout):
        groups = layout[tab]
        authored = [tab, *GROUP_ORDER.get(tab, ())]
        names = [g for g in authored if g in groups] + [g for g in groups if g not in authored]
        ordered[tab] = {g: groups[g] for g in names}
    return ordered


def plugin_layout(
    infos: Iterable[Mapping], settings: Mapping, experimental: bool = False
) -> dict[str, dict[str, list[Mapping]]]:
    """``{tab: {group: [record, ...]}}`` for every listed plugin record, in ribbon order.

    Records are ordered by ``(plugin_order, display_name)`` as the ribbon sorts
    them, then grouped by :func:`group_records`.
    """
    order = settings.get("plugin_order", {}) or {}
    listed = [i for i in infos if is_listed(i, settings, experimental)]
    listed.sort(
        key=lambda i: (order.get(i.get("plugin_name") or "", 0), i.get("plugin_name") or "")
    )
    return group_records(listed)
