---
type: Plugin
title: ndX on emtk (the port off PyQt)
description: The ndXplorer emtk app (modules/ndxplorer/ndxplorer/app), which is replacing the Qt window. It runs on a desktop and in a browser, and parity is proven scenario by scenario from screenshots.
resource: modules/ndxplorer/ndxplorer/app/
tags: [plugins, ndxplorer, emtk, port, parity]
timestamp: '2026-09-23T00:00:00Z'
---

The owner decided that ndX moves off PyQt onto emtk. The new app (`ndxplorer/app/`)
lives beside the Qt window until it reaches parity, and then the Qt GUI is
deleted. The same app object runs in a native window, in a browser (Pyodide +
WebGPU through `emtk.web`) and in the headless capture. Parity is judged by
**control inventory** against the Qt baseline shots: `tools/parity/scenarios.json`,
`parity/qt/`, the checklist `tools/parity/features.md`, and
`python -m ndxplorer.app.capture -s <id>` for the emtk shots. The core
(`frame`, `model`, `view_model`, `menus`, `plots`, `capture`) draws the window.
Everything else is a feature module in `ndxplorer/app/features/` that
registers through `create(app) -> Feature` (hooks are documented in
`features/__init__.py`). The ndX concept itself is
[ndxplorer.md](ndxplorer.md).

## Where to pick this up

### FRET calibration: population-wise factors, gating dimensions; z marginal (2026-09-24)

State: the options dialog (`analysis/fret_calibration_options.view.json`) has a
**Populations** panel. *Population-wise factors* off / auto (default) / on maps
to tttrlib `auto_calibrate`'s `species_factors` (off = False; auto = BIC
decides; on = ndX adopts the fitted per-population gamma whenever
`model_selection.identifiable`, `fret_result.force_species`). *Gating
dimensions* S, E, tau_d, tau_a, r_d, r_a (`CalibrationOptions.gate_*`; S alone
= `dimensions=[]`, the stoichiometry gating); `fret_backend.dimension_columns`
maps them onto burst columns (tau_d = tttrlib's `tau_f` role, the rest by
`DIMENSION_HINTS`), the dialog disables and explains the ones a table lacks
(emtk adf4cb5: tooltips on disabled items). *Population finder* (gmm /
hdbscan) is `population_method`, passed only when the installed tttrlib has it
(`population_method_reason()`), otherwise disabled with the reason. The report
window and text show mode, gating, selected model with both BICs, identifiable,
and the vectors written (`gamma[FRET 1]`…). The ChiSurf bridge
(`optimize_calibration_from_ndx`) takes the same three options. The z marginal
(Plot controls > z axis) is 100 px by default and resizable from the grip under
it (`docks.ZMARGINAL_*`, kept as layout extra `plot_controls.zmarginal_h`).

Measure: `ndxplorer/tests/test_fret_population_options.py` (synthetic
two-species bursts with gamma 0.6/1.2 and lifetimes: auto and on give
gamma[FRET 1/2] within 8 %, BIC 4.2 vs 125.6; on forces per-population gamma
on a shared sample; off writes no vectors; cal1 in every mode γ 0.7502 α
0.1570 β 1.0599 δ 0.0674). cal1 in the app: never identifiable — its table has
no lifetime column, the app's equation column `<tauD(A)>x` is picked as tau_f
but only one of the two FRET populations lies on the static line (n_obs 3);
auto with S,E,tau_d gating: 28.8 s, 3 FRET populations, still shared, γ 0.4317
β 1.5802 δ 0.0564 (S-only 4.5 s). Trap: the cal1 `.pto` in tttr-data already
carries a stored calibration with a `gamma` vector (0.4536, 0.8090), so the
Parameters tab shows gamma[FRET 1/2] on open regardless of the run; captures
work on a copy.

Next:
1. Wire `population_method` to the tttrlib HDBSCAN option once it lands (name
   and values to be confirmed; the dialog enables itself when
   `tttrlib.AutoCalibrateOptions` has the attribute and `_AFRET_OPTION_KEYS`
   lists it).
2. A run that selects shared gamma leaves an older `gamma` vector in the window
   (stored or from an earlier run); the report says "none written" but the
   Parameters tab still has it. Decide whether a written scalar gamma should
   make an existing gamma vector scalar (today: the user does Make scalar).
3. The Qt window's AutoForm shows the Populations panel but does not disable
   unavailable dimensions; the backend drops them with a note.

### `.pto` without ChiSurf (2026-09-24)

State: ndX reads and writes `.pto` containers with tttrlib alone.
`ndxplorer/io/container.py` (open/commit/lock bracket) over tttrlib's PTO.MFDB
layer (`pto_tag`, `pto_parents`, `pto_read_blob`, `pto_add_blob`,
`PtoWriteLock`, `deinterleave_burst_rows`; tttrlib `ext/python/PtoMfdb.py`).
`io/pto_reader.py` reads the burst search + companions (or, with no bursts, the
newest `pixel`-grain image table) and the provenance; `analysis/fret_background`
reads the stored background (`stored_rates`); `io/fret_calibration_io` saves
(locked, described blob, FIFO of 5), lists, loads and computes `restorable()`
(newest saved calibration + background, newer wins Bg/Br/By). The emtk app
applies `restorable()` on open (`AccurateFretFeature.restore_stored`, once per
stored value); ChiSurf's bridge uses the same for the Qt window.

Measure: `ndxplorer/tests/test_fret_backend_without_chisurf.py` (fresh process,
`sys.modules["chisurf"/"IMP"/"IMP.bff"] = None`): cal1 and bh_spc132 `m000.pto`
columns equal ChiSurf's `Measurement.get_store` + `deinterleave_bursts`;
`background="measurement"` gives Bg/Br/By = the stored rates; save → load in a
copied `.pto`. Browser: `NDX_TTTRLIB_WHEEL=<tttrlib dev Pyodide wheel> python -m
ndxplorer.app.web`, drop cal1: default FRET calibration γ 0.7502 α 0.1570 β
1.0599 δ 0.0674 (desktop equal); measurement background γ 0.7737 α 0.1432 β
1.0230 δ 0.0430 both places. Trap: the cal1 burst table is stored with the
legacy `2N+1` zero-row interleave — any reader that skips
`deinterleave_burst_rows` sees 88541 rows instead of 44270, silently.

Next:
1. The Qt window's Load (`chisurf/plugins/ndxplorer/window.py`,
   `_load_calibration`) and the bridge's restore on open apply only the flat
   constants (`gamma[FRET 1]` as a plain name), not the stored vector constants
   (`restorable()["vectors"]`), which the emtk app applies through
   `write_vector`. Uncertainties are saved by population, not by position.
2. The "accurate fret calibration" factor table (ChiSurf's Accurate FRET step)
   is still read only by ChiSurf's bridge (`calibration_from_container`, it
   needs `calibration_columns`); the emtk app does not restore it on open.

### Parameter tables and the parameter model (2026-09-24)

