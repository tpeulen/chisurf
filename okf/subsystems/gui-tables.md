---
type: Subsystem
title: chitable — the shared table widget family
description: One model/view table implementation with filtering, sorting, column hiding, value colouring and export, shared by ChiSurf and ndX and replacing the retired third-party DataFrameEditor.
resource: chisurf/gui/widgets/chitable/
tags: [gui, qt, table, dataframe, chitable]
timestamp: '2026-07-25T00:00:00Z'
---

# Why it exists

ChiSurf's tables used to be a third-party `DataFrameEditor` plus several dozen
hand-rolled `QTableWidget`s. The third-party editor was the only one with
value-scaled cell backgrounds, per-column formatting and a real context menu, so
call sites that wanted those imported it and then fought it — one proxy to strip
its colouring, another to lock a column read-only, a delegate grafted on for
booleans, and post-hoc surgery walking the dialog's children to install all
three. Everything else grew its own item-based table, and none of them shared
sorting, filtering, column hiding, colouring or export.

`chitable` is the single implementation those call sites share. It follows the
same shape as the [chiplot](/subsystems/gui-autoform.md) plotting seam: one
facade, swappable internals, no third-party GUI toolkit. Retiring the last two
`DataFrameEditor` call sites let that dependency be dropped entirely, and with
the plotting toolkit already gone, ChiSurf now ships no third-party GUI
framework beyond Qt itself.

# Shape

```
chisurf/gui/widgets/chitable/
  columns.py    ColumnSpec — key, label, kind, format, editable, delegate
  source.py     TableSource protocol + DataFrame / DataStore / Array / Record adapters
  filters.py    ColumnFilter, FilterSpec, ColumnCache
  model.py      ChiTableModel
  colorize.py   ValueColorScheme
  delegates.py  boolean / float / rich-text delegates, rich-text header view
  view.py       ChiTableView — clipboard, export, context menus, frozen columns
  proxy.py      ForeignTableProxy for models that keep their own semantics
  widget.py     ChiTableWidget — toolbar + view + status line
  editor.py     ChiTableDialog, edit_dataframe(), show_dataframe()
  dialogs.py    column picker, per-column filter editor
```

## Sources, not subclasses

A caller supplies a **`TableSource`** rather than subclassing the model, so
filtering, sorting, formatting, colouring, staged edits and paging are written
once. Four adapters cover every tabular shape in the tree:

* `DataFrameSource` — a pandas frame (burst tables, model parameters);
* `DataStoreSource` — a [columnar store](columnar-store.md), the container the
  burst tables are migrating onto. It answers the protocol more directly than a
  frame does — `column_array()` is the column's own buffer in its own dtype,
  where the frame adapter converts to float64 — and it can do three things a
  frame cannot: keep a narrow dtype through an edit, blank a cell by setting a
  validity mask instead of writing a sentinel (so an integer column keeps both
  its dtype and the difference between "zero" and "not measured"), and offer a
  text column's dictionary as a drop-down. It also cannot reproduce the
  extension-dtype crash below: a store column *states* its type;
* `ArraySource` — named numpy column arrays, short columns NaN-padded (fit
  curves: x / data / model / residuals / mask plus support curves);
* `RecordSource` — row objects or dicts with an explicit column spec, its
  `getter`/`setter` being the injection point for an RPC mutator.

Every adapter exposes `column_array()`, a vectorised view. That is what keeps a
10⁶-row table responsive: filters compile to a boolean row mask in one numpy
pass per column rather than a Python predicate per row.

## Filtering by index array, not by proxy

`ChiTableModel` carries the filter and sort in a **visible-row index array**
rather than a `QSortFilterProxyModel`. Two reasons: `filterAcceptsRow` is a
Python call per row and untenable at burst scale, and an index array keeps
source rows recoverable through `source_row()` — which matters wherever a
table's own row numbers are part of the data.

## Colouring through the model

Value-scaled backgrounds are served from the model's `BackgroundRole`, not a
delegate, because a column can only carry one delegate and the boolean, float
and rich-text delegates already occupy that slot. The ramp is HSV by default so
no plotting backend is pulled in to paint a cell; a named colormap resolves
through the chiplot registry when one is available. Colouring is off by default
and disables itself above a cell-count cutoff — the per-column min/max reduce is
the cost, not the paint. Because the colour is alpha-composited over the
palette, it reads correctly in both light and dark themes.

## Foreign models

Some tables carry semantics that cannot be expressed as a source — the Global
View routes every edit through an RPC mutator and addresses parameters by row
number. `ForeignTableProxy` layers search, filtering, sorting and colouring on
top of such a model instead, so it gains the features without a rewrite. This is
explicitly the small-table path: its predicates run per row in Python. With no
scheme set it also strips whatever background the wrapped model paints.

