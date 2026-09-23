---
type: Plugin
title: ndX multidimensional explorer
description: The interactive explorer for burst and image parameter tables — projection, gating, curve overlays, and playing a measurement back along one of its own columns.
resource: modules/ndxplorer/
tags: [plugins, ndxplorer, bursts, gating, playback]
timestamp: '2026-08-06T00:00:00Z'
---

ndX is ChiSurf's interactive explorer for wide numeric tables: burst data (E, S,
lifetime, brightness), imaging-derived parameters, posterior draws. You project
the cloud onto one or two axes, gate a sub-population, overlay a parameterised
curve and fit it. Theory in
[`docs/concepts/multidimensional_exploration.md`](../../docs/concepts/multidimensional_exploration.md),
usage in [`docs/guides/46_ndxplorer.md`](../../docs/guides/46_ndxplorer.md).

It lives in its **own repository**, vendored as the git submodule
`modules/ndxplorer` (branch `development`); the ChiSurf side is a thin plugin
wrapper (`chisurf/plugins/ndxplorer/`) that puts the module on `sys.path` and
builds the window. Changes to ndX commit **there**, and ChiSurf records only the
gitlink. It declares `chisurf` as a hard dependency and a test enforces it —
running without ChiSurf is a broken environment, not a supported configuration —
but every chisurf import is lazy or guarded, so nothing pulls the GUI stack at
module import time.

## The calibration button asks what it may determine

"🎯 Optimize FRET calibration" runs
`chisurf.core.fluorescence.fret.accurate.auto_calibrate` — **the** accurate-FRET
implementation, the same code the Accurate FRET step runs, not a second one. ndX
evaluates the corrected columns from constants; determining those constants
happens here, and `calibration_bridge.py` is the join.

It used to take every default and write every factor, which is right exactly
once. After that it is usually wrong in one way: γ from a measurement's own
populations is only as good as those populations, and someone who determined γ
on a reference sample wants α and δ fitted *around* it rather than replaced by a
worse estimate. So the action now asks first (`calibration_options.py` +
`.view.json`): which of α, δ, γ, β, R₀ may be written, which route γ comes from,
whether the light-path priors are used, the bootstrap count, τ_D(0) and the
linker width, and whether the accurate per-burst columns are added.

**The calibration still runs in full** whatever is selected — the report shows
what every factor came out as, including the ones held fixed, because holding
one is a decision and the number it was held against is what justifies it.

**The trap, if this is ever touched:** `auto_calibrate` refines the calibration
object *in place*, so a factor to be kept has to be snapshotted **before** the
call. Reading it back afterwards returns the refined value, and "held fixed"
would silently mean "applied". Pinned by
`tests/test_calibration_options.py::test_a_held_factor_keeps_the_window_value`.

R₀ is off by default: it is not a correction factor but a property of the dye
pair and its environment, and the distance columns depend on it.

**Backgrounds are a separate choice, because they are not determined here at
all.** They are an *input* — every corrected quantity is a count minus one — and
the input whose error is hardest to see: it moves the dim bursts and leaves the
bright ones, which looks exactly like a real sub-population. `measured_background`
reads the rates the background step stored in the measurement's container and
multiplies each by that burst's **duration**, so the background becomes per-burst:
a 4 ms burst carries four times the background of a 1 ms one, which a single
typed number cannot express (kHz × ms = counts, which is why no unit factor
appears in the code).

It reaches the calibration by being subtracted from the counts with the scalar
backgrounds zeroed — identical algebra, since the background only ever enters as
`counts − background`, and the only way to carry a per-burst value through a
calibration object whose backgrounds are single numbers. **Only when there is
something to subtract:** a container with no stored estimate falls back to the
window's constants rather than zeroing them and subtracting nothing, which would
be worse than the setting it replaced.

Measured on the cal1 container: using the stored background instead of the typed
zeros moves γ from 0.826 to 0.795 and α from 0.157 to 0.147.

