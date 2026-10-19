---
type: Reference
title: ChiSurf Global Settings
description: The user-configurable ChiSurf settings, what each one changes, and where the settings files live.
tags: [reference, settings, fitting, global-analysis]
---

# ChiSurf Global Settings

This document describes the user-configurable settings ChiSurf reads.
Values are loaded from YAML files in `chisurf/core/settings` into `chisurf.settings`
(e.g. `chisurf.settings.cs_settings`, `chisurf.settings.gui`, `chisurf.settings.fret`).
The copy in your settings folder (`~/.chisurf`) is merged over the packaged one,
so a key missing from it takes the shipped value.

Settings are grouped and ordered as in the YAML files:

- `settings_chisurf.yaml` – core application and analysis settings
- `experiment_configs.yaml` – experiment type registry and readers/models
- `settings_colors.yaml` – predefined color palette used by plotting code

Only keys some code reads are documented, and only those ship.

---

## 1. `settings_chisurf.yaml`

### 1.1 `correlator` (TTTR-based FCS correlation)

Used by:
- `chisurf.plugins.fcs.fcs_correlator.correlator_model.CorrelatorSettingsModel` (the FCS correlator)
- `chisurf.plugins.fcs.fcs_channel_preset` (the FCS channel presets)
- `chisurf.core.fluorescence.fcs.channel_setups` (a channel setup without its own `n_bins` / `n_casc` / `fine`)

Keys:

- **`B`** (shipped `9`)  
  Number of correlation lag bins *per cascade level* in the multi-tau
  algorithm used by `tttrlib.Correlator` (`n_bins` in the C++ code).
  For each coarsening level, `B` correlation points are computed before the
  time axis is coarsened again.

- **`number_of_cascades`** (shipped `20`)  
  Number of coarsening steps / cascade levels in the multi-tau correlator
  (`n_casc` in the C++ code). Each additional cascade halves the effective
  time resolution and adds another block of `B` correlation points at longer
  lag times, extending the accessible correlation window.

- **`split`** (shipped `6`)  
  Number of chunks the photon stream is split into for separate correlations.
  Used to compute multiple partial correlations that are then averaged.

- **`method`**  
  The tttrlib correlation algorithm: `laurence` (default; symmetric
  normalization, no long-lag upturn when the intensity drifts), `wahl`
  (multiple-tau on the time tags) or `felekyan`. An unknown name is refused.

- **`fine`** (shipped `0`)  
  Enable "fine" correlation (micro-time–resolved / higher resolution). If
  true, additional micro-time information is passed to `tttrlib.Correlator`.

- **`microtime_binning`**  
  Micro-time binning factor the FCS correlator starts with (1 = no binning).

---

### 1.2 `database` (embedded data handling in `chisurf.core.base.Data`)

Used by: `chisurf.core.base.Data` for embedding raw files into YAML/JSON save files.

- **`embed_data`**  
  If true, small files loaded through `Data.filename` are embedded in memory
  (and in saved YAML/JSON) instead of being referenced only by path.

- **`read_file_size_limit`**  
  Maximum file size (bytes) that will be read and possibly embedded when a
  `Data` object is created from a filename.

- **`compression_data_limit`**  
  Size threshold (bytes) above which embedded file contents are compressed with
  `zlib` before storing.

- **`embed_data_limit`**  
  Maximum size (bytes) of the *compressed* payload that will actually be
  embedded. Larger files are left unembedded and only the filename is stored.

---

### 1.3 Top‑level flags

- **`enable_experimental`**  
  Experimental mode: the ribbon and menus also list experimental, CLI-only and
  disabled plugins (`chisurf/emtk/shell_ribbon.py`), and
  `chisurf.settings.is_dev_mode()` turns on the developer code badges.

- **`verbose`**  
  Global verbosity flag. Used in multiple modules (e.g. `chisurf.__init__`,
  `TCSPCReader`, structure and photon I/O) to control the amount of diagnostic
  logging and console output.

- **`log_level`**  
  Python logging level of the root logger (10=DEBUG, 20=INFO, 30=WARNING,
  40=ERROR, 50=CRITICAL; shipped `30`), set once at startup
  (`chisurf.__init__._apply_logging_settings`). The Log dock has its own level
  control.

- **`env`**, **`env_override_existing`**  
  Environment variables set at startup (`name: value`), applied by
  `chisurf/core/settings/env_bootstrap.py`. With `env_override_existing: true`
  (shipped) they replace variables already set in the OS; `false` only fills
  missing ones. An `env` object in `~/.chisurf/settings.json` is merged over the
  YAML one.

