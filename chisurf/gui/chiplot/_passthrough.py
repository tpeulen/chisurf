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

**Coverage.** Passthrough is deliberately near-total for real pyqtgraph usage:

- **Reads/calls** — any method/attribute/signal chiplot lacks natively
  (``.setData``, ``.getViewBox``, ``.sigClicked``, …) forwards to the native
  object.
- **Attribute assignment on handles** — ``handle.foo = x`` forwards to the
  native item (``_Item.__setattr__``), so ``item.attr = v`` behaves as in
  pyqtgraph.
- **Container/dunder protocols on handles** — ``len(handle)``, ``handle[i]``,
  iteration forward to the native item; ``bool(handle)`` is always ``True``.
- **``colormap``** — a shadowed name that can't fall through the module
  ``__getattr__``, so ``chiplot.colormap`` is a hybrid: called it returns a
  chiplot :class:`~chisurf.gui.chiplot.style.Colormap`; attribute access
  (``colormap.get(...)``) proxies to the backend's raw ``colormap`` module.

Two deliberate, rarely-hit exceptions remain: attribute *assignment on the
`Plot`/`Grid`/`ImageView` widget wrappers* is not forwarded (overriding
``__setattr__`` on a live ``QWidget`` risks native-teardown crashes, and real
pyqtgraph code sets attributes on *items*, not on the plot widget); and the
class-identity of chiplot's own ``Color``/``ImageView`` differs from pyqtgraph's
(no chisurf call site does ``isinstance(x, pg.Color/pg.ImageView)``). The
intended migration path is still a real port to the chiplot API, with ``.native``
for the rare pyqtgraph-specific bit; passthrough keeps a partially-ported file
running at parity.

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

#: pyqtgraph names that chiplot *does* cover under a different spelling. These
#: are not gaps — they are the caller reaching for the old name — and falling
#: through for them is actively harmful: ``Plot.plot(pen=to_pen(...))`` lands in
#: pyqtgraph, which cannot read a chiplot ``Pen`` and dies with an unrelated
#: "not sure how to make a color from" deep inside the backend. Naming the
#: replacement turns that into a one-line fix.
_RENAMED: dict[str, str] = {
    "plot": "Plot.line(x, y, pen=…, width=…, style=…, name=…)",
    "mkPen": "chiplot.to_pen(...) — and pass it to a chiplot method, not a pyqtgraph one",
    "mkBrush": "chiplot.to_brush(...)",
    "mkColor": "chiplot.to_color(...)",
    "setLabel": "Plot.set_labels(bottom=…, left=…)",
    "setLabels": "Plot.set_labels(...)",
    "setTitle": "Plot.set_title(...)",
    "setLogMode": "Plot.set_log(x=…, y=…)",
    "setXRange": "Plot.set_xlim(lo, hi)",
    "setYRange": "Plot.set_ylim(lo, hi)",
    "addLegend": "Plot.legend(...)",
    "addItem": "Plot.add(handle)",
    "removeItem": "Plot.remove(handle)",
}


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
    if key in _WARNED:
        return
    _WARNED.add(key)
    replacement = _RENAMED.get(name)
    if replacement:
        message = (
            f"chiplot spells '{name}' differently — use {replacement}. Falling "
            f"through to the pyqtgraph backend, which does not understand "
            f"chiplot's own Pen/Brush/Color objects and will fail on them."
        )
    else:
        message = (
            f"chiplot has no native '{name}' ({scope} scope); falling through to "
            f"the pyqtgraph backend. This is a migration gap — prefer a chiplot "
            f"API, or add one. Set it up via chisurf.gui.chiplot."
        )
    warnings.warn(message, ChiplotPassthroughWarning, stacklevel=stacklevel)


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
