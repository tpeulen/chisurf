---
type: Subsystem
title: GUI & AutoForm
description: The Qt application and the data-driven AutoForm UI framework that renders view.json schemes.
resource: chisurf/gui/
tags: [gui, qt, autoform, viewspec]
timestamp: '2026-07-05T00:00:00Z'
---

# GUI

`chisurf/gui/` is the Qt application: the main window, widgets, plots
(pyqtgraph), resources, and GUI startup helpers. It is launched via
`python -m chisurf` (`pixi run chisurf`).

# AutoForm

`chisurf/gui/autoform/` renders UI declaratively from JSON view schemes
(`*.view.json`) instead of hand-built Qt widgets. This is part of the PRD-40
model/UI split, backed by data specs in `chisurf/core/dataspec/`.

Notable section types the framework supports include `image` (3D stacks with
click-pick / markers / on-image text labels / ROI), `image_browser` (a
navigable entry list — files, molecules, frames — beside that `image` canvas,
with per-entry star ratings, an editable note, a filter and drag-drop; shared by
the TTTR image browser and the molecule-wise MLE tool), `waterfall` (RGB
time-vs-µtime images), `path_list` (drag-drop file/folder lists),
`rate_matrix` (a reusable editable N×N transition-rate grid that tracks a
`size_attr` such as the species/state count, with the diagonal fixed at 0 — for
kinetic interconversion matrices anywhere in ChiSurf), `parameter_group_table` (a
space-saving **table** rendering of a `FittingParameterGroup` — one row per
`FittingParameter`, `QTableView` with columns `name`/`value`/`fixed`/`bounds_lo`/
`bounds_hi`/`bounds_on`/`error` and click-to-toggle checkbox delegates, cells
bound to the live parameter objects; the compact alternative to the verbose
`parameter_group` section — same `target`/`exclude_source`/`collapsible`, just
swap the `type`; HTML labels keep sub/superscripts, right-click copy/paste; a
row offers the **same per-parameter actions as the verbose section's row
widget** — right-click links/unlinks the parameter across fits, clicking its
name opens the parameter detail popup — via a `FittingParameterProxyController`
standing in for the absent row widget, which also becomes each parameter's
`controller` so `FittingParameter.update()` repaints the row; a proxy's
`finalize()` is a **display refresh only**, never a fit-update dispatch, since
the model calls it during a recompute),
`scalar_table` (the same compact name/value table for **plain** `float`/`int`/
`bool` model attributes rather than `FittingParameter`s — `{rows:[{attr,label,
kind}], call}` — for parameter-dense editors like the FRET-species crosstalk /
anisotropy groups), `dynamic_group` (a variable-length list of parameter
components with add/remove controls driven by the model's own
`append`/`pop` methods; `row_width` parameters form one component. Its default
`style:"grid"` lays each parameter out as a standalone spin-box row, while
`style:"table"` renders the components as one **paired** `QTableView` — each
component is a single row: a `#` index column then the compact
`value`/`fixed`/`bounds_lo`/`bounds_hi`/`bounds_on`/`error` columns repeated once
per parameter slot, so an amplitude block sits beside its lifetime block. A
rich-text header renders the slot's HTML label (`x<sub>l</sub>` → xₗ,
`&rho;` → ρ) with the per-component index stripped; the paired table reuses the
`parameter_group_table` cell logic, `FittingParameterProxyController` link/detail
actions, and copy/paste. The TCSPC Lifetime model's Lifetimes (xₗ/τₗ) and
Anisotropy rotation (bᵢ/ρᵢ) groups use `style:"table"`. Both table widgets
(`parameter_group_table` and the paired `dynamic_group` table) can hide the
**Lo / Hi / Bounds** columns to keep the tables narrow — a `panel` with
`bounds_toggle:true` puts a small checkable "bounds" button in its fold header
that shows/hides those columns for *every* table in the panel at once (columns
start hidden; bounds stay editable in the parameter details popup). The
`CollapsibleBox` header gained `add_header_widget` to host such per-section
controls with no extra vertical space),
`help` (a `?` modal button), and
`wizard`/`info`/`embed`. **All tables** (log, `parameter_group_table`,
`scalar_table`, AutoForm record `table`) share the central
`chisurf.gui.widgets.general.table_font` — monospace by default (configurable via
`gui.table`) so tables look like the log/console and numeric columns align. Sections take a `description` field mapped to widget
tooltips, and manifest `rpc_methods` can be rendered as forms via
`AutoForm.from_rpc_method`. A `button_row` collapses into a single popup
`QToolButton` menu when given a `menu` label (emoji labels act as inline action
icons) — the space-efficient default for tool actions. Editable `table` sections
refresh the hosting form on a cell edit (the same walk-up to
`sync_fields`+`refresh_plots` that value/toggle/button sections use), so a
table-driven preview or derived field updates live without extra wiring.

