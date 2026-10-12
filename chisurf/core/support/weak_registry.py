"""An ordered registry that does not keep its members alive."""

from __future__ import annotations

import weakref
from collections.abc import Iterator
from typing import Any


class WeakOrderedRegistry:
    """Objects in registration order, held weakly.

    "The active editors" and "the open help windows" are registries a link handler walks to
    find a window that can take a file. Kept as plain lists they pin every window ever opened
    for the life of the process: the window is gone from the screen but not from memory, with
    its textures and caches, and a stale entry still answers "an editor is active" for every
    later caller. Here an entry disappears with its object; :meth:`remove` is still the
    prompt, explicit way out.
    """

    def __init__(self) -> None:
        self._refs: list[weakref.ReferenceType] = []

    def _live(self) -> list[Any]:
        live = []
        keep = []
        for ref in self._refs:
            obj = ref()
            if obj is not None:
                live.append(obj)
                keep.append(ref)
        self._refs = keep
        return live

    def append(self, obj: Any) -> None:
        """Register *obj* last (most recent); registering twice moves nothing."""
        if obj not in self:
            self._refs.append(weakref.ref(obj))

    def remove(self, obj: Any) -> None:
        """Drop *obj*; ``ValueError`` if it is not registered, like ``list.remove``."""
        for ref in self._refs:
            if ref() is obj:
                self._refs.remove(ref)
                return
        raise ValueError("object is not registered")

    def __contains__(self, obj: object) -> bool:
        return any(live is obj for live in self._live())

    def __iter__(self) -> Iterator[Any]:
        return iter(self._live())

    def __reversed__(self) -> Iterator[Any]:
        return reversed(self._live())

    def __len__(self) -> int:
        return len(self._live())

    def __bool__(self) -> bool:
        return bool(self._live())
