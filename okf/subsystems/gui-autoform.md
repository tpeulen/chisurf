---
type: Subsystem
title: GUI & AutoForm
description: The Qt application and the data-driven AutoForm UI framework that renders view.json schemes.
resource: chisurf/gui/
tags: [gui, qt, autoform, viewspec]
timestamp: '2026-07-05T00:00:00Z'
---

# GUI

`chisurf/gui/` is the Qt application: the main window, widgets, plots,
resources, and GUI startup helpers. It is launched via `python -m chisurf`
(`pixi run chisurf`). Plotting goes through the [chiplot](/subsystems/chiplot.md)
seam, not a plotting library directly.

## TCSPC first-use responsiveness

Fit windows demand-create their hidden Code editor; plot exports and optional
section factories resolve lazily. Metadata tables share compact complete-catalog
models, defer dictionary/description loading and avoid full-key layout scans.
Qt solid strokes batch whole finite runs without resampling, retaining gaps,
dashed fallback, clipping, painter state and the old effective line thickness.

### Where to pick this up

The scoped implementation and independent reviews are verified. The real-data
isolated native window pipeline measured 1.89x cold and 2.07x warm; these are not
end-to-end Add-button speedups. Finish successful-action Main pairing without
bypassing scientific history; old Main timings hid a caught checkpoint failure.
The latest guarded smoke passes on the current shared tree; the cause of that change was not established. Commands,
raw measurements, limits and next acceptance gates are in
[TCSPC first-fit validation](/validation/tcspc-first-fit.md).

## Fit window

A fit window's content is one emtk surface (plots, tabs and dock regions, data
table, report, Code face); see [Fit window](/subsystems/fit-window.md). An
earlier note here described a Qt `DockArea` restyled dark as an emtk tab bar;
that was never what the code did.

# AutoForm

`chisurf/gui/autoform/` renders UI declaratively from JSON view schemes
(`*.view.json`) instead of hand-built Qt widgets. This is part of the PRD-40
model/UI split, backed by data specs in `chisurf/core/dataspec/`.

## Model-port constraint: AutoForm now, emtk later

For the current model/state port, reuse AutoForm and its data specs; do not turn a later emtk migration into an immediate renderer rewrite or create a parallel framework. Keep configuration, validation, computation and actions in toolkit-neutral model objects. Declare ordinary controls and tables with existing generic spec sections and bind them through stable data paths/model methods. Serialize explicit scientific state and plain presentation data, never widgets, Qt item/index objects, signals, connections or callbacks. Do not retain old widget-model compatibility when the port explicitly drops it.

AutoForm is extensible, not a restriction on model capabilities. If a required interaction is missing, enhance its existing spec, binding or section machinery with the smallest concrete capability needed, sharing it across models where appropriate. Do not simplify the science, omit controls or replace a necessary interactive editor with inert labels to fit today's forms. Rich scientific viewers/editors can be named custom sections whose data, actions and saved state are toolkit-neutral; keep that contract separate from drawing so an emtk renderer can implement it later without changing the model or persistence schema.

Require a concrete unsupported interaction and a failing regression before extending the framework. Test the data/binding/state contract independently, then drive the actual renderer with legitimate inputs. Do not put domain behavior in Qt slots or make QObject names/layout introspection the model persistence schema. Keep matched before/after screenshots, direct visual inspection, interaction checks and numerical/fresh-file parity as acceptance gates.

### Where to pick this up

The current before-only catalogue capture covers all 42 configured entries with 196 PNGs, source hashes, exact scientific snapshots and control inventories in `scratch/autoform-migration-20261004/before-matrix.json`; all native/Qt children exited zero and rendering left their scientific snapshots/outputs unchanged. These are current Qt-AutoForm editor baselines, not deleted per-model widgets, after-pairs, full-window/plot coverage or migration approval. Initial direct image inspection found constrained-width clipping and compressed numeric fields. Preserve the baseline, follow the [shared project/model acceptance plan](/plans/2026-10-04-full-scientific-session-history.md), and require matched after evidence before closing a model row. No GUI production code was changed by the baseline/constraint recording.

The shared `rate_matrix` enhancement is now narrowly accepted: live addressed-cell commits and toolkit-neutral parameter/notification binding, refreshed fixed/link/bounds metadata and range warnings, minimum cell widths and reachable horizontal scrolling. Parent 25/25 unique focused passes, exact five reviewed hashes, matched 620×900/360×600 images directly inspected, measured-FCS keyboard edit plus canonical `.cs.pto` fresh readback with MMFDB/original source reads blocked; independent SPEC PASS followed by quality PASS. [Contract](../../docs/development/autoform_matrix_contract.md); receipt `scratch/autoform-migration-20261004/rate-binding/parent-accepted-evidence.json`. This does not accept all model modes or replace full application gates.

The shared scientific Main probe now recognizes a real rich rate control rather than requiring every parameter to appear in a flat table. Parent helper/binding/renderer union 28/28 and actual FCS kinetics Main lifecycle 1/1 (107.347 s), all six stage outcomes zero and ordinary API/macro save/readbacks exact. The real `k3_1` keyboard edit changes 500→750, predictions and relaxation modes, then survives fresh edited reload with original sources/MMFDB blocked. Normal/constrained six-tab before/restored contact sheets were directly inspected. Matrix scrolling, vertically hidden lower sections and overflow tab arrows remain part of full usability gates; a constructed idle scan tab is not an executed scan. Caught single-Fit sampling/`scale_x` fallback diagnostics remain. Probe independent SPEC then quality passed on exact two hashes; receipt `scratch/autoform-migration-20261004/rate-binding/rich-probe-accepted-evidence.json`. The complete-budget native/UID/owner/public/legacy regression now passes139/139 in241.451s, superseding earlier undersized240/150s timeouts. Fresh TCSPC/GeneralFCS Main reruns still fail the exact table-control ownership gate after successful public load and snapshot/science comparison; TCSPC grouped restoration independently fails on `rotation.amplitude.0`. Diagnose canonical inactive ports and scalar/output display bindings separately before changing production or loosening assertions. All42 full model rows remain pending.

### Declarable graph and store sections

Two general sections make a *graph* and a *store* declarable, and both were
added for the [PTO inspector](/plugins/core-tools.md) while belonging to nobody
in particular:

- **`node_graph`** — a read-only node-editor graph bound to a model method
  returning the [node-editor](/subsystems/graph.md) JSON. Anything whose
  structure is a directed graph (a provenance chain, a pipeline, an evaluation
  network) could until now only be drawn as a list or a tree, and both lie the
  same way: a node reached by two paths is either duplicated or one of its edges
  is dropped. `selected_call` / `activated_call` bind selection and double-click
  back to the model. **Trap:** the section compares `(nodes, edges)` and ignores
  `meta`, because a model reporting its selection through `meta.focus` hands back
  a different dict on every click, and reloading on that resets the zoom. A node
  whose config says `"shape": "circle"` is drawn as a coloured circle with its
  name beneath it (see [the node editor](/subsystems/graph.md)), which is the
  right shape for a graph whose nodes *name* things rather than hold editors.
- **`store_table`** — a `ChiTableWidget` bound straight to a `tttrlib.DataStore`.
  The built-in `table` section takes a list of row mappings, which is right for a
  few dozen records and wrong for data: materialising a 100k-row burst table as
  dicts costs more than reading it did. Column units need no option — a store
  column states its own unit and [the shared table](/subsystems/gui-tables.md)
  now reads it into the header.

`plot` gained **`axes_source`**, a model method returning
`{"x_label", "y_label", "log_x", "log_y"}`, re-read on refresh: a browser whose
plot shows an FCS lag axis in milliseconds on a log scale and then a decay axis
in nanoseconds on a linear one cannot state either in JSON, and labelling both
`x` is how the two get confused. `table` gained **`selected_call`** (the row dict
on every selection change, `{}` when cleared) — a master list driving a detail
panel is the commonest table idiom there is, and `selected_attr` covered it only
for a model willing to expose a reacting property setter.

**`data_table` and `table` read the same in both renderers.** emtk draws both
dialects from a spec (`emtk/widgets/data_table.py`: `TableBinding` +
`DataTable`, used by `emtk.widgets.view_spec.table_bindings`/`ViewSpecPanel`
and `emtk.view_form`), so the options a ranked or streamed table needs are
shared rather than renderer-specific: a column's **`"display": "bar"`** with a
**`"range"`** draws the value as a bar under its text (diverging from zero,
coloured by sign, when the range spans zero; `BarDelegate` in
`chitable/delegates.py`, `ColumnSpec.value_range`), **`format`**,
**`columns_source`** (columns known only at run time; then the declared columns
are exactly the columns), **`sort`** `{key, descending}`, **`tooltip_key`** and
**`row_key`**. A record list that **grows in place** is re-read without a
rebind, keeping sort and selection, and `selected_call` is not fired again for
the row already selected. Found on the way: a sorted `ChiTableModel` reported
the *view* row as the source row on selection (it sorts itself, with no proxy
to map through), so a sorted table handed `selected_call` the wrong record.

