---
type: Reference
title: Use case — Lazy Lifetime Analysis (LLTF), the automatic component count
description: Point the automatic TCSPC fitter at a decay and its IRF and let it choose the number of exponentials, the analysis range, the background and the IRF shift for you.
tags: [usecase, tcspc, lifetime, decay, model-selection, gui]
timestamp: '2026-07-28T00:00:00Z'
---

# Use case: Lazy Lifetime Analysis — "how many exponentials?", answered for you

**Goal:** the ordinary [TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md) asks
the user for everything: which channels to fit, what the background is, how far
the IRF is shifted, and — the question that decides the answer — **how many
lifetime components** the decay has. The [F-test](/usecases/ftest-model-comparison.md)
answers the last one, but only after the user has built and fitted both models by
hand. LLTF ("Lazy Lifetime") is the one-button version: hand it a decay and an
IRF, and it estimates the analysis range, the background and the IRF shift,
fits 1…N exponentials, F-tests the series, and returns the component count it
judges warranted together with the lifetimes, the amplitudes and χ²ᵣ.

**Tool:** `chisurf.plugins.fluorescence_decay.lltf` (`LLTFGUIWizard`). It is
reached as panel **3. Lazy Lifetime Analysis** of the **Decay Analysis** hub
(`lifetime_analysis`, the same shell as
[MaxEnt MEM and the G-factor calibration](/usecases/decay-analysis-maxent.md)),
and it carries the red *experimental — not yet validated* banner. Its own
manifest is `menu_hidden`, so the hub panel is the only GUI entry point. The
same engine is a CLI: `csc lltf fit <decay> <irf> …`.

The GUI does **not** fit in-process: pressing **Fit** spawns
`python -m chisurf.plugins.fluorescence_decay.lltf.core fit …` as a subprocess
and streams its stdout into the *Analysis Output* tab. Everything the fit does
is therefore governed by the CLI's flags plus a YAML config file, and the panel
exposes only four of the ~25 settings.

**Data:** the plugin's own shipped example,
`chisurf/plugins/fluorescence_decay/lltf/example/` — `5-44_D0.dat` (a donor-only
TCSPC decay, 6100 channels at 0.008 ns, peak ≈ 10⁵ counts) and `IRF_D0.dat` (the
matching prompt, 3714 of its 6100 channels are exactly zero). Also
`example/config.yml`, the shipped settings example.

## Steps

1. Open **Decay Analysis** and pick panel **3. Lazy Lifetime Analysis**. The
   panel comes up with the experimental banner, four *Input Files* rows and a
   *Fitting Options* group; **Fit** is greyed out. *Config File* is already
   filled with a copy of the packaged defaults written to the system temp dir
   (`$TMPDIR/lltf_config.yml`); *Output Directory* is empty.
2. **Decay File ▸ Load…** and pick `5-44_D0.dat`. **Fit** stays greyed.
3. **IRF File ▸ Load…** and pick `IRF_D0.dat`. **Fit** enables.
4. **Config File ▸ Edit…** to review the analysis range, background, IRF-shift
   scan and model-selection settings before running — the only way to reach
   them, since the panel exposes none of them. *(This aborts the application —
   RF-877.)*
5. Tick **Find Optimal Number of Lifetimes**. *Number of Lifetimes* greys out;
   **Max Lifetimes to Try** (4) and **Probability Threshold** (0.68) enable.
6. Optionally **Output Directory ▸ Select…**. If left empty, pressing **Fit**
   silently fills it with the *decay file's own folder* and writes the results
   there.
7. Press **Fit**. The panel switches to *Analysis Output*. Nothing is printed
   for the whole run (31 s here); at the end the subprocess's buffered stdout
   arrives in one block and the panel switches itself to *Results*.
8. Read *Results*: an HTML table of amplitude and lifetime per component, then
   χ², χ²ᵣ, the fitted time range and the component count, with a matplotlib
   decay + weighted-residual plot below.
9. Collect `<decay stem>_fit.json` (full model curve, parameters, and the
   `optimal_fitting` scan scores) and `<decay stem>_fit.png` from the output
   directory.

## Expected

- With **Find Optimal** ticked and *Max Lifetimes to Try* = 4, the panel returns
  the component count best supported by the F-test over the 1…4 series — for
  this donor-only decay, **two** components (χ²ᵣ ≈ 1.5–4 with a fast minor
  component near 0.2–1 ns beside the ≈ 3.9 ns main lifetime), not the
  one-exponential fit whose residuals visibly bow.
- χ²ᵣ near 1 with structureless weighted residuals, and a plain statement when
  it is not.
- The IRF-shift estimate expressed in nanoseconds actually shifts the IRF by
  that many nanoseconds.
