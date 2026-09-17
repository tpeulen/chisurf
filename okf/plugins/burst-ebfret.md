---
title: ebFRET — the MATLAB GUI and analysis, ported onto emtk
status: in-progress
group: plugins
updated: 2026-09-17
---

# ebFRET — the MATLAB GUI and analysis, ported onto emtk

`chisurf/plugins/burst/burst_ebfret/` is a **plain port** of the ebFRET GUI
(`junk/ebFRET`, github.com/ebfret/ebfret-gui at 28e548a, MIT): the
`ebfret.ui.MainWindow` window with its panels, menus, dialogs and defaults, and
the MATLAB analysis behind it. Plain means reproduced, not redesigned: every
control of the MATLAB window is present under its MATLAB name with its MATLAB
default, every numerical function is transcribed line by line and checked
against ebFRET running under GNU Octave. The theory is in
[ebfret-theory](../references/ebfret-theory.md); the user docs are
`docs/concepts/ebfret.md` and `docs/guides/20_ebfret_binned_hmm.md`.

## Where to pick this up

1. **Speed of the analysis loop.** Pure NumPy, serial: about 3 ms per `vbayes`
   call and about 5 s per empirical-Bayes iteration at K = 2 on the 350-trace
   `simulated-K04-N350` set (measured by fork A, `tests/test_recovery.py` slow
   test: K = 2 full dataset in 24 s). ebFRET's MEX forward-backward plus
   `parfor` is much faster, so a full K = 2..6 scan with the default 2 restarts
   takes minutes here. The per-trace work is embarrassingly parallel
   (`core/ebayes.py::run_vbayes` batches of 24, the `parfor` of
   `run_vbayes.m`), and the forward-backward is the hot loop
   (`core/hmm.py::forwback`). Tried: nothing yet. The obvious route is the
   compiled Gaussian-HMM kernels in tttrlib that `chisurf/core/math/hmm.py`
   already delegates to — but that module's Baum-Welch is maximum likelihood,
   not the VB e-step, so it needs a VB forward-backward entry point there first.
   Re-measure with `pytest -m slow chisurf/plugins/burst/burst_ebfret/tests`.
2. **Random restarts are A/B'd statistically only.** `init_posterior` with
   `draw_params` draws from `gamrnd`/`wishrnd`/`mvnrnd`; NumPy's generator gives
   different numbers, so the Octave fixtures use `restarts <= 1` (deterministic)
   and the default `restarts = 2` is checked by recovery instead: on the demo
   with seed 7, one restart ends at E = [0.20, 0.38, 0.50, 0.72], two recover
   [0.10, 0.35, 0.55, 0.75] (`tests/test_session.py`). A trap for whoever
   compares runs: a session's seed fixes the draws, MATLAB's do not repeat.
3. **Cosmetics that emtk's implot shim decides.** The y-axis label shares the
   plot's title row (emtk cannot rotate text), so *Probability* sits left of
   *Histograms* and *Donor / Acceptor* above its axes; the ensemble's y tick
   numbers are hidden with `AXIS_FLAGS_NO_TICK_LABELS` as MATLAB blanks them.
   A rotated axis title would need a painter operation emtk does not have.
4. **Tables are ChiSurf additions.** View → *Series List* (`data_table`,
   selection drives *Select Series*) and *States Table* (`table`, the selected
   model per state) are declared in `gui/main.view.json` and drawn by emtk's
   view-spec table support (emtk fbf3290). They float over the right half of the
   Time Series / Ensemble panel because the MATLAB layout has no room; a
   docked placement is open.

## What the MATLAB app consists of

* **One window** (`@MainWindow/MainWindow.m`, 1200×800): *Time Series* panel
  (signal `Signal [Efret]` over `Donor / Acceptor`, x `Time [Δ t]`, Viterbi path
  as state-coloured markers, frames outside the crop dashed); *Select Series*
  (edit + slider, `IndexControl.m`) and *Crop* (*Min*, *Max*, *Exclude*);
  *Ensemble* panel (*Histograms*, *Centers*, *Noise*, *Dwell Time* on a log
  axis; prior dashed, mean posterior solid, optionally scaled by occupancy);
  *Select States*, *States* (*Min*, *Max*), *Analysis* (*States* All|Current,
  *Restarts*, *Precision*, *Run*, *Stop*, *Reset*).
