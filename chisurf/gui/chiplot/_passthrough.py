"""Passthrough fall-through for the chiplot migration.

chiplot's native API does not yet cover every pyqtgraph feature in use. Rather
than block migration on 100% coverage, anything chiplot does not natively offer
falls through to the active backend's underlying library (pyqtgraph) — but
**flagged**, so every gap is visible and trackable.

Two levels:

- **Module level** — ``chisurf.gui.chiplot.__getattr__`` resolves unknown names
  (``mkPen``, ``LinearRegionItem``, `PlotWidget`, …) from the backend's raw
  module. A migration can then be as small as
  ``import pyqtgraph as pg`` → ``import chisurf.gui.chiplot as pg`` and still run.
- **Instance level** — a native :class:`~chisurf.gui.chiplot.Plot` proxies
  unknown attributes to its underlying backend plot object.

Every fall-through emits a :class:`ChiplotPassthroughWarning` **once per symbol**
and is recorded; :func:`passthrough_gaps` returns the set of everything that has
fallen through this session — the concrete worklist for growing the native API.
"""

from __future__ import annotations

import warnings


class ChiplotPassthroughWarning(UserWarning):
    """Emitted when chiplot falls through to the backend's raw library.

    Its presence means a call site is using a feature chiplot does not offer
    natively yet — a migration gap to close, not necessarily a bug.
    """


# Every (scope, name) that has fallen through, and the names already warned
# about (so each is flagged once, not on every access).
_GAPS: set[str] = set()
_WARNED: set[str] = set()


def record_and_warn(scope: str, name: str, *, stacklevel: int = 3) -> None:
    """Record a passthrough gap and warn once for it.

    Parameters
    ----------
    scope : str
        Where the fall-through happened (``"module"`` or e.g. ``"Plot"``).
    name : str
        The attribute that was not natively offered.
    stacklevel : int
        Passed to :func:`warnings.warn` so the warning points at the caller.
    """
    key = f"{scope}.{name}"
    _GAPS.add(key)
    if key not in _WARNED:
        _WARNED.add(key)
        warnings.warn(
            f"chiplot has no native '{name}' ({scope} scope); falling through to "
            f"the pyqtgraph backend. This is a migration gap — prefer a chiplot "
            f"API, or add one. Set it up via chisurf.gui.chiplot.",
            ChiplotPassthroughWarning,
            stacklevel=stacklevel,
        )


def passthrough_gaps() -> set[str]:
    """Return the set of ``scope.name`` symbols that fell through this session.

    Returns
    -------
    set of str
        The concrete list of pyqtgraph features still lacking a chiplot native
        equivalent — useful for the PRD-64 migration tracker and tests.
    """
    return set(_GAPS)


def reset_gaps() -> None:
    """Clear the recorded gaps and warning-dedupe state (mainly for tests)."""
    _GAPS.clear()
    _WARNED.clear()