> **Removed:** `n_threads` governed the `numexpr` thread pool and went with
> `numexpr`; thread counts come from the {ref}`threads <settings-threads>`
> section.

---

### 1.4 `fret` (global FRET distance grid and defaults)

Used by `chisurf.core.fluorescence.rda_axis` (the photon-distribution models and
helper functions), the labelled-structure and FRET-parameter defaults
(`chisurf.core.structure.labeled_structure`, `chisurf.core.models.fret_parameters`)
and the light path simulator (`kappa2`, `n`).

- **`rda_min`**, **`rda_max`**  
  Minimum and maximum donor–acceptor distances (in Å) defining the global
  `R_DA` axis used in FRET models.

- **`rda_resolution`**  
  Number of points on the distance axis. Used to reshape distributions and
  distance grids.

- **`rda_scale`**  
  `log` (default when absent) or `lin` spacing of the axis. Not shipped;
  written together with the three keys above when the axis is changed in the
  application.

- **`forster_radius`**  
  Förster radius $R_0$ (in Å) used as the default in FRET decay and efficiency
  calculations.

- **`tau0`**  
  Donor fluorescence lifetime in the absence of FRET (ns); default for FRET
  decay simulations.

- **`kappa2`**  
  Mean orientation factor ⟨κ²⟩ assumed in FRET efficiency calculations.

- **`n`**  
  Refractive index of the medium (shipped `1.33`); read and written by the
  light path simulator.

---

### 1.5 `gui` (graphical interface and plotting)

Sub‑sections control editor appearance, console behavior, fit windows, and
plot defaults. Many of these are read via `chisurf.settings.gui`.

#### 1.5.1 Window behavior

- **`language`**  
  UI language as a two-letter locale code. `en` (default) is the source
  language and needs no catalogue; `de`, `es`, `fr`, `pt` and `ru` load
  `chisurf/gui/i18n/chisurf_<code>.ts` ({src}`chisurf/core/support/i18n.py`).
  Picking a language in Settings or the ribbon flag dropdown writes it here, so
  the choice persists across sessions. A code without a shipped catalogue falls
  back to English.

- **`confirm_close_fit`**  
  If true, closing a fit window asks before the fit is discarded.

- **`confirm_close_program`**  
  If true, quitting ChiSurf asks "Quit ChiSurf?" first.

- **`style_sheet`**  
  The active emtk style sheet: a `.css` file shipped with emtk, or one of the
  emtk `.css` style sheets in the user styles folder. Written by
  **Settings ▸ Styles**.

- **`modal_blur`**  
  Blur what lies behind a dialog (default `true`); the wash stays when off.
  **Settings ▸ Styles ▸ Blur behind dialogs**.

#### 1.5.2 Embedded console

The console is ChiSurf's own ({src}`chisurf/core/console/settings.py`).

- **`console_init`**  
  Multiline string executed in the console on startup. The shipped value uses
  IPython spellings (`%config Completer.use_jedi = False`,
  `get_ipython().cache_size = 0`); both are implemented.

#### 1.5.2.1 `gui.console`

Optional block; every key has a default, so an absent block is normal. The
keys the console reads ({src}`chisurf/emtk/console.py`):

| Key | Default | Meaning |
| --- | --- | --- |
| `max_blocks` | `5000` | Scrollback cap; `0` for unlimited. |
| `history_length` | `5000` | Entries kept in `chinsole_history.txt`. |
| `banner` | `true` | Startup banner. |
| `completion` | `popup` | `none` turns completion off. |
| `calltips` | `true` | Show signatures on `(`. |
| `paging` | `vsplit` | `none` prints long output such as `obj?` inline instead of in a pager. |
| `images` | `true` | Render figures inline. |

#### 1.5.3 Script editor

Fields under `gui.editor` control the integrated text editor:

- **`font_family`**, **`font_size`**  
  Default font family and size for the editor.

- **`default_color`**, **`paper_color`**  
  Default text color and background color.

- **`caret_line_background_color`**  
  Highlight color for the current caret line.

- **`margins_background_color`**, **`marker_background_color`**  
  Colors used for margin gutters and marker backgrounds.

- **`language`**  
  Default language mode (e.g. `Python`) used by the editor for syntax
  highlighting.