State: every parameter table of the emtk app (Gaussian Fit, Parameters, an
overlay curve, the curve fit's two tables) is one `data_table` section,
`ndxplorer/app/views/parameter_table.view.json`, over
`ndxplorer/app/parameter_table.py:ParameterTable`; a feature spec writes
`{"type": "parameter_table", "table": "<attr>"}` and `expand()` inserts it with
dotted model names (`table.rows`, emtk 743319a). Content-sized columns, Lo/Hi as
bound or −∞/∞ (no Bounds column), Link only while something is linked,
Copy/Paste/Link…/Unlink. The parameters are ndX's own
(`core/parameters.py`: Parameter, ParameterGroup, registry, `link_targets`);
Gaussian EM is numpy, curve fit is scipy — all run with chisurf and IMP blocked
(`ndxplorer/tests/test_works_without_chisurf.py`). With chisurf,
`core/chisurf_binding.py` mirrors a registered group as FittingParameters (push
on write, pull on read) for the Global View, links from fits, and the Qt
window's ChiSurf tables (`chisurf_group`, `mirrored_list`).

The reported bug ("parameter edit does not work", Gaussian ρ typed as -0.1571):
the emtk DataTable committed a cell only on Enter or a press *inside* the
table; a click elsewhere left it open and uncommitted forever (fixed in emtk
8e33b9e, plus U+2212/∞ parsing and text typed with Enter). A press the menu bar
takes never reaches the tables; `NdxApp._press_overlays` commits open cells.
Measure: `ndxplorer/tests/test_app/test_parameter_tables.py` drives real
double-click, keys, Enter / click-away.

One mirror, 2026-09-24: the ChiSurf-hosted Qt window no longer builds its own
copy of the constants. `chisurf/plugins/ndxplorer/parameters.py`
(`NdxConstants`, `bind_ndx_parameters`) and the Qt toolbar's "⟲ Sync
constants" are gone; `chisurf/plugins/ndxplorer/window.py::_bind_global_view`
publishes `ndx.constants_group` through `chisurf_binding.publish(..., "ndxplorer",
"ndX constants")` and withdraws it on `destroyed`. Trap: the window builds its
parameter editor in `_deferred_init` (a zero timer), so at construction
`constants_group` is `None`; the publishing waits on a timer the window owns.
Load calibration writes through `calibration_bridge._push_constants` (the
table), not by replacing `ndx.constants` with a dict. The curve-fit dialog
releases its loose mirrors on close (`chisurf_binding.release`, ndxplorer
7492d18). Measure: `chisurf/plugins/ndxplorer/tests/test_window_routes.py`
(both routes publish the window's own group's mirror, label `ndX constants`,
and the slot empties when the window is destroyed; it fails if
`_bind_global_view` is dropped), `test/fitting/test_global_view_parameters.py`,
`ndxplorer/tests/test_ui/test_curve_fit_dialog.py::test_closing_the_dialog_drops_the_fits_mirrors`.

Next:
1. The ndX editor registers the same group as `"ndX"` in nDXplorer's own
   registry; the Global View label is `"ndX constants"`. One name would do.
2. `chisurf/plugins/ndxplorer/tests/test_calibration_options.py::test_the_options_map_onto_the_bridge`
   fails at HEAD (2026-09-24): `population_method`, `species_factors`,
   `dimensions` in the options have no parameter in
   `optimize_calibration_from_ndx`. Not from this change; the FRET work owns it.

### Browser (the app in a Pyodide + WebGPU page)

Run `python -m ndxplorer.app.web` (arm64 env) from the ChiSurf checkout root. It
serves http://localhost:8795/. The Zed task `ndx-emtk-web` runs the same command.
Take the measurement in a headless Chromium with WebGPU: playwright in `~/opt/playwright-venv`,
flags `--enable-unsafe-webgpu --enable-features=Vulkan,WebGPU --enable-gpu
--ignore-gpu-blocklist`. On macOS this gives an `apple metal-3` adapter in headless mode.
Feed a real folder drop through CDP (`Input.dispatchDragEvent` with
`data.files=[<folder path>]`). A synthetic `DataTransfer` cannot carry a folder.

1. **Works, 2026-09-23.**
   - Boot takes 11–45 s from the Pyodide CDN, and there are no page errors.
   - Dropping `test/mfd/burstwise_All 0.1500#30` opens it on the default axes. It
     shows Tau (green) × Proximity ratio, 12237/12237 bursts, and colour limits
     1.00e+00 / 2.01e+02, the same as the desktop.
   - Dragging a rectangle on the map gives two interval gates (3272 bursts kept).
   - Selection *save* goes through the emtk file dialog and then downloads
     `gates.selection.json`.
   - A single `.bur` drop works too.
   - **With the IMP.bff wheel (second round):**
     - The Parameters tab has real constants that can be edited: Bg 1.2 → 1.5
       takes, and `constants.values()` reads 1.5.
     - Overlays: *FD/FA vs tau (static line)* + *Add Curve* draws the line on
       Fd/Fa × Tau (green).
     - The curve-fit dialog's *Fit* frees kf, which goes from 0.2 to 0.205304
       (reduced χ² 11.21).
     - Gaussian Fit: three seeds clicked on the map, then *Fit*, gives
       "Fitted 3 Gaussians" with separate populations. Two seeds from *add*
       start at the same default point and fit as one symmetric pair, and the
       desktop does the same.
     - Find structure, K-means: the result matches the desktop. On Proximity
       ratio and `<tauD(A)>x` the page gives 6889/2017/3331 and native gives
       6904/3333/2000 (same clusters in another order, about 15 bursts
       moved), and the map colours three bands. On `Tau (green)`, K-means
       gives 12232/1/4 both natively and in the page: the column runs to
       13212, and K-means does not scale its input. That is a property of
       the method, not of the browser.
     - Screenshots: scratchpad `ndxweb/shots2/01…06_*.png`.
2. **What the page carries.** See `ndxplorer/app/web.py`:
   - ndxplorer and emtk;
   - chisurf's Qt-free core (`__init__`, `_bundled_packages`, `core`, `settings`)
     and `mmfdb/config.py`;
   - chimol's readers (`chimol/__init__.py`, `chimol/io`, about 1 MB).
     `chisurf.core.fitting.fit` imports `chisurf.core.experiments`, which
     imports every experiment type. The modelling type reaches
     `chisurf.core.fio.structure`, which takes `atom_dtype` from
     `chimol.io.atoms` at module level. Shipping these readers was chosen
     over reshaping chisurf's experiment registry for one host;
   - from Pyodide: numpy, scipy, pyyaml, matplotlib, Pillow, scikit-learn and
     **lzma** (`chisurf.core.fio` imports it);
   - the tttrlib wheel (`$NDX_TTTRLIB_WHEEL`, else `~/dev/worktrees/tttrlib-pyodide/dist/pyodide`);
   - the IMP.bff wheel (`$NDX_IMPBFF_WHEEL`, else `~/dev/worktrees/imp.bff-pyodide/dist/pyodide`).
     It is optional: without it, Gaussian Fit and the overlay curves say on
     their tabs why they are off.

   Nothing native was cut. The one fix in chisurf itself: `chisurf.core.settings`
   copied the Qt style sheets from `chisurf/gui/styles` at import and failed
   without the GUI package. It now skips that step.
3. **Open, found in the page:**
   - **Keys faster than frames.** `io.key` holds one key per frame. Six
     Backspaces sent together delete one character, so an edit typed fast
     parses wrong and reverts. Typed text already adds up (item 5). Special
     keys need an input queue in emtk `IO`, as ImGui has one. Until then,
     tests press keys about 100 ms apart.
   - **Greek letters.** χ and σ draw as `¤` in the page: σ in the Gaussian
     table, χ² in the fit dialog. The baked glyph atlas has no Greek. A
     desktop rasterises them on first use.
   - Overlay curves and Gaussian ellipses stay on the map after the axes
     change. Check whether the Qt window does the same.
4. **Not taken yet in a page:**
   - *Mount folder…* (needs a picker; `emtkMountDirectory` with an OPFS handle is
     the test route);
   - PCA, HDBSCAN and UMAP (UMAP says it cannot run: numba);
   - Load/Save Mask (`tttrlib.imread`/`imwrite`);
   - export and report downloads.
5. **Fixed on the way.** The headless tests draw twice after every event, which
   hid both of these:
   - A frame that changes the data now asks for the next frame
     (`ExplorerModel.stale`, `NdxApp.animating`). Before, a gate showed the
     old counts until the pointer moved.
   - Typed keys add up between frames. Before, `gates` typed fast became `ges`.
     The same fix went into emtk `ImApp` (`6287fba`).
   - emtk `boot.js` takes a dropped **folder** (`copyDropped`, which walks the
     entries). It landed inside `b49285a`; its test is `ffc832d`.
6. **Trap.** Running from `~` breaks the build: `~/chisurf` is a namespace
   package that shadows chisurf. `web.py` now refuses it rather than shipping an empty
   package.

### Vector parameters (one value per population) — 2026-09-23

**Model.** A constant can be a vector over populations: its elements are
ordinary constants named `base[label]` (`gamma[HF]`), each its own chisurf
`FittingParameter` (own value, fixed, bounds, link, own IMP.bff port); the plain
`base` is the global value for a burst in no population. One vector-valued
GraphPort was not used: bounds/fixed/link are per port, so one port per element
is what keeps them per element. Order, axis and uncertainties live on the group
(`_ndx_vectors`) and in the rich file's `"vectors"` entry. Code:
`ndxplorer/core/vector_constants.py` (pure), `core/constants_group.py`
(`set_vector`, `to_vector`, `to_scalar`, `vectors_state`, `ConstantsMapping.set_vector`).

**Equations.** `'gamma'` naming a vector is evaluated per burst: the element whose
code equals the burst's label column (default `Cluster Label`; int labels are
their own code, names their position, or `codes`), or the mix
`sum p_k gamma_k / sum p_k` when every probability column of the axis exists,
else the global. `'gamma[HF]'` is one element as a scalar. A changed element
recomputes what reads its vector; the tab re-hashes the axis columns twice a
second, so re-clustering recomputes too. A plain dict carrying `gamma[..]` keys
(the Qt window, a calibration's `constants`) is read the same way on the default axis.

**UI** (`features/constant_rows.py`, `overlays.py`, `parameters.view.json`,
`vector.view.json`): parent row `▸ gamma [2]  0.61, 0.83`, children `(global)`
and one per population; right-click *Make vector…* / *Copy values* / *Paste
values* / *Populations…* / *Make scalar*; per element Copy/Paste/Link/Unlink.
Add parameter has Scalar/Vector. Lo/Hi always show a value (`−∞`/`∞` when
unbounded; typing sets, clearing removes); the Bounds column is gone; Link shows
only while something is linked; columns fit their contents. emtk gained
`data_table` trees (`tree_key`, `expanded_attr`), elided-cell tooltips, info
`source` as property, Greek and math glyphs in the web atlas.

**Calibration API** (for `features/accurate_fret.py`, not edited here):
`app.model.manager.constants.set_vector(name, values, populations,
uncertainties=None, default=None, column=None, probabilities=None, codes=None)`
then the tab's `poll()` (their `write_constants` already polls), or the panel's
`feature.constants.set_vector(...)` which also opens the row and recomputes.

Open items:
1. The calibration file (`io/fret_calibration_io.py`, the FRET agent's) writes the
   elements flat with `sort_keys=True`: values round-trip, but the population
   order becomes alphabetical and a non-default axis column/probabilities are
   lost. Fix there: store `constants_group.vectors_state(group)` and restore via
   `set_vector` on load.
2. Settings > Load settings applies values only (`install()`); a rich file's
   `"vectors"` axis is read when the tab builds, not on a later load.
3. The legacy Qt table shows vectors read-only under the table; the Global View
   (`chisurf/plugins/ndxplorer/parameters.py`) already publishes each element
   as `name[pop]` — test `test_vector_constants_published.py`.
4. Screens checked: offscreen, native window, Pyodide page (per-population
   recompute verified in the page). Tests: `tests/test_vector_constants.py`,
   `tests/test_app/test_vector_parameters.py`, `tests/test_ui/test_parameter_editor_vectors.py`.

### Accurate FRET (what the ChiSurf-hosted Qt window adds) — 2026-09-23

The Qt window has Accurate FRET only when ChiSurf's ndX plugin decorates it,
and the first baseline had only standalone ndX. Now both are captured.

* **What ChiSurf adds** (`chisurf/plugins/ndxplorer/__init__.py`, `rpc_bridge.py`):
  the ChiSurf Phasor toolbar and panel, the "Send selection to" targets, the
  calibration restore when a `.pto` is opened (all from `make_ndxplorer`'s
  in-process RPC client and subclass); the Accurate FRET toolbar (FRET
  calibration, Save calibration, Load calibration, Sync constants); the MMFDB
  toolbar; the constants in the Global View (`bind_ndx_parameters`). Not GUI:
  `cli.py` (`filter`/`image`) and `mmfdb_launcher`. Full inventory: the
  "ChiSurf-hosted window" part of `tools/parity/features.md`.
* **Baseline:** `capture_qt.py` scenario key `"host": "chisurf"` runs the
  plugin's `__init__.py` as ChiSurf's ribbon does. Scenarios `chisurf_toolbars`,
  `accurate_fret_options`, `accurate_fret_run`, `calibration_save_load`,
  `mmfdb_open`, `chisurf_phasor`, on `~/dev/tttr-data/sm/cal1/…_alex.pto`
  (dataset `cal1_alex`, opened as a copy in the scratch `$HOME` because a run
  writes into the container). Qt run: α 0.1570 ± 0.0020, δ 0.0674 ± 0.0005,
  γ 0.7502 ± 0.0069, β 1.0599 ± 0.0043; 2945 donor-only, 9740 acceptor-only,
  2 FRET populations (E 0.335, 0.937); about 10 s per run.
* **emtk:** `ndxplorer/app/features/accurate_fret.py` (+ `accurate_fret/*.view.json`):
  a **FRET** menu before Help (FRET calibration…, Save calibration…, Load
  calibration…), always there, not only under ChiSurf; the options are
  `ndxplorer/analysis/fret_calibration_options.view.json`, the same file the
  Qt AutoForm shows; progress with Cancel on `emtk.tasks`; a report window
  with factor, population and constants tables and the full text; save/load
  through the `.pto` or `app.io_service`. File > Import > "From MMFDB… (only
  inside ChiSurf)" is disabled. No toolbar button (the map's space).
* **Moved, not copied, out of the ChiSurf plugin into ndX:** the options model
  and its form (`ndxplorer/analysis/fret_calibration.py`; the plugin's
  `calibration_options.py` keeps only the Qt dialog), the report text
  (`report_text`, which the plugin now calls), and `calibration_io.py` ->
  `ndxplorer/io/fret_calibration_io.py` (with its test). The plugin package
  no longer imports Qt at import time (the GUI imports sit in the `plugin`
  block).

Where to pick this up:

1. **Wire the backend.** The algorithm is being moved into a compiled library
   (board T-20260923-afret). The emtk app calls
   `fret_calibration.calibrate(columns, constants, options, container=, progress=)`
   and applies the result itself (`apply_result`: constants, then the new
   columns); the result keys are listed in its docstring. Until a backend is
   installed (`fret_calibration.set_backend`), Calibrate is off with the
   reason. When the library exists: install it as the backend, and make
   ChiSurf's `calibration_bridge.optimize_calibration_from_ndx` a thin caller
   of the same `calibrate`, so both windows run one path.
2. **Measured agreement, and how to re-take it.** With ChiSurf's current Python
   behind the contract (a scratch adapter, not shipped: `DataSource.from_columns`
   + `optimize_calibration_from_ndx` on a stand-in window), the emtk run on
   the cal1 `.pto` gives α, β, γ, δ and their uncertainties bit-identical to
   the Qt run, and the same report text. **Trap:** only from the same starting
   constants. The hosted Qt window restores the container's stored
   calibration on open (PhiA = PhiD = 1, gG/gR 1.333…), the emtk app opens with
   the settings' (PhiA 0.32, PhiD 0.8). α β γ δ still agree, but the equation
   column `<tauD(A)>x` differs, so the lifetime-route γ (0.548 vs 0.433), τf
   and gG/gR do.
3. **Open: restore on open.** `calibration_bridge.restore_calibration_from_container`
   (factor table, background artifact, saved constants) is held with the
   library move; port it as the emtk app's `on_data_changed` once the bridge
   is split. It is what item 2's trap is about.
4. **Open: per-population factors.** Another agent is making the constants
   vector-valued (owns `features/overlays.py`, `core/constants_group.py`, the
   equation engine). The feature writes global scalars through
   `AccurateFretFeature.write_constants` today; switch that to the vector API
   (population-wise γ/β/α/δ with uncertainties) when it exists.
5. **Open: Global View.** The emtk constants group is registered in ChiSurf's
   parameter-group registry (owner `ndxplorer`, the slot the Qt plugin uses),
   so it reaches the Global View as soon as the emtk app runs in ChiSurf's
   process; no ChiSurf plugin hosts the emtk app yet. "Sync constants" is not
   needed then (one group, no copy).
6. **Open: ChiSurf Phasor** (`chisurf_phasor`): needs a ChiSurf RPC client in
   `NdxApp` (`--chisurf-rpc` does not reach it).
7. **Browser.** Nothing in the feature imports Qt (tested). What blocks a
   calibration in the page is the missing backend, as on the desktop; the
   file save/load works there through the io service, and the container
   route needs `chisurf.core.fio.pto`. Not yet run in a page.
8. **ChiSurf bugs found here, fixed since** (2026-09-23): the MMFDB toolbar
   never appeared (a private `MMFDBClient(inprocess=True)` without a session
   token), and the menu route built a window without the Accurate FRET and
   MMFDB toolbars and the Global View binding. Both routes now call
   `chisurf.plugins.ndxplorer.window.build_ndxplorer_window`; see
   [ndxplorer](ndxplorer.md), *One window, whichever way it is opened*.

Re-measure: `python -m ndxplorer.app.capture -s chisurf_toolbars -s accurate_fret_options
-s accurate_fret_run -s calibration_save_load -s mmfdb_open` (with no backend the
run and report shots are not taken: install one first), `pytest
ndxplorer/tests/test_app/test_accurate_fret.py ndxplorer/tests/test_fret_calibration_io.py`,
and chisurf `chisurf/plugins/ndxplorer/tests`.

### Plot window space (toolbar, corner, marginals) — 2026-09-23

The map gets most of the window now. ndxplorer `1a21cc2`, `d51142c`, `8a5be94`,
`8252d86`; emtk `843bfdf` (`DockManager.set_extra`/`extra`: app values saved with
the layout), `75c59c9` (a `"field": false` slider: value on the slider, double
click to type), `3b69002` (a row's `"wrap_indent": false`: a toolbar wraps to the
left edge), `fa88ced` (a wrapped row is cut as evenly as its breaks allow).

* **Layout.** Toolbar (`views/plot_header.view.json`): Path, Browse, then
  colormap, log #, vmin, vmax, Contrast, Update. One line at 1120 and wider,
  two at 992, three at 735. The corner between the marginals
  (`views/plot_corner.view.json`) holds the counts "43283 / 44270", inf/NaN and
  Screenshot/Data/Export…/Clear two by two. When the user drags the marginals
  too small for it (under 110 px wide, or shorter than it measured), it goes to
  the toolbar's end (`NdxApp.corner_in_toolbar`; `NdxApp.control_rect(name)`
  finds a control in either place). The marginals are 96 px (x) and 132 px (y)
  by default. The bars between them and the map (`hsplit`/`vsplit` in
  `plot_boxes`) resize them, and the sizes are kept in the layout file under
  `extras` (`plot.xmarginal_h`/`plot.ymarginal_w`). *Reset window layout*
  forgets them. The x marginal's title is inside its plot, top left, so its
  tick labels sit right under the toolbar. The status line is in the menu bar's
  row, right-aligned. The left dock's share is 0.29, and its floor stays 405.
  Playback's Step and Speed are one slider each. The z marginal is 56 px, with
  two count labels (0 and a round top).