**An `expand` table measures what follows it; there is no `reserve`.** In emtk the
table takes the height left in its region less the rows drawn after it (fields, a
button row, a host-drawn status line, rows after an enclosing tab bar). Those rows
are measured when the region ends (window `end`, `end_child`, `end_frame`) and the
table fits from the next frame on (`emtk.layout.Fill`); two expanding tables in one
region share the room. The hand-set `"reserve": <px>` this replaced (33 specs) went
wrong whenever a translation, a label stacking under its field or HiDPI changed the
rows' height. Do not reintroduce a pixel number for it; the key is no longer valid.
`"stretch": <weight>` (with `"min_height"`) shares the room among several such items by
weight — the shell's Datasets dock gives its datasets and fits tables 1:1 and the status
line one text line; hand-drawn emtk code calls `im.stretch_height(id, weight, minimum)`
(the Read data dock's reader form, which used to leave a guessed 40 px).

#### Where to pick this up — vertical space (2026-10-12)

1. **Fixed-height tables still in specs.** Re-derive the list: walk every `*emtk*.view.json` and
   `chisurf/emtk/views/*.json` for `table`/`data_table` sections with neither `expand`, `stretch` nor
   `fit_rows` (26 on 2026-10-12, mostly in long scrolling settings forms: LUT tools, FCS filter calculator,
   FCS saturation, FRET lines, VV/VH batch files, ALEX regions). Two traps decide each one: in a form that
   already overflows its dock a stretching table drops to `min_height` (so set `min_height` to its old
   `height`, as the HMM / G-factor / Spectra / Burst-wise FCS docks do); and a table drawn *before* a host
   plot that sizes itself from `get_content_region_avail()` steals the plot's room — give the plot
   `im.stretch_height(...)` with a larger weight instead of stretching the table alone.
2. **Hand reserves in host code**: `avail_h - 4.0`, `avail[1] - 10.0`, `bar = 34.0` (pch, audifier,
   tttr_image_browser, burst_background, mfd_prepare, tr_anisotropy's wizard body; grep
   `avail_h - [0-9]` / `avail\[1\] - [0-9]`). Each is the same defect as the old `reserve`; port to
   `im.stretch_height`. Not done here: their files carry other agents' uncommitted edits.
3. **Datasets dock at 800x600** gives its tables ~50 % of a 217 px dock, not 70 %: the left column's
   default split is 0.5 (`main_app.py`, `Split("v", 0.5, …)`) and the Model label stacks above its combo
   at 200 px. Changing the split trades Analysis room — a product decision, not taken.

A section rendered as a **dock-area child no longer draws its own caption**: the
dock tab already carries the title, so a `custom` section in a dock used to put
"Provenance" directly under a tab reading "Provenance".

Notable section types the framework supports include `image` (3D stacks with
click-pick / markers / on-image text labels / ROI), `image_browser` (a
navigable entry list — files, molecules, frames — beside that `image` canvas,
with per-entry star ratings, an editable note, a filter and drag-drop; shared by
the TTTR image browser and the molecule-wise MLE tool), `waterfall` (RGB
time-vs-µtime images), `path_list` (the one drag-drop file/folder list every
plugin now uses instead of a hand-rolled widget — drops + Files/Folder/Remove/Clear
plus first-class MMFDB "select from database" selection, and options for the cases
that used to justify a custom list: `checkable` tick boxes, a `folder_expander`
hook, a `path_filter` predicate, `replace_on_drop`, and `allow_duplicates` for
ordered lists that may legitimately repeat an entry, such as a homodimer's per-body
PDBs),
`state_table` (the **rectangular sibling** of `rate_matrix`: one row per state, one column per property — molecules, diffusion, per-channel brightness, an efficiency. `rate_matrix` says how states *interconvert*; this says what each state *is*, and both track the same kind of count attribute. It is for **plain numeric lists** on a view-model, where `parameter_group_table`/`dynamic_group` cover rows of `FittingParameter`. Columns address `list[row * stride + slot]`, so several properties packed into one flat store each read their own slot; `columns_source` lets the model decide its own columns (which detection channels are enabled), and `trailing_rows_source` appends rows whose cells bind to *scalar* attributes — a background row is not a state but is read in the same columns. A column's `kind` picks the editor — `float` (default), `bool` (a checkbox) or `readonly` (a value the model writes and the user reads, such as a fitted result beside the initial value it started from) — and `minimum_attr`/`maximum_attr` name **per-row** bound lists, for tables whose rows are not interchangeable. Those three together are why an estimator's *parameter* table is the same widget as a state table: rows are things, columns are aspects, only the cell editor differs; the burst MLE wizard's schema-driven grid is declared this way. A column declaring `action` instead of `attr` is a **button per row**, calling `model.<action>(row)` — that is how a state gets a sub-editor for something too big for a cell (a decay spectrum), without a separate "which state am I editing" selector that can disagree with the table. It replaced the acquisition simulator's bespoke 90-line species table), `rate_matrix` (a reusable editable N×N transition-rate grid that tracks a
`size_attr` such as the species/state count, with the diagonal fixed at 0 — for
kinetic interconversion matrices anywhere in ChiSurf; `"popup": true` puts the
grid behind a button carrying a live summary — size and how many transitions are
non-zero — since an N×N grid costs N rows of panel whether or not anyone is
editing it, which is the wrong trade for a secondary control such as the
acquisition simulator's two matrices. The popup is **modeless**: edits apply
live, and a modal window on an offscreen run has nobody to close it. The grid is a
**view, not an owner**: building or refreshing it never writes back, and a stored
rate outside the configured `minimum`/`maximum` is displayed clamped and in red
while the model keeps the real value — a spin box clamps and rounds, so a grid
that wrote what it displayed silently moved every rate it could not
show), `parameter_group_table` (a
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
`global_parameter_table` (a **cross-owner** variant used by the Global View's
Parameters tab: unlike `parameter_group_table` it spans *many* owners — every fit
plus every out-of-fit group from the
[parameter-group registry](/subsystems/parameters.md) — and adds Owner and Link
columns. It is a `custom` section (`register_section`) rather than a bound-model
section, since its rows come from the live fit list and the registry, not one
model's attribute; edits route through an injected mutator, so fit rows use the
fit-addressed RPC path and out-of-fit rows use the `parameter_uid` path, keeping
the widget database- and mutation-policy-free),
`scalar_table` (the same compact name/value table for **plain** `float`/`int`/
`bool` model attributes rather than `FittingParameter`s — `{rows:[{attr,label,
kind}], call}` — for parameter-dense editors like the FRET-species crosstalk /
anisotropy groups), `dynamic_group` (a variable-length list of parameter
components with add/remove controls driven by the model's own
`append`/`pop` methods; `row_width` parameters form one component. Its default
`style:"grid"` lays each parameter out as a standalone spin-box row, while
`style:"list"` renders the same parameters **one per row** in the
`parameter_group_table` widget — the vertical layout for a narrow host, where a
six-parameter component would otherwise need a dozen columns; the section still
knows which component a row belongs to (`row // row_width`), so "del" removes the
selected *component*. `style:"table"` renders the components as one **paired** `QTableView` — each
component is a single row: a `#` index column then the compact
`value`/`fixed`/`bounds_lo`/`bounds_hi`/`bounds_on`/`error` columns repeated once
per parameter slot, so an amplitude block sits beside its lifetime block. A
rich-text header renders the slot's HTML label (`x<sub>l</sub>` → xₗ,
`&rho;` → ρ) with the per-component index stripped; the paired table reuses the
`parameter_group_table` cell logic, `FittingParameterProxyController` link/detail
actions, and copy/paste. Note: Qt's rich-text engine only supports HTML4's
Greek-letter entity set (`&tau;`, `&rho;`, `&epsilon;`, ...) — HTML5-only
entities like `&epsiv;` (the curly-epsilon variant) render as literal text,
not the glyph; stick to the HTML4 set in `label_text`. Both table widgets'
value/Lo/Hi columns use `_FloatEditDelegate` (`ScientificDoubleSpinBox`, `%g`
formatting, no artificial range) instead of Qt's default double-spinbox
editor, which defaults to 2 decimal places and a 0–99.99 range — without it, a
value like a 0.001 ms bunching time constant displayed as "0.00" while being
edited, and a value above 99.99 (e.g. `w_z[nm] = 2020.1`) could not be typed
at all. A spin box only turns typed *text* into a *value* when the entry is
committed, and an item delegate's commit runs **before** the editor sees the
Return / focus-out that would do it — so `_FloatEditDelegate.setModelData` calls
`ScientificDoubleSpinBox.interpretText()` (the subclass's stand-in for Qt's
non-virtual `QAbstractSpinBox::interpretText`, which knows nothing about the
value this subclass manages) before reading `value()`. Without that call every
number typed into a table cell was discarded on commit and the cell snapped back
to its previous value. A cell edit is applied through the parameter's
`controller` (the proxy the table installs), whose `apply_value` /
`apply_fixed` / `apply_bounds_on` / `apply_bounds` helpers do the three things
every parameter editor owes: local write, backend RPC through the fitting
client, and a provenance-trace entry — the same route the per-parameter row
widgets and the detail popup take, so a table edit is no less visible to the
backend or the history projection than a row-widget edit. `setData` signals the
whole **row** as changed, since one column's edit changes what its neighbours
show (enabling bounds fills the Lo/Hi cells; a bound that excludes the current
value clamps it). The boolean columns' click-to-toggle delegate acts on the
**left** button only and only on an editable cell — otherwise the right-click
that opens the link/copy context menu flipped the flag on its way. The TCSPC
Lifetime model's Lifetimes (xₗ/τₗ) and
Anisotropy rotation (bᵢ/ρᵢ) groups use `style:"table"`. Both table widgets
(`parameter_group_table` and the paired `dynamic_group` table) can hide the
**Lo / Hi / Bounds** columns to keep the tables narrow — every `panel` puts a
small checkable "bounds" button in its fold header (`bounds_toggle` defaults to
`true`; set `false` on a panel to opt out) that shows/hides those columns for
*every* table in the panel at once (columns start hidden; bounds stay editable
in the parameter details popup) — this is the default specifically so a
`dynamic_group` table's paired Lo/Hi/Bounds/Error columns (doubled per slot)
don't force horizontal scrolling in a narrow dock. The paired table takes the
**same `columns` whitelist** as `parameter_group_table` (`section.columns`), so
"which columns this table shows" is declared one way for both — a host whose
parameters no fit optimises leaves out `error` rather than carrying one empty
column per slot, and the bounds toggle honours the whitelist instead of bringing
back what it excluded. Two more section fields exist because a component table
outside a model editor needs them: `slot_labels` names the columns independently
of row 0 (a group that starts empty would otherwise show bare column numbers) and
`remote: false` says the parameters belong to no backend fit, so an edit is not
answered with "fit not found". The section's `del` button removes the **selected**
component when the group's remove method takes an index (deleting the second of
four lifetimes was otherwise impossible, and taking the last one silently is a
surprise), falling back to the last one.

Three sizing rules the tables learned from being put in a dock rather than a
scrolled editor. Sizing to content has to allow for the **horizontal** scrollbar
a table wider than its host grows, which is drawn inside that height and
otherwise eats the last row exactly as a bad row-height estimate would.
`RichTextHeaderView` measures the *rendered* title, not the markup, or a column
headed `&sigma;<sub>x</sub>` reserves the width of nineteen characters to paint
two glyphs. And the per-slot value columns only **stretch** when the equal share
is wide enough for every value — squeezed below its content a column elides the
number it exists to show, so the alternative is to hug the contents and give the
slack to the last column. `set_scrollable(min_visible_rows)` is how a host that
cannot grow (a dock) says so: the table then asks for that many rows, accepts
anything up to its full content, and scrolls the rest, so enlarging the host
shows more rows instead of blank space. The
`CollapsibleBox` header gained `add_header_widget` to host such per-section
controls with no extra vertical space), `help` (a `?` modal button),
`progress` (the one inline progress bar — see below), and
`wizard`/`info`/`embed`.

`embed` takes either `widget` (a dotted import path — a *fresh* instance is
constructed) or **`attr`** (the name of a model attribute or zero-argument method
holding a widget that already exists, which is adopted as it is). The second is
what a panel loaded from a `.ui` file needs: its controls are built by `uic`,
wired by `objectName` and referenced from a dozen places, so constructing a
second copy yields a panel-shaped decoy with nothing connected to it. That is how
ndX's Histogram block became foldable without rebuilding thirty controls its
mixins reach by name. Pair it with `"expanding": false` for a compact block of
controls, which should stay at the height it needs rather than absorb the dock's
spare space — a panel that keeps that space folds into a panel-sized hole.

`"expanding": true` inside a `panel` now reaches the layout. The stretch is
handed to *top-level* children only, so an expanding section nested in a panel
was invisible to it: the form appended a trailing stretch, the panel stayed at
its minimum, and the height a table or plot asked for went to the gap underneath.
A panel whose subtree contains an expanding widget is marked expanding itself.

# Drop guards: nag, transform, or refuse before a dropped path commits

Every drop zone used to go straight from `dropEvent` to committing the raw
path. `chisurf/gui/widgets/dropguard.py` adds a small registry — shaped like
this file's own `register_section`/`get_section_factory` on purpose — that a
drop zone opts into **by name**, so different drop zones can disagree about
what should nag them, or name nothing and behave exactly as before:

- `DropGuard` — `applies(path) -> bool` (cheap, no I/O beyond a suffix/header
  check) and `resolve(parent, paths) -> list[str]` (shown only the paths
  `applies()` accepted; returns what to actually commit — a converted path,
  the original, or fewer entries than it was given when a guard declines a
  path outright). `resolve` owns its own dialog, if any.
- `register_drop_guard(name)` registers an instance, a subclass, or a
  zero-arg factory.
