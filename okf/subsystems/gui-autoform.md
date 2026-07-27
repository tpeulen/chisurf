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
`style:"table"` renders the components as one **paired** `QTableView` — each
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
don't force horizontal scrolling in a narrow dock. The
`CollapsibleBox` header gained `add_header_widget` to host such per-section
controls with no extra vertical space), `help` (a `?` modal button),
`progress` (the one inline progress bar — see below), and
`wizard`/`info`/`embed`.

# Every form is restorable from JSON

A view spec names, per control, the model attribute it binds to. That is already
a complete description of where a form's state lives, so reading it out and
putting it back needs no per-plugin code —
`chisurf/gui/autoform/state.py` does it once, and `AutoForm` exposes
`state()`, `apply_state()`, `save_state(path)` and `load_state(path)`.

This is not a convenience feature. **A tool whose settings cannot be written
down is a tool whose results cannot be reproduced**: an analysis folder can hold
the numbers that came out while holding no record of what was asked for.
Restorability belongs to the form framework, not to whichever plugin author
thought of it. It currently covers **83 of the 92 shipped view specs — 690
controls** — with no work per plugin; the remainder are built from `custom`
sections whose widgets own their own values.

Three rules the implementation follows, each of which decides whether saved
settings are worth keeping:

* **Action-bound controls are not state.** A section with `set_action` is a
  command; "restoring" one would re-run the analysis rather than restore a
  setting.
* **Applying is lenient.** Unknown keys and rejected values are collected into a
  `StateResult` rather than raised, so a file written by an older version
  restores the fields it still shares — and the caller can tell the user exactly
  what did not survive. A restore that fails whole on one dropped field is a
  restore nobody keeps files for.
* **Values are coerced JSON-safe.** numpy scalars and arrays are everywhere in
  these models, and a settings file that cannot be written because of one is
  worse than one that stores it as a list.

A guardrail asserts that no shipped spec binds the same attribute twice, which
would make a restore ambiguous.

The burst-analysis folder is the first consumer: `Info/analysis.json` carries
the settings a run used and optionally a form state, and
`burst_manifest.restore_form()` puts a tool back where it was. `view_state` and
`settings` are stored separately on purpose — the first restores *the form* key
for key, the second records what the analysis actually used, and conflating them
when they disagree would be silently wrong.

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
visual dataflow toolkit — see [Orange3 mining](/references/orange3-mining.md).

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
[Orange3 mining](/references/orange3-mining.md).

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
`DEFAULT_POLICY` (rich, Python-like, bare names) and `NDX_POLICY` (ndXplorer
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
(`{attr, names, call, policy}`). ndXplorer's equation editor delegates to this
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
name, so a collision costs at most the constant, never the data. The parse-model
formula widget
(`gui/widgets/models/parse/widget.py::ParseFormulaWidget`, shared by the TCSPC,
FCS and PCF parse models) hosts an `ExpressionInput` in place of its raw text box
— the box is kept hidden as the backing store the rest of the widget reads — so a
mistyped or unsafe formula is caught with a clear message instead of failing at
`eval`. (ParseModel's own evaluation is unchanged; the engine drives editing and
validation, not model math.)

When touching GUI code, prefer porting hand-built widgets to AutoForm + a
JSON view scheme.

## Runtime `.ui` forms are prototyping-only (migration target: removal)

The ~43 Qt Designer `.ui` files still loaded at runtime via `uic.loadUi`
(`chisurf/gui/decorators.py:_compiled_ui_class`) are a **prototyping-era carry-over,
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
  widget tooltip, [[viewspec-description-tooltip]]); in hand-built widgets call
  `setToolTip`. App-wide tooltip folding ([`chisurf/gui/tooltip.py`](/workflows/build-and-env.md))
  keeps long tooltips readable, so descriptions can be as complete as needed.
  When a field section (`value`/`choice`/`toggle`) carries no explicit
  `description`, `_BoundControlMixin._effective_description`
  (`sections/builtin.py`) falls back to the shared parameter registry, keying
  on the bound `attr` (scoped by the target group's class) via
  `chisurf.core.settings.describe_parameter` — so any field bound to a
  registered parameter gets inline help for free, matching the description its
  fitting widget already shows (see [[parameters]]).
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

# Citations

[1] [ChiSurf architecture doc](/references/architecture-doc.md)
