---
type: Reference
title: Orange3 mining — dataflow, widget-framework and testing patterns for chisurf
description: Second-pass survey of the Orange3 checkout beyond the data-model lessons already recorded — write-locked data, the background-task mixin, declared widget messages, contract test mixins, VizRank, the report system, domain-context settings and the safe-expression layer — ranked against what chisurf has today and mapped to PRDs.
tags: [reference, architecture, gui, testing, dataflow, roadmap]
timestamp: '2026-07-27T00:00:00Z'
---

# Orange3 mining — dataflow, widget-framework and testing patterns

Orange3 (Bioinformatics Lab, University of Ljubljana; GPL-3.0) is a visual
dataflow environment for data mining: a canvas of typed nodes ("widgets") that
pass tables along typed links. ChiSurf keeps a full checkout at
`junk/orange3/`. Its dataflow core (`orangecanvas`, `orangewidget`) lives in two
separate packages that are **not** in this checkout; everything cited below is
in the `orange3` tree itself.

An earlier pass already mined the **data model and provenance** layer — compute
values as replayable lineage, typed ports, transformer-as-value, the typed
schema object, the metas annotation channel, data-only settings migration, and
workflows-as-documents. Those are recorded in
[Node/workflow-toolkit lessons](orange3-lessons.md) and folded into PRD-11/16/
19/21/22/25/26/27; they are **not** repeated here.

This document is the second pass: what else is worth harvesting once the data
model is set aside — the **widget framework, the concurrency and messaging
contracts, the testing harness, the ranking/report/annotation conventions, and
the presentation layer**. Reuse policy follows the
[PAM port](fcs-pam-port.md) and [QuickFit3 mining](quickfit3-mining.md)
precedent: patterns and algorithms are documented prior art, reimplemented
independently in ChiSurf's own code with attribution, never verbatim GPL copies.

What was **actually adopted** — and how each idea was translated, including
where ChiSurf deliberately departs from the original — is recorded separately
in [What ChiSurf took from Orange3](orange3-adopted.md). This document stays
the survey and the backlog.

## Path index