**Help behind a `?` modal (general UI rule).** Keep forms uncluttered — short
labels, detail in tooltips, and *longer* explanations behind a small `?` button
that opens a modal help popup rather than inline paragraphs. The reusable `help`
custom section renders that button:
`{"type":"custom","key":"help","options":{"title":"…","text":"# markdown…"}}`
(or `"resource":"path.md"`); it opens a modal `QTextBrowser` (Markdown/HTML). Add
one to any dense view instead of packing instructions into the layout.

A reusable **synthetic-decay editor** (`chisurf/gui/widgets/synthetic_decay_editor.py`,
`SyntheticDecayEditorModel` + `synthetic_decay_editor.view.json`) packages an
amplitude/lifetime spectrum table, IRF (file or Gaussian FWHM), Poisson
shot-noise, a measured-pattern override, "Read from Fit", and a live decay
preview into one view; the FCS Filter Calculator's synthetic-component dialog and
the acquisition simulator's Decay modal both embed it so the two never diverge
(see [plugins/fcs.md](/plugins/fcs.md)).

When touching GUI code, prefer porting hand-built widgets to AutoForm + a
JSON view scheme.

## UI convention: space-efficient labels + tooltips (general rule)

Screen space is a first-class constraint everywhere in ChiSurf — panels dock
side by side and controls must stay narrow. Therefore, for **all** UI (AutoForm
`label`/`description`, and hand-built Qt widgets alike):

- **Labels are terse** — one or two short words, abbreviations welcome (`Ch A`,
  `µt A`, `Bins`, `Fine`, `Width`, `Skew`, `AP`, `IRF`). Never put a full phrase
  or a unit-laden sentence in a label.
- **The full meaning goes in the tooltip** — the complete description, units,
  and examples. In AutoForm this is the section `description` (mapped to the
  widget tooltip, [[viewspec-description-tooltip]]); in hand-built widgets call
  `setToolTip`. App-wide tooltip folding ([`chisurf/gui/tooltip.py`](/workflows/build-and-env.md))
  keeps long tooltips readable, so descriptions can be as complete as needed.
- **Prefer vertical stacking over wide side-by-side rows** when horizontal space
  is tight (AutoForm panel `n_col: 1`); prefer compact controls (short spin-box
  widths, emoji `QToolButton`s over text buttons). Default to the layout that
  keeps a panel usable at its *narrowest* docked width.

This is a standing rule: when adding or editing any control, choose the
space-efficient form by default and move detail into the tooltip.

# Node editor widget

`chisurf/gui/widgets/node_editor/` is a self-contained, dependency-light node
editor (PyQt + optional `networkx`) with model/view/editor layering. It has a
**versioned JSON graph schema** (`{version, nodes:[{id,type,title,inputs,outputs,
config,pos,collapsed}], edges:[{source,source_port,target,target_port}]}`),
validate-before-mutate loading (`NodeGraphValidationError`, no partial scene on
failure), non-GUI file/dict serialization, a **node-type registry** replacing
hardcoded type lists, and DAG utilities (`is_directed_acyclic`, cycle
highlighting, optional `enforce_acyclic` edge guard). Round-trip and cycle
behaviour are covered by tests under its `tests/` directory. It is the substrate
the visual burst-programming canvas builds on (PRD-29).

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