* **Default window 1120x720** (`launch.SIZE`, three quarters of a 1470x949
  work area). Parity captures stay at 1400x900 (`capture.WINDOW`). emtk.docking
  does not persist the OS window size, so `--size` or the default always wins.
* **Measure** with `Replay(...).app.plot_boxes["map"]` after opening
  `test/mfd/burstwise_All 0.1500#30` in a scratch `$HOME` (a real `$HOME` reads
  the user's saved split ratio). Map area was 636x647 = 411k px², 32.7 % of the
  window at 1400x900, and 389x388 = 151k px², 25.7 % at 992x593. It is now
  851x736 = 626k px², 49.7 % at 1400x900; 443x409 = 181k px², 30.8 % at 992x593;
  571x556 = 317k px², 39.4 % at 1120x720. Guards:
  `test_window_sizes.py` (six sizes: nothing clips, the corner holds its
  controls, vmin/vmax show "2.01e+02" whole) and `test_docks.py` (bar drag
  resizes and persists; small marginals send the corner to the toolbar).
* **Trap: the user's own layout keeps their split.** `~/.ndxplorer/ndxplorer_layout.json`
  has `root: 0.3936`, so their window keeps a wider left dock until View >
  Reset window layout. A real-screen check of the defaults needs
  `NdxApp(layout_store=None)`, as `scratchpad/space/realrun.py` did.
* **Tried and not done: hiding a lone window's tab strip** (the Plot's). It
  would save about 20 px, but the strip is the only handle to undock, drag and
  close the window, so hiding it loses a control. Revisit only with another
  handle, such as a grip that shows on hover.

