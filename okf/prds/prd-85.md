---
type: PRD
prd: "85"
title: "PRD-85: Drop guards — an opt-in nag-before-commit pattern for file drops, first applied to .pto conversion"
description: A dropped file is committed as-is everywhere in ChiSurf today; nothing gets a chance to say "wait, first...". This PRD adds a general, registry-based drop-guard pattern — mirroring the existing AutoForm section-registry decorator — that a drop zone opts into by name, each guard free to ask about something different and to apply to only some drop zones, never all of them. The concrete first guard closes a real gap: the Qt-free function that would import a dropped vendor photon file (.ptu/.spc/.ht3/...) into ChiSurf's own .pto container exists (pto.Measurement.create / staging.import_measurement) and is called from nowhere in the tree. Wired through the new pattern, plus a zero-setting drop-only tool for people who just want the container. Because a .pto stacks the raw stream plus every derived table in one growing file, the second half audits and fixes photon-level plots (scatter/trace views reading macro_times/micro_times directly) that were sized for a lone vendor file and must not try to draw millions of raw points at once.
status: in-progress
phase: "Part A (drop-guard pattern + tttr_to_pto) landed; Part B (decimation) not started"
resource: chisurf/gui/widgets/dropguard.py
tags: [prd, tttr, pto, data-loading, gui, plugins, plotting, chiplot]
timestamp: '2026-08-07T00:00:00Z'
---

## Where to pick this up

Part A (the mechanism and its one guard) is done and tested. Part B's
decimation utility exists and is wired into the one plugin that actually
paged live: `burst_selection`. It is **not yet in `chiplot`** or the other
seven listed plugins.

1. **`chisurf.core.fio.decimate.thin_for_plot` exists, tested, min/max-per-bin**
   (`test/fio/test_decimate.py`) — built and wired directly into
   `burst_selection/gui/tool.py`'s raw per-photon plots (the "dT"/"Filter"
   diagnostic plots in `update_burst_plots`, and the MCS intensity trace in
   `_update_mcs_plot`) after a real session hit the lag this PRD predicted:
   dropping 11 `.spc` files merged into one `.pto` (the `tttr_to_pto` guard,
   Part A) made a burst-selection diagnostic plot draw millions of points at
   once. Budget is `data_loading.max_plot_points` (default 1.5M, an AutoForm
   "Plotting" panel in `staged_loading_view.json`), split across files in a
   multi-file diagnostic so the sum stays near budget rather than
   `budget × file_count`. **Decay and burst-length plots were audited and
   left alone** — already aggregated (a microtime histogram, a per-burst
   duration histogram), not raw per-photon, exactly the "not every hit is a
   bug" case Scope B.3 called out.
