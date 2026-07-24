"""Passthrough fall-through for the chiplot migration.

chiplot's native API does not yet cover every pyqtgraph feature in use. Rather
than block migration on 100% coverage, anything chiplot does not natively offer
falls through to the active backend's underlying library (pyqtgraph) — but
**flagged**, so every gap is visible and trackable.

Two levels:

- **Module level** — ``chisurf.gui.chiplot.__getattr__`` resolves unknown names
  (``mkPen``, ``LinearRegionItem``, ``PlotWidget``, …) from the backend's raw
  module.
- **Instance level** — a native :class:`~chisurf.gui.chiplot.Plot`,
  :class:`~chisurf.gui.chiplot.ImageView`, :class:`~chisurf.gui.chiplot.Grid`,
  and every drawn **handle** proxy unknown attribute *reads* to their
  underlying backend object.

**Scope and limits (this is NOT total parity — do not rely on a blind
``import pyqtgraph as pg`` → ``import chisurf.gui.chiplot as pg`` swap).**
Passthrough covers the common, high-value case: *reading or calling* any
method/attribute/signal chiplot does not define natively (``.setData``,
``.getViewBox``, ``.sigClicked``, …). It does **not** cover:

1. **Shadowed names.** Names chiplot defines itself do not fall through:
   ``colormap`` (chiplot's is a function, so ``cp.colormap.get(...)`` fails —
   use ``cp.get_backend().raw_module().colormap`` instead), ``Color``, and
   ``ImageView`` (chiplot's own class — ``isinstance(x, cp.ImageView)`` is not
   ``pg.ImageView``).
2. **Attribute assignment.** ``obj.foo = x`` sets on the chiplot wrapper, not
   the native object (``__setattr__`` is not forwarded).
3. **Dunder / container protocols.** ``len(handle)``, ``handle[i]``, iteration —
   Python resolves these on the type, bypassing ``__getattr__``.

The intended migration path is therefore a *real port to the chiplot API* (with
``.native`` for the rare pyqtgraph-specific bit), not a blind alias swap;
passthrough is the safety net that keeps a partially-ported file running.

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