- The saved PNG legible: data, fit and IRF on a log-count axis spanning the
  data's own dynamic range.
- Settings reachable and a failed run leaving no stale numbers behind.

## Observed (last run: 2026-07-28)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) through both the
standalone `LLTFGUIWizard` and the Decay Analysis hub panel, with the shipped
example data. Screenshots at each step; the fit engine also exercised directly
and through `csc lltf` to separate GUI from engine.

**What works.** The hub embeds the panel cleanly behind the experimental banner
(*20_hub_lltf.png*). File loading, the **Fit**-enable gate (both files required),
the find-optimal enable/disable interlock and the subprocess plumbing are all
correct. The fit itself is real and quick — 31 s for a 1…4 component scan over
4948 channels — the analysis range (4.57–44.14 ns), background (3.46 counts) and
the reported numbers are self-consistent, the JSON carries the full model curve
*and* the per-n scan scores, and the *Results* plot the panel draws itself is
correct and well labelled (*06_plot.png*). Pressing **Fit** a second time during
a run is refused (*"Error: A process is already running."*). A two-exponential
fit requested explicitly (`-n 2`) returns 0.998 ns / 3.962 ns at **χ²ᵣ = 1.54** —
the engine can fit this decay well.

**The automatic component count picks the worst model it fitted.** With **Find
Optimal** ticked and max 4, the panel returned **one** lifetime, τ = 3.867 ns,
**χ²ᵣ = 9.07** — with weighted residuals swinging −6…+25 in an obvious bow
(*05_results.png*, *06_plot.png*). Running the shipped scan directly shows what
it had in hand and threw away: χ²ᵣ = **7.97 / 3.95 / 12.88 / 68.78** for n =
1/2/3/4. It fitted the good two-exponential model and returned the
one-exponential one. Two independent causes, both confirmed:

- The `'lower'` selection loop can only ever return `best_idx`'s initial value.
  It breaks out only where χ² *improved* **and** the F-test calls that
  improvement insignificant; while every added component keeps helping, the loop
  runs off the end with `best_idx` still 0 → **n = 1** (RF-878).
- The mode is `'lower'` even when the config says otherwise. The config file in
  use said `selection_mode: upper`, and the panel still behaved as `lower`,
  because the panel never passes `--selection-mode` and the CLI's `--find-optimal`
  branch overwrites whatever the config held with its own default. Forcing
  `-sm upper` on the *same* config file gives χ²ᵣ = **1.19** instead of 9.07
  (RF-879). The panel has no control for it.

Nothing about the returned χ²ᵣ = 9.07 is flagged: the log says *"Fit completed
successfully"* and *"Process completed successfully"*.

**Settings are unreachable.** **Config File ▸ Edit…** — step 3 of the panel's own
welcome text — raises `NameError: name 'LTFSettingsEditor' is not defined` and
takes the process down with SIGABRT (exit 134) (RF-877). The four spin boxes on
the panel are the only settings a user can change; the analysis range, the
background estimation, the IRF-shift scan, the randomisation bounds and the
pile-up correction can only be edited by finding `$TMPDIR/lltf_config.yml` in a
text editor.

**The IRF shift is in the wrong unit.** The shift is converted to channels as
`irf_shift / 2.0` — a hard-coded 2 ns channel width, independent of the data. On
this example (0.008 ns per channel) asking for **8 ns moves the IRF 4 channels =
0.032 ns**, 250× short; 1 ns and 2 ns both move it by the same single channel.
`estimate_irf_shift` over the configured ±8 ns therefore rails at exactly
`8.0` — the edge of its own scan range — and the correction that gets applied is
≈ 0 (RF-880). The residual spike at the rising edge in every plot is consistent
with this.

**Verbose does nothing.** With the panel's **Verbose Output** ticked the run
printed 8 lines. The panel always passes `-c <config>`, and `fit_lifetime`
overrides the explicit `-v` with the config's `verbose:` — which is `false` in
the shipped defaults. The same command without `-c` prints the full per-step log
(range, background, IRF-shift estimate, per-component results) (RF-881).

**The scan's own evidence is computed and thrown away.** The config ships
`plot_probabilities: true` and `plot_weighted_residuals: true`; both figures are
built inside the subprocess and handed to `plt.show()`, which in a headless
child does nothing (`FigureCanvasAgg is non-interactive`). The probability-vs-n
bar chart that justifies the component count never reaches the panel (RF-883).
The scan scores *are* in the JSON, but nothing in the GUI displays them.

**The saved PNG is the unusable one.** The plot the panel draws is fine; the
`<stem>_fit.png` written beside the data is not — the IRF's ~3700 zero channels
are clipped to the bottom of the log axis rather than masked, so a solid green
block covers the figure, and in the find-optimal run it dragged the y-axis down
to 10⁻⁸ and squeezed the data and fit into the top eighth of the panel
(*out/5-44_D0_fit.png*) (RF-882).