## Vector parameters in the parameter table

`ParameterGroupTableWidget` (`chisurf/gui/autoform/sections/parameter_table.py`,
every fit model editor's `list` tables and nDXplorer's Qt tables) shows a
vector as **one expandable row**. Its model builds `_Row`s, not one row per
parameter: parameters named `base[label]` (nDXplorer publishes a vector
constant one `FittingParameter` per population, so each keeps its own fixed
flag, bounds and link) are filed under a parent `▸ base [n]` with the values
summed up, `base` itself as the *(global)* child; a parameter whose value is an
array (a `GraphPort` of length > 1) is a parent over `[0]`, `[1]` … rows whose
*Value* edits that element (`_set_array_element`). Before, the first kind read
as unrelated rows and the second as its first element only, and typing into it
collapsed the array to a scalar. A click on a parent's name opens or closes it
(`toggle`); the parent's *Fixed* holds or frees every element; row → parameter
goes through `param_at(row)` and the controllers are keyed by parameter, since
opening a vector moves the rows. `top_level()` / `top_level_position(row)` map
a row back to the parameter list, which the AutoForm `dynamic_group` list
style uses to find the selected component. An empty bool cell draws no box
(`BooleanToggleDelegate`). The emtk Global View does the same for its
Parameters table with the data table's tree (`tree_key: parent`,
`_nest_vector_elements`). Measure: `test/gui/test_parameter_table_vectors.py`
(mouse click opens, double-click + typed value + Enter edits),
`chisurf/plugins/core/globalview/tests/test_model.py::test_a_vector_published_by_population_is_one_expandable_row`.

# Consumers

* the [Data table plot](/subsystems/gui-autoform.md) (`chisurf/gui/plots/table_plot.py`)
  — the fit's curves, with `x`/data/mask editable and edits routed through the
  fitting client; its "Show model" parameter editor is a `ChiTableDialog`;
* the Global View parameter table
  (`chisurf/gui/autoform/sections/global_parameter_table.py`) — via the foreign
  model path;
* the burst selector's results editor;
* ndX's `DataFrameEditor` and its item tables, through the optional-import
  arrangement below.

The AutoForm `table` section and its `TableWidget`
(`chisurf/gui/autoform/sections/builtin.py`) are unchanged: they remain the
right tool for small fixed-order record tables. Migrating the remaining
hand-rolled plugin tables is open work.

# The ndX contract

ndX lives in its own repository and installs standalone — it does not
depend on ChiSurf. Its `ui/dataframe_editor.py` therefore imports chitable
inside a `try`/`except ImportError` and keeps a reduced local implementation as
the fallback, the same arrangement `ui/parameter_editor.py` and `ui/glyphs.py`
use. The public surface (`DataFrameEditor(df, parent)`, `.dataframe`,
`.exec_()`, `edit_dataframe`) is identical on both branches, so call sites never
branch. Changes to those files are committed in the ndX repository, not
in ChiSurf.

`ndxplorer/ui/table.py` extends the same arrangement to the ordinary *item*
tables: `ValueTable` is a `ChiTableWidget` wrapping a `QStandardItemModel` when
chitable imports, and a plain `QTableWidget` when it does not, with `TableItem`
resolving to the matching item class. Both branches present the `QTableWidget`
item API the call sites are already written against.

**The trap this arrangement introduces, and the rule that answers it.** Giving a
table sorting and filtering means the row on screen is no longer the row the data
is in. `selectionModel().selectedRows()` reports *view* rows; using one to index
the underlying list reads — or deletes — a different record, silently, as soon as
the user sorts a column. `ValueTable.source_row()` and
`selected_source_rows()` are the only supported way across, and are correct on
both branches (the identity where there is no proxy). Any table gaining chitable
must have its selection-to-record call sites converted at the same time; this is
the same hazard `DataFrameEditor` records for its own `_source_rows` list.

Tables whose cells hold real widgets (`setCellWidget` — ndX's selection
table and report table) are **not** shim candidates: chitable expresses those
with delegates, so they need their state handling rewritten rather than swapped.

# Styling

Typography comes from `chisurf/gui/widgets/general.py` (`table_font()`,
`table_row_height()`, `table_header_height()`), driven by `settings.gui["table"]`.
`apply_compact_table_style()` disables sorting and header clicks by default
because most ChiSurf tables are fixed-order record lists; a sortable table
passes `sortable=True`.

# Related

* [GUI & AutoForm](/subsystems/gui-autoform.md) — the declarative UI framework
  and its own `table` section.
* [Parameters](/subsystems/parameters.md) — what the parameter tables display.
* [PRD-66](/prds/prd-66.md) — the design note driving this work.