Open:

1. On a very narrow floating Plot (under about 400 px) the toolbar takes 4-5
   lines. That is correct, but a lot of it. A compact colour group (vmin/vmax
   beside the colormap in one control) would help.

### docks (every dock a sticky window)

Built on emtk's window manager, `emtk.docking` (emtk `a4bda9d`, `1fa683b`,
`cfb404b`; its example is `python -m emtk.native --app examples.docking:make_app`
from the emtk checkout). ndX side: `ndxplorer/app/docks.py` and ndxplorer
`122f008`. There is a left and a right region. Plot controls, Parameters,
Overlays, Equations and Gaussian Fit are tabs on the left, and the Plot fills
the right. Equations and Gaussian Fit start hidden and View opens them.

Re-measure:

* `pytest ndxplorer/tests/test_app/test_docks.py` covers the default layout,
  every View toggle, close with × then reopen, and persistence. It also checks
  that a bare `NdxApp()`/`Replay` never reads or writes the user's layout.
* The scenarios `open_mfd_folder`, `parameters_panel`, `equations_panel`,
  `gaussian_fit`, `menu_view` and `colour_log_contrast`, compared by control
  inventory. The 2026-09-23 pass found no control missing. What changed on
  purpose: a × on each region's strip, the View entries *Plot* and *Reset
  window layout*, and a status row kept along the bottom.
