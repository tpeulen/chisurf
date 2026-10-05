"""Toolkit-neutral live edit semantics for AutoForm's ``rate_matrix`` section.

A renderer may round or clamp its display, but it must commit only the cell
actually edited. Untouched values are read from the current scientific model,
not copied from a stale display. The binding is a runtime handle, not state to
serialize: its configuration is the existing plain target/size attribute paths.
"""

from __future__ import annotations

import math
from typing import Any


class RateMatrixBinding:
    """Bind one row-major source→target matrix to a scientific model."""

    def __init__(self, model: Any, target: str, *, size_attr: str = "") -> None:
        """Use the same dotted paths as a declarative custom section."""
        self.model = model
        self.target = target
        self.size_attr = size_attr

    def _resolve(self, path: str) -> Any:
        """Read a declared attribute or zero-argument getter path."""
        value = self.model
        for part in path.split("."):
            value = getattr(value, part)
            if callable(value):
                value = value()
        return value

    def values(self) -> list[float]:
        """Read a detached live vector without changing the scientific model."""
        return [float(value) for value in self._resolve(self.target)]

    def size(self) -> int:
        """Resolve the declared count, or infer an exact full square vector."""
        if self.size_attr:
            n = int(self._resolve(self.size_attr))
        else:
            n = math.isqrt(len(self.values()))
        if n < 1:
            raise ValueError("rate matrix must contain at least one state")
        return n

    def parameter(self, source: int, target: int) -> Any:
        """Return the live parameter, if the target belongs to a rate group."""
        parent_path, _, _ = self.target.rpartition(".")
        group = self._resolve(parent_path) if parent_path else self.model
        items = getattr(group, "rate_items", None)
        if callable(items):
            return dict(items()).get((source + 1, target + 1))
        by_name = getattr(group, "rates_by_name", None)
        if callable(by_name):
            prefix = getattr(group, "rate_prefix", "k")
            return by_name().get(f"{prefix}{source + 1}_{target + 1}")
        return None

    def commit_cell(self, source: int, target: int, value: float) -> None:
        """Apply one edit to the *live* matrix; leave all other cells intact."""
        n = self.size()
        if not 0 <= source < n or not 0 <= target < n:
            raise IndexError(f"rate cell ({source}, {target}) is outside {n} states")
        edited = float(value)
        if not math.isfinite(edited):
            raise ValueError("a rate edit must be finite")
        values = self.values()
        if len(values) != n * n:
            raise ValueError(f"rate matrix has {len(values)} cells, expected {n * n}")
        values[source * n + target] = edited
        parent_path, _, attr = self.target.rpartition(".")
        parent = self._resolve(parent_path) if parent_path else self.model
        setattr(parent, attr, values)
        self.notify_changed()

    def notify_changed(self) -> None:
        """Recompute/notify the addressed fit, or the stand-alone model action."""
        callback = (
            getattr(self.model, "_on_changed", None)
            or getattr(self.model, "on_changed", None)
            or getattr(getattr(self.model, "fit", None), "update", None)
            or getattr(self.model, "update", None)
        )
        if callable(callback):
            callback()
