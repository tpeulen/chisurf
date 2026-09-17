"""Read and write the ``plugins:`` settings block.

Two things the old manager got wrong and this fixes.

**Edits used to apply themselves.** ``self.disabled_plugins`` was the *same list
object* as ``cs_settings['plugins']['disabled_plugins']``, so ticking a checkbox
mutated live application state immediately, before Save was ever pressed --
while the menus that read those lists had been built at startup. The in-memory
state and the visible menus diverged with nothing to indicate it, and closing
the window without saving did not undo anything. Here the edits live in a
private copy and only :meth:`PluginSettings.apply` writes them back.

**Settings were keyed by display name.** Rename a plugin and its
``disabled_plugins`` / ``plugin_order`` / ``toolbar_plugins`` entries silently
stopped matching. New entries are written under the manifest id; existing
display-name entries are still honoured on read, so nothing breaks on upgrade.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from typing import Any

#: The sub-keys this manager owns. Everything else under ``plugins:`` is left
#: exactly as found -- the old Save rewrote the whole settings tree.
OWNED_KEYS = (
    "disabled_plugins",
    "hide_disabled_plugins",
    "plugin_order",
    "toolbar_plugins",
    "icon_generation",
    "statefulness",
    "show_demo_plugins",
)


class PluginSettings:
    """A working copy of the ``plugins:`` settings block.

    Parameters
    ----------
    block : dict, optional
        The live settings block. Deep-copied, so nothing here touches the
        running application until :meth:`apply`.

    """

    def __init__(self, block: dict[str, Any] | None = None) -> None:
        source = block or {}
        self._data: dict[str, Any] = {
            key: copy.deepcopy(source.get(key)) for key in OWNED_KEYS if key in source
        }
        self._data.setdefault("disabled_plugins", [])
        self._data.setdefault("toolbar_plugins", [])
        self._data.setdefault("plugin_order", {})
        self._data.setdefault("statefulness", {})
        self._data.setdefault("hide_disabled_plugins", True)
        self._original = copy.deepcopy(self._data)

    # -- reads ----------------------------------------------------------

    @property
    def disabled(self) -> list[str]:
        """Ids (or legacy display names) of switched-off plugins."""
        return list(self._data.get("disabled_plugins") or [])

    @property
    def toolbar(self) -> list[str]:
        """Ids (or legacy display names) pinned to the toolbar."""
        return list(self._data.get("toolbar_plugins") or [])

    @property
    def order(self) -> dict[str, int]:
        """Menu ordering weights, by plugin key."""
        return dict(self._data.get("plugin_order") or {})

    @property
    def statefulness(self) -> dict[str, Any]:
        """The statefulness settings block."""
        return dict(self._data.get("statefulness") or {})

    @property
    def hide_disabled(self) -> bool:
        """Whether disabled plugins are hidden from the table."""
        return bool(self._data.get("hide_disabled_plugins", True))

    @property
    def dirty(self) -> bool:
        """Whether anything has changed since load or the last :meth:`apply`."""
        return self._data != self._original

    def icon_generation(self) -> dict[str, Any]:
        """The AI icon-generation settings (provider, endpoint, model)."""
        return dict(self._data.get("icon_generation") or {})

    # -- writes ---------------------------------------------------------

    def set_disabled(self, key: str, disabled: bool, *, aliases: Iterable[str] = ()) -> None:
        """Switch a plugin off or on.

        *aliases* are the plugin's other names (display name, leaf name). On
        enable, every alias is removed, so an entry written by an older version
        under the display name is cleared too rather than lingering and
        re-disabling the plugin on the next start.
        """
        entries = [str(x) for x in (self._data.get("disabled_plugins") or [])]
        names = {str(key), *(str(a) for a in aliases if a)}
        entries = [e for e in entries if e not in names]
        if disabled:
            entries.append(str(key))
        self._data["disabled_plugins"] = entries

    def set_toolbar(self, key: str, pinned: bool, *, aliases: Iterable[str] = ()) -> None:
        """Pin or unpin a plugin from the main toolbar."""
        entries = [str(x) for x in (self._data.get("toolbar_plugins") or [])]
        names = {str(key), *(str(a) for a in aliases if a)}
        entries = [e for e in entries if e not in names]
        if pinned:
            entries.append(str(key))
        self._data["toolbar_plugins"] = entries

    def set_statefulness_override(self, key: str, value: bool | None) -> None:
        """Force window-state persistence on, off, or back to the plugin default."""
        block = dict(self._data.get("statefulness") or {})
        per_plugin = dict(block.get("per_plugin") or {})
        if value is None:
            per_plugin.pop(key, None)
        else:
            per_plugin[key] = bool(value)
        block["per_plugin"] = per_plugin
        self._data["statefulness"] = block

    def set_statefulness_mode(self, mode: str) -> None:
        """Set the global window-state mode."""
        block = dict(self._data.get("statefulness") or {})
        block["mode"] = mode
        self._data["statefulness"] = block

    def set_hide_disabled(self, hide: bool) -> None:
        """Whether the table hides switched-off plugins."""
        self._data["hide_disabled_plugins"] = bool(hide)

    def set_icon_generation(self, **values: Any) -> None:
        """Update the AI icon-generation settings."""
        block = dict(self._data.get("icon_generation") or {})
        block.update({k: v for k, v in values.items() if v is not None})
        self._data["icon_generation"] = block

    def move(self, key: str, keys_in_order: list[str], delta: int) -> None:
        """Move *key* one position up or down and renumber every neighbour.

        The old implementation set ``order[key] = neighbour ± 1`` and left it,
        so the integers drifted apart without bound and two plugins could end up
        sharing a weight. Renumbering the whole visible sequence 0..n-1 keeps the
        values meaningful and the operation idempotent.
        """
        sequence = [k for k in keys_in_order if k]
        if key not in sequence:
            return
        index = sequence.index(key)
        target = index + delta
        if not 0 <= target < len(sequence):
            return
        sequence[index], sequence[target] = sequence[target], sequence[index]
        self._data["plugin_order"] = {k: i for i, k in enumerate(sequence)}

    # -- commit ---------------------------------------------------------

    def apply(self, block: dict[str, Any]) -> dict[str, Any]:
        """Write the working copy into the live settings *block*.

        Only :data:`OWNED_KEYS` are touched; any other key under ``plugins:``
        is left as found.
        """
        for key, value in self._data.items():
            block[key] = copy.deepcopy(value)
        self._original = copy.deepcopy(self._data)
        return block

    def revert(self) -> None:
        """Discard every unsaved edit."""
        self._data = copy.deepcopy(self._original)