* In the page, the Playwright drive `dock_drive.py` goes through default,
  tab, float, drop preview, re-dock, close, View reopen and reload. The layout
  comes back after the reload, from `localStorage` key `emtk.layout.ndxplorer`.

Open:

1. ~~A small floating Plot crowds its corner~~: resolved 2026-09-23. The corner
   controls move to the toolbar when the corner is too small (see *Plot window
   space*).
2. **The layout file is keyed by window title.** Renaming a window drops its
   saved place: it comes back at the default, which is harmless.
3. **Trap: a `Replay` built outside `scratch_home` must not get a store.**
   One did, and the tests wrote `~/.ndxplorer/ndxplorer_layout.json`. That
   leaked a Gaussian Fit tab into later runs, where it hid the Cluster
   button. Only `capture_scenario` passes `layout_store()`, inside the
   scratch `$HOME`.

### core (window, main view, hooks, capture)

Re-measure with `python -m ndxplorer.app.capture -s open_mfd_folder -s axes_fdfa_tau
-s axes_log_norm_bins -s colour_log_contrast -s menu_file -s clear_plot -s startup_empty`
(arm64 env; every scenario runs in a scratch `$HOME`) and `pytest
ndxplorer/tests/test_app/test_emtk_app.py ndxplorer/tests/test_qt_free_logic.py`
(the core tests build `NdxApp(features=[])`). Compare each shot with `parity/qt/`
by control inventory; the ticks are in `tools/parity/features.md`.

1. **Parity status, 2026-09-23 (final pass).** `tools/parity/features.md`:
   249 [x], 35 [~], 2 [-], 0 [ ]. `python -m ndxplorer.app.capture` (all 61)
   then `python3 tools/parity/compare.py`: every scenario PARITY except
   `fix_report_tool`, dropped on purpose (the module never existed; the entry is
   gone from both GUIs), which the report lists as NOT STARTED because no shot
   can exist. The look is emtk's and ImPlot's default (user directive).
   Deliberate differences: `log #` re-derives vmin/vmax in log10 units; Print
   window saves a picture; Exit is disabled in a browser.
2. **Window title** is done: `NdxApp.window_title` ("ndX - <file>"), carried by
   every emtk host (emtk `b49285a`).
3. **Check on a real Retina screen** after the emtk HiDPI fix (emtk `d7d1f23`
   and later): offscreen captures run at ratio 1. The view specs still use
   fixed pixel widths for bins (58 px) and buttons; re-check them for clipping
   at the real ratio. The docks are becoming emtk dock windows (another agent,
   `app/docks`); re-capture after that lands.
4. **Browser boot: taken.** See the Browser item above (`python -m ndxplorer.app.web`).
5. **Hooks** (`features/__init__.py`): actions/available/fields, menu_entries,
   custom_sections (`playback`, `draw_mask` in the core spec), tabs,
   draw_windows, draw_plot/plot_input, mask_terms, map_image, on_data_changed,
   on_z_select, animating, files_dropped, capture_ops/targets/actions; plus
   `NdxApp.open_menu` and `show_status`. Add a hook rather than editing a
   feature from the core.

Qt-free logic both GUIs call (moved, not copied): `core/gates.py`,
`core/histograms.py` (display_counts, colour_limits, auto_contrast_limits),
`plotting/colormap_lut.py` (pyqtgraph's map files read without pyqtgraph),
`settings/bundle.py`, `utils/axis_helpers.settings_for_axis`,
`DataSource.merge(warn=...)`. emtk gained on the way: view_form folds, fixed
widths, host-drawn custom sections, spin boxes (`style: "spin"` / `spin: true`),
combo-box choices, data_table editing (check boxes, cell edits, delete),
`FileDialog(mode="folder")`, `Texture(filter="nearest")`, windows with an opaque
background, edge tick labels kept inside the frame, labelled minor ticks on
short log axes, `Style.frame_border_size`, the Qt host honouring `animating()`.

### selection (gate table, context menus, pick population, z gate, draw mask, NaN/inf, weights)

Re-measure with `python -m ndxplorer.app.capture -s gate_rectangle -s gate_invert_disable
-s selection_table_menu -s canvas_context_menu -s pick_population -s z_axis_dynamic
-s z_add_selection -s draw_mask -s mask_nan_inf_off -s weights`, and run `pytest
ndxplorer/tests/test_app/test_selection.py ndxplorer/tests/test_qt_free_logic.py` plus
(Qt, offscreen) `ndxplorer/tests/test_ui/test_gate_table.py`.

1. **Parity status, 2026-09-23: all ten scenarios captured and ticked** in
   `tools/parity/features.md`. Counts match the Qt shots: weights, NaN/inf off
   (12237/12237), z dynamic and z select (1725). The two gate-drag scenarios
   differ by a few bursts, because the drag fractions land on a slightly
   different plot box. Deliberate differences:
   - Min and Max open for typing on a double click. A double click on
     Parameter deletes the row.
   - No row numbers.
   - Send to Napari is disabled with a reason, and there is no installer
     prompt.
   - Menu rows have no tooltips.
   - The `pick_population` "refused" shot shows the working pick.
2. **One gate list.** `core/gates.GateList` (ndxplorer `8a6d77e`, `2ae93e8`) is
   the Selection table in *both* GUIs. A mask or region row keeps its object
   as `GateRow.selection`, and `stored_selections` is gone. The Qt table is
   rebuilt from the list and writes its edits through `GateList.edit`, and
   `plot_control.get_selections()` is `gates.selections()`. The API change:
   `addMaskSelection`, `addRegionSelection` and `add_region_selection` became
   `plot_control.add_selection_object(sel)`.
3. **Fixed rather than copied** (both marked "Qt: broken"):
   - **Pick population.** The fit is `core/population_pick.fit_population`,
     and both GUIs use it (the Qt fix is `dbc4891`). It works in
     display-scaled units: it climbs to the local density maximum, grows the
     population downhill to 25 % of the peak, and divides out the
     truncation. A Qt canvas click now goes through the histogram edges,
     because the view box is in bin indices.
   - **Draw Mask.** `core/mask_paint.MaskCanvas` does the painting. The Qt
     side's painting is still broken (`PGImageWidget.invTransform`
     NameError), and nobody owns that fix. The Qt GUI is to be deleted.