- `apply_drop_guards(parent, paths, guard_names=())` is the one call a drop
  zone's `dropEvent` makes. `guard_names` defaults to `()` — inert, shows
  nothing, returns `paths` unchanged — which is what makes the pattern
  opt-in rather than a hidden global hook. Guards run in order; each only
  ever sees (and can only ever transform or drop) the paths its own
  `applies()` accepted, so two guards compose without interfering.
- `path_list` and `data_source` (above) both gained a `guards` option
  (`{"guards": ["tttr_to_pto"]}`) applied only on an actual drag-and-drop —
  never on a browsed or database-picked file, since browsing is already a
  deliberate choice. Pre-unification hand-rolled `dropEvent` handlers call
  `apply_drop_guards` directly instead.

The one guard ChiSurf ships is `tttr_to_pto`
(`chisurf/plugins/core/tttr_to_pto/`): dropping a vendor photon file
(`.ptu`/`.spc`/`.ht3`/...) onto a drop zone that opted in offers converting it
into a `.pto` container — **convert-and-keep** (the default, both for the
dialog and headlessly: it never deletes anything, so it is the one answer
that is always safe to take unattended), convert-and-delete (only after the
copy verifies), or use-as-dropped — once, with a "remember my choice" tick
persisted per-guard as a tri-state under `data_loading.drop_guards.tttr_to_pto`
(`ask`/`always_keep`/`always_delete`/`never`). Several files dropped together
(a measurement split across `m000.spc`, `m001.spc`, ...) are embedded into
**one** container, in lexical order by file name
(`Measurement.create`'s multi-file form) — not one `.pto` per file. A
Becker & Hickl `.spc`'s `.set` sidecar (`pto.SIDECAR_ONLY_EXTENSIONS`) is
never itself a candidate: `applies()` excludes it, and `_add_instrument`
picks it up automatically beside its `.spc` regardless of whether it was
dropped at all — dropping `.set` alone is inert. The plugin also ships a
bare, prompt-free drop tool (`gui/tool.py`) that works **both ways** from
what was dropped: vendor file(s) are packed into one `.pto`; a `.pto` is
unpacked back to the vendor file(s) it embeds (`Measurement.disassemble`,
checksum-verified). See [photon container](/subsystems/photon-container.md)
for what a `.pto` holds and why opening a vendor file should produce one.

Wired opt-in so far at the drop zones that genuinely load a measurement
(burst background/IRF estimation, count-rate analysis, burst analysis, the
microtime shifter, the PCH tool, the TCSPC/PCH experiment readers) — not
every widget that merely inspects a vendor file in passing. Auditing the
remaining pre-unification vendor-file call sites and giving `chiplot` a
decimation budget for the photon-level plots a stacked `.pto` makes an
every-session concern are open follow-ups (see
[PRD-85](/prds/prd-85.md)'s "Where to pick this up").

# Reporting to the user: one message box, one progress bar

Two things every long-running or fallible tool must do — say that something went
wrong, and show how far the work has got — were each done four different ways,
so the same operation looked different depending on which window started it, and
head-lessly either popped a modal nobody could close or went silent. Both are now
single classes, and both follow one rule: **the caller says what happened, not
where it is shown.**

`chisurf/gui/dialogs.py` — `ChiSurfMessageBox`, used as `dialogs.error` /
`warning` / `information` / `question` / `confirm` / `choice` / `about` /
`report_exception`. It logs every box whether or not it is shown, raises the
window only when a person could dismiss it, and otherwise returns the answer the
caller declared **safe** (so an unattended run declines a deletion rather than
hanging on a click that never comes). `choice` covers what used to justify a
hand-built box — custom-labelled buttons plus an optional tick box, returning
`Answer(key, checked)` — and `informative` / `detail` / `text_format` cover the
rest. `auto_answer` scripts answers in tests. A guard test bans a raw
`QMessageBox` anywhere outside that module; the former per-file allow-list is
empty and the parallel `MyMessageBox` class is gone.

`chisurf/gui/widgets/messages.py` — `Msg` / `MessagesMixin`, the *other* half of
the dialog seam. A dialog is for a question or an event; most of what a tool has
to say is a **condition** it is in — "load a file first", "compute the histogram
first", "the last fit failed" — which arises, persists while its cause persists,
and is retracted when it is fixed. A modal box says it once and leaves nothing
behind, so the tool looks ready while still being unusable, and a test can only
observe it by intercepting a dialog. A widget therefore *declares* its conditions
as `Msg` attributes on nested `Error`/`Warning`/`Information` classes (which
subclasses derive from, so declarations accumulate like class attributes) and
raises them by name: `self.Error.no_file()`, `self.Error.no_file.clear()`,
`self.Error.clear()`. Three properties follow from declaring rather than firing:
the set of conditions is **enumerable** (reviewable and translatable — the
extractor picks up `Msg("…")` alongside `i18n.tr("…")`, and the text is
translated at render time so a language change re-renders what is on screen), a
message can be **retracted**, and a test asserts on `is_shown`/`text` instead of
on a patched dialog. Rendering is one line in the host's status bar, most severe
first, the rest counted and in the tooltip, elided rather than widening the
window, and added as a *permanent* widget so a standing condition is not hidden
by the transient `showMessage` text tools already use; the bar hides itself when
nothing is active. Any `QMainWindow` gets it lazily on its first message, so
`ChisurfDockTool` subclasses opt in by declaring a message; a plain `QWidget`
calls `install_message_bar(layout)`. First consumer: the PCH tool, whose six
modal boxes became six declared conditions. Pattern taken from an established
visual dataflow toolkit — see [the data-mining suite mining](/references/orange3-mining.md).

`chisurf/gui/progress.py` — `ChiSurfProgress`. The constructor takes the widget
the work was started from and resolves the display nearest-first: an inline
`progress` section in the same panel → the navigation shell's shared status bar
→ a modal dialog when standalone → the log when there is no GUI. The handle
duck-types both `QProgressDialog` (including `finish(final_text=…, auto_close=…,
close_delay_ms=…)` / `finalize(force_auto_close=…)`) and the status-bar task, so
migrating a call site is a one-line change. `iterate()` wraps a loop (range from
`len`, stops on Cancel, closes on exit); `maximum=0` is a busy indicator.
Cancellation is cooperative in two forms: a GUI-thread loop polls
`wasCanceled()`, while threaded work (fitting, FRET docking, H2MM, staged
loading) passes `cancel=<callable>` so the stop is *pushed* to the thread — a
flag it never reads would let the run continue to the end. The modal
`EnhancedProgressDialog` is now strictly the *backend*: constructing it directly
pins work to a popup even when embedded or headless, so the guard test rejects
it, and the two further duplicates (a `ProgressWindow` in the photon-filter
wizard and a dead Qt-free stand-in in the BVA core) are gone.

`chisurf/gui/task.py` — `run_in_background`, also reachable as
`ChiSurfProgress.run`, is the **execution** half of that seam. `ChiSurfProgress`
answers "where does this show up" and carries cancellation, but runs nothing, so
every operation that wanted to stay responsive grew its own executor, cancel
flag and result-delivery scheme and none of them agreed. The caller now says
what to run and what to do with the answer; the worker takes a `TaskHandle` as
its **last positional argument** and reports through it
(`set_progress`/`set_text`/`set_partial`, `is_cancelled`,
`raise_if_cancelled`). What that buys, each clause earning its place: every
callback is delivered **on the GUI thread** (a queued signal bridge), so the
worker may touch neither widgets nor plots and the caller need not care;
**partial results** let a plot fill in progressively instead of freezing then
jumping; **one run per owner** cancels and drops the previous run's result, so a
double-clicked Compute cannot let the older answer win; cancellation is
**pushed** to the flag the worker polls; and with no `QApplication` the work
runs **inline**, so a CLI or a headless test exercises the real call site rather
than a mock. Starting a task from a completion callback raises, because the
teardown still running would cancel it. Two teardown paths are easy to get
wrong and are pinned by tests: a future cancelled while still queued never runs
and so never emits — the task would stay "running" forever, `on_done` never
firing — and a superseded task must have its *updates* disconnected but its
*completion* left connected, or it never finishes its own bookkeeping. A
standalone tool window renders the run in its own status bar
(`StatusBarProgressHost`, attached lazily by `find_progress_host`) rather than
falling through to the modal dialog, which would take back exactly what moving
the work off the GUI thread bought. Consumers so far: the PCH tool's histogram
computation, and the two burst tools that each carried a **byte-identical** copy
of the machinery this replaces — the Gopich-Szabo photon-by-photon kinetics fit
and the accurate-FRET calibration, whose `_ComputeSignals`/`_ComputeTask` pair
swallowed every exception into `logger.debug`, offered no cancellation for a run
that takes minutes, and started a second run on a second click. The remaining
burst candidates are a different shape and a bigger job: burst-selection's
batch, the burst-wise FCS wizard, BVA and H2MM all drive their loop **on the GUI
thread** behind a window-modal progress dialog, so moving them means splitting a
loop that interleaves with model state, not deleting a worker class. Pattern
taken from an established visual dataflow toolkit — see
[the data-mining suite mining](/references/orange3-mining.md).

The `progress` **AutoForm section** (`{"type": "custom", "key": "progress"}`) is
what makes this wiring-free: the widget itself is a progress host, so a run
button in the same form is found by walking up from it. Note the bar is normally
a *sibling* of the button, never an ancestor — resolution therefore looks inside
each ancestor as it climbs, which is exactly the run-button-plus-bar row four
plugins had each hand-rolled. Options: `cancellable`, `hide_when_idle`,
`show_text` (turn it off where the surrounding tool already prints the running
message in its own label, or it appears twice), `handle` (publish the widget on
the model), and `target` (a model attribute holding a fraction 0–1 or percent,
polled on refresh) for progress a model owns rather than a GUI loop drives; a
live task always wins over a stale model value.

Tools whose layout comes from a `.ui` file cannot declare that widget without a
Designer promotion, so they call `adopt_progress_bar(self)` after `loadUi`: the
child named `progressBar` is swapped in place, keeping its position (grid cells
and spans included) and its attribute name. The replacement answers the plain
`QProgressBar` calls (`setValue`, `setRange`, …), so the tool's existing code is
untouched — that façade is what makes adopting the shared bar a one-line change
rather than a rewrite, and it turns the tool into a progress host at the same
time.

A `panel`'s (or `parameter_group_table`'s / `dynamic_group`'s)
`collapsed_when: {target?, attr, equals|not_equals}` folds it based on a bound
attribute's current value at editor-build time; `not_equals` folds *unless*
the attribute matches, the shape a mode selector wants (fold every panel
except the active mode's). A `panel` can additionally (or instead) set
`hidden_when` — same `{target?, attr, equals|not_equals}` shape, evaluated by
the same generic condition check, but *fully* hides the panel (header
included, via `setVisible(False)`) rather than just folding its body; use it
when an irrelevant panel should disappear entirely, not sit there collapsed.
Both conditions are evaluated centrally in `AutoForm._emit_sections` (the same
place that honors a section's static `visible: false`), not by the individual
section builder, so any section type gets `hidden_when` for free just by
declaring the field — a section builder does not need to remember to call
`setVisible` itself. A `choice` section can additionally set
`rebuild_on_change: true` so picking a new value schedules a deferred
`AutoForm.rebuild()` (`QTimer.singleShot(0, ...)`, generalizing the
combo-driven rebuild pattern several tool-specific hosts already used, e.g. the
PCH detector/setup combos) — this makes `collapsed_when`/`hidden_when` live
instead of build-time-only, at the cost of a full form rebuild, so it is
opt-in and scoped to `choice` sections only (never fires for a `value`/
`toggle` edit, so a spin box drag never triggers a mid-edit rebuild). See the
FCS general model's `diffusion_mode` selector
(`chisurf/core/models/fcs/general.view.json`) for the worked example — each
diffusion panel's `hidden_when` means only the active mode's panel is even
visible, not just expanded.

A `choice` section's options are inline (`options`/`labels`) or resolved
GUI-side from a model-backed `options_source` — a zero-arg method/attribute on
the view-model returning the list, re-read on every `sync()` so the combo tracks
live model state. That source may return either a flat list of values **or**
`(value, label)` pairs; the pair form lets a dynamic combo display a
human-readable label while committing the raw value, so a foreign-key dropdown
can show `"3 — Alexa 488"` yet store `3`. The MMFDB-admin entity form
(`autoform_entity_form.py`) uses this: each FK field binds
`options_source="fk_opts_<name>"` to a memoised, refreshable provider, so a
`refresh_dropdowns()` (cache-bust + `sync_fields()`) surfaces targets added while
the form is open — replacing the previous build-time-frozen option snapshot.

A `dynamic_group`'s add/remove buttons (`on_add`/`on_del`, and the
`style:"table"` variants `on_add_table`/`on_del_table`) call
`self.refresh_plots()` after dispatching the fit update, alongside rebuilding
their own row widgets — so any other `AUTOFORM_REFRESH` widget elsewhere in
the form (an `info` panel deriving text from the model, a plot, a status
table) stays in sync with the component count too, not just the table that
was clicked. **All tables** (log, `parameter_group_table`,
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
The AutoForm `table` section stays item-based on purpose — it is the right tool
for small fixed-order record tables. Anything data-sized (a burst frame, a fit's
curves, every parameter across every fit) uses the model/view
[chitable](/subsystems/gui-tables.md) family instead, which is also where the
boolean/float/rich-text delegates and the rich-text header view now live;
`parameter_table` re-exports them under their historic names.

**Help behind a `?` modal (general UI rule).** Keep forms uncluttered — short
labels, detail in tooltips, and *longer* explanations behind a small `?` button
that opens a modal help popup rather than inline paragraphs. The reusable `help`
custom section renders that button:
`{"type":"custom","key":"help","options":{"title":"…","text":"# markdown…"}}`
(or `"resource":"path.md"`); it opens a modal `QTextBrowser` (Markdown/HTML). Add
one to any dense view instead of packing instructions into the layout.

The same modal is what a *tool's* toolbar `?` opens, beside a **Guide** button
that walks the user through the tool one real widget at a time. That pair is now
attached through one shared mixin rather than a base class, so any tool can have
it — see [Help buttons and guided tours](/subsystems/gui-help-and-guides.md).

A reusable **synthetic-decay editor** (`chisurf/gui/widgets/synthetic_decay_editor.py`,
`SyntheticDecayEditorModel` + `synthetic_decay_editor.view.json`) packages an
amplitude/lifetime spectrum table, IRF (file or Gaussian FWHM), Poisson
shot-noise, a measured-pattern override, "Read from Fit", and a live decay
preview into one view; the FCS Filter Calculator's synthetic-component dialog and
the acquisition simulator's Decay modal both embed it so the two never diverge
(see [plugins/fcs.md](/plugins/fcs.md)).

## A bound control only dispatches at a fit the machinery knows

`_own_fit_index()` answers "which fit does this bound model belong to". When the
model's fit is **not registered** in `chisurf.fits` — a scripted or headless
fit, or a tool with no fit at all — it now returns **-1**, and every
fit-targeted dispatch goes through the single `_dispatch_fit_update()` guard
that skips a negative index. It used to return `0`, which is not "unknown" but
*another fit*: against an empty list it raised (the edit was logged as a failed
commit and the host form never rebuilt), and against a populated one it would
have aimed the edit at whichever fit happened to be first. `ValueWidget._commit`
additionally falls back to the direct attribute set when the index is negative,
so a scripted form still applies the value instead of dropping it.
`test/gui/test_autoform_fit_dispatch.py`.

## Equation editor + safe expression engine

`chisurf/core/expressions.py` is a **general, Qt-free safe expression engine**:
an AST-whitelist parser/validator/evaluator for *user-entered* formulas (derived
columns, analytical parameter relations, model equations). It replaces the
codebase's ad-hoc alternatives — `eval` under `from numpy import *`, a
`re.Scanner` tokeniser — none of which sandboxes input or gives structured
feedback. Everything is governed by an `ExpressionPolicy`: which node kinds are
allowed (arithmetic, optional comparisons/bit-ops), the whitelisted function set
(`DEFAULT_POLICY` ships a rich NumPy library — `sin/cos/exp/log/sqrt/where/clip/
minimum/maximum/…`), the named constants (`pi/e/inf/nan`), and how names
resolve: **quoted** references (`'Green Count Rate'`, so names may contain
spaces) vs **bare** identifiers (`tau`), optionally case-insensitive and matched
on the part left of a `|` (the `"Name | unit"` column convention). A caller
symbol always **shadows** a constant of the same name — a column called `e` is
that column, and the constant only fills in when no such symbol exists — so the
engine can never silently swap a user's data for a number. (The rewriter cannot
decide this: it runs at compile time and its result is cached per
`(text, policy)`, with no symbol table in sight. A constant name is therefore
rewritten to a `_c{j}` slot next to the `_r{i}` reference slots and resolved at
evaluation time. `refs` stays free of constants, so a constant is neither an
unresolved name nor a discovered fitting parameter.) Public surface:
`validate_expression(expr, known_names, policy) -> ValidationResult(ok, message,
refs)` for GUI ✓/✗, plus `compile_expression`/`evaluate_expression`. Two presets:
`DEFAULT_POLICY` (rich, Python-like, bare names) and `NDX_POLICY` (ndX
burst-column convention — quoted names, arithmetic + `abs`, case-insensitive,
left-of-`|`).

`chisurf/gui/widgets/equation_editor.py::EquationTableEditor` is the general
widget on top of that engine: a validated `Output | Expression | ✓/✗` table with
per-row error tooltips, a names+functions reference dialog, an optional inline
LaTeX preview of the focused row (reuses the parse-model `latex.py` helper;
auto-off for quoted-name conventions), add/remove rows, an `applied` signal, and
the lightweight `CodeEditor` surface (`text()`/`setText`/`load_file`/`save_text`/
`save_callback`/`filename`) so it drops in wherever a YAML equation blob was
edited as raw text. Validation is pluggable: a caller may inject its own
`validator` so the editor's ✓/✗ stays in step with whatever engine will *evaluate*
the formulas. The `equation_editor` AutoForm section
(`sections/equation_editor_section.py`) exposes it view.json-drivably
(`{attr, names, call, policy}`). ndX's equation editor delegates to this
widget when ChiSurf is importable (injecting its own `equation_graph`
validator + a `(columns, constants)`→mapping names adapter), and falls back to a
local table when ChiSurf is absent.

`chisurf/gui/widgets/expression_input.py::ExpressionInput` is the **single-**
expression counterpart used where a model is *one* formula rather than a table of
named outputs. It is a compact one-line editor with the same live ✓/✗ validation,
a names/functions reference, an optional inline LaTeX preview, and automatic
**parameter discovery**: `PARSE_MODEL_POLICY` (bare names, rich maths, unknown
names allowed via `validate_expression(..., allow_unknown=True)`) treats every
name that is not the independent variable, a function, or a constant as a free
fitting parameter, read back with `expressions.discover_parameters`. Note the
engine deliberately omits `tau` from its constants — `tau` is the universal
lifetime-parameter name and binding it to 2π would silently corrupt decay
formulas — and that any remaining constant is shadowed by a symbol of the same
name, so a collision costs at most the constant, never the data.

**It is reached declaratively**: a `value` section of `kind: "expression"` renders
an `ExpressionInput`, so *any* view spec gets a validated, previewed formula field
with parameter discovery — not only the parse models. That is what retired
`gui/widgets/models/parse/widget.py::ParseFormulaWidget` and the last `.ui` under
`models/`; the badge and the LaTeX preview were the only reason that file
survived its model becoming data-described. **Do not re-implement the check at a
call site** — a second answer to "is this formula safe" is worse than none.
The field takes a whole form row (`_autoform_full_row`): packed two-up beside
another field it shrinks to showing its last few characters.
(ParseModel's own evaluation is unchanged; the engine drives editing and
validation, not model math.)

When touching GUI code, prefer porting hand-built widgets to AutoForm + a
JSON view scheme.

## Prefer the table rendering of a parameter group (repo-wide)

**`parameter_group_table` is the default; `parameter_group` is the exception.**
This was already universal practice before it was written down: every
`*.view.json` in the tree uses the table form, and *none* uses the verbose one.
Only the FCS-scoped statement existed, so the rule read as a local preference
rather than the convention it is.

A parameter group is a homogeneous list of parameters each carrying the same
columns — value, fixed, bounds, error. That is a table. The stacked form spends a
labelled row plus six controls per parameter, so an eleven-parameter convolve
group fills the panel on its own and pushes the rest of the editor below the
fold.

Reach for the verbose `parameter_group` only when:

- a parameter needs a control a table cell cannot host — a prior editor, a
  bespoke widget; or
- the group is short enough (one or two parameters) that a table's header row
  costs more vertical space than it saves.

Both are `target`/`exclude_source`/`collapsible`-compatible, so the choice is one
word in the JSON.

`Model.view_spec()`'s auto-derive fallback emits `ParameterGroupTableSection` for
the same reason: a model with no authored spec should get the rendering every
authored spec chose, not the one none of them did.

## A fixed parameter set is still a table

`parameter_group_table` originally rendered exactly `target.parameters_all`, one
per row. Two knobs cover the cases that were otherwise written as columns of
standalone parameter rows:

- **`parameters_source`** — a method returning the parameters to show, in order. A
  model that carries its own parameters (a chain model's contour and persistence
  lengths, a maximum-entropy model's grid settings) has no group to target, and
  `parameters_all` on the *model* is every nuisance group as well.
- **`row_width`** (+ `slot_labels`, `row_labels` / `row_labels_source`) — packs
  parameters side by side, reusing the paired widget the component tables use over
  a *fixed* list. For a group that is really a **matrix** — PDDEM's quantities ×
  fluorophore A/B — a flat one-per-row list hides the pairing that is the entire
  structure of the group.

  Rows must be **named** when they are quantities rather than interchangeable
  components: the first column otherwise numbers them, and `1..5` beside `A`/`B`
  says nothing about which row is the transfer rate. `row_labels` are drawn in a
  table **cell**, so unlike the slot/column headers they are *not* rich text — use
  the literal character (`α`), not an HTML entity.

Both also mean a section can omit `target`: **no target means the model itself**,
consistently across bound controls (`_BoundControlMixin._group`) and group
resolution (`AutoForm._resolve_group`). Before, one honoured it and the other did
not, so whether a section could address the model depended on its type.

## Columns are dropped by priority as the table narrows

A parameter table is asked to fit anything from a wide fit window to a docked side
panel, and its columns are **not equally worth the room**. Rather than squeezing
every column equally (or scrolling the value out of sight), the table drops whole
groups in priority order, defined by `_ContentSizedTable.RESPONSIVE_TIERS`:

1. **Lo / Hi / Bounds** first — a bound you cannot see is still one click away in
   the parameter details popup.
2. **Error** next.
3. **Fixed** last, for the same reason: the popup carries it too. Two tiers were
   not enough — a table packing four parameters per row still overflowed a dock
   once bounds and errors were gone, and clipped its last slot off the edge.

**Name and Value are never dropped.** A value you cannot read is the table failing
at the one thing it is for.

**Bounds are always wanted; only space hides them.** There is no toggle any more —
the width check made it redundant, so the `bounds_toggle` spec field and the
per-panel button are gone. The `columns` whitelist is still honoured as intent, and
the width check is a *ceiling* on it: it may hide further, never reveal something
the author hid.

Re-decided on **resize and on show**. The show hook matters because a table inside a
*collapsed* panel is never resized while hidden, so expanding one revealed a table
still showing every column and scrolling sideways.

### The measurement is apply-then-ask, not a sum of hints

The tier is chosen by **applying a candidate set and asking the header how wide it
came out** (`header.length()`). Size hints are not the widths Qt lays out, and
summing them was wrong in *both* directions:

- a **stretch** column is given more than its hint (its hint is just its longest
  label), so summing made wide tables look overfull and dropped every optional
  column at any width;
- every section is floored at `minimumSectionSize`, and the paired table's value
  columns switch between stretching and hugging their content, so a narrow table
  measured as fitting and then scrolled anyway.

In the paired table the column choice and the value-column policy
(`_fit_value_columns`) **depend on each other** — which columns show sets the width
left for values, and whether values stretch sets how much room is needed. It is
settled, chosen, then settled again.

A paired table may still scroll rather than squeeze a number until it elides (`0…`
is not a value anyone can check), but only once nothing optional is left to drop.

*Testing note:* a headless test must `show()` the editor and use `setFixedWidth` —
`resize()` alone is refused below a layout's minimum, so the editor never narrows
and such a test asserts nothing.

## Every fitting model's editor is generated — there is no model-widget layer

A fitting model is a pure, Qt-free class under `chisurf/core/models/` with a
co-located `<model>.view.json`; `AutoModelWidget` renders that spec, and
`gui/widgets/models/model_editor.py` is the seam the app calls
(`build_model_editor`, `model_plot_specs`). `chisurf/gui/widgets/models/` holds the
renderer, the registered custom sections, and **deprecation shims** — a user copy
of `experiment_configs.yaml` *replaces* the bundled model list and a pickled
project pins class paths, so every retired widget name still resolves, to the
model that replaced it. `test/gui/test_model_widget_modules_import.py` is the
guard.

Three things follow from this and are easy to undo by accident:

- **A model never names a plot class.** `view_spec().plots` lists registry
  *keys*; `sections/registry.py::resolve_plot_specs` maps them to classes. The old
  `plot_classes` attribute is gone — it was the last hard dependency from the
  compute side onto the GUI. A model that declares no plots gets **no** plot tabs,
  which is visible and fixable; the old fallback could hand it another model's.
- **A model never opens a dialog.** Anything a model must *do* is a zero-arg
  method a `button_row` calls, or an attribute a `choice`/`toggle`/`value` writes.
  Work that takes time is a plain `threading.Thread` on the model plus a
  `background_run` section, which owns the buttons, the bar and the repaint timer.
- **A computed output is a parameter write.** Publishing one through
  `get_fitting_client()` inside a bare `except` — the pattern that made four
  models hard to extract — does nothing whenever that client is absent and says
  nothing about it.

The migration record, including what each model needed and what its port found,
is [PRD-38](/prds/prd-38.md).

## Runtime `.ui` forms are prototyping-only (migration target: removal)

The **28** Qt Designer `.ui` files still loaded at runtime via `uic.loadUi`
(`chisurf/gui/decorators.py:_compiled_ui_class`) — down from 43, with all six
under `models/` gone — are a **prototyping-era carry-over,
not a supported UI layer** — AutoForm + `*.view.json` is the one intended UI
mechanism. Each `.ui` form should be ported to a `view.json` (+ a view-model where
it carries logic) and the `.ui` deleted; the target end-state is **zero runtime
`.ui` files**. Reasons this is debt, not just style:

- **No live retranslation.** `uic.loadUi` binds every string at build time, so an
  open `.ui` form cannot follow a UI-language switch without the
  reparse-and-reapply shim `chisurf/gui/retranslate.py` — whereas AutoForm reads
  its text through the [i18n seam](/subsystems/i18n.md) on every build and
  retranslates for free. (This is what motivated flagging the forms: see
  [PRD-63](/prds/prd-63.md).)
- **Two divergent UI paths** — data-driven specs vs. hand-drawn XML — double the
  surface for glossary/terminology drift ([I18N-01](/specs/assessment.md#i18n-01)),
  tooltip/label conventions, and theming.
- **Opaque to tooling** — `.ui` XML is invisible to the model/UI dataspec, the
  parameter registry, and the AutoForm section library (tables, `path_list`,
  `image`, `waterfall`, …) that already replace most hand-built widgets.

Tracked as [INC-13](/specs/assessment.md#inc-13). Until a form is migrated, keep
it on the [`retranslate_from_ui`](/subsystems/i18n.md) path so language switching
still works.

## UI convention: space-efficient labels + tooltips (general rule)

Screen space is a first-class constraint everywhere in ChiSurf — panels dock
side by side and controls must stay narrow. Therefore, for **all** UI (AutoForm
`label`/`description`, and hand-built Qt widgets alike):

- **Labels are terse** — one or two short words, abbreviations welcome (`Ch A`,
  `µt A`, `Bins`, `Fine`, `Width`, `Skew`, `AP`, `IRF`). Never put a full phrase
  or a unit-laden sentence in a label.
- **The full meaning goes in the tooltip** — the complete description, units,
  and examples. In AutoForm this is the section `description` (mapped to the
  widget tooltip, the view-spec description→tooltip note); in hand-built widgets call
  `setToolTip`. App-wide tooltip folding ([`chisurf/gui/tooltip.py`](/workflows/build-and-env.md))
  keeps long tooltips readable, so descriptions can be as complete as needed.
  When a field section (`value`/`choice`/`toggle`) carries no explicit
  `description`, `_BoundControlMixin._effective_description`
  (`sections/builtin.py`) falls back to the shared parameter registry, keying
  on the bound `attr` (scoped by the target group's class) via
  `chisurf.core.settings.describe_parameter` — so any field bound to a
  registered parameter gets inline help for free, matching the description its
  fitting widget already shows (see [Parameters](parameters.md)).
- **Prefer vertical stacking over wide side-by-side rows** when horizontal space
  is tight (AutoForm panel `n_col: 1`); prefer compact controls (short spin-box
  widths, emoji `QToolButton`s over text buttons). Default to the layout that
  keeps a panel usable at its *narrowest* docked width.

This is a standing rule: when adding or editing any control, choose the
space-efficient form by default and move detail into the tooltip.

### Curve previews in tooltips

Rows that stand for a curve say very little in their one elided line, so every
curve list shows on hover the **full file name and a thumbnail of the curve
itself**. The shared implementation is `chisurf/gui/widgets/tooltip_plot.py`: a
`QPainter` mini-plot renderer (`render_series_thumbnail` /
`render_curve_thumbnail`) embedded as a base64 `<img>`, the composed tooltip
(`curve_tooltip_html`, `dataset_tooltip_html`, `fit_tooltip_html`), and
tooltip items for every item-view flavour (`TooltipItem` for tables,
`TooltipTreeItem`, `TooltipListItem`, `TooltipStandardItem` for combo models).
Painting is **lazy** — an item renders only when Qt first asks for its tooltip
and then caches it, so a list of hundreds of curves costs nothing to populate.
Series spanning ≥ 2 decades are drawn logarithmically; data and model share one
y scaling. The spectra tooltips of the light-path simulator are built on the same
renderer. Whether previews are drawn at all, and how large, is configured under
`gui.tooltip.curve_preview` (default on) and read via
`chisurf.gui.tooltip.curve_preview_config`; disabled, the tooltip degrades to the
plain file name. New list/tree/combo widgets that show curves use these items
rather than an eager `setToolTip`.

## UI convention: write labels plain, let them be typeset

A quantity has two names — the one code and translators use (`tau_D(0)`,
`R_DA`, `Phi_A`, `kappa^2`) and the one a physicist reads (τ with a real
subscript). Writing the second by hand as HTML in a view spec buys the
typography and loses everything else: the string stops being greppable, the
translator is handed markup, and the generated documentation cell renders
literal angle brackets.

So **spell view-spec labels plain** and let [`chisurf/core/labels.py`](/subsystems/gui-autoform.md)
derive the typeset form. The convention is the one already used in the models:
`_` opens a subscript, `^` a superscript, braces group an explicit run
(`tau_{D,app}`), and a spelled-out Greek name becomes the letter — only when it
is the whole word, so `alphabet` survives.

Three renderings, one source:

- `to_rich` — HTML for a rich-text `QLabel`. `AutoForm._emit_sections` applies it
  to every field caption, so a plain `label` in a `.view.json` is typeset with no
  work at the call site. Labels that already carry hand-written markup (there are
  hundreds in the models) are passed through untouched.
- `to_unicode` — Greek plus Unicode sub/superscripts, for the places markup
  cannot go: table cells, plot axes, CSV headers, log lines. Only digits and
  signs have subscript glyphs, so `R_DA` deliberately keeps its underscore rather
  than being mangled into `RDA`, which names a different thing.
- `to_plain` — markup stripped, for tooltips, documentation tables and search.

The plain text stays reachable at run time as the label's `plainLabel` property,
so a caption that is typeset on screen can still be matched by a test.

`AutoForm.set_field_label(target, text=…/html=…)` retitles a caption
programmatically — the counterpart of a `FittingParameterWidget`'s `label_text`:
the field keeps its programmatic identity (the model attribute it binds to) while
what the reader sees changes. A `FittingParameter` follows the same split: `name`
is what links, state files and the ndxplorer mapping key on and must not move;
`label_text` is what the parameter table shows.

# Node editor widget

`chisurf/gui/widgets/node_editor/` is a self-contained, dependency-light node
editor (PyQt + the in-tree [`chinet.graph`](/subsystems/graph.md) layer) with
model/view/editor layering. It has a
**versioned JSON graph schema** (`{version, nodes:[{id,type,title,inputs,outputs,
config,pos,collapsed}], edges:[{source,source_port,target,target_port}]}`),
validate-before-mutate loading (`NodeGraphValidationError`, no partial scene on
failure), non-GUI file/dict serialization, a **node-type registry** replacing
hardcoded type lists, and DAG utilities (`is_directed_acyclic`, cycle
highlighting, optional `enforce_acyclic` edge guard). Round-trip and cycle
behaviour are covered by tests under its `tests/` directory. It is the substrate
the visual burst-programming canvas builds on (PRD-29).

# Glyph registry

`chisurf/gui/glyphs.py` is the single source of truth for the small pictographic
"emoticon" icons used in widget labels, actions, menus and `icon` metadata. It
exposes named canonical constants grouped by concept (`Glyphs.SAVE`,
`Glyphs.DELETE`, `Glyphs.REFRESH`, `Glyphs.SEARCH`, …) plus a `normalize(text)`
helper that rewrites the *unambiguous* historical variants to canonical form —
synonyms (`🔎`→`🔍`, `✎`→`✏️`, `✖`→`✕`) and missing emoji **variation selectors**
(`⚙`→`⚙️`, `🗑`→`🗑️`, …) so text-default symbols always render as colour emoji.
`normalize` is idempotent and leaves directional arrows, tree markers and plugin
brand icons untouched. The module is Qt-free (imports only `re`), so it is
testable headlessly (`test/test_glyphs.py`).

Genuinely distinct semantics stay distinct: `❌` = error status vs `✕` =
interactive close/cancel; `🗑️` = destructive delete vs `➖` = remove-a-row;
`🔄` = refresh vs `🔁` = loop/brand-icon vs `♻️` = reset-to-defaults. These
collisions are resolved per-site, not by `normalize`. New/edited GUI code should
reference `Glyphs.*` rather than hardcoding a glyph; JSON view/manifest files use
the same canonical literals by convention. Production GUI Python has been swept
to follow this: inline emoji literals are `Glyphs.*` references (whole-string
literals as attribute refs, `icon = "ℹ️"` → `icon = Glyphs.INFO`; mixed strings as
f-strings, `"💾 Save"` → `f"{Glyphs.SAVE} Save"`), so each concept has one authored
source. Left as literals on purpose: **directional arrows** `→`/`←` (prose- and
identifier-dominant), docstrings and multi-line help text, tests (literal
regression anchors). Plugin **brand** icons are a parallel axis: every plugin now
declares a single **emoji** brand icon (in its `manifest.json` `icon` field, or a
module `icon` attribute for manifest-less legacy plugins) — the former mix of
raster `icon.png`, dangling image references, and blank/name-fallback icons was
eliminated so a family reads coherently in the menu/ribbon (icons are distinct
within a family; cross-family repeats are fine since they live in separate menus).
Superseded and dead `icon.png` assets were removed; the resolver order is manifest
icon → on-disk image → module attribute → name fallback, so a leftover png would
otherwise shadow a module emoji. Rendering emoji/text/color/file icons into
`QIcon`s is a separate concern handled by `chisurf/plugins/icon_utils.py` (see
`chisurf/plugins/ICON_SYSTEM.md`).

# Long-term direction (maintainer, 2026-08-14)

AutoForm's declarative `view.json`/dataspec rendering is the seam the
web-capability plan runs through: the long-term goal is to abstract the UI
backend(s) — today Qt/PyQt is the only one — so a web-capable backend renders
the same schemas, then replace PyQt with chimol's emtk ([PRD-104](/prds/prd-104.md))
behind that seam to drop the PyQt licence obligations. Full statement in
[PRD-64](/prds/prd-64.md)'s "Long-term direction". This is a direction, not a
scheduled phase; it is recorded so the declarative-UI choice keeps its rationale.

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)

## Release-readiness native roots (W5, 2026-10-06)

### Where to pick this up

W5 roots are committed in emtk `a1398e0` (Driver first: `5de4c87`). Next is
W7's authoritative schema exports and click-all; 102 schema failures remain,
with every other existing Part A guard green.
[Receipts, captures and measurement traps](/validation/release-readiness-w5.md).

ViewSpecPanel now reuses the form grid rather than a SettingsEditor: column
weights and wrapping work while group/search/table/numeric controls retain
parity. Helpers with callers remain. Window state includes size, position and
docks; host close persists it and closes workers once. Qt masks incidental
modifiers and owns Tab; native GLFW advertises position capability. Keyboard
focus/activation, configurable frames, fonts and game modifier handling were
driven and inspected headlessly. All 58 ALWAYS size calls in 27 files describe
viewport regions; they are not initial host defaults to replace mechanically.

## Native click-all callback roots (2026-10-07)

The confirmed runtime failures were interface mismatches, not missing controls:
PTO Inspector now calls DatasetPicker.render; Global View accepts the boolean
delivered by its auto-refresh form while retaining direct zero-argument calls;
Structure Tools forwards key release only when a child implements that optional
hook. The toolkit Driver excludes None rectangles for unsubmitted canvases.
Seventeen focused runtime/Driver cases pass; actual Global View, PTO Inspector
and Spot Finder click-all workers pass and their PNGs were inspected. FRET
Docking's optional-hook crash is fixed; its missing guided tour remains W6 work.


## Uncalled loader retirement — 2026-10-07

AVProperties and WizardTTTRFileFormat have no external AST/config callers or
registry references and are removed with five dedicated files and two export
statements. Fresh runtime probes retain exact scientific/widget identity and
four neighboring wizard classes;46 parent cases pass. Catalogue regeneration
changes nothing. AV1/AV3/realSPC control baselines were inspected before removal.
[Receipt](../validation/release-readiness-w1/dead-loader-retirement/receipt.json).


## Retained quenching property repair — 2026-10-07

The old widget could not construct: a lazy aggregate lookup failed, then the
scientific Parameter field was assigned a Qt editor. The direct public factory
now binds a separate editor to that existing Parameter. Canonical scale/default
identity is retained; explicit historical alias applies only when needed. The
core duplicate missing-return boolean getter is removed, and public exclusions
and flag setters initialize/synchronize the original controls.74 parent cases
pass; qualified constructor-repaired before/final after PNGs inspected with
identical17 controls. Two unchanged Sticking/abstract-update type diagnostics
have a separate owning investigation; they are not hidden by suppression.
[Receipt](../validation/release-readiness-w1/quenching-properties/receipt.json).


## Dense plotting and stable column access — 2026-10-07

emtkd998f93f1/version0.1.6 provides exact cached Qt marker replay and equivalent
opaque software paths while retaining all source/hover inputs.65 parent owner
cases pass against the canonical installed Git revision, with byte parity for
alpha, clip, transforms and DPI;21 lock refs/version updated and lockcheckgreen.
Repeated unchanged table column visibility no longer resets horizontal scroll
each frame; real transitions retain reset/invalidation and last-column safety.
[Inspected measured evidence](../validation/release-readiness-w1/dense-markers/receipt.json).


### W1 FCS wizard retirement — 2026-10-07

The FCS Correlator/toolbox, Merger and Burst FCS callers host their existing native apps; obsolete central FCS/TTTR wizard Python/generated/UI chains are retired. Public publication/background/PTO/td4 lineage, skipped-row sentinels and bounded cancel/rollback behavior are preserved. No scientific algorithm changed. The original 8de6 before-facts used header seconds as milliseconds and are retained explicitly as invalid historical unit evidence. Final SPC13213.5ns is1.35e-5ms through readers/fitting; the real MaxEnt0.001..20 grid and core None sentinel are preserved.

Parent validations:56 host, earlier84 burst,54 diagnostic and15 new unit cases; final burst repeat and help/guide pointer review are recorded in the frozen acceptance receipt. All actual final images are inspected by the parent before execution. Next W1: GF row11, then rows12–14 and shared decorator retirement. Main gui.ui remains W9; W7 matrix acceptance remains open. Evidence: [FCS retirement](../validation/release-readiness-w1/fcs-retirement/acceptance.json).


## Installed toolkit0.1.7 table, texture and editor roots — 2026-10-07

Canonical SDK2c30fc559 is installed from the declared Git source and pinned in all21 lock references. Parent installed-package/metadata assertion and explicit14-file owner validation:261 passed/1expectedskip. Table Ctrl/Command selection modifiers reach string/numeric editors; real detector values and portable roundtrip are verified. PixelPainter now respects nested texture/font clipping while preserving UV/alpha/DPI. Actual Qt Help body was already clipped correctly; its apparent software overflow was diagnostic-renderer debt, not a product layout fix. Code-editor descriptions now use the existing translated tooltip path and actual hover rectangle.

Table/painter owned typing is clean. Fifteen inherited view_form declaration/inference findings are recorded unchanged without casts/suppressions; programme owner review remains open. Genuine narrow Help category packing is a separate application root. All recorded before/after PNGs were inspected by the parent. SDK source commits dd034d7/b92e9cb66/2c30fc559 are local; no provider/dependency or unrelated SDK/dialog/web changes. [Installed acceptance](../validation/release-readiness-w1/sdk-0.1.7/acceptance.json).


## Native Help controls stay reachable in small windows — 2026-10-07

Header actions and category filters now wrap using translated button widths; all sections remain reachable at600×400 and480×320. Full document text/live links are retained in a clipped scrollable child with stable identity, so moving the dialog preserves reading position. Footer space follows actual frame/font metrics, including2×DPI. Actual Qt body clipping was already correct; the separate SDK software texture clipping root is recorded in installed0.1.7. No guided-tour code or scientific/document text changed. Parent11 installed-SDK cases pass, scoped source/test typing andRuff clean, narrow/scroll/Outputs/DPI2 before-after images inspected. [Acceptance](../validation/release-readiness-w1/native-help/acceptance.json).


## Complete detector-definition JSON editing — 2026-10-07

The shared native detector editor restores the live Edit JSON action through a declared AutoForm code editor and Apply/Cancel modal. Existing portable definition validation and table projections run before committing; valid application preserves model/store/callback identity, preview data, last_used, unknown fields and calibration IDs unless explicitly edited. Invalid/read-only/busy/cancelled drafts leave the current definition unchanged. Apply is a working-definition change, not an implicit setup-file/MMFDB write.

Parent8 installed-SDK JSON tests pass; owner20 new/native cases and scoped source/test typing/Ruff pass. All5 measured before/after/modal/error/apply PNGs were inspected. The broader owner-page selection reports80 passes and one width720 gch-visibility failure; that responsive boundary is being repaired/verified with the full reference-calibration phase, not waived. Core source and foreign widget semantics are excluded from this focused commit. [Acceptance](../validation/release-readiness-w1/detector-json/acceptance.json).


## Independent native detector reference calibration — 2026-10-07

The shared detector row now reads an independent TTTR reference on a private definition and embeds the existing full native G-factor calculator. Named VV/VH writing, per-channel corrections/binning, raw-tail↔binned-tail coordinates, effective ps→ns timing and complete archival context are preserved. Loaded preview/timing stay unchanged; Preview G retains the explicit quick, unarchived route. Saved-tail headless and interactive routes archive through the canonical client and apply once only after valid IDs; prior mixing is retained unless a valid estimate or explicit manual override replaces it.

Actual pending-field hover commits the edit and starts computation; Apply queues rather than becoming disabled, waits for the completed result and publishes once. Readonly/error/cancel/context replacement, timing-only SET and changed fast-DAT handoffs refuse mutation. Parent drops delegate to the child during the reference lifetime and exact endpoints restore afterward; late reads dispose temporary resources without waking a closed host. Required imaging mixin close releases the child before the next MRO close. Nested Help/chooser Escape stays local.

Parent111 targeted runtime cases and967 available programme/feature guards pass (16expectedskips); five full controls/Batch/scrolled/Help/Guide scenes and independent host/nested-input pairs were inspected. Shifted BH fixture G1.32776/SD.456709 is distinct from the unshifted provider-clock G1.34785469696/SD.48512835796; neither is measured instrument calibration ground truth. Source typing adds no diagnostics (74before/74after); existing native declaration work remains registered W0. BID's untracked handwritten prototype stays on disk for W6f adoption, excluded from source;16 HEAD-backed factories and3 real family lifecycles are guarded without skips. [Acceptance](../validation/release-readiness-w1/detector-reference/acceptance.json).


## Native microtime histogram retirement — 2026-10-07

The public CLI/manifest and remaining lifetime panel now use the existing native AutoForm histogram app; wizard.py/UI and its old Qt reference are retired. Immutable measured arrays/fullsettings replace recomputing the deleted legacy widget. Five print-only scripts retire while the independent fortune assertion remains unchanged. The saved BID setup publisher synchronizes the editor before replacing the completed model; switching polarization merges/splits the current ordered routes and retains explicit timing/G/shifts/manual channels. Scientific model and package initializer bytes/modes remain unchanged.

The plugin supplies a synthetic PTU Demo (3000VV/1500VH,32ps micro/25ns macro clocks,4-bin/.128ns FWHM) and real Guide awaits Demo then Compute. Current native defaults/scientific outputs preserve provider timing; the headerless BH3.2958984375ps is not independent instrument calibration and explicit25ps is validation only. Three polarized measured exports match the legacy bytes. Unpolarized output corrects the extra-all-source-VH bug:135967selected/4096rows rather than319624/8192. All17 final images were inspected, including legacy-host and complete detector controls; paired docs and3realfigures accompany the source.

Parent112 targeted cases pass in three isolated normal-exit groups; scoped Ruff14/mypy6 are clean. The actual policy guard identified one stale Qt GUI allowance after entrypoint retirement; removing only that line makes all285 policy cases pass/16expectedskips, with other available guard files already green. No allowance or skip added. [Acceptance](../validation/release-readiness-w1/microtime-retirement/acceptance.json). W1 next is ordered Burst13, then Channel14 and shared Designer helper cleanup.


## Burst Selection legacy fallback retirement — 2026-10-07

The unused legacy GUI/assets and runtime selector are removed. Public BurstSelectionTool/wizard retain the implemented modern Qt tool; the production Burst Analysis hub still uses the existing native factory. Native model/backend/search and output contracts are unchanged. Frozen real m000/m001 runs retain198 bursts (71/127),353909 photons/45868 selected, active71×10 table, ten numeric-column hashes, settings and72 control IDs. All10 after scenes were inspected against preserved before evidence; the loaded legacy143-row BUR diagnostic is not a legacy search rerun. Prior shared JSON/Preview controls are added by their earlier unit; existing header elision/read-clock0 are qualified rather than claimed as new corrections.

Parent26 owning runtime cases and968 available guard/import cases pass (16expectedskips), scoped Ruff4/mypy2 clean. Current packaged instructions no longer recommend the deleted selector: four dated originals are archived in [history](../validation/release-readiness-w1/burst-selection-retirement/package-notes-history.zip), current reference paths remain and foreign verification formatting is preserved. Existing paired theory/workflow and one real figure accompany the source; canonical catalogue regeneration is byte-identical for the owned page. [Acceptance](../validation/release-readiness-w1/burst-selection-retirement/acceptance.json). Next is Channel14 and Designerhelpers; modern Qt surface retirement stays with W9.

## Where to pick this up — detector host retirement, 2026-10-08

The retained Qt wizard shell hosts one real native detector surface; old
Designer page/JSON/shift forms are retired after independent control/data and
caller acceptance. Portable model, flags, full export/Finish and ownership
lifecycle are the authority, not old combo/table fields. Parent80 final cases
and959availableguards/16skips pass; real normal/narrow/enclosing/Optical and
visible legacy/native pairs inspected. [Receipt](../validation/release-readiness-w1/channel-definition-retirement/acceptance.json).
Next W1 unit removes unused Designer helper/cache/source-jump branches while
retaining actual drag-file injection and explicit main gui.ui packaging. The
main shell remains W9, and the separate Burst MLE model feature remains active.

### Designer helper cleanup complete — 2026-10-08

The retired UI loader/cache/source-path branches are removed. Keep native specs
and Python source resolution; do not restore obsolete UI metadata. The existing
drag injector body is unchanged and actual MIME/drop behavior is regression
tested. Main shell packaging is explicit, deferred to W9.
[Receipt](../validation/release-readiness-w1/designer-helper-retirement/acceptance.json).
Next active acceptance is the requested Burst MLE model feature; W0 owns the
missing bundle guard/inherited typing before full programme closure.

## Declared initial native geometry

The shared `window_size(spec, default)` parser reads bounded width/height
metadata from loaded view specs. The schema requires both integer fields
120–8192 and rejects typos. Shared ToolHub/CalculatorHub defaults 1100×720, FRET
calculator 640×480, TTTRimagebrowser 1200×800; SetupStep uses the same parser.
Saved geometry overrides the default through attach_native_state. emtk native
and Qt hosts read window_size only; responsive ALWAYS regions are retained.
Ten real-data before/after pairs preserve all controls and exact computed
results; eight same-size pairs are byte-identical. Baselines were first taken
before edits, then reconstructed from frozen source after a concurrent capture
rerun overwrote files; both phases and SDK revisions are recorded.

Remaining native factories still need explicit primary-spec declarations and
real render acceptance. See [active job](../validation/release-readiness-w6g/current-job.md)
and native-window-map.json; do not treat geometry-only declarations as new
AutoForm control coverage.

Shared imaging/trajectory shells now read raw primary-spec geometry before
prepare_spec/sectionflattening. Drift/rotate declarations are explicit 1100×720;
remaining 16specs use fallback and still require individual metadata/render
review. Exact 10 imaging/8 trajectory route map is archived in W6g evidence.
Real drift 12-frame known shifts and trajectory 8 frames×5235atoms with zero
coordinate error are unchanged across full/small pairs. Inherited narrow
projection label overlap was fixed in emtk 0df138cd using final measured bounds,
without changing ticks/grid/data. Six trajectory typing errors and five stale
strict picker/wheel xfails were also corrected.

The remaining 16 shared imaging/trajectory primary specs now declare1100×720
and remove 39 missing tooltip contracts. Scientific arrays and control inventories
match actual before/after scenes. Qt signed UVs now render scientific histograms
through emtk 6e685bb8; recorder visible-text bounds are in b38bb892. The installed
pin includes both fixes. Existing text tuple shapes remain intact, and layout
checks use active clips without hiding overflow at alignment boxes.

Initial imperative audit reads 1,750 committed Python files and measures 1,202 bare
visible literals (before alias refinement); the ledger is an open worklist,
not an allowance or completed i18n claim. Tooltips now have 1,104 open findings.
See the [active acceptance](../validation/release-readiness-w6g/current-job.md).

Seven remaining calculators now consume explicit 640×480 defaults and preserve
computed state. Compact FRET uses the SDK public first-viewport declaration,
with saved custom layouts and Reset precedence; text Enter/Escape and fractional
scrolling defects are fixed in emtk. The actual RICS Qt wrapper also respects
the declared default before its saved-geometry restoration.

Committed-only help enrollment prevents foreign prototype claims. The native
tour checker performs real example clicks and records pending/unwired waits
without forging satisfaction; its whole-plugin interaction gate remains open.
The calculator slice removes 22 more tooltip gaps (1,082 remain) and36 imperative
literals (1,167 remain). Source/science/PNG receipts are in W6g validation.

Eleven existing demos expose the settings/demos/plugin cache through DEMO,
demo_folder and make_demo, returning a primary Path. Actual member hashes and
effective parameters validate reuse; overwrite and failed-write retention are
checked. Each first example tour step awaits the real load_example control;
shared hub page routing reveals that control without pressing it. The SDK and
ChiSurf tour title reserve a separate drag row. Existing scientific results
remain exact; the reader-owner repair restores all Flow frames and photons.
[Demo acceptance](../validation/release-readiness-w6g/demo-contracts-acceptance.json)
records the qualified flow bias and remaining broader uniformity gates.

Five more ordinary primary specs now declare host geometry while saved user
sizes retain precedence. Browser uses1200×800; Selection, AI Settings, FCS Preset
and Intensity Trace use1100×720. Scientific/configuration/control parity is
verified in actual scratch Qt captures. Result-selector rows measure visible
labels with hide_double_hash=True, matching real button rectangles; hidden
identities no longer cause premature wrapping. Existing selectors wrap without
changing callbacks; a concise FRET title preserves its ##fretdist identity.
[Acceptance and exact evidence](../validation/release-readiness-w6g/ordinary-window-acceptance.json)
qualifies offscreen screen clamping and remaining74declarations.

Photon Table/LUT Tools and Trace Browser consume explicit primary geometry,
retaining saved preferences and exact event/trace/calibration values. LUT's
native Normalize caption fits the initial clamped host. Both active native and
legacy declared descriptions explain threshold normalization and masked bins;
changing that setting can alter correction construction, not just plotted
amplitudes. Existing algorithms/defaults are retained. Public setup setters
repair stale parity fixtures without restoring a private alias.
[Acceptance](../validation/release-readiness-w6g/photon-viewer-acceptance.json)
records measured arrays, real tooltip renders and remaining71declarations.

The external ndX owner now reads and packages a1200×800 primary declaration.
Its standalone launchers deliver that default instead of forcing900×600;
explicit CLI sizes and existing ChiSurf saved geometry retain precedence.
Source tables, axes, histograms/marginals and controls remain exact across real
before/after scenes. The owner adds no new persistence subsystem or loader.
Individual PNG inspection avoids a multi-image presentation artifact mistaken
for a black canvas. [Owner acceptance](../validation/release-readiness-w6g/ndx-window-acceptance.json)
records the exact wheel/source identities and inherited static diagnostics.

Three TTTR base apps now declare1100×720 initial geometry while preserving
saved host preferences, inputs and computed results. Time Windows uses a new
host-only primary declaration, not a standalone-wrapper-only hint. Real detector
scrolling proves late row/actions remain reachable; instrumented busy states
are distinguished from naturally fast completion. The stale test painter now
matches SDK stroke width semantics with its original counting/assertions.
[Acceptance](../validation/release-readiness-w6g/tttr-window-acceptance.json)
records exact physical arrays/rates/windowrows and remaining FPS/card work.

The FPS JSON card has its own1100×720 host declaration and preserves saved
custom dimensions without changing other CardShell siblings. Actual AV
computation, molecular rendering, point clouds/means/grid spacing and complete
position/restraint/configuration data prove real before/after parity; a
load-onlyfixture orskippedrenderer is not acceptance. [Exactcardacceptance](../validation/release-readiness-w6g/fps-card-window-acceptance.json)
records tested geometry, fixture identity and scoped static limits.

A real spectral-window baseline exposed a provider-call mismatch in the owning
lifetime-FCS simulator: positive uncorrelated background lacked a decay pattern,
so the engine generated prompt scatter at microtime zero. The caller now declares
uniform calibrated bins; zero-background config/signal arrays are exact, while
positive-background seeded outputs legitimately change. [Physical acceptance](../validation/release-readiness-w6g/lfcs-background-acceptance.json)
records actual native distribution/clock/provider checks. GUI geometry acceptance
must be recaptured under this corrected caller, not force old scatter hashes.

Three spectraltools declare1100×720 andpreserve savedhostgeometry andreal
computedcontrols/data. UniformTCSPCbackground fixes the lifetime-FCS caller's
physicalcontract; afterbaseline/reference recapture is explicit. OptionalMEM
completionstatus reports actualmainanalysis/failure; stochasticmodeltest
assumptions usepairedspecies andobjective/gradient/convergence evidence rather
than fixedcomponentorder/roundedtext orunnormalizedamplitudesum. [Spectralacceptance](../validation/release-readiness-w6g/spectral-window-acceptance.json)
records independentproviderdiagnostics, realPNG andscopedstaticlimits.

Calibration and PSF composite hosts now read declared1100×720 geometry before
preparing/slicing their controls. Savedcustomdimensions retain precedence;
actualphotons/calibrationApply andnoisybeadGaussian measurements are unchanged.
ConciseemptyIRFcaption fits the initialhost, while metric-aware testpainter
coverage retains actualclip/occlusion data. [Pairacceptance](../validation/release-readiness-w6g/imaging-window-acceptance.json)
records scientifictruth versus four detectedregions, ownership residue and
headlessbefore/after/resize/reopen evidence.

Regionfilepath lifetime fitting andpreview now share declaredproducer scanner
metadata delivery. Source-onlyproducer headers expose correct physical clocks,
independently ofpreexistingworkingtree edits. Pythonimage counts use canonical
owneru32 anddeferredchannel layout isaccurate; actualdataGUIacceptance must be
recaptured afterthese scientificroots instead ofpreserving wrappedcounts. [Rootacceptance](../validation/release-readiness-w6g/region-root-acceptance.json)
records realbroken/explicitreference physics and installedtest/arm64 identities.

Spot Finder and Region MLE now declare1100×720 on their raw primary specs. Region filter/selector reserve measured caption widths; saved dimensions retain precedence. Actual corrected wide-count data and all control/scientific identities match before/after. [Pair acceptance](../validation/release-readiness-w6g/spot-region-window-acceptance.json) qualifies frozen-dipole versus ensemble polarization residuals and records actual arm64 screenshots, original/owned sources and commands. Reopening restores configuration; Preview/Run rebuild computed results.

CLSM Draw and Generator now read1100×720 from rawprimary specs and expose their existing manualsettings methods through native preference hooks. Saved dimensions/physicalparameters/namedmasks retain precedence. [Pairacceptance](../validation/release-readiness-w6g/clsm-pair-window-acceptance.json) records realarm64data/map/pointer/export/persistence/tooltip proof; mixingtest/nativepainters duringheldgestures is an invalid physical baseline. No common painter change was needed.

Audifier andMicrotimeShifter read1100×720 beforeprocessingrawprimaryspecs. Shifterunknown sampleproxyattributes no longerparseunopenedmetadata; scalarpaths/identities use stringwidgets, whilemultilineprose/sequence forms scrollabovefixedactions. [Pairacceptance](../validation/release-readiness-w6g/audifier-shifter-window-acceptance.json) recordsactualstream/audio/shifts/export/nativepreferences/PNG/table-scroll proof, preservedforeignhunks andallfourREDtestclosures.

ALEXCreator andmanualFileTools hostread1100×720 primarydeclarations withsavedgeometryretained. Splitterprogress/status staysinsideexistingIOdock; InspectorDatausesdeclared130pxminimum/horizontalnavigation forwideburstschemas. [Pairacceptance](../validation/release-readiness-w6g/alex-filetools-window-acceptance.json) recordsactual7childscientificoutputs,propertyfactorytypingrepair,realnativePNG/readability, exactownedsource andMFDpersistencequalification. Foreignconcept/modelportnotes remainunadopted.

PTOInspector andChiMOLhost read1200×800 primarydeclarations andretainstoredviewer geometry. PTOcontainer/data/curve/provenance readback isbyte/numerically unchanged; Chimolcoordinates/atom/secondary/state andactualrenderedframes remainexact. [Vieweracceptance](../validation/release-readiness-w6g/pto-chimol-window-acceptance.json) recordsrealstandalonebeforeafter/nativecontrol/tab/hash/test evidence andlazytyping/persistence/provider qualifications, withforeignhunks excluded.

Burst Browser’s native presentation now uses the existing declarative DataTable
for the paged37-column measurement vocabulary, with typed numeric sort keys,
original source row selection and horizontal navigation. The initial1200×800
primary declaration retains saved geometry/dock precedence. E/S sliders include
actual measured/current limits beyond[0,1], without altering scientific masks.
[Verified uncommitted acceptance](../validation/release-readiness-w6g/burst-browser-window-acceptance.json)
records real data, before/after inventory, static/targeted checks, paired docs and
permissions that currently prevent canonical Git/board publication. No SDK sorting
workaround, new dependency or scientific algorithm was introduced.

The FCS Merger and Filter Calculator candidates read1100×720 from their raw
primaries, with saved host geometry taking precedence. Filter plots bound legend
captions to160logical pixels and show the full original scientific identity on
native hover; curve visibility remains stable across resize. Actual736×552 host
clamping and control scrolling are measured separately from authored dimensions.
[Pair acceptance](../validation/release-readiness-w6g/fcs-pair-window-acceptance.json)
records exact measured-repeat/filter/Project/export parity, correct canonical test
isolation, poor-reference-fit and native-persistence qualifications. Canonical
publication is pending read-only Git/board permissions; full manual tour gates
remain part of W6.

IRF Estimator and Synthetic Decay candidates now consume1100×720 rawprimary
metadata before their layout/controls adaptations. The native generator stacks
Mode options to preserve full captions on736×552; actual scroll and per-option
scientific tooltips are verified. Its owner text loader retains columns for a
one-row time/count IRF rather than interleaving the time value as a count.
[Decay pair acceptance](../validation/release-readiness-w6g/decay-pair-window-acceptance.json)
records common corrected-core before/after proof, unchanged normal measuredIRF,
raw fresh-UUID provenance, real exports/fits/renderings and physical/nativestate
limits. Canonical publication remains pending current read-only permissions.

LLTF and MaxEnt candidates consume1100×720 rawprimaries beforepanel adaptation.
LLTF surfacesactualoptimizerstatus/iteration-limit warnings throughGUI/CLI/JSON
while preservingnumericalfits; its nested-selectionowner nowretainsfixed/seed/
exactembedding semantics. MEMrawamplitude/defaultuniform labels andFRET/sampling
checkbox layout aretruthful/reachable. Its samplingowner reconstructsSDKscaled
entropy/objective andpriorconvention, retains countunits andhonorspartialsteps.
[Lifetimepair acceptance](../validation/release-readiness-w6g/lifetime-pair-window-acceptance.json)
records realcommonobjective/worker/export/GUIproof, stochastic/method/persistence
limits andexplicitinheritedtyping debt. Canonicalpublication remainspermission-
blocked; this doesnotmarktheprogrammecomplete.

Burst MLE and Accurate FRET candidates consume1100×720 rawprimary metadata.
MLEerror/readiness prose wraps; model choices remainthe shippedFit23/24/25.
AccuratelegacyBUR input useslogicalrows/companions, unassignedrecords carry−3,
andthefactor table usesdeclaredidentification/prior provenance. Actualnarrow
long-cell text remainsreachablethroughnativehover. [Pair acceptance](../validation/release-readiness-w6g/burst-calibration-window-acceptance.json)
separates theseverifiedsurfaces fromOS-IPC batchvalidation andread-onlySDKReport/
Gitpublication gates; nofullprogrammecompletionclaim.

BVA now consumes a1100×720 host-only primary declaration; existing controls
andresponsiveviewport sizing remain. Its owner reader discovers BUR andmatching
ending4 companion files beforetextdecode, preservingbinaryPTOcache andallrow/
sentinel identities. [Acceptance](../validation/release-readiness-w6g/bva-window-acceptance.json)
records actual152burst/SPCvariance/static/profile/nativeexport/companionparity,
independentphotonreference,32PNGinspection, typedoptionalcallbacks andexplicit
settings/type/publication limits. This isnot a fullAutoFormcontrolmigration.

## Reachable section help — 2026-10-09

emtk e73a68973 routes descriptions from existing panel/tab/custom-table captions.
A table uses translated section help only when no specific header, row or elided
cell help applies, with a stable owner. Untitled or titles=False panels have no
caption and remain host-header work. Authored metadata is not proof of reachable
help: attach to the actual submitted item and preserve more specific explanations.
Source and installed-provider hover/paint, pointer departure, translation and
unchanged default/narrow geometry are accepted. No controls/layout or scientific
algorithms changed; no metadata recapture. Exact source/provider identities and
accepted evidence are in [section-help acceptance](../validation/release-readiness-w6g/emtk-section-help-acceptance.json).
W0a and the production literal/ownership guards are complete. A0 keeps family
repairs separate and aggregate release gates open.


## Help on suppressed-title hosts — 2026-10-09

The shared imaging host, AI Settings and Photon Table now pass existing outer
panel descriptions into dock-window tooltip metadata. The toolkit routes this
help from floating title items as well as docked tabs, through translation and
normal delay; close/collapse explanations retain priority. No controls or layout
rows were added. Populated imaging/photon outputs, AI settings, unhovered paint
and geometry match at default/narrow widths; actual hover/paint/departure prove
reachability. The fourteen unchanged literal occurrences displaced by insertion
have paired key-relocation evidence; the 1,155-literal denominator is unchanged.

This closes the bounded shared host-help mechanism. Other hosts must bind their
own outer description; missing family-authored help remains in the exact owner
ledger, including four ALEX panels and three calibration tables. Aggregate W6
still requires those repairs and empty allowances. [Host acceptance](../validation/release-readiness-w6g/host-help-acceptance.json).


## Core host declaration completion — 2026-10-09

The20retained core records now read primary numeric host metadata. Actual defaults
remain1200×800 exceptHelp800×600; the inventory's1100×720 estimates are not actual
host defaults. Existing root loaders are reused, GlobalView binds in its surface,
HMM retains root metadata before panels, and MMFDB keeps its shell/root distinct
from entity includes. Saved dimensions and preferences retain priority.

Exact owned-source/primary-JSON factory tests verify default and altered metadata,
fresh binding and saved resize. Geometry and model/control workflow code are
unchanged; A0 requires metadata checks without recapture. The281unchanged literal
occurrences shifted by insertion have paired source/text key-relocation receipts;
no allowance or family denominator grows. All116declared/shared window readers
are covered, but that is not whole-plugin scientific/account/service acceptance.
Other W6f and aggregate release obligations remain open.
[Acceptance](../validation/release-readiness-w6f/core-window-acceptance.json).

## Nested disabled input and native tour text — 2026-10-09

Native Help exposed a toolkit defect: a nested enabled control cleared a
parent disabled scope. The toolkit now inherits parent disablement while retaining
its low-level flag semantics, delayed tooltips and scope restoration. Fifty
producer tests and real game default-window regressions verify the installed
`3416806a` provider. The game action row uses AutoForm, not hand-drawn buttons.
Shared tour authored text and navigation pass through translation before card
measurement; IDs and complete English paint remain unchanged. The game chrome
acceptance retains exact source and interaction evidence. Concurrent port guard
drift remains a separate finite prerequisite; no baseline is expanded.

## New committed UI guard reconciliation — 2026-10-10

A finite prerequisite closes 17 new tooltip sites and 144 new direct literals
introduced by concurrent native ports. The shared typed-number control explains
its type, commit behavior and allowed bounds; callers can supply domain help.
Acquisition, About, burst, pair-selection and header-editor metadata retain the
original scientific logic, options, units, identities and geometry. Source AST
normalization and actual translated hover/action tests prove this boundary.

The accepted production baseline shrinks from1077 to1023 tooltips and from1151
to1148 literals.638 literal-key relocations are paired by source scope, argument
and complete call structure; six hidden-ID changes retain visible labels. Three
H2MM tuple descriptions are genuinely translated rather than silently dropped
from measurement. No new or stale candidate findings remain. These are shrinking
existing allowances, not aggregate UI completion; family owners still owe zero.

## About identity and deliberate clipboard action — 2026-10-10

The native About window preserves its real logo, identity text, Close and380×420
default while consuming a primary view declaration. Its AutoForm row provides
Help, Copy details, Guide and Close; conditional status is a declared info
section. The tour awaits Help→successfulCopy→Close. A failed clipboard write
remains pending and visible; the terminal Close acknowledges and stops the tour
before requesting host closure. No clipboard operation occurs on opening.
Host-aware clipboard calls are intercepted in tests, preserving user contents.
Six locales, two widths, actual modal/closed boundaries and Qt-free construction
pass. Root inspected all before/default/narrow images;98/pass retains geometry
and old Close. [Acceptance](../validation/release-readiness-w6f/about-help-acceptance.json).