**And they can be fitted, which is usually what is wanted** — the background is
rarely known. `fitted_background` reads it off the reference populations, each
of which has one channel measuring background and nothing else: an
acceptor-only burst has no donor, so the donor channel is background (`bg_dd`);
a donor-only burst has no acceptor, so the acceptor-excitation channel is
background (`bg_aa`); and the leakage relation `I_DA = α·I_DD + bg_da` gives the
third **as its intercept**. Fitting that line is what separates leakage from
background at all — the usual ratio-of-means shortcut folds the background into
α and then subtracts it from every burst as though it scaled with donor
brightness. Medians, not means, because these are the populations a mixture
model is least sure of.

It costs a second calibration pass, and the two passes are not the same pass
twice: the populations must exist before the background can be read off them,
and once it is subtracted the classification that found them is no longer the
one the data supports, so it is made again. The first pass skips the bootstrap —
only its split is used.

Recovered on a simulation with planted backgrounds (5 / 3 / 7 counts and
α = 0.06): `bg_dd` 5.00, `bg_aa` 7.00, `bg_da` 2.67, α 0.0613.

## Opening a measurement restores its calibration

A calibration belongs to the measurement it was determined on. The Accurate FRET
step already wrote it there — an `accurate fret calibration` artifact whose
`alpha` / `beta` / `gamma` / `delta` / `r0` columns are **constant across the
populations on purpose**, so any row carries the whole calibration. Nothing read
it back. Opening a container therefore gave a window still holding the
*previous* measurement's constants: numbers that look determined, belong to
another file, and correct every burst by the wrong amounts.

`calibration_from_container` reads it (walking up from a run path to the `.pto`,
since every burst reader addresses a run), and `restore_calibration_from_container`
applies it. Only the stored factors are replaced — the window's backgrounds and
quantum yields survive, because those are not what the artifact describes.

There is no "a load finished" signal in ndX, but there is one place every load
ends: the assignment to `data_source`. `rpc_bridge._measurement_aware` subclasses
the window to hook that property, so this works for every in-GUI ndX regardless
of which path opened the file.

**Under flrCIF's names, not chisurf's.** `_flr_fret_calibration_parameters`
has carried `alpha`, `alpha_sd`, `beta`, `gamma`, `delta`, `gG_gR_ratio` and
`phi_acceptor` all along, and the Förster radius has its own category
(`_flr_fret_forster_radius.forster_radius`). The writer had invented its own
headers, which made the one artifact that most needs to be readable by something
other than chisurf readable only by chisurf.
`accurate_fret/calibration_columns.yaml` declares the schema with those terms —
covered by `test/core/test_analysis_feature_terms.py`, the guard that requires
every declared feature to resolve in the dictionaries — and the writer *and* the
reader both emit from it, which is what stops a stored artifact and the code
that loads it drifting apart. Headers earlier versions wrote (`r0`) still
restore: a file already on disk cannot be asked to follow a newer schema.

**The background comes back with it.** A measurement usually has its background
measured long before its factors are determined, and ndX's `Bg` / `Br` / `By`
are *rates*: `Fg(PIE) = Sg(PIE) − Bg` where `Sg(PIE)` is
`S prompt green (kHz)`. So the container's per-detector rates go in as they
stand — no duration, no conversion — and a measurement carrying only a
background still restores something, which is the part the equations use most
directly. They travel on the calibration object, because
`calibration_to_ndx_constants` already maps `bg_dd`/`bg_da`/`bg_aa` onto
`Bg`/`Br`/`By`, so one push carries both.

**Two traps, both load-bearing.** Writing constants directly is not enough: the
values must reach the parameter *table*, since ndX's recompute throttle resets
`constants` from that table on the next parameter event — a value written the
short way is correct only until something happens. And the table is built in
`_deferred_init`, which runs on first show, while a measurement can be handed
over before that; the restore therefore waits for the table rather than applying
into a window that will overwrite it. Both readers also take the **last**
matching artifact: a container keeps every estimate it is given, so re-running
the background step leaves the older one in front.