4. **Browser, not yet run in a page.** The selection code imports without Qt
   (a subprocess test checks this). In the browser, "Send selection to" and
   "Send to Napari" are disabled and give the reason. Copy uses
   `emtk.clipboard` (the host hook, then `navigator.clipboard` under
   Pyodide, then pbcopy/clip/xclip). Load/Save Mask use `tttrlib.imread`
   and `tttrlib.imwrite`, so they wait on the tttrlib Pyodide wheel.
5. **Performance, measured.** One recompute with an interval pair, a G2D gate
   and a dragged z range takes ~4 ms at 1e5 rows and ~15–20 ms at 1e6. The
   recompute runs at most once per frame, however many changes arrive. That
   frame coalescing is the debounce, and it needs no timer. A pick takes
   ~15 ms at 1e5 rows and ~140–200 ms at 1e6 (a one-shot action).
6. **Open:** `z_add_selection` "during playback the slice is added as a gate
   too" (playback group, `on_z_select`). The ChiSurf RPC client of the emtk
   app is never set: `app.chisurf_rpc` is `None`, so Send always says "No
   ChiSurf connection". The `--chisurf-rpc` CLI flag does not reach
   `NdxApp` yet.

emtk additions: `DataTable` Select All (`also_selected`, `select_all`,
`selected_indices`), where Delete removes every selected row and a right click
inside the selection keeps it (`b945263`, `4699396`), and `emtk.clipboard`
(`93a9a8c`).

Tried and reverted: a Mahalanobis re-centring fit (grow the ellipse and divide
out the truncation at each pass). On the MFD data, clicking the diffuse FRET
cloud absorbed the dense donor-only population next to it: 9584 bursts in
one ellipse. The density-watershed search replaced it.

### overlays (Parameters, Overlays, curve fit, Equations, Table Editor)

Re-measure with `python -m ndxplorer.app.capture -s overlays_curve -s overlays_equation_list
-s curve_fit_dialog -s parameters_panel -s add_parameter -s equations_panel -s store_editor`
and `pytest ndxplorer/tests/test_app/test_overlays.py`; the Qt side with (offscreen)
`ndxplorer/tests/test_ui/test_curve_fit_overlay.py test_curve_fit_dialog.py
test_store_editor.py test_equation_editor.py` and `test/test_curve_overlay_update.py`.

1. **Parity status, 2026-09-23: all seven scenarios PARITY** in `parity/report.html`
   (features.md ticked; deliberate differences written there). The static FRET line
   is drawn where the Qt one is; 59 equations, all valid; 12,237 rows × 58 columns.
   Fixed rather than copied: the equation list reads the *user's*
   `curve_equations.yaml` first (Qt read the shipped file first); Names & functions
   lists only the functions ndX's engine accepts (`abs`), not chisurf's.
2. **Trap -- a green test run can be a skipped one.** A chisurf `FittingParameter`
   needs chisurf's compiled port runtime (IMP.bff). When it cannot load (every
   browser; a desktop mid-rebuild, as on 2026-09-23 ~09:45 when `_IMP_bff.so` and
   `libimp_bff.0.dylib` came from different builds) the feature degrades on purpose:
   the constants become plain numbers (edits still recompute), curves and the fit are
   off, and the Parameters/Overlays tabs say why. The chisurf tests in
   `test_overlays.py` then *skip*; check that `overlays._has_chisurf()` is true before
   reading a pass as a measurement.
3. **Blocked for the browser: chisurf parameters.** Curves, the curve fit, links and
   bounds need `chisurf.core.fitting.parameter`, which needs IMP.bff; there is no
   Pyodide build of it. Unblocking needs either an IMP.bff Pyodide wheel or a pure-
   Python parameter model for chisurf's port runtime. Everything else (constants as
   numbers, equations, Table Editor) is Qt-free and chisurf-free.
4. **chimol, answered.** The Qt window needed `~/dev/chimol` only through
   `chisurf.gui`: autoform / the parameter table -> `chisurf.gui.widgets.fitting` ->
   `chisurf.gui.widgets.experiments` -> `chisurf.core.structure` ->
   `chisurf.core.fio.structure.coordinates` (`from chimol.io.atoms import ATOM_DTYPE`).
   Without it `NDXplorer._deferred_init` dies in the Gaussian panel's autoform
   *before* the constants table exists, so the equations run without constants --
   that is the "equation columns silently missing". chimol is already an explicit
   chisurf dependency (`pixi.toml`, editable install); the harness adds it to
   `PYTHONPATH` only because it runs from sources. The emtk app imports no
   `chisurf.gui` and needs no chimol; `test_overlays.py` loads the MFD folder with
   chimol blocked and finds the equation columns.
5. **Open.**
   - View > Parameters / Overlays hide the tab's content, but `frame._draw_left`
     still draws those two titles (disabled) when no feature provides them (core).
   - The fit runs on a thread on a desktop. A fit with a freed constant rewrites the
     plotted columns from that thread while frames draw; the model only re-bins when
     something invalidates it, so nothing races today, but any per-frame reader of
     those two columns would.
   - The Qt Parameters table still comes from `chisurf.gui` (legacy, deleted with
     the Qt GUI).

Qt-free logic both GUIs call (moved, not copied): `core/overlay_curves.py`
(CurveEvaluator out of `plotting/curve_overlay.py`, parameter names, filled text,
predefined list, sampling, CSV, `OverlayCurve`), `analysis/curve_fit_setup.py`
(`plot_main.build_curve_fit_for` / `_build_cloud_fit` / `build_data_parameters`
behind a `FitHost`: `plot_main` is one, `ModelFitHost` the other; the dialog's
targets, reductions and result line), `core/equation_table.py` (rows, validation,
YAML, names), `core/store_edits.py` (`apply_edits`). `core/constants_group.py` and
`core/curve_parameters.py` stay the model. emtk: DataTable right-click
`context_call`, value shading `colour_source`, `column_filters`, sideways scrolling
(`min_column_width`), `fit_columns()`, `reserve` for an expanding table
(`d80bb85`, `1d3462d`). Core: `capture.py` adds the final `main` shot the Qt harness
always takes (`6bf25d1`); View > Equations reads `show_equations` (`8e1b805`).

Tried and reverted: building a table's rows afresh every frame -- the data table
rebinds on a new list and lost its sort order and selection each frame; rows are
handed out through a cache that returns the same list while the content is equal.

### playback_export (playback, find projections, publication export)

