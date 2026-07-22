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