**And it repopulates.** Restoring on *open* alone is not enough: the container
is the shared surface between the steps, so re-running the background step
writes a new estimate into the same file while the ndX window is still up.
`refresh_stored_parameters` is called whenever a step that owns an ndX window is
revisited — cheap enough for that (one container open, two small artifact reads)
because it compares against **what was last restored from that container**, not
against what the window now holds. So a revisit with nothing changed is a no-op,
a value the user tuned in between is theirs and survives, and a re-run of the
background step reaches the window.

Round trip verified on a real container: planted α 0.0731, β 1.234, γ 0.8642,
δ 0.0519, R₀ 54.3 come back identically and land as ndX's own names —
`gG/gR = (PhiA/PhiD)/γ`, its `beta` = δ, `r` = 1/β.

## "Auto" ranges past the outliers, and a region keeps its meaning

Three defects on the z-axis panel, all about a number on an axis being
meaningless without the projection it was written in.

**Auto ranged to the extremes.** On a real µs-ALEX burst table the photon count
has a 99.9th percentile of 1 108 and one burst at 450 094, so the z axis came
out 60 – 450 094 and the whole distribution drew inside the first pixel.
`axis_helpers.robust_axis_range` now uses the 0.1/99.9 percentiles, with each
end **snapped back out to the true extreme when that extreme is within 5 % of
the robust span**. That second half is what keeps the change from being a
regression of its own: an efficiency running 0 to 1 has no outliers and must
still auto-range to exactly 0 and 1, or "Auto" stops meaning "all of it" on the
data where it always worked.

**A region lost its units when the scale toggled.** `PGRangeSelection` converts
data ↔ view on every read and write, but the pyqtgraph item *stores* view
coordinates and nothing told it the axis had changed. A range written on a log
axis (view 1.78 – 5.65 for counts of 60 – 450 094) became, the moment the axis
went linear, a selection of 1.78 – 5.65 **counts**: a sliver at the left edge
gating away the whole measurement while the range boxes still read 60 and
450 094. The other direction puts the region at 10**60, off the plot. The plot
now keeps its selections and calls `reproject()` on a scale change — read back
through the projection they were written in, written again in the current one.
`_drawn_log` is the record of which that was.

**The z min/max boxes were different sizes**, and the maximum clipped
mid-number. They were in two cells of a `QGridLayout` whose column widths are
set by the *other* rows: the minimum inherited the width of the parameter combo
above it, the maximum that of a bin-count spin box. They now share one cell
through a `QHBoxLayout`, so both stretch equally.

**A trap for whoever tests this next.** A test that toggles log and back without
writing the range in between passes whatever the code does — the item still
holds the linear numbers it started with. The log→linear test has to *set* the
range while the axis is log, which is what `fit_z_selection_to_axis` does.

## A background is a rate; the calibration works in counts

The two meet at this bridge, and they were not converted. ndX computes
`Fg = Sg - Bg` where `Sg` is a count **rate** in kHz, so its `Bg`/`Br`/`By` are
rates. `chisurf.core.fluorescence.fret.accurate` works on **per-burst counts**
and its `bg_dd`/`bg_da`/`bg_aa` are counts (`f_dd = i_dd - bg_dd`). The push
mapped one onto the other by name.

Both background routes were wrong, in opposite directions:

* **`background="fit"`** estimated the background as the *median counts* of the
  channel that has no fluorophore in each reference population, and wrote that
  straight into the rate constant. On the owner's µs-ALEX file that put
  **Bg = 8, By = 4** into a window whose real background is about **3 kHz** —
  over-correction, and the more so for short bursts. The reported symptom.