Re-measure with `python -m ndxplorer.app.capture -s playback -s playback_image_frames
-s publication_export -s find_projections -s find_projections_z -s find_projections_iris`
and `pytest ndxplorer/tests/test_app/test_playback_export.py` (16 tests, including
a cooperative ranking run, which is the browser's path, and a check that no Qt is imported).

1. **Parity status, 2026-09-23.**
   - `playback`: done. 87 of 12237 bursts at step 5 of 20, the same as the Qt window.
   - `playback_image_frames`: done for playback (Frame axis, 10 steps, Integrate).
     The shot's axes differ because image mode on open belongs to `open_image_h5` (io group).
   - `find_projections`, `find_projections_z`, `find_projections_iris`: done. Iris
     gives the same six scores as the Qt window and petal width × petal length is applied.
   - `publication_export`: done.

   The deliberate differences are in features.md: Stop is labelled ■ in both GUIs
   (no font the emtk atlas or a browser has includes ⏸); the Speed default comes
   from the *user's* settings (40 fps from an old `frame_duration_ms` 25), while
   the Qt window reads only the packaged file; the Playback fold shows disabled
   without data instead of hidden; and the ranking is an in-app `DialogWindow`,
   not a second top-level window.
2. **Blocked on core:** `z_add_selection` "during playback the slice is added as a gate
   too". The feature implements `on_z_select()`; the core hook that calls it from
   `PanelModel.z_select` was requested (lead, 2026-09-23). Check that it calls into the
   feature, then tick the item.
3. **Browser run not yet taken.** Every module imports without Qt (tested). Ranking
   runs on `emtk.tasks` in 10 ms slices (a `_Handle` whose `is_cancelled` also turns
   true at the end of a slice, so `run_vizrank` hands back its batch and the next slice
   resumes from the shared state iterator). Export needs matplotlib, which Pyodide
   ships, and goes to `app.io_service.save_bytes` (a download). What has not been done
   yet is a real page load via `emtk.web` that clicks Play, Start and Export.
4. **Clusters as ranking classes** are read from any feature's `cluster_labels`
   attribute. The analysis group must expose its labels under that name, or
   "Clusters" is never offered.

Tried and reverted: a hand-drawn `ToolWindow` in the feature (title row, drag,
✕, opaque body; an emtk window paints no background). It was replaced by
`emtk.dialog_window.DialogWindow`, which does the same and is shared by every
feature. Reading
the ranking's help/guide by importing `ndxplorer.ui` builds Qt dialogs, so the
files are read by path instead.

### io (open, merge, image mode, working path, burst IDs, selection files, screenshot)

Re-measure with `python -m ndxplorer.app.capture -s startup_empty -s file_dialog_analysis_folder
-s merge_dialog -s open_csv_iris -s open_csv_file_dialog -s open_bur_cli -s open_sampling
-s open_analysis_file_error -s open_image_h5 -s save_burst_ids -s selection_save
-s browse_working_path -s screenshot_button`, then run `pytest ndxplorer/tests/test_app/test_io*.py`
(35 tests) and, for Qt offscreen, `ndxplorer/tests/test_ui ndxplorer/tests/test_workflows
ndxplorer/tests/test_cli.py`.

1. **Parity status, 2026-09-23: all 13 scenarios are captured, and every io item is ticked**
   in `tools/parity/features.md`. The one item left open is open_image_h5's "Frame drives
   playback", which belongs to the playback group. The deliberate differences:
   - A load error shows the reader's reason, not the Qt traceback.
   - Screenshot saves the whole window, as Qt's `grab()` does. It is not copied to the
     clipboard.
   - BID is enabled only for a table with First/Last File and First/Last Photon.
   - The Process-Burst-IDs follow-ups say that the correlator and the microtime
     histogram are ChiSurf plugins.
2. **`app.io_service`** (`features/io_service.FileService`) is the one file service.
   - The API is `ask_open`, `ask_save`, `ask_folder` and `save_bytes`. Answers come
     through a callback. `answer()` presses a dialog for tests and replays.
   - On a desktop the dialogs are emtk FileDialogs in a `DialogWindow`.
   - In a page they open on `/mnt/local` (the mount), else `/mnt/dropped`. `save_bytes`,
     and any save outside the mount, becomes a download (emtk `emtk.web.page.download`).
   - The settings and playback_export groups already use it.
3. **Qt-free, shared (moved, not copied).**
   - `io/loading.py` holds the importers (dialog caption, file or folder, filters, merge
     title), the drop dispatch, the reader for each kind, the worker load, the merge
     question and its answers, and the working path and title rules.
   - `utils/axis_helpers.image_axes`.
   - `io/writer`: `save_burst_ids_headless(progress=)`, `find_bst_files`,
     `find_setup_name`.
   - `export/screenshots.py`.
   - `region_selection`: interval gates save and load without ChiSurf.
   - `file_operations.open_files` keeps only the Qt dialogs and the worker.
4. **Fixed on the way.**
   - A `.bur` line's trailing tab no longer becomes a parameter named "". The emtk axis
     chooser had picked it for x.
   - The emtk file dialog's save-mode name field was not drawn, because
     `set_next_item_width(-1)` gave it a negative width. The fix is emtk `0a64a62`.
   - Opening a `.pto` or `.h5` without an importer used to fall to the CSV reader.
5. **Browser, not yet run in a page.**
   - Nothing under `features/io*` imports Qt (a test checks this).
   - Loads run unthreaded in a page, on the next frame.
   - Saving a drawn region or a mask to `*.selection.json` needs `chisurf.core.roi`,
     which a page does not have. Interval gates work without it.
   - A real `emtk.web` page load that drops a file, mounts a folder and saves is still
     to be done.
6. **Asked of the core (lead).**
   - `model.read_path` (drop and `--file`) duplicates `io.loading.kind_for_paths` and
     reads a `.pto` with the burst reader. It should call `io.loading.read`.
   - `frame.open_dialog`/`_draw_dialog` and the core open actions are shadowed by io's
     and can go.
   - `pyproject` package-data does not list `ndxplorer/app/**/*.json` (views and feature
     specs), so a wheel would ship without them.

emtk additions: `view_form` choice `style: "radio_list"` (`0ccf122`), `emtk.web.page.download`
/ `in_browser` (`d906b00`), and `Layout.row` negative widths (`0a64a62`).

Tried and reverted: an `im_widgets.begin_modal` in emtk (dim, chrome, title bar). It was
dropped before its commit because `emtk.dialog_window.DialogWindow` landed at the same time
and does the same thing.

### analysis (Find structure, UMAP, Gaussian Fit)

Re-measure with `python -m ndxplorer.app.capture -s clustering_dialog
-s column_selection_dialog -s clustering_kmeans_run -s clustering_pca_run -s umap_run
-s view_umap_action -s gaussian_fit -s gaussian_select -s gmm_settings_dialog` and
`pytest ndxplorer/tests/test_app/test_analysis_app.py
ndxplorer/tests/test_app/test_analysis_logic.py` (28 tests: clustering as a cooperative
`emtk.tasks` task, cancel, the browser's UMAP text, PCA report, seed orientation, fit with
a held centre, save/load, settings, and a check that no Qt is imported). Trap: the
Gaussian tests need `chisurf.core.fitting.parameter`, which needs IMP.bff. While
someone rebuilds IMP.bff they fail with an `_IMP_bff.so` symbol error. That is the
environment, not the port; `python -c "import IMP.bff"` tells which.

1. **Parity status, 2026-09-23.** All nine scenarios are ticked in features.md, with
   the deliberate differences noted there. The values match the Qt window:
   - K-means on iris finds 3 clusters, and the colour survives isolating a cluster (it
     did not in Qt).
   - PCA on the six MFD columns gives 29 %/27 %, 12089 rows fitted and 148 dropped.
   - The Gaussian fit gives x1 3.77419, σx,1 1.30578 and w1 0.617.
   - gaussian_select keeps 10257 of 12237 rows.
   The work is in Qt-free modules both GUIs call:
   - `analysis/structure.py`: the method table, the clustering and the UMAP
     embedding as generators of checkpoints, and the PCA report.
   - `analysis/gaussian_mixture.py`: EM, seeds, ellipses, marginals, files and GMM
     settings.
   - `utils/package_install.py`: conda/pip and `install_task`.
   - `io/writer.save_clustering_data`: now takes a progress callback.
2. **UMAP was verified outside arm64.** arm64 has no umap-learn, so `umap_run`
   records the install offer, as the Qt baseline does. A real run used umap-learn
   0.5.12 and pynndescent from a `pip install --no-deps --target` scratch folder on
   `PYTHONPATH`, with arm64 left untouched. It covered columns, the progress log, Plot
   2-D and Plot 3-D. To re-check, do the same, or accept the in-app Install, which runs
   `conda install umap-learn -c conda-forge` into the env as a task.
3. **Browser run not yet taken.** Every module imports without Qt. What is missing:
   - K-means, HDBSCAN and PCA fall back to scikit-learn when `chisurf.core.ml` cannot
     be imported. This code path was never run under Pyodide.
   - UMAP says in words that it cannot run in a browser (numba).
   - The Gaussian Fit panel needs chisurf's `FittingParameter` (IMP.bff, native). In a
     page it shows the reason instead of the table. A browser Gaussian fit needs a
     parameter group that does not depend on IMP.bff, and there is none today.
   - A real `emtk.web` page load that clicks Run has not been done yet.
4. **Handed to others.** The selection feature outlines enabled Gaussian gates. This
   panel stops drawing a component once it is that gate (`GaussianPanel.is_gate`).
   `cluster_labels` feeds the ranking's "Clusters" classes (playback_export item 4).
   Docks becoming windows (window-manager agent) will move the Gaussian Fit tab
   from `tabs()` to a feature window.

Fixed on the way, in both GUIs:
- the seed width was read from the transposed bin;
- a saved `_gaussians.csv` did not load again;
- `_hist2d.csv` wrote y down the rows;
- Weight floor was never applied;
- Log Gauss did nothing;
- GMM Settings never opened;
- View > UMAP raised AttributeError;
- three installer offers imported `deps_installer` from the wrong package.

emtk gained:
- `emtk.tasks`;
- `emtk.dialog_window.DialogWindow`, now used by several features;
- in view_form, `special_text`, `label_source`, per-button `hidden_when` and the
  `progress` section;
- newlines in `text_wrapped`.

### settings (Settings menu, View > Axis Control, File > Make Report, Help)

Re-measure with `HOME=<scratch> python -m ndxplorer.app.capture -s menu_settings -s menu_view
-s menu_help -s set_default_axis -s load_settings_dialog -s save_axis_settings_dialog
-s performance_settings -s axis_control_dialog -s report_tool` and `pytest
ndxplorer/tests/test_app/test_settings.py test_settings_logic.py test_plot_axis_display.py
test_feature_hooks.py` (33 tests). Qt, offscreen: the whole non-app suite (864 passed). The
trap: set_default_axis, Save constants and performance Apply write `~/.ndxplorer`, so
capture and test with a scratch HOME (the tests set one).

1. **Parity status, 2026-09-23: all nine capturable scenarios are captured and ticked.**
   fix_report_tool is `[-]`: `ndxplorer.fix_report_tool` never existed (a5a1b2a added a
   dangling import), the entry is gone from both menus (core 3cf8811), and the report
   tool's Report column, Clear Reports and Generate Reports cover a missing or stale
   report. Deliberate differences, in features.md:
   - Axis Control has no tick-size, title-size or bold fields: the app draws in emtk's
     font (user directive). The values stay in axis_labels.yaml.
   - Performance has no Plot Backend choice.
   - The report's folder list is single-select, with a Report column instead of the
     green highlight.
   - Help > Update tells you how to update; it installs nothing.
2. **What changes the plots.** `plotting/axis_display.AxisDisplay` is
   `app.model.axis_display`, and `app/plots.py` reads it:
   - ticks per plot and side, one side per axis (bottom/left win when both are on);
   - the x-top and y-right titles;
   - the title colour.

   **Open:** the y-top and z-plot titles are stored but not drawn, because the core
   draws no such titles. Adding them to `plots.py` would make those three switches do
   something.
3. **Qt-free, shared (moved, not copied).**
   - `settings/persist.py`: axis settings, default axes, constants (a rich file keeps
     its format), equations.
   - `plotting/axis_display.py`: the label file.
   - `utils/performance_config.save_performance_config`.
   - `export/report.py`: discovery, templates, histograms through the GUI-free
     `ExplorerModel`, matplotlib `Figure` to PNG bytes, CSV, axes_info, DOCX, clear.

   `settings_helpers.py` and `report_tool.py` keep only the Qt dialogs; the Qt report
   no longer builds a hidden NDXplorer.
4. **Fixed rather than copied.**
   - Report 2-D CSV/PNG were transposed: H is (n_y, n_x) and the report used it as
     (n_x, n_y). With equal bins this was wrong without an error; with unequal bins
     it raised.
   - Performance Reset reset nothing, and the plot backend was never saved.
   - Save settings > Equations was not connected.
   - Help, About and Update were not connected.
5. **Measured.** A report of the three packaged plots on the MFD folder takes 0.46 s per
   folder once warm (the first takes 0.8 s). The report tool runs one folder per frame.
   None of the Performance values changes a computation in either GUI, because nothing
   reads `PerformanceConfig`: either wire `histogram_threads` into tttrlib's fill or
   drop the dialog.
6. **Browser, not yet run in a page.** Nothing imports Qt (tested in a fresh
   process). Files go through `app.io_service`: the combined DOCX is `save_bytes`, and a
   report written into a folder reaches the disk only inside the mounted folder.
   python-docx is not in the arm64 env, so the DOCX path has not been exercised in the
   emtk app (the message says so).
7. **Delegation.** Save > Constants and Save > Equations call the overlays feature's
   `constants.save_parameters` and `equations.save_equations_file` when they are there
   (rich constants, the table's equations), and `persist` otherwise. Load settings hands
   constants over as a plain dict, which the Parameters tab takes over on its next frame.

emtk additions: `view_form` `kind: "color"` values (swatch, HSV picker, hex) and the
`code_editor` section (a TextEditor bound to an attribute), in `dfb7823`. Core hooks
added on the lead's request: a capture op that returns False passes the step on, and a
target locator that returns None falls through (`039f918`); `files_dropped` (`9490acb`);
`plots.py` reads `axis_display`.

Tried and reverted: `emtk.begin_modal` for the dialogs. It left before its commit, and
`DialogWindow` replaced it. A Qt-sized dialog (resize_dialog to 460x1500) left a
half-empty window, so resize is a no-op and the dialogs are sized to their controls.