| Orange3 path | What it is | ChiSurf equivalent | Verdict | Value |
|---|---|---|---|---|
| `Orange/data/table.py:489,654-700` | Write-locked arrays; explicit `unlocked()` context to mutate | ✅ **adopted** — `NCurve`/`DataCurve` lock their sample arrays | **DONE** — see [data model](/subsystems/data-model.md) | **5** |
| `Orange/widgets/utils/concurrent.py:387,453,558` | `TaskState` / `ConcurrentMixin` / `ConcurrentWidgetMixin` — cancel, partial results, auto-wired progress | ✅ **adopted** — `chisurf/gui/task.py` on the `ChiSurfProgress` seam | **DONE** — see [GUI/AutoForm](/subsystems/gui-autoform.md) | **5** |
| `Orange/widgets/tests/base.py:46,248,608,686` | Widget-contract test mixins + pathological-dataset battery + `ParameterMapping` | static manifest contract tests only | **CLEAR-GAP** — behavioural contract tests over 104 plugins | **5** |
| `Orange/widgets/visualize/utils/__init__.py:40` | VizRank — score-ranked candidate views computed in the background | ✅ **adopted** — ndX *Find informative projections* (`ndxplorer/analysis/vizrank.py`, `ui/vizrank_panel.py`) | **DONE** — see [adopted §4](orange3-adopted.md) | **5** |
| `orangewidget.widget.Msg` + `class Error/Warning/Information` | Declared, named, non-modal, testable widget messages | ✅ **adopted** — `chisurf/gui/widgets/messages.py` | **DONE** — see [GUI/AutoForm](/subsystems/gui-autoform.md) | **4** |
| `Orange/widgets/report/` (`report.py:14`, `owreport.py`) | Every node contributes `send_report()`; one aggregated HTML/PDF report | none | **CLEAR-GAP** — cross-plugin analysis report | **4** |
| `Orange/widgets/settings.py:65,312` | `DomainContextHandler` — settings matched to the *data*, not just the widget | per-plugin `state_namespace` only | **CLEAR-GAP** — per-dataset setting recall | **4** |
| `Orange/widgets/data/owfeatureconstructor.py:76,370,947` | `validate_exp` (AST whitelist), `freevars` (deps), `make_variable(compute_value)` | equation editor / calculator / parameter-transform, unvalidated | **Partial-gap** — safety + free dependency tracking | **4** |
| `Orange/widgets/utils/annotated_data.py:9,63,89` | "Selected Data" + full data with a `Selected`/`Group` column; `get_unique_names` | `RegionCollection`, burst selections — no shared convention | **Partial-gap** — output convention for selections | **4** |
| `Orange/util.py:568` | `Reprable` — auto `__repr__` that is a valid constructor call | hand-written macro recording | **Partial-gap** — provenance/macro strings for free | **3.5** |
| `orangewidget.utils.widgetpreview.WidgetPreview` | One-line standalone run of a single widget with sample data | ad-hoc screenshot scripts per tool | **CLEAR-GAP** — makes the screenshot rule one line | **3.5** |
| `Orange/preprocess/preprocess.py:24,546` + `widgets/data/owpreprocess.py:1087` | Preprocessors as composable values; a flow-list editor node emitting a `PreprocessorList` | PRD-16 transformer contract (right shape, no chain UI) | **Partial-gap** | **3.5** |
| `Orange/widgets/utils/colorpalettes.py:162,477` | Named discrete/continuous/binned palettes, colour-blind-safe defaults, Glasbey overflow | ad-hoc colours per plot | **Partial-gap** — chiplot palette layer | **3.5** |
| `Orange/widgets/utils/state_summary.py` + `summarize` singledispatch | Per-payload-type short/long summaries in the status bar and link tooltips | none | **Partial-gap** | **3** |
| `Input(..., replaces=[...])`, `keywords=`, `priority=`, `settings_version` + `migrate_settings` | Rename compatibility, launcher search synonyms, ordering, data-only state migration | manifest has none of these | **Partial-gap** — cheap manifest additions | **3** |
| `Orange/widgets/data/owdatasets.py:38-44`, `i18n/README.md`, `utils/localization` | Never persist translated strings; per-string translate/verbatim triage; `pl()` plurals | PRD-63 `.ts` catalogues | **Partial-gap** — two concrete i18n rules | **3** |
| `Orange/widgets/utils/save/owsavebase.py:16,178` | One save-widget base: filters, auto-save, paths relative to the saved workflow | per-plugin save code | **Partial-gap** | **3** |
| `Orange/canvas/workflows/*.ows` | Numbered example workflows surfaced in a Welcome/Examples screen | `okf/usecases/`, boarding wizard | **Partial-gap** — ship runnable examples | **3** |
| `orangewidget.utils.matplotlib_export` (`scatterplot_code`, `scene_code`) | "Copy this plot as matplotlib code" | none | **Partial-gap** — publication figures from a GUI plot | **3** |
| `widgets/data/owgroupby.py`, `owpivot.py`, `owmelt.py`, `owtranspose.py`, `owaggregatecolumns.py` | Table reshaping as first-class operations | chitable (PRD-66) — view-side only | **Partial-gap** | **3** |
| `widgets/visualize/owviolinplot.py`, `owheatmap.py`, `owdistributions.py`, `owsilhouetteplot.py` | Violin, clustered heat map with dendrogram, fitted-distribution overlay | chiplot has none of these | **Partial-gap** — plot-type gaps | **3** |
| `widgets/data/owcorrelations.py` | VizRank applied to correlation — most-correlated pairs, ranked | ✅ **adopted** — ndX ranking's Pearson/Spearman score | **DONE** — see [adopted §4](orange3-adopted.md) | **3** |
| `Orange/widgets/utils/domaineditor.py` + `data/owcsvimport.py` | Inline column name/type/role editor; per-file remembered import options | staging + readers | **Partial-gap** | **2.5** |
| `Orange/misc/cache.py:6,27` | `single_cache`, `memoize_method` (no `self` reference leak) | `functools.lru_cache` on methods in places | **Partial-gap** — a real leak class | **2.5** |
| `Orange/misc/environ.py` | Config-file-driven data/cache/settings directories | `chisurf/core/settings/` | Low-priority | 2 |
| `Orange/widgets/data/owcreateinstance.py` | Build a synthetic instance with sliders — "what-if" input | simulation plugins | Low-priority | 2 |
| `Orange/widgets/data/owdatasets.py` | Curated remote dataset browser with local cache | MMFDB dataset browser (PRD-10) | Low-priority — the caching UX is the lesson | 2 |
| `Orange/clustering/`, `Orange/projection/`, `Orange/distance/` | k-means, DBSCAN, Louvain, hierarchical, SOM, t-SNE, MDS, PCA, CUR | scikit-learn + hdbscan already shipped | Already-covered (thin sklearn wrappers) | 1 |
| `Orange/classification/`, `regression/`, `ensembles/`, `modelling/`, `evaluation/` | Supervised ML + scoring | — | **Out-of-scope** — ChiSurf's inference is physical-model fitting | 1 |
| `Orange/data/sql/`, `Orange/misc/server_embedder.py` | SQL-backed tables, remote embedding service | MMFDB | Out-of-scope | 1 |
| `Orange/widgets/visualize/owpythagorastree.py`, `ownomogram.py`, `owruleviewer.py` | Classifier visualizations | — | Out-of-scope | 1 |