2. **Wired directly at `burst_selection`'s own pyqtgraph calls, not through
   `chiplot`.** `burst_selection/gui/tool.py` is not on chiplot yet (`self.dt_plot`
   etc. are raw `pg.PlotWidget`s) — porting it there is a separate, larger
   change (see [chiplot](/subsystems/chiplot.md)'s own allow-list) that this
   fix deliberately did not bundle in. `thin_for_plot` takes plain arrays, so
   it works the same whichever plotting call ends up using it; **surfacing it
   as `chiplot.Plot.line`'s opt-in `max_points`** (the original Scope B.2) is
   still open, and is the natural point to revisit once a plugin using it is
   actually on chiplot.
3. **The other seven plugins Scope B.3 named are still unaudited**:
   `tttr_correlate/gui.py`, `trace_browser`, `tttr_histogram`,
   `tttr_count_rate_analysis/gui/view_model.py`, `fcs_filter_calculator/gui_parts/*`,
   `flc_2d/gui/{tool,client}.py`, `clsm_generator/gui/view_model.py`. First
   task for each is the same confirmation `burst_selection` just went
   through: which of its plots are raw per-photon (call `thin_for_plot`
   directly, same pattern) versus already-aggregated (leave alone).
4. **The pre-unification drop-zone audit (A.5) is not exhaustive.** Wired so
   far: `burst_background`, `burst_irf_bg`, `tttr_count_rate_analysis` (via
   the `path_list` `guards` option in their view.json), `burst_analysis` and
   `tttr_microtime_shifter` (via the `PathListWidget` `guards` kwarg), and
   the hand-rolled `dropEvent`s in `chisurf/gui/widgets/experiments/pch.py`,
   `chisurf/gui/widgets/experiments/tcspc/tcspc_tttr_reader_control_widget.py`,
   and `chisurf/plugins/pch/gui/tool.py` (`on_paths_dropped`). Deliberately
   **not** wired: `bid_to_analysis/__init__.py` (its drop zone accepts
   `.bid`/`.bst`/`.txt`, never a vendor photon file — the PRD's original list
   was wrong about this one); `burst_selection/gui/tool.py` and
   `chisurf/gui/widgets/fio/fio.py` (both load a vendor file only through a
   `QFileDialog`, not a drop, so `apply_drop_guards` has nothing to hook —
   would need drop support added first, which is out of this PRD's scope).
5. **A guided tour was deliberately skipped** for the bare drop-only tool
   (`tttr_to_pto/gui/tool.py`) — it is one drop target with a self-explanatory
   label and tooltip, and CLAUDE.md's guided-tour rule exists for panels dense
   enough that order-of-operations is not obvious. Revisit only if the tool
   grows a second control.

# Summary

No file-drop zone in ChiSurf today gets a chance to object, transform, or ask before
a dropped path is committed to the model behind it — `dropEvent` goes straight to
`_commit`/`_add`. That is the wrong default in more than one place, and differently
wrong each time: a dropped vendor photon file should probably become a `.pto`; a
dropped multi-page image might need an axis-order confirmation; a dropped legacy
stacked-decay file might want the `vv_vh` rename surfaced. **A. below builds the
general mechanism** — a small **drop-guard registry**, the same decorator shape as
the existing AutoForm section registry (`register_section`/`get_section_factory` in
`chisurf/gui/autoform/sections/registry.py`): a guard is registered under a name, and
a drop zone opts into specific guards by name in its own view-spec options. **No
drop zone is naggy by default**, and two drop zones that both accept `.ptu` can name
different guards, or none.

The one concrete guard this PRD ships closes a real, verified gap: the Qt-free
function that would import a dropped vendor photon file into ChiSurf's own `.pto`
container exists and is correct — `chisurf.core.fio.pto.Measurement.create` /
`chisurf.core.fio.staging.import_measurement`, embeds the vendor bytes verbatim,
never touches or deletes the original — but **nothing in the tree calls it**: a
repo-wide grep for `import_measurement(` finds only its own definition. Wired
through the new pattern as the `tttr_to_pto` guard, a drop zone that opts in offers
convert-with-original-kept (default) / convert-and-delete-original /
use-as-dropped, once, dismissably — plus a zero-setting drop-only tool for people who
just want the container with no prompt at all, because they already know they want
one.

Because the container this produces is a **stacked** file — the raw stream plus
every burst/dwell/pixel/... table derived from it, all in one growing object — the
PRD's second half (B) is auditing and fixing the plugins that plot raw
`macro_times`/`micro_times` directly, which were sized for a single vendor file and
must not try to draw an unbounded photon stream point-for-point.

# Status

In progress. Part A (Scope §A: the drop-guard registry, the `tttr_to_pto`
guard, the bare two-way drop tool, and wiring into the genuine measurement
drop zones) is done and tested. Part B (Scope §B: decimated plotting for a
stacked container) has its core utility (`thin_for_plot`) done and tested,
and wired into the one plugin (`burst_selection`) that actually hit the lag
this PRD predicted; `chiplot` and the other seven listed plugins are
untouched — see [Where to pick this up](#where-to-pick-this-up) for exactly
what was and was not wired.

# Motivation

- **The conversion path is built and unwired.** `Measurement.create` (`chisurf/core/fio/pto.py`)
  and `import_measurement` (`chisurf/core/fio/staging.py:495`) are correct,
  tested, Qt-free, and non-destructive by construction — `create` copies the vendor
  file's bytes in *verbatim*, checksummed, and never deletes or rewrites the source.
  A user who drops a `.ptu` today gets none of that; the file is opened where it sits,
  silently, forever.
- **The two unified drop widgets have no hook for *anything*.** `DataSourceSection.dropEvent`
  and `PathListSection`'s add/drop path (`chisurf/gui/autoform/sections/data_source_section.py`,
  `.../path_list_section.py` — the `data_source`/`path_list` AutoForm sections
  documented in [GUI & AutoForm](/subsystems/gui-autoform.md)) both call straight
  through to `_commit`/`_add` with the raw dropped path, unconditionally. This is the
  one seam that reaches every plugin built after the file-list unification — the
  right place to add a pattern once, not the `.pto` behaviour specifically. A `.pto`
  nag on *every* drop zone that happens to accept `.ptu` would be wrong just as
  often as no nag at all: a tool that reads a raw vendor file for a one-off inspection
  (a header editor, a quick histogram) has no business asking to convert it.
- **`.pto` is deliberately stacked, and plotting code was not written for that.**
  Per [photon container](/subsystems/photon-container.md), a `.pto` holds the
  instrument stream *and* every result computed from it in one file that only grows.
  Several plugins already read `macro_times`/`micro_times` straight off a loaded
  `tttrlib.TTTR` for a scatter/trace view (`tttr_correlate/gui.py`, `trace_browser`,
  `tttr_histogram`, `tttr_count_rate_analysis`, `fcs_filter_calculator`, `flc_2d`, ...);
  `chisurf.gui.chiplot.canvas.Plot.line`/`.scatter` (the one plotting seam, per
  [chiplot](/subsystems/chiplot.md)) has no point budget or decimation today. Converting
  more files to `.pto` by default makes this an every-session problem instead of an
  edge case.

# Scope

## A. The drop-guard pattern, and one guard that uses it

1. **A registry, not a hook.** New module `chisurf/gui/widgets/dropguard.py`, shaped
   like the existing section registry (`chisurf/gui/autoform/sections/registry.py`:
   `register_section`/`get_section_factory`) on purpose — same repo, same pattern,
   one more registry rather than a new idiom to learn:

   - `class DropGuard` — a small protocol/ABC with two members: `applies(path: str) ->
     bool` (does this guard care about this path at all — cheap, no I/O beyond a
     suffix/header check) and `resolve(parent: QWidget, paths: list[str]) -> list[str]`
     (shown only the paths that `applies()` accepted; returns the paths to actually
     commit — a converted path, the original unchanged, or the path dropped from the
     list entirely, guard's choice). `resolve` owns its own dialog — a guard is free to
     ask a yes/no, a three-way choice, or nothing at all if it decides not to nag this
     time (e.g. a persisted "always convert" preference).
   - `@register_drop_guard(name: str)` — decorator registering a `DropGuard`
     (instance or zero-arg factory) under a name, mirroring `register_section`'s
     shape exactly.
   - `apply_drop_guards(parent, paths: list[str], guard_names: Sequence[str]) ->
     list[str]` — the one function a drop widget's `dropEvent` calls: runs the
     *named* guards, in order, only over the paths each guard's `applies()` accepts,
     and returns the final list. **`guard_names` defaults to `()`** — a drop zone
     that names no guards behaves exactly as it does today, unconditionally. This is
     what makes the pattern opt-in per drop zone rather than a blanket behaviour.
2. **Drop zones opt in by name, in their own view spec.** `data_source`/`path_list`
   AutoForm sections (`data_source_section.py`, `path_list_section.py`) gain a
   `guards` option — `{"type": "custom", "key": "path_list", "options": {"guards":
   ["tttr_to_pto"], ...}}` — read once at construction and passed to
   `apply_drop_guards` from `dropEvent`/`_add`. A plugin's author decides which
   guards its own drop zone should run, including none; two plugins that both accept
   `.ptu` can disagree. Widgets outside AutoForm (the pre-unification `dropEvent`
   handlers below) call `apply_drop_guards` directly with an explicit guard list.
3. **The concrete `tttr_to_pto` guard.** A new core plugin,
   `chisurf/plugins/core/tttr_to_pto` (living under `plugins/core/` — shared
   infrastructure, not a domain tool — alongside `setup`, `acq`, `help`, ...), with:
   - a Qt-free `api.py`: `convert(path, *, keep_original=True, out_dir=None) -> Path`,
     a thin wrapper over `pto.Measurement.create` that, when `keep_original=False`,
     calls `Measurement.verify()` on the freshly written container **before**
     unlinking the vendor file — deleting only after the embedded copy is confirmed
     byte-identical;
   - a `DropGuard` implementation registered as `@register_drop_guard("tttr_to_pto")`:
     `applies()` is `suffix in staging.VENDOR_EXTENSIONS and suffix not in
     pto.SIDECAR_ONLY_EXTENSIONS and not staging.is_measurement(path)` — a Becker &
     Hickl `.set` is never itself a candidate, since it is undecodable alone and is
     picked up automatically beside its `.spc`; `resolve()` shows
     `ChiSurfMessageBox.choice` (`chisurf/gui/dialogs.py:516`) with three options —
     **Convert, keep original** (default, both for the dialog and headlessly: it
     never deletes anything, so it is the one answer that is always safe to take
     unattended) / **Convert, delete original** / **Use as dropped** — plus its
     built-in `checkbox` ("remember my choice"), and calls `api.convert` for
     whichever the user picked. Files dropped together are embedded into **one**
     container in lexical order by name (`Measurement.create`'s multi-file form) —
     a measurement split across `m000.spc`, `m001.spc`, ... is one recording, not
     one `.pto` per file.
   This is the *only* code that knows about `.pto` conversion; the registry and
   `apply_drop_guards` know nothing about it.
4. **A persisted "stop asking" is per-guard, not one flat flag.** The checkbox in a
   guard's dialog is the guard's own business to persist — `tttr_to_pto` writes a
   `data_loading.drop_guards.tttr_to_pto` tri-state (`ask` / `always_keep` /
   `always_delete` / `never`) into the existing `data_loading` settings section
   (`staging.DEFAULTS`, `chisurf/gui/widgets/staged_loading_view.json`) rather than a
   shared key a second guard would have to avoid colliding with.
5. **Wire `guards: ["tttr_to_pto"]` into the drop zones it belongs on** — the
   `data_source`/`path_list` instances that are genuinely "load this as the working
   measurement" (burst selection, the TCSPC/FCS setup readers, the microtime
   shifter), not every widget that merely inspects a vendor file in passing. Then
   audit the ~10 pre-unification call sites still filtering on
   `staging.VENDOR_EXTENSIONS`/`TTTR_FILE_FILTER` by hand (`pch/gui/tool.py`,
   `tttr_microtime_shifter/gui/tool.py`, `flc_2d/gui/tool.py`,
   `burst_selection/gui/tool.py`, `burst_analysis/gui/tool.py`,
   `bid_to_analysis/__init__.py`, `gui/widgets/fio/fio.py`,
   `experiments/tcspc/tcspc_tttr_reader_control_widget.py`, `experiments/pch.py`),
   deciding per widget whether it calls `apply_drop_guards(..., ["tttr_to_pto"])`
   directly, migrates onto `path_list`/`data_source` with the `guards` option, or is
   a genuine "just inspect it raw" tool that names no guard at all — closing the
   drop-conversion gap and the pre-unification-widget gap together, deliberately,
   file by file, rather than by one blanket rule.
6. **A super-simple, zero-setting drop tool** (the user's direct ask, distinct from
   the settings-heavy `tttr/converter` hub which transcodes *between vendor
   container formats* and is unrelated to `.pto`, and distinct from the guard
   itself): a second, minimal GUI entrypoint on the same `tttr_to_pto` plugin — one
   drop target, no panel, no options, and **no guard/dialog in front of it** (it *is*
   the explicit "convert" action a guard would otherwise ask permission for). Drop
   one or more vendor files, each becomes a `.pto` beside it (original kept), done.
   Calls `tttr_to_pto.api.convert` directly.

## B. Subsampled plotting for stacked containers

1. **One decimation utility**, Qt-free, e.g. `chisurf.core.fio.decimate.thin_for_plot(x,
   y=None, *, max_points=...)`. Default algorithm: min/max-per-bin decimation (not
   plain stride sampling) so a photon trace's bursts/dips survive thinning instead of
   being aliased away — plain stride is only safe for genuinely-random point clouds
   (e.g. a 2D phasor scatter), not for time-ordered traces.
2. **Surface it in chiplot** — `Plot.line`/`Plot.scatter`
   (`chisurf/gui/chiplot/canvas.py:88`) gain an opt-in `max_points` (or the decimation
   is applied by the caller before handing arrays to `line`/`scatter`; either way it
   lands in chiplot once rather than once per plugin, consistent with
   [chiplot](/subsystems/chiplot.md) owning every plotting concern).
3. **Audit + fix the known direct-array plotters**: `tttr_correlate/gui.py` (already
   reads `macro_times`/`micro_times` at full resolution for its display),
   `trace_browser`, `tttr_histogram`, `tttr_count_rate_analysis/gui/view_model.py`,
   `fcs_filter_calculator/gui_parts/*`, `flc_2d/gui/{tool,client}.py`,
   `burst_selection/gui/tool.py`, `clsm_generator/gui/view_model.py`. Not every hit is
   a bug — a histogram or correlation curve is already aggregated and safe; only the
   call sites building a **raw per-photon** scatter/line (time trace, arrival-time
   cloud) are in scope. First task under this heading is confirming which of the
   above are which, not fixing all of them blind.
4. **A budget, not a hard cap.** Default `max_points` should be a `data_loading` (or a
   new `plotting`) setting, not a literal — a user with 4 GB spare RAM and a fast GPU
   should be able to raise it.

# Reuse

- `chisurf.gui.autoform.sections.registry` (`register_section`/`get_section_factory`)
  — the pattern the new `register_drop_guard`/`get_section_factory`-shaped registry
  is deliberately copied from, so a reader who already knows one registry knows the
  other.
- `chisurf.core.fio.pto.Measurement` (create/verify) and
  `chisurf.core.fio.staging.{import_measurement,is_measurement,VENDOR_EXTENSIONS}` —
  written, tested, unused; the `tttr_to_pto` guard is entirely about wiring existing
  conversion infrastructure up, not building new conversion logic.
- `ChiSurfMessageBox.choice` (`chisurf/gui/dialogs.py`) — already the general
  "Overwrite / Skip / Cancel"-shaped dialog with a remember-checkbox and a headless-safe
  default; no new dialog class needed, and every future guard gets it for free.
- `chisurf.gui.autoform.sections.{data_source_section,path_list_section}` — the two
  places a `guards` option can be declared per-drop-zone post-unification
  ([file-list unification](/plugins/tttr.md)).
- `chisurf.gui.chiplot` (`Plot.line`/`Plot.scatter`) — the one plotting seam
  ([chiplot](/subsystems/chiplot.md)); decimation is a chiplot feature, not a
  per-plugin one.
- `chisurf/gui/widgets/staged_loading_view.json` / `staged_loading_settings.py` — the
  existing "Data loading" AutoForm settings surface `tttr_to_pto`'s persisted choice
  nests under, as `data_loading.drop_guards.tttr_to_pto`.

# Design decisions / open questions

- Where the registry itself lives: `chisurf/gui/widgets/dropguard.py` is Qt-aware
  (guards own a dialog), so it cannot sit beside the Qt-free `staging.py`/`pto.py`;
  confirm `gui/widgets/` is the right home versus e.g. `gui/autoform/` given guards
  are meant to be usable outside AutoForm sections too (the pre-unification
  `dropEvent` handlers call it directly, per A.5).
- Whether `DropGuard.resolve` may **drop** a path outright (declined entirely, not
  just "used as-is") — needed for a hypothetical future guard that refuses a file
  rather than transforms it; `tttr_to_pto` itself never needs this (its "no" is
  "use as dropped"), so the protocol should allow it without the first guard
  exercising it.
- Plugin id/location for the conversion core: proposed `chisurf/plugins/core/tttr_to_pto`
  (api + guard registration + the bare drop tool — one manifest). Confirm this
  doesn't collide with the existing `tttr/converter` hub's mental model; cross-link
  both in their docs so "convert" isn't ambiguous between "vendor↔vendor transcode"
  and "vendor→.pto".
- Decimation default (`max_points`) and whether it lives under the existing
  `data_loading` settings section or a new `plotting` one — lean `data_loading` (same
  "how much of a big file do we touch" concern as staging).
- Whether a guard also fires for a **file-open dialog** pick (not just a drop) — out
  of initial scope (see Non-goals) but `apply_drop_guards` taking a plain path list
  rather than a Qt drop event already makes this a call-site change, not a redesign,
  if extended later.

# Acceptance

- Headless: `apply_drop_guards(parent, paths, guard_names=())` returns `paths`
  unchanged and shows nothing — the no-guards-named default is inert, proving the
  pattern is genuinely opt-in and not a hidden global hook.
- Headless: two fake `DropGuard`s registered under different names, applied to the
  same path list via different `guard_names`, each only sees/transforms the paths
  its own `applies()` accepts and does not interfere with the other — proves the
  registry composes rather than assuming one guard per drop.
- Headless: `tttr_to_pto.api.convert(vendor_path, keep_original=True)` produces a
  `.pto` beside the source, source untouched, `Measurement.verify()` clean;
  `keep_original=False` produces the same container and the source is gone only
  after verification passes (inject a corrupted write and assert the source
  survives).
- Headless: dropping a vendor path onto a model bound through `data_source`/`path_list`
  with `guards=["tttr_to_pto"]` and `data_loading.drop_guards.tttr_to_pto` pre-set to
  each of the four tri-state values produces the right outcome with no dialog shown
  (`ChiSurfMessageBox` auto-answer path); the same drop onto a section with no
  `guards` option produces the untouched vendor path regardless of that setting.
- GUI, screenshotted per [testing](/workflows/testing.md): the `tttr_to_pto` nag
  dialog itself, and the bare drop-only tool, both rendered headlessly in a
  realistic state.
- At least one audited plotting call site (from B.3) has a synthetic-large-file
  regression test asserting the number of points actually handed to `chiplot` stays
  under the configured budget regardless of input photon count.

# Non-goals

- Authoring any guard other than `tttr_to_pto`. The registry is deliberately general
  — a second guard for something unrelated to `.pto` is a small, self-contained
  follow-up once the pattern exists — but inventing one here would be scope
  creep with no real use case behind it yet.
- Auto-enrolling every existing `data_source`/`path_list` instance into
  `guards: ["tttr_to_pto"]`. Which drop zones should nag is a per-plugin editorial
  call (A.5), not something this PRD's infrastructure decides on their behalf.
- Converting on a **file-open dialog** pick rather than a drop (mentioned above as a
  natural follow-up, not required here — the user's ask was specifically about drops).
- Deleting/rewriting the vendor file inside an *existing* `.pto` that already embeds
  it (`Measurement.disassemble` already covers "get the original back out"; nothing
  here changes that).
- A general "downsample any large dataset" framework — B is scoped to photon-level
  (`macro_times`/`micro_times`) plots specifically, not e.g. large fit-result tables,
  which `chitable` ([PRD-82](prd-82.md)) already paginates.
- Changing what `tttr/converter` (vendor↔vendor container transcoding via
  `tttr_splitter`) does — it is unrelated to `.pto` and out of scope.

# Relationships

- Builds directly on [photon container](/subsystems/photon-container.md) and the
  staging half of [Data IO](/subsystems/data-io.md) — this PRD is the missing call
  site for `import_measurement`, not a new format decision.
- Shares the plotting seam with [PRD-64](prd-64.md) (chiplot) — the decimation API
  lands there.
- B's audit list overlaps files also touched by [PRD-82](prd-82.md) (table layer onto
  DataStore) and the TTTR plugin group ([tttr](/plugins/tttr.md)); coordinate rather
  than duplicate when both touch the same file in the same window.