#### 1.5.4 Fit‑models browser

- **`fit_models.n_columns`**  
  Number of columns used to arrange fit models in the model‑selection dialog.

#### 1.5.5 Plotting defaults (`gui.plot`)

How fit plots look. Edited in **Settings ▸ Plots**, which applies a change at
once and writes only what differs from the shipped values; every plot reads
them when it draws, through `chisurf.core.plotting.appearance` (fit line plots,
distribution plots, protein MC plots, the photon-filter wizard).

- **`colors`**  
  - **`data`**, **`model`**, **`irf`**, **`residuals`**, **`auto_corr`** –
    the curves of a fit plot (`auto_corr` is the autocorrelation of the
    weighted residuals).
  - **`region_selector`** / **`region_selector_alpha`** – colour and opacity
    (0–255) of the fit-range band.
  - **`active_transparency`**, **`inactive_transparency`** – opacity (0–1) of
    the selected dataset's curves and of the other datasets of a global fit.
    The names are historical; the values are opacities.

- **`line_width`**  
  Width of the model, IRF, residual and autocorrelation curves; the data trace
  is drawn at half of it.

- **`font_size`**  
  Point size of the axis text (ticks, axis names, legend); `0` follows the
  interface font.

- **`enable_grid`**, **`show_data_grid`**, **`show_residual_grid`**,
  **`show_acorr_grid`**, **`grid_alpha`**  
  Grid on or off everywhere, per panel, and its strength (0–1; `0.3` is the
  theme's own grid, `1` solid lines).

- **`enable_region_selector`**  
  Draw the draggable fit-range band on the data panel.

- **`show_legend`**, **`label_axis`**  
  Show the legend and the axis names on new fit plots.

- **`node_graph`**  
  Grid and node size of the node graphs (Global View, the light path, the
  provenance inspector, the node editor).

Retired keys -- `backend` (emtk is the only renderer), `pyqtgraph_config` (the
options of the removed pyqtgraph renderer) and `hideTitle` (read by no plot) --
are removed from a user's settings file when it is loaded.

---

(settings-threads)=
### 1.6 `threads` (numeric backend threading)

Applied very early at startup by `env_bootstrap._apply_thread_env_from_settings`
(`chisurf/core/settings/env_bootstrap.py`). The values become environment
variables for MKL and OpenMP; both default to one thread, which also pins the
OpenMP kernels of tttrlib and IMP.bff. A `threads` object in
`~/.chisurf/settings.json` overrides the YAML values.

- **`mkl_num_threads`**  
  Value for `MKL_NUM_THREADS` – maximum number of threads used by Intel MKL
  (BLAS/LAPACK).

- **`omp_num_threads`**  
  Value for `OMP_NUM_THREADS` – maximum threads for OpenMP‑using libraries
  (NumPy, SciPy, tttrlib, IMP.bff).

- **`mkl_threading_layer`**  
  Value for `MKL_THREADING_LAYER` (e.g. `SEQUENTIAL`) to avoid nested
  parallelism issues.

- **`override_existing_env`**  
  If true, the above variables are applied even if already set in the OS
  environment; otherwise they only fill missing or empty variables.

---

### 1.7 `mc_settings` (protein Monte‑Carlo)

Used by: `chisurf.plugins.modelling.proteinmc.model` and
`chisurf.core.models.structure.proteinmc` (`normalize_settings` /
`ProteinMCRunner`). The section is the base a run's own settings are merged
over; a run without its own `potentials` uses only the labelling potential.

- **`mc_mode`**  
  Monte‑Carlo algorithm; only `simple` is supported, anything else is refused.

- **`kt`**  
  Effective thermal energy (kT) of the Metropolis acceptance.

- **`scale`**  
  Width of a torsion move: a move adds a uniform draw from [−`scale`/2, `scale`/2].

- **`move_map`**  
  Per-residue move probabilities. `null` derives them from the FlexFit set of
  the labeling file when a dye potential names one, and otherwise moves every
  residue with equal probability.

- **`n_iter`**  
  Maximum number of Monte‑Carlo iterations.

- **`n_out`**  
  A frame is written every `n_out` accepted moves.

- **`pdbOut`**  
  Number of frames after which the run stops.

- **`pChi`, `pOmega`, `pPhi`, `pPsi`**  
  Probabilities for proposing moves in different torsion angles (χ, Ω, φ, ψ).

---

### 1.8 `optimization` (global & local fitting)

Used by: `chisurf.core.fitting.fit.Fit` / `FitGroup`, the global-fit model and
the sampling routines.

- **`noise_model`**  
  Estimator of a fit whose data are not photon counts: `default` (weighted
  least squares on the error column, shipped) or `poisson` (2I* deviance).
  TCSPC decays use `tcspc.noise_model`. See
  [Fitting objectives](../concepts/fitting_objectives.md).

- **`global_optimize_local_first`**  
  In `FitGroup.global_optimize`, controls whether individual fits are
  locally optimized before the global least‑squares run.

- **`global_threaded_model_update`**  
  If true, `GlobalFitModel.update_model` updates individual models in
  parallel threads before computing the global objective.

- **`global_structure_aware_update`**  
  Recompute only the local models a parameter change reaches, using the fit's
  factor graph (shipped `true`); `false` always recomputes all of them.

Sub‑sections:

- **`leastsq`** (used in local and global least‑squares)  
  Passed into the bounded least-squares fitter (`chisurf.core.fitting.minimizer`,
  IMP.bff's MINPACK `lmdif` port):
  - **`ftol`**, **`xtol`**, **`gtol`** – standard convergence tolerances
    (an `xtol` at MINPACK's old 1.49e-8 or above is replaced by 1e-10)
  - **`maxfev`** – max. number of function evaluations (0 = auto)
  - **`factor`**, **`epsfcn`** – step‑size and finite‑difference parameters
    (`epsfcn: 0` is replaced by 1e-6)

- **`sampling`** (MCMC / error‑estimation sampling)  
  Used by the fit controls' error estimate and
  `chisurf.core.fitting.fit.sample_fit`:
  - **`method`** – sampling backend (shipped `blocked`). The list is not maintained here: the samplers advertise themselves in `chisurf.core.fitting.sample.SAMPLERS`, and the settings dialog is populated from it (`emcee` is accepted as the old name of `ensemble`)
  - **`chain_format`** – how the chains are stored: `er4` (tab-separated text) or `hdf5` (compressed table, ~4x smaller). Both open in nDXplorer. Editable from the fit controls (⚙), which writes it back here
  - **`steps`** – number of steps per walker / chain
  - **`substeps`** – sampler steps between two recorded steps
  - **`n_runs`** – number of independent chains or restarts
  - **`thin`** – thinning factor for recorded samples
  - **`chi2max`** – maximum χ² value allowed when accepting samples.

- **`mcts`** (the fit window's model search, `chisurf/server/services/fits.py`)  
  - **`n_simulations`**, **`c_puct`**, **`reward_scale`**, **`dirichlet_alpha`**,
    **`seed`** – tree-search budget and parameters (shipped 400, 1.4, 1.0, 0.3, 7)
  - **`search_fit_settings`** – also search how each candidate is fitted
    (tolerances, start values, step bound); written by the fit window.

---

### 1.9 `plugins` (plugin discovery and visibility)

Used by: plugin manager, ribbon and menu construction, model list, updater plugin.

- **`disabled_models`**  
  List of model names that do not appear in the model selection
  (`chisurf/emtk/fit_docks.py`, the model manager).

- **`disabled_plugins`**  
  List of plugin addresses that are not listed in the ribbon and menus.

- **`hide_disabled_plugins`**  
  If true, disabled plugins stay hidden even in experimental mode; if false,
  experimental mode lists them.

- **`show_demo_plugins`**  
  If true, plugins that declare themselves demos appear in the generated
  menus; off (shipped) leaves them out.

- **`statefulness`**  
  Whether plugin windows remember their size and position: `mode`
  (`plugin_default` lets each manifest decide) and `per_plugin`, a mapping of
  plugin id to its own choice. Edited in **Settings ▸ Plugins**.

- **`plugin_order`**  
  Optional mapping used to order plugins in menus. Keys are plugin names or
  categories; values are integer sort keys.

- **`toolbar_plugins`**  
  Full plugin addresses pinned to the toolbar (e.g.
  `Spectroscopy:Correlation:Correlator`). Edited in the plugin manager's
  *Toolbar* column; the emtk shell builds no toolbar from it yet.

- **`updater.ignore_updates_on_startup`**  
  If true, suppresses automatic update checks at application startup.

- **`updater.check_on_startup`**  
  If true (and `ignore_updates_on_startup` is false), the updater plugin
  checks for conda or GitHub updates when ChiSurf starts.

---

### 1.10 `tcspc` (TCSPC reader and fit defaults)

Used by: `chisurf.core.experiments.tcspc.TCSPCReader` (a reader constructed
without the value) and `chisurf.core.fitting.default_noise_model`.

- **`noise_model`**  
  Estimator of a photon-counting decay fit: `default` (weighted least squares,
  i.e. Neyman χ², shipped) or `poisson` (2I* deviance). The reasons for the
  shipped choice are in the YAML comment and in
  [Fitting objectives](../concepts/fitting_objectives.md).

- **`dt`**  
  Default time resolution (ns per bin) for TCSPC decays when not explicitly
  provided to `TCSPCReader`.

- **`rep_rate`**  
  Default excitation repetition rate (MHz) of a `TCSPCReader`.

- **`fit_area`**  
  Fraction of the decay used for automatic fit‑range selection
  (`initial_fit_range`).

- **`fit_count_threshold`**  
  Minimum count threshold used by `initial_fit_range` when locating the
  significant part of the decay.

- **`fit_start_fraction`**  
  Fraction of the decay at which fitting typically starts (relative to the
  peak region).

- **`g_factor`**  
  G‑factor of a reader when neither the reader nor `anisotropy_corrections.json`
  gives one.

- **`threshold`**  
  Amplitude below which the FRET-structure model drops distance components
  (default `0.001`; not shipped).

---

### 1.11 `mmfdb` (Measurement File Database settings)

Used by: Measurement File Database APIs, the switch-user and user-editor
plugins and the fitting client.

- **`default_user_id`**  
  The `user_id` that database operations and entities are attributed to when no
  explicit user is given, and the account the login dialog offers first. Ships as
  `"user"`, the unprivileged desktop account; set it to `"admin"` only to work as
  the administrator.
  It **may** carry the same name as the bootstrap administrator. The first write
  auto-creates this user as a plain row, and the bootstrap is allowed to claim
  that row precisely because the database created it from this setting rather
  than a person registering it. The claim is narrow: once the row has a password,
  admin rights or passwordless login it is somebody's account and the bootstrap
  refuses it, so a configured secret can never take over an existing identity.

- **`config_file`**, **`client`**  
  Path to a standalone server's `mmfdb.yaml`, and the client block (`mode`,
  `username`, `host`, `cmd_port`, `pub_port`, `base_url`, `timeout_ms`) whose
  explicit values override it. Passwords never belong here.

- **`fitting_timeout_ms`**  
  How long (ms) the client waits for a `fit.run` reply (shipped `5000`).

- **`save_login`**, **`autologin`**  
  The login dialog's *remember* (shipped on) and *sign in automatically*
  (shipped off) choices. Autologin is switched off again when no token could be
  saved.

- **`last_server`**, **`server_history`**  
  The server last signed in to and the list offered; written by the login dialog.

- **`object_store.root`**  
  Object-store folder, relative to the settings folder (shipped `objects`).

**Workspace login.** The embedded desktop database is created with two local
accounts: `user` / `user` for everyday work, and `admin` / `admin` for
administering the database. Both are offered in the login dialog and both allow
passwordless sign-in, so the dialog normally stays out of the way.

The curated source database that **MMFDB Admin → Reset** restores contains no
accounts at all, so the reset re-creates both after copying: a reset workspace is
always loginable as `user` / `user` or `admin` / `admin`, whatever accounts
existed before it. A backup of the replaced database is written to
`<settings dir>/flr/backups/` first.

Server and standalone deployments are unaffected: they stay fail-closed and
create no account unless `admin.user`/`admin.password` are configured (or the
`MMFDB_BOOTSTRAP_ADMIN_USER`/`MMFDB_BOOTSTRAP_ADMIN_PASSWORD` environment
variables are set), and a reset there restores exactly that configured
administrator.

**If a login is refused as "Too many failed login attempts".** Five *wrong
passwords* for one account inside fifteen minutes stop further attempts. Only
real password guesses count: a client that offers no password is asking whether
the account is passwordless, and that question is never counted. The lockout
also ends as soon as any sign-in succeeds, so the correct password works again
once the window passes — nothing has to be reset.

---

### 1.12 `project` (autosave)

- **`autosave.enabled`**, **`autosave.interval_s`**  
  Write a silent `<name>.autosave.cs.pto` copy of a project holding data every
  `interval_s` seconds (shipped: on, 120). Applies at the next start; see
  [Saving and reopening projects](../guides/saving_projects.md).

---

### 1.13 `data_loading` (staging of slow files, plot budget)

Read by `chisurf.core.fio.staging`; edited in **Settings ▸ Data loading…**.

- **`enabled`**  
  Copy a file to a local cache before reading it when its source is slow.

- **`threshold_mbps`**, **`min_size`**  
  A file is staged when the measured throughput is below `threshold_mbps`
  (MB/s) and the file is at least `min_size` bytes.

- **`probe_bytes`**, **`probe_min_bytes`**, **`probe_min_seconds`**  
  How much of the file head is read to measure the throughput.

- **`chunk_bytes`**, **`progress_interval`**  
  Copy chunk size, and how often (seconds) the progress is reported.

- **`import_to_container`**  
  Opening a vendor photon file creates the measurement's `.pto` container;
  off reads the vendor file where it lies.

- **`drop_guards`**  
  The "stop asking" choices of the drop prompts, keyed by prompt name.

- **`max_plot_points`**  
  Point budget of one raw per-photon plot (a time trace), across all its
  curves.

---

## 2. `experiment_configs.yaml` (experiment registry)

This file defines how high‑level "experiment types" are mapped to
reader classes and models. It is read through
`chisurf.core.experiments.load_experiment_types()` and
`chisurf.core.experiments.bootstrap`.

### 2.1 `experiment_types`

Top‑level mapping from experiment keys to display names and visibility:

- **`<key>.name`**  
  Human‑readable name shown in the GUI (e.g. `"TCSPC"`, `"FCS"`).

- **`<key>.hidden`**  
  If true, the experiment type is not shown in generic experiment selectors
  but can still be constructed programmatically.

### 2.2 Per‑experiment sections (`tcspc`, `stopped_flow`, `pda`, `deer`, `fcs`, `pcf`, `ics`, `mfd`, `pch`, `structure`, `global`)

Each experiment key has:

- **`readers`** – list of reader definitions:
  - **`reader_class`**  
    Fully‑qualified Python class path implementing the reader.
  - **`reader_params`**  
    Keyword arguments passed when constructing the reader
    (e.g. `name`, `experiment_reader`, file‑type specific hints).

- **`models`** – list of model class paths that can be used with this
  experiment type (e.g. TCSPC lifetime models, FCS models, PDA models).

These mappings allow new experiment types, readers, or models to be added or
reordered without changing Python code, by editing the YAML instead.
`controller_class`, `controller_params` and `settings_key` named the widgets of
the retired Qt window; nothing reads them.

One experiment may cover data of more than one shape — `pda` reads two-colour
S1S2 histograms and three-colour burst tables with the same reader — so a model
class can declare which datasets it accepts via `supports_data`, and the model
list offered for a dataset is filtered by it.

:::{note}
The copy of this file in your settings folder is merged **on top of** the
packaged one, so a section only your copy still knows about would shadow the
shipped one — including the readers and models added since. Sections that were
superseded are therefore dropped on load: `pda2c` and `pda3c` were merged into
the single `pda` experiment, and any customization inside them is not carried
over.
:::

---

## 3. `settings_colors.yaml` (global color palette)

`settings_colors.yaml` defines a list of named colors used throughout the GUI
for plots and styling. It is loaded as `chisurf.settings.colors`.

Each entry has the form:

```yaml
- hex: "#78DBE2"
  name: Aquamarine
  rgb: "(120, 219, 226)"
```

Fields:

- **`hex`**  
  Hexadecimal RGB color code cycled by the fit plots (line, weighted-residual,
  distribution, protein MC and parameter-scan pages) and the FCS merger.

- **`name`**, **`rgb`**  
  Colour name and the `(R, G, B)` string of `hex`; informational, no code
  reads them.

The palette provides a consistent set of visually distinct colors that can be
cycled for multiple data sets or used as theme colors by different plot types.


---

## 4. Resetting local settings

**Settings ▸ Reset local settings** deletes the settings files of the settings
folder (`~/.chisurf`), so the shipped values apply at the next start.

Resetting affects settings only. The settings folder also holds user data —
the metadata database (`~/.chisurf/flr/`), the object store
(`~/.chisurf/objects/`), the installed user plugins (`~/.chisurf/plugins/`) and
the fetched-structure cache (`~/.chisurf/structures/`) — and those are left
untouched. Clear the plugins with the separate **Clear user plugins** action.