## Tier 1 — the five worth doing

### 1. Write-locked data: mutation is opt-in and auditable

The single hardest problem in a dataflow graph is that a node hands a value to
three downstream nodes and one of them mutates it. Orange solves it by making
the arrays **read-only by default**: `Table` locks `X`, `Y`, `metas` and `W`,
every write path goes through `_check_unlocked` (`Orange/data/table.py:489`),
and a caller who genuinely needs to write must say so in a scoped context
manager (`table.py:675`):

```python
with table.unlocked(table.metas):
    table[:, var] = column_data
```

`unlocked()` additionally **refuses** to unlock a part that is a view into
another table — mutating it would corrupt the source — and a separate
`unlocked_reference()` (`table.py:654`) exists for the deliberate,
caller-asserts-safety case. The distinction between "I may write to my own
buffer" and "I am about to write through a view into someone else's" is made
explicit rather than left to reviewer vigilance.

**ChiSurf had no equivalent**: `chisurf/core/data.py` never called `setflags`,
so every dataset array passed between fits, plugins and node-editor nodes was
writable by whoever held a reference. The failure mode is silent — downstream
results change because an unrelated tool normalized in place.

**✅ Adopted.** `NCurve` declares the per-sample arrays it owns in
`array_attributes` and locks them in `__setattr__`, so a future assignment
cannot forget; `DataCurve` extends the tuple with `ex`/`ey`/`mask`;
`unlocked(*names)` is the scoped escape hatch, nesting, re-locking after an
exception and refusing a view into another array exactly as the reference does.
Full description in the [data model](/subsystems/data-model.md) concept. The
invariant now holds ahead of [PRD-22](/prds/prd-22.md) (pipeline engine) and
[PRD-29](/prds/prd-29.md) (node-graph canvas) — a visual pipeline without it
would produce irreproducible results that nobody can trace.

### 2. One background-task contract with cancel and partial results

`Orange/widgets/utils/concurrent.py` is the most directly transplantable file
in the tree. `TaskState` (`:387`) is a `QObject` that a worker function receives
as its last argument and uses to push progress, status text and **partial
results** back to the GUI thread over queued connections, and to poll
`is_interruption_requested()`. `ConcurrentMixin` (`:453`) gives the caller four
methods — `start(task, *args)`, `on_partial_result`, `on_done`, `on_exception` —
and handles everything else:

* starting a task **cancels the previous one** (no double-run races),
* signals are disconnected before the old task is dropped, so a late result from
  a cancelled run cannot reach the widget,
* `ConcurrentWidgetMixin` (`:558`) additionally wires progress bar, status
  message and the "invalidated" (greyed/marked) visual state automatically,
* an assertion **forbids starting a new task from `on_done`/`on_exception`**,
  which is the standard way these designs deadlock,
* `set_progress_value` only emits when the value moved by ≥0.1, so a tight loop
  does not flood the event queue.

Partial results are the feature worth stealing beyond the plumbing: a long
computation streams intermediate state and the plot fills in progressively
instead of freezing then jumping.

**ChiSurf had** `ChiSurfProgress` and the AutoForm `progress` section for
*display*, but the execution side was ad-hoc — `ThreadPoolExecutor`/`QThreadPool`
in three unrelated places with no shared cancel or partial-result contract.

**✅ Adopted**, and cheaply, because the display half was already unified: the
execution half went *on top of* the existing seam rather than beside it.
`chisurf/gui/task.py` adds `run_in_background` (aliased `ChiSurfProgress.run`)
with the same clauses — cancel, streamed partial results, auto-wired progress,
previous run superseded, no restart from a completion callback — and all four
existing display backends keep working unchanged, so call sites migrate one at a
time. Two departures from the reference, both because ChiSurf is not
canvas-only: with no `QApplication` the work runs **inline**, so a CLI or
headless test exercises the real call site; and a standalone tool window renders
in its own status bar rather than a modal, which would take back what the
threading bought. Fits [PRD-23](/prds/prd-23.md) (thin widgets). Still open: the
remaining ad-hoc threading sites (fitting, FRET docking, H2MM, staged loading)
have not been migrated — each has its own cancellation story to unpick.

### 3. Widget-contract test mixins and a pathological-data battery

`Orange/widgets/tests/base.py` is how ~100 widgets stay honest without ~100
bespoke test suites. Three ideas:

* **A degenerate-dataset battery** (`base.py:46-80`): a class-level list of
  tables that break naive code — all-NaN values, zero rows, zero attributes,
  no target, string metas only. Every widget is fed all of them.
* **Category mixins**: `WidgetOutputsTestMixin` (`:608`) and
  `ProjectionWidgetTestMixin` (`:686`) contribute whole test families to any
  widget of that shape — outputs on selection, none-data, saved selection
  restored, sparse input, subset colouring, `send_report()` runs, settings
  survive a round trip, minimum size, search keywords present.
* **`ParameterMapping`** (`:248`): a declarative map from a GUI control to the
  model parameter it drives. The harness then **iterates every value of every
  control** and asserts the parameter actually changed — catching the classic
  "combo box is wired to nothing" defect generically.

**ChiSurf today** tests plugins statically: `test/plugins/test_plugin_contracts.py`
verifies that manifests parse and that `.ui` paths resolve. Nothing feeds a
plugin a one-burst file or an all-NaN decay.

**Do:** add a `PluginToolTestMixin` in `test/plugins/` parameterised over all
104 manifests — construct, feed a degenerate input battery, visit every tab,
round-trip `state_schema`, and grab a screenshot. This is the mechanical enforcer
for the project's never-implement-a-GUI-blind and thin-widget rules, and it
composes with the existing `/test-model-editor` path.

### 4. VizRank — rank the candidate views, don't make the user hunt

`VizRankDialog` (`Orange/widgets/visualize/utils/__init__.py:40`) is a small
framework, not a widget: a subclass supplies `iterate_states()` (enumerate
candidate configurations), `compute_score(state)`, `state_count()` and
`row_for_state()`, and gets a background-threaded, incrementally-filling,
sortable table with in-cell score bars where clicking a row **applies that
configuration to the parent widget**. It runs on `ConcurrentMixin`, so it is
cancellable and streams partial results; `VizRankDialogAttr` and
`VizRankDialogAttrPair` are ready-made single-attribute and attribute-pair
enumerations.

