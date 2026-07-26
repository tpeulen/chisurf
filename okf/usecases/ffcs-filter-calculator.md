---
type: Reference
title: Use case — filtered-FCS (fFCS) lifetime filter calculator
description: Compute species-selective fFCS lifetime filters from micro-time decay patterns — open the FCS window's Filter Calc tool, auto-fit the mixed decay into lifetime components, unmix it, and export the filters for a filtered correlation.
tags: [usecase, fcs, ffcs, filtered-fcs, lifetime, filters, unmix, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: filtered-FCS lifetime filters

**Goal:** the "filtered-FCS" entry of the FCS coverage list. Two (or more)
species in the same sample diffuse together and cannot be separated by colour,
but they have **different fluorescence lifetimes**. The user turns those
micro-time decay patterns into a set of statistical **weights (filters)**
`f_i(t_TAC)`, one per species, that are then applied photon-by-photon in the
correlator so the resulting correlation curve belongs to *one* species instead
of the mixture. Concretely the user must: get a mixed decay and one pattern per
species, decide the fit/filter window, compute the filters, check that the
filters actually reconstruct the mixed decay (residuals), read the species
fractions, and export the filters for
[the correlator](/usecases/fcs-correlate-tttr.md).

**Tool:** `chisurf.plugins.fcs.fcs_filter_calculator`
(`FcsFilterCalculatorWidget`), reached as the **🧪 Filter Calc** panel of the
unified **FCS** window (`FcsTool`, `Spectroscopy:FCS`) — the plugin is
`menu_hidden`, so the FCS window (or the `fcs-filter-calculator` CLI) is the only
way in. It is flagged **experimental** in its manifest, and the navigation list
shows the ⚠ marker.

**Data:** *none required* — the tool boots with a **built-in example**: a
convolved 70 / 30 mixture of τ = 1.2 ns and τ = 4 ns (100 000 counts, 256 TAC
bins at 50 ps, plus scatter and afterpulse), labelled *"Convolved example (70/30
+ scatter + afterpulse)"*, and two matching component patterns *Fast example* /
*Slow example*. The detector set comes from the saved detector setup (here the
shipped **BS** setup: `green`, `red`, `yellow`). For the headless path, three
plain histogram text files (mixed + one per species) are enough.

## Steps

1. Open **Spectroscopy:FCS**. The left rail lists the *Correlator* steps 1–5 and
   then a **Tools** group; select **🧪 Filter Calc**.
2. Look at the **Decay sources** dock: *Inputs* (**Pol** = polarization-resolved,
   **IRF** = use a scatter/IRF nuisance pattern, **AP** = fit an afterpulse /
   constant term), the **Detectors** table (per-detector IRF width / skew / shift
   and a `…` measured-IRF picker), the **Mixed decay** row, the **Fit range**
   spin boxes, and the **Components** list.
3. Optionally replace the example: **📂 Mixed…** loads a measured mixed decay, or
   **📡 From correlator** reuses the TTTR files already loaded in the correlator's
   *Files & Steps* step. Components are added through the **Components** list's
   right-click menu (double-click edits one).
4. Pick the detectors to work on in the **Detectors** table. One detector →
   one filter set; several → one independent filter set per detector, or (with
   **Global (stacked) multi-detector filters**) a single joint set over the
   concatenated detectors.
5. Set the **Fit range** — the TAC window the filters are computed over — either
   in the two spin boxes or by dragging the blue region on the *Reconstruction /
   decay* plot. Start it past the prompt for a tail fit.
6. Open the **Auto-fit** dock tab. Set *Type* = `Lifetime species`,
   *Components / states* = `2`, the lifetime bounds, and press
   **🎯 Fit + generate filters**. This fits the mixed decay through a real
   `LifetimeModel` (IRF fitted jointly when no measured IRF is loaded) and
   replaces the component list with the fitted species.
7. Read the fitted parameters in the Auto-fit dock's table (`sc`, `bg`, the
   amplitudes `xL,i` and lifetimes `τL,i` with errors) — these are real
   `FittingParameter`s and can be linked to other fits from the table's context
   menu.
8. Inspect the **Lifetime filters** plot (one curve per species plus the rejected
   nuisance patterns), the **Reconstruction / decay** plot (mixed decay vs. the
   filter reconstruction) and the **Weighted residuals** plot.
