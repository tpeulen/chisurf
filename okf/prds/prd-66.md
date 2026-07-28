---
type: PRD
prd: "66"
title: "PRD-66: chitable — single table seam and DataFrameEditor replacement"
description: One model/view table family shared by ChiSurf and ndX — value filtering, column hiding, hide-empty columns, colour-by-value, column picker, copy/export — replacing a third-party DataFrameEditor and dozens of hand-rolled QTableWidgets, and dropping the last third-party GUI dependency.
status: in-progress
phase: "unassigned"
resource: chisurf/gui/widgets/chitable/
tags: [prd, gui, table, dataframe, architecture]
timestamp: '2026-07-25T00:00:00Z'
---

# Summary

PRD-66 introduces **chitable** (`chisurf.gui.widgets.chitable`), one model/view
table family through which every tabular view is built. It is the table
counterpart of [PRD-64](/prds/prd-64.md)'s chiplot: a single facade, swappable
internals, no third-party GUI toolkit.

# Problem

Tables in ChiSurf and ndX were historically a third-party `DataFrameEditor`.
That widget supplied value-scaled cell backgrounds, per-column formatting,
chunked loading and a real context menu; nothing in-tree did. As the third-party
plotting toolkit was retired, those features were left stranded, and each call
site grew its own `QTableWidget` — roughly forty across the plugins, four in
ndX — sharing nothing.

The concrete symptoms:

* **The dependency survived for two call sites.** The Data-table plot and the
  legacy burst selector were the only importers, and the first one *fought* the
  widget: `NoBackgroundProxy` to strip its colouring, `ReadOnlyColumnProxy` to
  lock a column, a duplicated checkbox delegate, and ~45 lines walking
  `dlg.findChildren(QTableView)` to install all three after construction.
* **No shared machinery.** No `QSortFilterProxyModel` existed anywhere in either
  repository, no colour-by-value delegate, no table→CSV export, no reusable
  column picker.
* **The richest table was also the buggiest.** ndX's editor was
  item-based (`df.iloc[i, j]` per cell, rebuilt on every keystroke), tested
  numeric-ness with `np.issubdtype` — which *raises* on the nullable dtypes the
  pyarrow burst reader produces — and wrote edits through the view row while
  filtered, silently corrupting an unrelated row.

# Design

## Sources, not subclasses

Callers supply a `TableSource` rather than subclassing the model, so filtering,
sorting, formatting, colouring, staged edits and paging are implemented once.
`DataFrameSource`, `ArraySource` and `RecordSource` cover every tabular shape in
the tree; every adapter exposes a vectorised `column_array()`.

## Filtering by index array

`ChiTableModel` carries filter and sort in a visible-row index array rather than
a proxy. `filterAcceptsRow` is a Python call per row and untenable at burst
scale; an index array is one numpy pass and keeps source rows recoverable
through `source_row()`.

## Colouring through the model

Value shading is served from `BackgroundRole`, not a delegate, so it composes
with the boolean/float/rich-text delegates. HSV ramp by default (no plotting
backend needed), off by default, self-disabling above a cell-count cutoff, and
alpha-composited so it works in dark themes.

## Foreign models

`ForeignTableProxy` layers the features onto a model that must keep its own
semantics, so tables like the Global View's parameter table are not rewritten.

## ndX

ndX imports chitable optionally with a local fallback, keeping it
standalone-installable. Its changes land in its own repository.

Full architecture in the [chitable subsystem concept](/subsystems/gui-tables.md).

# Definition of Done

- [x] `chisurf/gui/widgets/chitable/` with sources, model, filters, colour
      scheme, delegates, view, proxy, container widget and dialog.
- [x] Delegates consolidated out of `parameter_table.py`; the duplicate
      checkbox delegate in `table_plot.py` deleted.
- [x] `apply_compact_table_style()` gains a `sortable` flag.
- [x] Data-table plot on chitable; "Show model" uses `edit_dataframe()`.
- [x] Global View parameter table on chitable via the foreign-model path, with
      a regression test that Link-by-row-number survives sort + filter.
- [x] Legacy burst selector migrated.
- [x] `guidata` removed from `pixi.toml`, the rattler recipe and
      `build_tools/setup_runtime.sh`, with a guardrail test.
- [x] ndX's `DataFrameEditor` backed by chitable with a fixed fallback;
      the extension-dtype and filtered-edit-row defects regression-tested.
- [ ] Remaining hand-rolled plugin tables migrated (mmfdb_admin ~26,
      lightpath_simulator, burst_browser's `_BurstTableModel`).
- [ ] A scalable AutoForm `data_table` custom section for plugin view schemes,
      registered via `@register_section` alongside the existing `table` section.

# Out of scope

The AutoForm `table` section and its item-based `TableWidget` stay as they are:
they are the right tool for small fixed-order record tables, and five view
schemes depend on them. ndX's Gaussian-fit and report-wizard tables mix
`setCellWidget` combo boxes with `UserRole` metadata; porting them is a
behavioural rewrite, not a drop-in, and is deferred.