**A failed fit leaves the previous answer on screen.** Feeding a file that is not
a decay dumps a raw Python traceback ending
`TypeError: Improper input: N=5 must not exceed M=(2,)` into *Analysis Output* —
no dialog, no plain-language message — and the *Results* tab still shows the
**previous** file's table, χ²ᵣ and plot, with nothing marking them stale
(*11_bad_input.png*) (RF-884).

Screenshots: `01_opened`, `02_files_loaded`, `03_options_set`,
`04_analysis_output`, `05_results`, `06_plot`, `10_results_large`,
`11_bad_input`, `20_hub_lltf`.

## UX / UI suggestions

- **Say when the fit is bad.** χ²ᵣ = 9.07 with bowed residuals is reported as
  *"completed successfully"*. Colour χ²ᵣ against a threshold and say so in one
  sentence beside the number.
- **Show the scan.** The 1…N table of χ²ᵣ, F-probability and parameter count is
  already computed and already in the JSON. It is the whole justification for
  the component count and it appears nowhere in the panel — put it in *Results*
  as a small table with the selected row marked, instead of a matplotlib window
  that never opens.
- **χ²ᵣ is below the fold.** The results splitter is fixed at `[200, 400]`, so
  the pane shows the lifetimes table and cuts off χ², χ²ᵣ, the time range and the
  component count; the user must scroll a 150 px box to read the fit quality, at
  1000×800 *and* at 1400×1000. Size the text pane to its content.
- **No progress for 31 s.** The subprocess's stdout is block-buffered, so the
  output pane stays empty for the whole run and then fills at once. Run the child
  with `-u` (or line-buffered) and add a busy indicator; **Stop Process** is
  enabled the whole time but there is nothing on screen to suggest work is
  happening.
- **Expose selection mode and the analysis range.** The two settings that most
  change the answer — the component-selection mode and the fit range — are not
  on the panel, and the one path to them (**Edit…**) is broken.
- **Disable Fit while a fit runs.** It stays enabled; the second press is
  refused with a line of text buried in the log pane rather than by the button
  going grey.
- **Do not write into the user's data folder by default.** Leaving *Output
  Directory* empty silently redirects the JSON and PNG next to the decay file.
  Pre-fill the field when the decay is loaded so the destination is visible
  before **Fit**, not after.
- **Labels need units and meaning.** *Probability Threshold* (0.68) is an F-test
  confidence and reads like a fraction; *Max Lifetimes to Try* has no tooltip.
  Both want a `description` in the tooltip-and-docs sense the rest of ChiSurf
  uses.
- **The result cannot leave the panel.** A finished LLTF fit produces a JSON file
  and nothing else — no dataset, no fit in the session, no hand-off to the
  regular lifetime fit for refinement. A **Send to ChiSurf** action would make
  this the fast first pass it is meant to be.
- **A nested menu bar inside a panel.** The embedded `QMainWindow` keeps its own
  *File / Settings / Analysis* menu bar inside the hub panel, duplicating the
  buttons beside it and offering an *Exit* whose meaning inside a panel is
  unclear.

## Bugs filed

- **RF-877** — *Config File ▸ Edit…* raises `NameError` (`LTFSettingsEditor` vs
  `LLTFSettingsEditor`) and aborts the process; the only route to the analysis
  settings.
- **RF-878** — the `'lower'` component-selection loop returns its initial
  `best_idx = 0` (n = 1) whenever every added component keeps improving χ²;
  the scan picked χ²ᵣ = 7.97 over 3.95.
- **RF-879** — the panel never passes `--selection-mode`, and the CLI's
  `--find-optimal` branch overwrites the config file's `selection_mode` with its
  own default, so a config saying `upper` runs as `lower` (χ²ᵣ 9.07 vs 1.19).
- **RF-880** — the IRF shift is converted with a hard-coded 2 ns channel width,
  so a shift asked for in ns is applied 250× too small on 0.008 ns data and the
  shift estimate rails at its scan-range edge.
- **RF-881** — the config file's `verbose` overrides the explicit `-v` flag, so
  the panel's *Verbose Output* checkbox never does anything.
- **RF-882** — the saved `<stem>_fit.png` clips the IRF's zero channels to the
  log-axis floor, painting a green block over the figure and stretching the axis
  to 10⁻⁸.
- **RF-883** — the model-selection probability plot and the per-n residual panel
  are built in the fit subprocess and handed to `plt.show()`, so the evidence for
  the chosen component count is silently discarded.
- **RF-884** — a failed fit leaves the previous run's table, χ²ᵣ and plot in the
  *Results* tab and reports the failure as a raw Python traceback.