9. Press **🧩 Unmix** to fit non-negative species intensities; the status line
   reports the species fractions and the nuisance (afterpulse / scatter) counts.
10. **💾 Project ▾ → Export results…** writes the filters, reconstruction,
    residuals and metadata; *Save project…* stores the whole setup.
11. Headless equivalent:
    `fcs-filter-calculator compute -t mixed.txt -s fast.txt -s slow.txt -o filters.json -v`,
    then `fcs-filter-calculator info filters.json`.

## Expected

- Step 1 opens the panel in well under a second with the example already
  computed and plotted, and **no dialog**.
- Step 6 with *Components = 2* recovers ≈ 1.2 ns and ≈ 4 ns at ≈ 70 / 30 with
  χ²ᵣ ≈ 1.
- Step 8 shows two filter curves that cross zero (positive where their species
  dominates), a reconstruction lying on top of the mixed decay, and flat
  weighted residuals.
- Step 9 reports ≈ 70 % / 30 %.
- Step 11 writes a JSON with a `(n_species, n_bins)` filter matrix.

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through the real
widgets — `FcsTool` navigation, then `FcsFilterCalculatorWidget` standalone:
detector checkboxes, both auto-fit entry points, `🧩 Unmix`, the fit-range spin
boxes, the dock tabs — with screenshots at every step, rendered both unstyled and
under the shipped `dark_blue_flat` theme.

**The tool is currently unusable in the GUI.** Selecting *Filter Calc* in the FCS
window pops **five modal error boxes** in a row, each titled *Multi-Detector
Computation Error* and quoting a raw PyQt signature:
`addItem(self, item: Optional[QGraphicsItem]): argument 2 has unexpected type
'_Region'` (alternating with the matching `removeItem`). The first offscreen run
did not just fail — it **hung for six minutes** inside the modal's nested event
loop, at 0 % CPU, before I killed it; the same hang stops the plugin's own test
suite (`pytest chisurf/plugins/fcs/fcs_filter_calculator/test` never terminated,
11 min, 0 % CPU). The cause is one line: `_clear_recon_plot` re-adds the
draggable fit region to the plot with the pyqtgraph passthrough `addItem`, but
since today's chiplot migration (`ff7aec4ba`) the region is a chiplot `_Region`
wrapper, not a `QGraphicsItem`. Every recompute — open, detector change, range
change, unmix — raises there. See **RF-181**.

**The consequences the user sees:** the **Reconstruction / decay** and **Weighted
residuals** plots are **permanently empty** (0…1 axes, no data), because
`_update_plots` dies at that call before it draws them — so the one thing that
tells the user whether the filters are trustworthy is missing. The status bar
carries the raw Python `TypeError` text instead of a message. In single-detector
mode the same failure is titled *Computation Error*, and pressing **🧩 Unmix**
ends in *Unmixing Error* — although the unmix itself had already computed the
right answer (`Fast example: 70.9 %, Slow example: 29.1 %` against a 70 / 30
ground truth, plus `Afterpulse 7083` / `Scatter 8762` counts).

**The two Auto-fit buttons give different answers, and the toolbar one is
wrong.** The toolbar **🎯 Auto-fit** is connected straight to the handler, so
`QAction.triggered`'s `checked=False` arrives as `n_components`; `int(False) = 0`
is passed to the fitter, which silently returns a **single** component. With
*Components / states* showing **2**, the toolbar button reported
`1 components (χ²ᵣ=2.9) — 100 %·1.53 ns` and replaced the component list with
that one species; the dock's **🎯 Fit + generate filters** button, on the same
data in the same session, reported `2 components (χ²ᵣ=1.03) — 67 %·1.20 ns,
33 %·3.74 ns`, which matches the 1.2 / 4 ns ground truth. Nothing warns the user
that the number they typed was ignored. See **RF-182**.

**Opening the panel computes the filters six times.** Instrumenting
`_compute_filters` shows **6** full computations during construction, nested two
deep — a recompute launched from inside the previous one's `_update_plots`,
because `_init_fit_region` → `_set_fit_range` writes the spin boxes and each
`setValue` fires `_on_range_spin_changed` → `_on_fit_range_committed` →
`_on_data_changed`. One programmatic range set costs **2** further full
recomputes (one per spin box). On the 256-bin example this is invisible; on real
4096-bin multi-detector data it is the difference between an instant panel and a
frozen one, with no progress indication. See **RF-183**.