This is the highest-value *new capability* in the tree, and it maps onto
several open ChiSurf problems:

* rank 2D projections of a burst-parameter table by class separation or
  bimodality (ndX today asks the user to pick axes by hand),
* rank detector/channel pairs by correlation amplitude,
* rank candidate fit models by χ²ᵣ/AIC and apply the winner,
* rank filter/gate combinations by the purity of the resulting population.

`widgets/data/owcorrelations.py` is the same machinery applied to correlation
search and is the closest template for a burst-parameter version.

**Landed 2026-09-17 in ndX** (projections by class separation, population
structure and correlation; z parameters by separation and structure) — what was
taken, how it departs, and where it lives: [adopted §4](orange3-adopted.md). Still
open from the list above: fit-model ranking by χ²ᵣ/AIC, gate-combination purity.

### 5. Declared messages instead of modal dialogs

Every Orange widget declares its failure modes as class attributes:

```python
class Error(widget.OWWidget.Error):
    failed = widget.Msg("Clustering failed\nError: {}")
    no_attributes = widget.Msg("Data is missing features.")
```

(`widgets/unsupervised/owkmeans.py:123-138`). Raising one is
`self.Error.failed(exc)`; clearing is `self.Error.failed.clear()`. The message
group renders in the widget's own message bar **and** marks the node on the
canvas, so a broken node is visible from the graph without opening it. Because
messages are declared objects, tests assert `widget.Error.no_attributes.is_shown()`
instead of patching a dialog. `MessageOverlayWidget` (`utils/overlay.py`) covers
the transient in-place case.

**ChiSurf had** unified its popups behind `ChiSurfMessageBox` — a real
improvement over raw `QMessageBox`, and the guard test keeps it that way — but
the class of message was still *modal and imperative*: it blocked, it was not
addressable after the fact, and in a node graph it could not annotate the node.

**✅ Adopted** as `chisurf/gui/widgets/messages.py`: `Msg` declarations on nested
`Error`/`Warning`/`Information` groups, bound per instance by `MessagesMixin`,
rendered one line in the host's status bar and assertable in tests. The
enumerable-and-retractable properties are the point; the rendering is the small
part. The node-glyph use is a `messages_changed()` override away, which is what
[PRD-29](/prds/prd-29.md) will need.

## Tier 2 — worth folding into existing work

**The report system.** `Orange/widgets/report/` gives every widget a
`send_report()` that appends its parameters, its data description
(`report.py:14`, `describe_data`/`describe_domain`) and a rendered image of its
plot to a shared report window; the report is one HTML document, printable to
PDF, and each entry remembers the widget state that produced it. ChiSurf has no
cross-plugin report — the closest thing is the operation history
([PRD-43](/prds/prd-43.md)). A `send_report()` on the dockable-tool base
([PRD-36](/prds/prd-36.md)), rendered from the same view-spec that already
carries every control's `description`, would produce a per-session analysis
report nearly for free and gives the docs rule a runtime counterpart.

**Data-matched settings.** `DomainContextHandler`
(`Orange/widgets/settings.py:65`) stores settings in *contexts* keyed by an
encoding of the input columns, and on new input picks the best-matching context
— so reopening a tool on a dataset it has seen restores the axis, colour and
attribute choices used **for that dataset**, while a different dataset gets its
own. Matches are scored, not exact: a partially-overlapping domain still
restores what still applies, and `PerfectDomainContextHandler` (`:312`) is the
strict variant. ChiSurf's plugin state is keyed only by `state_namespace`, so
one global set of choices is reused across every file. Worth adding as an
optional `context_key` on the plugin state seam.

