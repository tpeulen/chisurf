---
type: Architecture
title: GUI Layout
description: Compact-layout conventions for ChiSurf panels, and the main window's dock arrangement, persistence and reset.
resource: chisurf/gui/main.py
tags: [gui, layout, docks, qsettings]
timestamp: '2026-08-05T00:00:00Z'
---

# GUI Layout Conventions

**General rule: save space — build compact layouts.** ChiSurf tools are dense,
multi-panel scientific UIs that must fit real fit windows and docks. Prefer a
tight, information-dense layout over generous whitespace, everywhere.

Practical guidelines (apply throughout `chisurf/gui` and every plugin):

* **Zero/small margins and spacing.** Set `layout.setContentsMargins(0, 0, 0, 0)`
  and a small `setSpacing` on container layouts; don't accept Qt's default
  padding for nested panels.
* **Group related controls into foldables**, not always-open group boxes.
  Use `chisurf.gui.widgets.collapsible_box.CollapsibleBox` (or AutoForm
  `PanelSection`/`DockAreaSection`) so a user can collapse what they aren't
  using and reclaim vertical space. Fold advanced/optional sections collapsed
  by default.
* **Don't duplicate inputs.** When a widget is embedded in a larger workflow
  that already supplies its inputs upstream, hide the redundant controls (e.g.
  the burst-MLE panel hides its file-drop docks inside the Burst Analysis
  workflow — see `_burst_mle` / `_embedded`). Keep the standalone tool complete.
* **Compact widgets.** Prefer `QToolButton`/icon buttons over wide push buttons
  where a label isn't essential; keep spinbox/label columns narrow; let plots
  take the spare space (`_autoform_expanding`).
* **Responsive, not sprawling.** Use splitters and expanding stretch so the
  window scales; never hard-code large fixed sizes.

Rationale: these tools are used side-by-side in the fit-window dock area; every
row of wasted space pushes plots and results off-screen. Compactness is a
correctness concern for usability, not just aesthetics.

# The main window's docks

The arrangement has **two sources**, and they are applied in this order inside
`Main.arrange_widgets` (`chisurf/gui/main.py`):

1. `Main.apply_default_dock_layout()` — the authored default. Read data,
   Datasets, Analysis, Plot settings and Logging are tabified into **one stack
   on the left**; the console holds the bottom edge; everything else is the
   workspace. It un-floats and shows each dock first, so a dock the user closed
   or tore off comes back rather than staying out of the stack.
2. `Main._restore_window_state()` — whatever the last session saved through
   `QSettings("ChiSurf", "MainWindow")` on close, applied **over** the default.

Because the saved state wins, **a change to the authored default is invisible to
anyone who has ever run ChiSurf** — the layout on disk simply re-applies itself
every start, including the one it was derived from. That is why the saved state
carries `layout_version`: `_restore_window_state` ignores a state whose version
is not `Main._LAYOUT_VERSION` and returns `False`, leaving the new default in
place for exactly one start; the user's own rearrangement is then saved under
the current version and survives from there on. **Bump `_LAYOUT_VERSION`
whenever `apply_default_dock_layout` changes**, or the change ships to new
installs only.

*View → Reset Layout* (`Main.onResetWindowLayout`, also on the ribbon's Main
tab) removes the saved state as well as re-applying the default, so the reset is
not undone by the next start.

Two things are easy to get wrong here, both invisible in code review and
obvious in a screenshot:

* **A tab stack has to be sized for its tab bar, not just its widgets.** The
  left column is sized by `_apply_read_data_dock_width`, which takes the larger
  of the read-data width and the tab bar's own size hint. Sized to the widgets
  alone, five labels elide to `Read…`/`Dat…`/`An…` and the stack becomes
  unreadable — and worse in a language with longer words, which is why the width
  is re-applied after a live language switch.
* **Re-tabbing a dock builds a new `QTabBar`**, so `apply_dock_tab_colors` must
  run *after* the layout settles (after restore, and again after a reset) or the
  colours go with the discarded bar. Those colours are keyed by dock **title**
  in `gui.dock_tab_colors`: rename a dock and its tab silently loses its colour,
  as `History / Log` did after the dock became `Logging`.
  `test/gui/test_dock_layout.py` pins all of this.