**What does work:** the numerics. The unmix fractions are right; the dock
auto-fit recovers the ground-truth lifetimes and exposes them as real
`FittingParameter`s with errors in a table that offers the standard *Link…*
targets; the **Lifetime filters** plot draws correctly (species filter plus the
two rejected nuisance patterns) once a single detector is selected. The
**headless CLI is completely clean**: `compute` on three histogram files printed
its progress, wrote a `(2, 256)` filter matrix with full metadata, and `info`
read it back — no Qt, no dialogs. The FCS window shell itself is good: lazy panel
loading, the ⚠ experimental marker on *Filter Calc*, *2D-FLCS* and *Lifetime-FCS
Sim*, and a readable selected row under the shipped theme.

## UX / UI suggestions

- **A tool must not open with an error dialog, and never with five.** Whatever
  the failure, the initial example computation should degrade to an inline
  message in the status strip; a modal `QMessageBox` fired from a widget
  *constructor* also makes the panel unopenable in any headless or test context.
- **Never show a PyQt signature to a user.** *"addItem(self, item:
  Optional[QGraphicsItem]): argument 2 has unexpected type '_Region'"* appears
  verbatim in the dialog, in the status bar and in the sidebar label. The dialog
  should say what failed in the user's terms ("the reconstruction plot could not
  be updated") with the traceback in the log.
- **One Auto-fit, not two.** The toolbar **🎯 Auto-fit** and the dock's **🎯 Fit +
  generate filters** are the same operation with different behaviour; drop the
  toolbar copy, or make it raise the Auto-fit dock so the user sees the settings
  the fit will use.
- **The empty plots need an empty state.** *Weighted residuals* and
  *Reconstruction / decay* show a bare 0…1 axis box with no hint whether they are
  empty because nothing was computed, because computation failed, or because the
  tab is simply behind another one. The *Reconstruction / decay* tab also starts
  **behind** *Instrument*, so the first thing a user sees on opening the tool is
  an instrument-parameter table, not their data.
- **Instrument table columns are unusable.** *Name* is truncated to
  `α (spectral …`, `β (direct accepto…`, `δ (acceptor direc…` while *Value* takes
  three-quarters of the width for one-character numbers. Size the Name column to
  its contents (and put the long text in the tooltip).
- **Label the units and expand the cryptic abbreviations.** The detector table's
  *Width / Skew / Shift* columns carry no units (ns), the *Shift* value is
  clipped mid-number (`-0.27…`), and the Inputs toggles are `Pol`, `IRF`, `AP`
  with no expansion visible in the panel. The auto-fit parameter table shows
  `sc`, `bg`, `xL,1` — fine for a fitting expert, opaque for a first-time user.
- **The filter plot legend sits on top of the data** and is drawn in a grey that
  is nearly unreadable on the black canvas; the *Reconstruction* plot's log y
  axis collapses its tick labels into a vertical blob (`9876…`) when the plot is
  empty.
- **The CLI has no fit-range option** while the GUI computes filters over a
  restricted window, so the same input gives different filters through the two
  paths. Add `--range start stop` (and `--nuisance/--no-nuisance`) so the
  headless path can reproduce a GUI result.
- **Say what the filters mean.** Neither the panel nor a `?` help section
  explains that a filter is a per-TAC-bin weight, that negative values are
  expected, or that the filters must be handed to the correlator to have any
  effect — the next step in the workflow is nowhere on screen. A "Send to
  correlator" button beside *Export results…* would close the loop with
  [the correlator use case](/usecases/fcs-correlate-tttr.md).

## Bugs filed

- **RF-181** — chiplot `_Region` passed to the pyqtgraph passthrough `addItem`
  breaks every recompute: 5 modal error dialogs on open, permanently empty
  reconstruction/residual plots, and a hang (GUI *and* the plugin's own pytest
  suite) inside the modal.
- **RF-182** — the toolbar **🎯 Auto-fit** passes `QAction.triggered`'s `checked`
  bool as `n_components`, so it always fits a single component and silently
  ignores the *Components / states* setting; `fit_lifetime_model` accepts
  `n_components=0` instead of rejecting it.
- **RF-183** — `_on_range_spin_changed` recomputes even when `_set_fit_range` is
  suppressed by `_syncing_range`, so opening the panel runs the whole filter
  computation 6× (nested 2 deep) and one programmatic range set costs 2 more.