**The safe-expression layer.** `owfeatureconstructor.py` lets a user type a
Python expression to derive a new column, and does three things ChiSurf's
expression surfaces (equation editor, calculator, parameter transform) do not:
`validate_exp` (`:947`) walks the AST and accepts only a whitelist of node types
— no imports, no attribute access to arbitrary objects, no calls outside the
provided environment; `freevars` (`:370`) extracts the free variables, giving
the **dependency set of the expression for free** (which columns it reads →
which edges the derived value needs); and `make_variable` (`:76`) attaches the
expression as a `compute_value` so the derived column is replayable — the
lineage idea already recorded in [orange3-lessons](orange3-lessons.md), here
with a concrete implementation. ChiSurf's expression entry points have no AST
validation at all.

**The annotated-data output convention.** A widget that produces a selection
emits two outputs: `Selected Data` (the subset) and `Data` (everything, plus a
`Selected` yes/no column), with `create_groups_table` for multiple selections
producing a `Group` column instead
(`utils/annotated_data.py:63,89`). `get_unique_names` guarantees the added
column never collides with an existing one. Downstream nodes therefore never
have to choose between "the selection" and "the context" — they get both, and
the selection is expressible as data. This is exactly the missing convention for
ChiSurf's region/selection unification (`chisurf/core/roi`, `RegionCollection`)
and for burst selections in [PRD-04](/prds/prd-04.md)/[PRD-34](/prds/prd-34.md).

**`Reprable`.** `Orange/util.py:568` auto-generates `__repr__` as a valid
constructor call listing only arguments that differ from their defaults —
`Normalize(norm_type=Normalize.NormalizeBySD)`. Every preprocessor, learner and
distance inherits it, so any object printed in a report or log is a line you can
paste back. ChiSurf writes macro/history strings by hand; a `Reprable` base on
the transformer contract ([PRD-16](/prds/prd-16.md)) would make
"what did I run" text derive from the object rather than from parallel code.

**Cheap declarative metadata.** Three one-line features ChiSurf's
`manifest.json` lacks and should copy: `keywords` on a widget (launcher search
synonyms — "k-means, kmeans, clustering"), `replaces=[...]` on an input/output
(`widgets/data/owmergedata.py:253`) so renaming a port does not break saved
workflows, and `settings_version` + `migrate_settings`/`migrate_context`
(`widgets/visualize/owscatterplot.py:418,855,869`) so stored state migrates
stepwise. ChiSurf manifests declare a `state_schema` with no version and no
migrator, which will bite the moment a plugin's state layout changes.

**`WidgetPreview`.** Every Orange widget ends with

```python
if __name__ == "__main__":
    WidgetPreview(OWKMeans).run(Table("iris"))
```

which starts a single widget, feeds it named inputs, and exits cleanly. It is
also what their screenshot tooling drives. Giving every ChiSurf plugin tool the
same `__main__` — loading a canonical test file — would turn the
render-and-inspect rule from a per-tool script into one shared helper, and would
make the `PluginToolTestMixin` above trivial to write.

## Tier 3 — smaller, concrete pickups

* **Palettes.** `utils/colorpalettes.py` has typed `DiscretePalette` /
  `ContinuousPalette` / `BinnedContinuousPalette` classes, a colour-blind-safe
  default set (`:477`), and `LimitedDiscretePalette` (`:162`) which falls back
  to Glasbey when a categorical variable has more values than the default
  palette. Palettes are stored on the variable's metadata, so the same category
  keeps its colour across every plot in the session. chiplot ([PRD-64](/prds/prd-64.md))
  should own an equivalent layer rather than letting each plot choose colours.
* **Signal summaries.** `utils/state_summary.py` registers a `summarize`
  implementation per payload type (`singledispatch`), returning a short line for
  the status bar and a rich HTML block for the link tooltip. ChiSurf could
  register the same for datasets, fits, TTTR files and burst selections and get
  consistent "what is flowing here" text everywhere.
* **Matplotlib export.** `scatterplot_code`/`scene_code` emit runnable
  matplotlib source reproducing the on-screen plot — a publication figure from a
  GUI plot, with no new export backend. Complements the QuickFit3 finding about
  vector export.
* **Save-widget base.** `OWSaveBase` (`utils/save/owsavebase.py:16`) centralises
  filter lists, auto-save, and — via `workflowEnvChanged` (`:178`) — stores paths
  **relative to the saved workflow file**, so a moved project still resolves.
  Directly applicable to ChiSurf project files.