* **`background="measurement"`** did the per-burst algebra correctly (rate × the
  burst's own duration) but then pushed the *zeroed* scalars, so ndX's own
  equation columns were left with `Bg = 0` — uncorrected, while the injected
  accurate columns were fine. Nobody had noticed, because the two sets of
  columns are never compared.

`fitted_background` now returns **rates**: a median of per-burst *ratios*
`counts/T` for the two channels that measure background alone, and for `bg_da`
a two-regressor least squares of `I_DA = alpha·I_DD + bg_da·T` — the duration is
a regressor, not an intercept, because an intercept says a 4 ms burst carries no
more background than a 1 ms one. Without a duration column it returns nothing
rather than a count labelled as a rate. The rate is converted to per-burst counts
for the calibration itself (through `burst_durations_ms`, the same helper the
measured route uses) and pushed to the window as a rate.

Recovered on a simulation where the background really is a rate (mean burst
2.79 ms): 1.87 / 1.09 / 2.66 kHz against a truth of 2.0 / 1.2 / 2.8. The old
path would have written 108 and 145 — the median counts.

## Saved calibrations are a FIFO of five, ordered by their own timestamp

Saving a calibration appends to the measurement, and one working session was
enough to leave thirteen `fret_calibration` artifacts in a container — every
reader then walks them all to find one. Keeping only the newest is the other
extreme: the previous calibration is what you compare against when a new one
comes out differently, and the one before that is what you go back to when it
turns out worse. So `calibration_io.CALIBRATION_HISTORY` bounds the history at
five and `_prune_calibrations` drops the excess after each save.

**The trap is the ordering, and it only appears after the first prune.**
Removing an object frees its slot and the next `put_blob` reuses it, so from
that point `objects()` is not even a permutation of write order — a FIFO that
trusts position starts discarding the *newest* save, and the reader starts
returning a stale calibration while the file looks perfectly healthy. Measured
directly: nine saves of a distinguishable `gG/gR`, and the value that came back
was the fifth (0.5), not the ninth (0.9). Both the prune and every reader
(`stored_calibrations`, `calibration_bridge.saved_constants_from_container`)
therefore sort on the payload's own `saved_utc`, which is written to the
**microsecond** — at one-second resolution two saves in the same second tie and
the ordering is back to being position's. Pinned by
`tests/test_calibration_io.py::test_history_is_bounded_and_drops_the_oldest`
and `::test_history_bound_survives_repeated_pruning`, which fail on positional
order.

## The z marginal is shown whether or not it gates

**Four** places decided whether the third axis had a plot, all keyed on the
"dynamic z-selection" checkbox: the histogram was not computed
(`histogram_helpers.histogram_axes`), and three separate `setVisible` calls in
`plot_update_helpers` hid the widget. But that box arms the *gate* — whether the
z range filters the other plots — and hiding the distribution until the gate is
armed asks for a range to be chosen before it can be seen. The marginal is now
drawn like x and y whenever a third parameter is selected; the checkbox still
decides only whether its range filters.

## Where to pick this up

1. **Leakage through compound derived columns in the gate-separation ranking.**
   Gating on `Tau (green)` excludes it and every column monotone in it
   (Spearman |ρ| ≥ 0.98: `E_tau`), but `(1-E)*E_tau` still carries τ and tops
   the MFD ranking (κ 0.924 with `R_FRET(PIE)`). Measure: open the MFD folder,
   gate τ 2.5–4.2, *Find informative projections* — see which top pairs are
   functions of τ. A fix needs the equation graph (`core/equation_graph.py`
   knows each derived column's inputs): exclude every column downstream of a
   gated one. Tried and rejected: a Spearman test against combinations (too
   slow, and a threshold would drop genuinely correlated parameters).
2. **Population structure and point masses.** 2-means reads a pile-up at a fit
   bound or sentinel as a population: on the MFD folder the top structure pairs
   are the red-channel fit columns with `-1` in 22 % of bursts (unfitted,
   mostly donor-only) — interpretable, but an artefact of the fit's sentinel.
   The ≥ 5 % smaller-group rule removed `rho = 10⁴` (2.7 %); flags (< 20
   distinct values) are skipped. Tried and rejected: stripping edge point
   masses with a gap test — it also strips an exact `E = 0` donor-only
   population. The honest fix is sentinels declared per feature
   (`burst_features.yaml` already names them for chisurf's own writers).
3. **Ranking is 12–16 s for ~1 500 pairs** (5 000 bursts; kNN ~8 ms,
   structure ~11 ms per pair on the arm64 box). Fine streamed; a table of 100
   columns (4 950 pairs) would take a minute. Measure with
   `ProjectionRanker(...).compute_score` over `iterate_states()`; batching
   states per worker call is the obvious next step before any C++.
4. **Not yet ranked:** fit models by χ²ᵣ/AIC and gate combinations by purity
   (the other two uses the Orange3 mining note lists); applying a z row enables
   the z gate checkbox but leaves the folded *z axis* panel folded.

5. **Playback on a real burst folder.** The gate, the panel and the axis
   detection are covered headlessly
   (`ndxplorer/tests/test_playback_controller.py`,
   `tests/test_ui/test_playback_panel.py`,
   `tests/test_ui/test_open_image_hdf5.py`), all on synthetic tables. What is
   *not* measured is what playing back an hour of real bursts costs: a redraw is
   ~20 ms on the sizes those tests use, and the panel offers up to 60 fps. Take
   the measurement by timing `update_plots` over a loaded `.bur` folder at
   several step counts before deciding whether the speed cap needs lowering or
   the redraw needs to skip a tick it cannot keep up with.
   - **The trap:** the mask is cached on
     `(axis, mode, position, n_steps, bounds, data_version)` and the *identity*
     of the array returned by `DataManager.get_value_mask` is load-bearing
     downstream. A benchmark that rebuilds the controller per step measures the
     uncached path and reports a cost the app never pays.
6. **`integrate` mode has no normalisation.** Each step draws more points than
   the last, so a colour scale that autoranges makes the early steps look empty
   and a fixed one makes the late ones saturate. Neither is wrong; there is
   simply no decision recorded. Deciding it (autorange per step vs. fix on the
   final frame) is what makes integrate mode readable rather than merely correct.
7. **Nothing exports a playback.** The obvious next thing a user asks for after
   watching a population move is a GIF/MP4 of it, and the screenshot helper
   (`utils/screenshot_helpers.py`) already grabs a single frame. Stepping it over
   the range and encoding is a small job that has not been done.
8. **ndX still owes a `?` and a Guide.** It is on
   `test/plugin_help_guide_allowlist.txt`: no `add_toolbar_help`, no
   `gui/guide.json` anywhere in the module. Every *control* now carries a
   `description` (the playback panel's are in its view spec, and AutoForm turns
   them into tooltips), but a dense window of documented settings is still
   unusable without a tour that says which control to touch first. The playback
   panel is the natural opening step of one, since it is the only control that
   changes what the plot means rather than how it looks.
9. **Tried and rejected: a fixed window width in seconds.** It was the first
   design, and it makes playback duration proportional to acquisition length — a
   three-minute playback of a one-hour measurement and an instant one of a short
   file. A fixed *step count* was chosen instead, so the wall-clock length of a
   playback is the same whatever the file; the width is derived and shown in the
   readout.

## Find informative projections: the views are ranked, not hunted

**View ▸ Find informative projections…** ranks every x/y pair and **View ▸ Find
informative projections (z axis)…** the third axis; both sit directly below
*UMAP* and, like it, are disabled while no table is loaded. Clicking a row sets
the axes. They started as buttons under the y picker and in the z panel; the
user found that position bad, so they became two `QAction`s declared in
`plotting/plot_main.ui` beside `actionUMAP` (one action per panel, as UMAP is one
action) -- which also puts them under `update_ui_enabled_state`, the same
data-gating UMAP gets, with no enable logic of their own. It is Orange3's VizRank
([what was taken and how it departs](../references/orange3-adopted.md)); the
theory of the three scores is `docs/concepts/multidimensional_exploration.md`
(*ranking the views*), the workflow `docs/guides/46_ndxplorer.md`.

| Piece | Where | What it owns |
| --- | --- | --- |
| framework | `ndxplorer/analysis/vizrank.py` | Qt-free `Ranker` / `AttrRanker` / `AttrPairRanker`, `run_vizrank` (score, then check cancel; throttled batches), `ScoreList`, `RunState` |
| scores | `ndxplorer/analysis/projection_scores.py` | `RankingTable` (one shared subsample, displayed coordinates), `knn_separation`, `correlation`, `cluster_index`, `ProjectionRanker`, `ParameterRanker` |
| panel | `ndxplorer/analysis/vizrank.view.json` + `analysis/vizrank_model.py` | the spec (drawn by `emtk.view_form`, the table a `data_table` section) and the Qt-free `VizRankModel`. It runs on an injected *runner* and continues through an injected `defer`: `chisurf.gui.task.run_in_background` and a zero-timer in the Qt window, `emtk.tasks` slices and the next frame in the emtk app |
| context + model | `ndxplorer/analysis/projection_rank_model.py` | `build_context` (numeric columns, axis settings as views, gates → rows, classes) and `ProjectionRankModel`, shared by both GUIs |
| Qt wiring | `ndxplorer/ui/projection_rank.py` + `ui/vizrank_panel.py` | `collect_context` (reads the Qt window, calls `build_context`), the controller (menu entries, apply, auto-select) and the Qt host window `VizRankWindow` |
| emtk wiring | `ndxplorer/app/features/playback_export.py` | the same panel in an `emtk.dialog_window.DialogWindow`, with its Guide tour and `?` help |

**What the classes are.** The gate (inside vs outside; all rows ranked), each
gate as its own population (bursts in exactly one gate), the clusters (noise
label dropped), and the z parameter (ids when ≤ 10 integer values, else a
quantity). Without a gate or clustering the panel opens on *population
structure*: the z parameter is always offered but is no sign the user wants
separation by it.

**Three traps, each found on the real MFD folder.**
* A 0/1 fit flag (`BIFL scatter?`, `r0 (green)`) is a perfect 2-means split:
  every top structure row was one. Structure skips columns with < 20 distinct
  values.
* A clump at a fit bound (`rho = 10⁴`, 2.7 %) is also a perfect split; the
  smaller group must hold ≥ 5 %.
* Excluding the gated parameter is not enough when a transform of it is a
  column: `E_tau` separated the τ gate trivially. Columns monotone in a gated
  one (Spearman |ρ| ≥ 0.98) go too; compound ones still leak (item 1 above).

**A data change discards the panel.** Its settings carry a key over the table
(`data_version`, columns, axis settings, gate keys); the z parameter and the
clustering only matter to a ranking separating by them. A stale panel is rebuilt
when its View-menu entry is chosen again.

## Playing a measurement back

A burst table is a time series: each row carries `Mean Macro Time (s)`, made
monotonic across every `.bur` file of a measurement by the reader
(`io/reader.py::_process_burst_analysis_dir`, which also rebases milliseconds to
seconds — the HDF5 and CSV readers do neither, so a table loaded that way still
spells it `(ms)` and restarts per file). A static 2-D histogram integrates that
time away, which is why a photobleaching sample and a stable one with broader
populations draw the same picture.

This used to be two features. An image stack got a frame selector — a spin box,
five transport buttons and a timer in the `Image` group box — and burst data got
nothing; the frame-column detector explicitly rejected any column whose name
contains "time". They are now one:

| Piece | Where | What it owns |
| --- | --- | --- |
| `PlaybackController` | `ndxplorer/core/playback.py` | Qt-free. Axis, mode, step, step count, bounds; produces the keep-mask and the scalar key it was built from. |
| `PlaybackViewModel` | `ndxplorer/plotting/playback_view_model.py` | The form binding, used by both GUIs, with no toolkit. Every field is a property forwarding to the controller. Playing is a flag plus a due time: `tick(now)` steps when a step is due, at most one per call. The emtk app ticks it from its frame loop, so it plays in a browser; the Qt window drives it with a `QTimer` it re-times on `on_timing`. |
| `playback.view.json` | `ndxplorer/plotting/` | The panel: axis combo, step count, step slider, transport row, mode radios, speed slider, live readout. Rendered by ChiSurf's [AutoForm](../subsystems/gui-autoform.md) as a foldable `panel`. |
| `setup_playback` | `plot_control.py` | Picks the axis after **every** load — frame index first, then macro time, else idle with all columns offered. |

The panel opens **folded** — it is the block a user sets up once and then wants
out of the way — and the fold state is remembered on the view model rather than
re-read from the spec, because the step slider's range is the step count and
changing it rebuilds the form. A spec that re-asserted `collapsed: true` on every
rebuild would fold the panel under the hands of the user who just opened it.

The three modes are three questions. `window` (`edges[i] <= v < edges[i+1]`) is
the population as it was then; `integrate` (`v < edges[i+1]`) is everything so
far, which converges to the static plot and shows a late-arriving population
arriving; `stack` is no gating, and is how a file opens.

Two details carry the design:

- **A frame index is the same gate.** Its bounds are pushed half a step outwards
  (`lo = -0.5`, `hi = n − 0.5`, one step per value), so a window over it reduces
  *exactly* to the `column == frame` the frame selector did. That equivalence is
  pinned by a test; without it the unification would be a second implementation
  wearing the same name.
- **The last step includes the top edge.** Half-open on every step leaves the
  largest value — the last burst, the last frame — in no step at all, so playing
  to the end shows an empty plot.

The slice reaches the data layer as `MaskState.slice_mask` plus
`MaskState.slice_key` (`core/data/mask_state.py`). The array is never in the
cache key: it is expensive to compare and, compared by identity, wrong. The key
is the scalars.

## The plot-control dock is folding, block by block

Playback arrived as an AutoForm `panel` and got a fold for free, which made the
asymmetry with the rest of the dock the obvious next thing. **Histogram** follows
(`plotting/histogram.view.json` + `histogram_view_model.py`), but by a different
route: its thirty-odd controls are the ones `plot_control.ui` declares, wired to
the axis/scale/histogram mixins by `objectName` and read from a dozen tests as
`control.comboBoxSelX`, `control.n_xhist_2d`, `control.xmin`. So the panel
**adopts** that widget instead of rebuilding it, through the `embed` section's
new `attr` option (chisurf-side: `embed` could only *construct* a fresh widget,
which is the wrong half for anything `uic` built and something else is wired to).

Wrapping it turned up a defect that had been there all along and was merely
hidden: `QGridLayout.replaceWidget` — used to swap four min/max spin boxes for
pyqtgraph's — takes the old widget out of the layout but leaves it a **child**,
and a child no layout positions draws at (0, 0). All four sat stacked in the
top-left corner as one spin box reading `0`. The group box's title bar had been
absorbing them; without it they landed on the x-axis row and ate the `x:` label.
`deleteLater()` was already being called and does not help: the deferred-delete
event is only processed when the event loop unwinds past the level the widget was
created at, which never happens for a panel built headlessly. `setParent(None)`
first, then delete. A test asserts no child of the histogram panel is outside a
layout.

`z axis`, `Draw Mask` and `Selection` followed the same way, so the dock is five
foldable panels and **no group box at all** — their order and fold defaults are
`plotting/plot_panels.view.json` rather than the `.ui`. Two of them were
*checkable* group boxes, and their check state was not decoration: it gated the
z plot and mask drawing. A collapsible box has no such state, and conflating the
two would mean a panel someone tidied away silently stopped gating, so each got
an explicit check box inside the panel — `checkBoxEnableZ` and
`checkBoxEnableDrawing`, which every call site now names.

A real AutoForm port of those controls — `value` and `choice` sections instead
of an adopted widget — is a separate change with a separate payoff (tooltips,
generated docs, state save/restore) and a large blast radius through the mixins.

## The window's docks are ChiSurf's

`plot_main.ui` declared five `QDockWidget`s and the window tabified three of them
by hand (`arrange_docks_preserving_geometry`, now deleted) and hid the other two.
They are one `DockArea` now (`utils/dock_conversion.py`), the same widget the fit
windows use: styled draggable tabs, drop-to-split in any direction, a context
menu, and an arrangement that could be persisted.

The panels themselves are untouched. A `QDockWidget` is a *container*, so the
conversion lifts its contents out — the widget `uic` built and everything else is
wired to — hands them to the dock area and disposes of the container. Three
details carry it:

- **Take the contents out before removing the dock.** `removeDockWidget` on a
  dock that still owns its widget takes the widget with it.
- **The attribute keeps its name and gains a new referent.** The window enables
  and hides these by name (`dockWidget_Parameters`, …), so each now points at the
  panel rather than at a container that no longer exists; otherwise every
  `setEnabled` becomes a silent no-op.
- **A dock tab is shown through the area, not by the widget.** The Fit action
  drove `QDockWidget.setVisible`; hiding the *widget* of a tab still in the bar
  leaves the tab there with nothing behind it. It calls `showTab`/`hideTab` now.

Panels stay on the left and the plot splits off to the right — where the Qt dock
had them, because moving a column someone reaches for without looking is a change
with no upside.

## Redraws: group and dispatch

Every control that changes what is on screen calls `request_plot_update`.
Requests inside one 40 ms window are grouped and dispatched **once**, with
`skip_clustering` OR-ed across the batch — so a control that fires continuously
(a dragged region, a spun value, a held key) costs one redraw per frame rather
than one per signal. `update_plots` is called directly only where the redraw has
to have happened before the next line runs: a load that just replaced the data,
the explicit *Update plot* action, and the parameter throttle, which times its
own redraw to size its next window.

Two things had grown around that rule rather than through it:

- **The z selector was polled, not listened to.** A 500 ms `QTimer` compared
  `selection_z.get_range()` against the last value it had seen; the region emits
  when it moves and nothing was connected. Measured on 200 000 bursts through
  the real loader, a paced 1.3 s drag got **4 updates — 3.1 per second** while
  one redraw costs ~25–40 ms. Connected to the region's live signal it is **20
  updates — 16.3 per second**, and the poll is gone. Listening to a *live* signal
  is cheaper than polling only because the dispatch is debounced; wired to an
  undebounced redraw it would be one redraw per mouse move.
- **Four handlers computed every histogram twice** — the z-axis toggle, the
  weight check box, the weight column and dynamic selection all called
  `update_histograms()` and then `update_plots()`, which fills them itself. The
  same pattern had been found and fixed once before, elsewhere, so it is worth
  grepping for the pair rather than assuming it is gone.

## Gating: one path, one answer

`plot_main._collect_mask_state()` is the only place the GUI is read to decide
which points are visible. It gathers drawn selections, the z-range, the isolated
cluster and the playback slice into a Qt-free `MaskState`;
`DataManager.get_value_mask()` applies all of them and caches on
`(data_version, state.key())`, deliberately returning the *same array object*
while nothing changed, because the histogram layer keys on that identity.
Polarity throughout: `True` means **excluded** in the value mask, `True` means
**keep** in the slice mask that feeds it.

## Related

- [AutoForm](../subsystems/gui-autoform.md) — the panel is a view spec, not widget code.
- [Burst companions](../subsystems/burst-companions.md) — where the columns ndX merges come from.
- [Burst analysis](burst.md) — the plugins that write tables ndX opens.