* **Menus**: File (Load, Save, Export ▸ Analysis Summary / Traces /
  Single-molecule Dataset (SMD), Exit), Analysis (Remove Photo-bleaching, Clip
  Outliers, Set Priors), View (Viterbi Paths, Prior, Posterior, Normalize by
  Occupancy).
* **Dialogs**: Remove Photo-bleaching, Set Priors, Channels, Assign Channels,
  Select (states/group), plus `questdlg` (Append Data? Keep/Replace/Cancel;
  Update Priors Auto/Manual/Keep Current), `inputdlg` (Select Range),
  `msgbox`/`warndlg`/`errordlg`, `waitbar`, `uigetfile`/`uiputfile`.
* **Formats**: session `.mat` (controls, series, analysis, plots); raw `.dat`
  (stacked `[id donor acceptor]` or 2N columns, first row of each series its
  label); SF-Tracer `.tsv`; SMD `.mat`/`.json`/`.json.gz` in and out; analysis
  summary `.csv` (`write_report.m`); traces `.dat` (`save -ascii`) / `.mat`.
* **Defaults** (constructor): clip −0.5…1.5, states 2…6, restarts 2, precision
  1e-3, crop margin 20, all View items on; Set Priors 0 / 1 / 0.05 / 100 and
  0.1 / 10 / 10; Clip Outliers −0.2 / 1.2 / 10.

## Where it landed