* **Two i18n rules for [PRD-63](/prds/prd-63.md).** First: *never persist a
  translated string as a setting.* `owdatasets.py:38-44` keeps
  language-independent sentinels precisely because the combo-box labels are
  translatable — a saved setting must survive a language change. Second: their
  message files mark each string as translated, `true` (fine as-is but may need
  changing for other languages) or `false` (a literal that must **not** be
  translated) — a triage state ChiSurf's `.ts` flow lacks, and the reason their
  extractor can be re-run without re-reviewing every string. `pl()` for plurals
  is the third, smallest pickup.
* **Cache helpers.** `misc/cache.py` documents why `lru_cache` on a method leaks
  — the cache holds `self`, creating a cycle that defeats garbage collection —
  and provides `memoize_method` (`:27`) and a size-1 `single_cache` (`:6`) that
  compares by identity. Worth auditing ChiSurf's method-level caches against.
* **Reshaping as operations.** `owgroupby`, `owpivot`, `owmelt`, `owtranspose`
  and `owaggregatecolumns` make group-by/pivot/melt first-class, undoable steps
  rather than view-side filters. chitable ([PRD-66](/prds/prd-66.md)) is
  view-side today; burst-parameter tables would benefit from group-by/pivot.
* **Plot types.** Violin plots, heat maps with attached dendrograms and
  split-by-column, and distribution plots with fitted-model overlays are all
  missing from chiplot and all standard for burst/parameter data.
* **Shipped example workflows.** `Orange/canvas/workflows/*.ows` are numbered
  (110, 120, 250, 305, 410, 450 …) example graphs surfaced in the welcome
  screen. ChiSurf's [usecases](/usecases/index.md) are prose; making them
  loadable projects would give the boarding wizard real content and the test
  suite real end-to-end fixtures.

## Explicitly not worth harvesting

Orange's supervised-learning half — `classification/`, `regression/`,
`ensembles/`, `modelling/`, `evaluation/`, and the classifier visualizations
(Pythagorean tree, nomogram, rule viewer) — is out of scope: ChiSurf's inference
is physical-model fitting with priors ([PRD-61](/prds/prd-61.md),
[PRD-68](/prds/prd-68.md)–[PRD-70](/prds/prd-70.md)), not classifier training.
The unsupervised algorithms (`clustering/`, `projection/`, `distance/`) are thin
scikit-learn wrappers and add nothing over the scikit-learn/hdbscan dependency
already shipped. The SQL-backed table and the remote embedding service are
superseded by MMFDB.

## Priority ordering

1. ✅ **Write-locked data with an explicit `unlocked()` context** — the
   correctness precondition for
   [PRD-22](/prds/prd-22.md)/[PRD-29](/prds/prd-29.md); cheap to add, silently
   expensive to skip. **Landed 2026-07-27.**
2. ✅ **One cancellable background-task contract** with partial results, wired
   to the existing progress seam ([PRD-23](/prds/prd-23.md)). **Landed
   2026-07-27**; migrating the existing threading sites onto it remains.
3. **`PluginToolTestMixin` + degenerate-input battery + `WidgetPreview`-style
   `__main__`** — mechanical enforcement of the thin-widget and
   screenshot-the-GUI rules across 104 plugins.
4. ✅ **Declared message groups** — non-modal, addressable, testable widget
   messages layered on the existing dialog seam. **Landed 2026-07-27.**
5. ✅ **VizRank** — the one genuinely new user-facing capability; burst-parameter
   projection ranking in ndX. **Landed 2026-09-17.**
6. **Report system** on the dockable-tool base, rendered from the view specs
   that already carry every control's description.
7. **Data-matched settings contexts**, then the **safe-expression layer**, the
   **annotated-data output convention**, `Reprable`, and the cheap manifest
   metadata (`keywords`, `replaces`, `settings_version`).
