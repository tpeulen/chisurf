"""Resolve package precedence without importing any plugin or parent package."""

from __future__ import annotations

import pathlib
from importlib.machinery import PathFinder


class PackageResolver:
    """A per-scan cache of Python's regular/namespace package search locations.

    Looking at leaf names alone misses a regular parent that shadows an entire
    later subtree. PathFinder supplies the actual filesystem precedence, including
    merging namespace portions and preferring a regular package over those portions.
    No loader is executed. Basenames avoid requiring parent modules in sys.modules.
    """

    def __init__(self, search_paths):
        paths = []
        for path in search_paths:
            try:
                paths.append(str(pathlib.Path(path).resolve()))
            except (TypeError, ValueError, OSError, RuntimeError):
                continue
        self._locations: dict[tuple[str, ...], tuple[str, ...]] = {(): tuple(paths)}
        self._directories: dict[tuple[str, ...], pathlib.Path | None] = {}

    def preferred_directory(self, parts: tuple[str, ...]) -> pathlib.Path | None:
        for size in range(1, len(parts) + 1):
            prefix = parts[:size]
            if prefix in self._locations:
                continue
            parent_paths = self._locations[prefix[:-1]]
            spec = PathFinder.find_spec(prefix[-1], parent_paths) if parent_paths else None
            self._locations[prefix] = (
                tuple(spec.submodule_search_locations or ()) if spec is not None else ()
            )
            self._directories[prefix] = (
                pathlib.Path(spec.origin).parent.resolve()
                if spec is not None and spec.origin is not None else None
            )
        return self._directories.get(parts)

    def parent_locations(self, parts: tuple[str, ...]) -> tuple[str, ...]:
        parent = parts[:-1]
        self.preferred_directory(parent)
        return self._locations[parent]