| MATLAB | port |
| --- | --- |
| `@MainWindow/*.m` callbacks | `core/session.py::Session` (one method per file), dialogs' answers as arguments |
| panels, menus, layout | `gui/app.py` (`GEOMETRY` = the constructor's normalized positions), `gui/main.view.json` + `gui/controls.py` |
| `+ui/+dialog/*`, `inputdlg` | `gui/{remove_bleaching,set_priors,clip_outliers,select_channels,assign_smd_channels,select_analysis}.view.json` + `gui/dialogs.py` forms |
| `refresh.m`, `+plot/*` | `core/plots.py`, `core/views.py` (JSON view), drawn by `gui/app.py::_plot` |
| `+analysis/+hmm`, `+dist`, `photobleach_index`, `x_lim` | `core/hmm.py`, `core/dist.py`, `core/_matlab.py` (MATLAB `hist`/`linspace`/`median`/`std` semantics) |
| `run_ebayes.m`, `run_vbayes.m` | `core/ebayes.py`; runs in `backend/services.py::SessionStore.run` |
| `+io/*`, session, exports | `io.py` |
| — | `api/client.py` (GUI → RPC), `gui/tool.py` (Qt host, tour anchors), `demo.py`, `gui/guide.json`, `gui/help.md` |

The window is **declared and DB-free**: the GUI holds only the last view and
talks to `burst_ebfret.session.*` RPC methods (in-process dispatcher by
default). Form-like controls are AutoForm `view.json` specs drawn by
`emtk.view_form`; hand-drawn emtk code is only the plots, the menu bar, the
panel frames and the generic question/message boxes.

## emtk additions made for this port

* `88b00f7` — implot dashed lines (`set_next_line_style(..., dash=)`),
  `set_next_marker_style`, `AXIS_FLAGS_NO_TICK_LABELS`/`NO_LABEL`, decade log
  ticks; `emtk.file_dialog.FileDialog` (filters with index, multiselect, save
  extension).
* `0a2f840` — `input_text` `ENTER_RETURNS_TRUE` fired only for key 13, never for
  Qt's Return/Enter codes under `qt_host`.
* `2eb8919` — `emtk.view_form` (AutoForm spec as an immediate-mode form, with
  `enabled`/`bounds` model hooks); `fit_text` half-pixel slack (the widest menu
  label lost its last letter: "Expo."); log tick text 3 significant digits.
* `5de0258` — `view_form` columns align within a panel.
* (fbf3290, by the ndX/VizRank session) — table/data_table rendering used for
  the two tables.

## Validation (A/B)

* **Core vs Octave-run ebFRET** (`tests/test_octave_ab.py`, fixtures from
  `tests/octave/make_fixtures.m`; 6 traces of 70–120 frames, K = 2/3):
  guess/init prior, init_posterior, e-step, forward-backward, m-step, KL, the
  17-step VBEM lower-bound trace, dirichlet tau, get_bins, whist (counts
  exact), state curves, get_lim, time_series ≤ 4e-14 relative; x_lim,
  num_to_str, Viterbi paths exact; three EB iterations L = [696.66188763,
  753.66994934, 754.81480797] within 1.5e-14, priors/posteriors ≤ 6e-12;
  h_step, h_step_remap, report ≤ 1.2e-11; photobleach_index same indices.
  Octave 11 cannot run `import`, so the driver patches a *temporary copy* of the
  sources (the `hmm.`/`dist.` shortcuts and one unparseable dead condition in
  `dirichlet/h_step.m`); the junk files are only annotated.
* **Core vs MATLAB** (the shipped session `.mat`, K = 4, compiled kernels):
  restarting VBEM from the saved posteriors reproduces the saved lower bounds to
  ≤ 1.9e-8 on 24 series with identical Viterbi paths. Full dataset K = 2:
  [0.303, 0.547] vs ebFRET's [0.30, 0.55].
* **Formats** (`tests/test_io.py`): raw load gives the MATLAB session's 350
  series exactly; K = 4 traces export byte-identical to
  `simulated-K04-N350-traces-K04.dat`; SMD `.json.gz` line-identical over
  107 241 lines except ids and version string; SMD `.mat` to 1e-9; the MATLAB
  session loads and re-saves unchanged; Octave loads a Python session with
  identical fields/shapes; `write_report` byte-identical to Octave.
* **Workflow/GUI**: `tests/test_session.py`, `test_services.py`,
  `test_gui.py` (emtk window driven by clicks, every declared control drawn,
  tour anchors exist), `test_tool_qt.py` (offscreen Qt host, tour resolution).

## Control parity (MATLAB → port)

All present: the 6 File entries, 3 Analysis entries, 4 View entries; the 7
panels and their 14 controls (series edit/slider, crop min/max, exclude, states
edit/slider, min/max states, All|Current, restarts, precision, Run, Stop, Reset);
every dialog control listed above with its default. **Deliberate differences:**
dark emtk theme instead of MATLAB grey; `uipanel` borders drawn as etched boxes;
popups are a button with a list; the file dialog is emtk's, not the OS one;
the loading `waitbar` is dropped (loads are synchronous and short); the
"Number of Sates" label typo is shown as "Number of States"; `questdlg`'s
literal `\n\n` is shown as a line break; *Load demo*, **Guide**, `?` and View →
*Series List* / *States Table* are additions; the analysis runs in a backend
thread (the window follows the series every second like `run_vbayes.m`'s redraw,
the 10 s ensemble redraw is replaced by revision polling).

**Not taken** (reasons in the junk headers): the prior-mixture path
`+hmm/ebayes.m` (calls `init_w_hmm`/`vbem_hmm`/`hstep_nw`/`hstep_dir`, which do
not exist in the checkout; nothing calls it) and `normwish/h_step.m` that only
it uses; `gmm/map.m` and the k-means restarts (never enabled by the GUI);
`jitter_filter.m` (`ignore='none'` always); MEX/C++ kernels; `+batch/*`
(command-line drivers; `core/analysis.py::analyse` and the CLI are the headless
path); invgamma and unused dist moments; MATLAB-only checks
(`check_parfor`, `check_matlab_version`). SMD ids are MD5 of the values
(DataHash's MATLAB serialisation is not reproducible); SMD load sets `group`
(MATLAB's SMD branch never does, which breaks later grouping); the SMD export
writes the stored Viterbi path whole (`write_smd.m` crops an already-cropped
path, misaligning series cropped at the start).

`junk/ebFRET` coverage: 126 of 127 counted files reviewed
(`python -m build_tools.dev_utils.reference_coverage junk/ebFRET`; `.m` counted
since this port); `ORIGIN.txt` is checkout metadata and left untouched.
`documentation/ebfret_user_guide.tex` and the `+ui` files carry headers too.
