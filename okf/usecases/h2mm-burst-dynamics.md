---
type: Reference
title: Use case — sub-burst conformational dynamics with H2MM
description: Fit a photon-by-photon hidden Markov model to a folder of .bur bursts — pick the burst folder and the donor/acceptor streams, scan state counts with BIC/ICL, and read the dwell FRET states, transition rates, dwell times, per-state decays and the per-burst Viterbi state path.
tags: [usecase, burst, h2mm, smfret, dynamics, single-molecule, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: H2MM — dynamics inside the burst

**Goal:** the question a FRET histogram cannot answer. Burst selection gives one
E per burst, so a molecule that switches conformation *during* the ~1 ms it
spends in the focus shows up only as a broadened peak between two states.
**H2MM** (photon-by-photon hidden Markov modelling, Pirchi *et al.*, JPC B 2016)
fits the model directly to the photon arrival times and colours inside each
burst, so it recovers (a) how many states there are, (b) each state's apparent
FRET efficiency, (c) the transition *rates* between them, and (d) a
photon-resolved state path per burst. Concretely the user must: point the tool at
an existing burst folder, say which detectors are donor and acceptor, choose the
range of state counts to try and the selection criterion, run, then decide from
the BIC/ICL curve whether the winning model is believable.

**Tool:** `chisurf.plugins.burst.burst_h2mm` (`H2mmTool`, display name
*Spectroscopy:Single-Molecule:H2MM*) — a `QMainWindow` with a toolbar, a dock
area holding two settings tabs (*H2MM Settings*, *Channel Definitions*) and seven
independent result-plot docks. It is `menu_hidden`, so the normal way in is
**step 6. H2MM** of the [Burst Analysis](/usecases/burst-selection-fret.md)
navigation shell, which hands it the burst folder and channel settings.
Headless: `h2mm compute <ANALYSIS_FOLDER>` (CLI) or the
`burst_h2mm.jobs.compute` / `.workflow.prepare` RPC methods.

**Data:** `chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15/`
— the burst folder the repo ships next to the ten Becker & Hickl SPC-132 sm-DNA
files (`bi4_bur/m000.bur … m009.bur` plus `Info/`). The `.bur` tables only carry
`First File` / `First Photon` / `Last Photon`, so the tool re-reads the raw
`.spc` photons by walking up from the `.bur` directory. 2 980 bursts,
~220 000 photons in the selected streams, macro-time resolution 13.5 ns.

## Steps

1. Open **Spectroscopy → Burst Analysis → 6. H2MM** (or the standalone
   `H2mmTool`). The window opens on *H2MM Settings* with all seven result plots
   empty, the toolbar reading *No folder selected* and the status line *Ready*.
2. Press **▶ Run** before anything is loaded — the status line answers
   *"Please select a folder of .bur files first."* (no dialog, no traceback).
3. Drag the burst analysis folder onto the toolbar's folder field (or press
   **📁** for a folder chooser). Inside the Burst Analysis shell this step is
   already done: the folder and the detector setup arrive through the workflow
   context. Status: *"Data folder: …/burstwise_All 0.1000#15"*.
4. Switch to **Channel Definitions**. Pick a **Setup** — here `BS`, which brings
   file type `SPC-130`, macro-time 13.5 ns / micro-time 3.2959 ps, and three
   detectors: `green` = channels 8,0,3 over micro-time 0–4095, `red` = 9,1,2 over
   0–2048, `yellow` = 9,1,2 over 2048–4095.
5. Check the three combos above the table: **Donor detector** = `green`,
   **Acceptor detector** = `red`, **Acceptor (Aex)** — which the tool
   auto-selects as `yellow` whenever the setup has a third detector. For
   2-colour (non-ALEX/PIE) data set it back to **— none —**; leaving it on turns
   the whole analysis into an E–S analysis (see RF-326).
6. Back on **H2MM Settings** set the model scan — **Min states** 1, **Max
   states** 3–4, **Criterion** `bic` or `icl`, **Scan patience** 1 (stop early
   once the criterion rises) — and the optimisation: **Engine** (`EM float32` by
   default), **Restarts** 2, **Max iterations** 500, **Min photons/burst** 5,
   **Macro-time scale** 1, **Nanotime divisors** off.
7. Press **▶ Run**. A progress bar with an ETA appears (status bar when embedded,
   dialog when standalone, log when headless) and can be cancelled; the
   *Model selection* and *Dwell FRET states* plots update live after each state
   count finishes. The Run button is disabled for the duration.
8. Read the result. The status line reports *"Selected N states (BIC) from 2980
   bursts / 218452 photons"* and the seven docks fill:
   *Dwell FRET states* (per-state dwell-E histogram with the model E marked and
   the kinetic scheme drawn as arrows across the top — or an E–S scatter when an
   Aex stream is set), *Transition density*, *Model selection* (BIC and ICL vs
   state count), *Dwell times*, *Per-state decay* (micro-time histogram per
   state, log y), *Transition rates* (the rate matrix as a labelled heat map),
   and *State path*.
9. In **State path** step through bursts with **◀ / ▶** or the spin box and tick
   **dynamic bursts only** to visit just the bursts with ≥ 1 transition; the
   label reads *"burst 240 · 321 photons · 1 transitions"*.
10. Press **±** (*Uncertainty*) to bootstrap the selected model over bursts —
    20 resamples with their own progress bar — which overlays E (and S)
    confidence intervals on the dwell-FRET panel.
11. Press **📈** (*LL scan*) to profile the log-likelihood in each state's E and
    S; a dialog opens with the deviance profiles, the MLE, the likelihood CI and
    the bootstrap CI for comparison.
12. Press **💾** to save the active plot dock as PNG, and **ℹ** for the help
    dialog (method summary, workflow, and the `h2mm compute --help` CLI
    reference).

## Expected

- Every burst in the folder is loaded and fitted photon-by-photon; the number of
  bursts and photons is reported.
- The selected state count is the one the chosen criterion minimises, **and the
  user can tell whether that model converged and whether the criterion had
  actually turned around**.
- The per-state FRET efficiencies, populations, dwell times and transition rates
  describe the same model and are mutually consistent — a state whose escape
  rate is 15 s⁻¹ should not be reported with a 1 ms mean dwell time.
- Panels are labelled with what they actually show, in units the user can quote.

## Observed (last run: 2026-07-26)

Two complete runs on the repo burst folder, offscreen Qt (`QT_QPA_PLATFORM=offscreen`),
window driven programmatically, every step screenshot-inspected.

**The workflow works, and it is fast.** Folder drag-drop, setup selection,
combo population, the threaded fit with a live ETA and live plots, burst-path
navigation, the bootstrap and the likelihood scan all ran without a single
traceback or hang. Timings on this machine (`em-float32`, 2 restarts): states
1–3 in **20.5 s**, states 1–4 in **126 s**, the 20-resample bootstrap in
**73 s**, the likelihood scan (150 evaluations) in **23 s** — each with its own
cancellable progress bar. The empty-folder case gives a clear status message
rather than an error.

**Run A — the setup's third detector silently changed the analysis.** With
`BS` selected and the `Acceptor (Aex)` combo left at its auto-default `yellow`,
the tool fitted three streams and picked **3 states** (BIC 314141 / 260822 /
255110) with E = 0.022 / 0.395 / 0.855, populations 0.39 / 0.57 / 0.04 and rates
k₀₁ = 34 s⁻¹, k₁₀ = 46 s⁻¹, k₁₂ = 44 s⁻¹, k₂₁ = 685 s⁻¹. The primary panel
switched from the dwell-E histogram to a **Dwell E–S scatter** in which every
point sits at S = 0.93–0.99 — this is CW two-colour data, so the "Aex" stream is
just the delayed half of the red detector's TAC range and S is meaningless. No
warning is shown, and `has_alex` is simply "S is finite anywhere" (RF-326).

**Run B — the winning model did not converge and nothing said so.** With Aex set
to *— none —* and Max states 4, BIC kept falling (252391 → 202126 → 196504 →
195707) while **ICL exploded at n = 4** (197291 → 240711) and the n = 4 fit hit
the iteration cap without converging. The tool reported *"Selected 4 states
(BIC)"*, drew the model, and gave state pairs exchanging at **20 537 s⁻¹ and
17 248 s⁻¹** (49 µs dwells) — the textbook degenerate H2MM solution. The
`converged` flag is computed and stored in the result, but it is read by nothing
in the GUI, the CLI or the export (RF-322).

**The dwell-time panel disagrees with the transition-rate panel by ~50×.** Every
burst contributes at least one dwell, and the first and last dwell of each burst
are cut off by the burst boundary. Run B produced 11 905 dwells, of which 4 458
touch a burst edge and 1 502 *are* a whole burst; for the two slow states only
**4 of 1 378** and **3 of 156** dwells are interior. The *Dwell times* histogram
and the reported per-state mean (1.14 ms for state 0) are therefore essentially
the burst-duration distribution, while the *Transition rates* dock next to it
gives 1/k_out = 64.8 ms for the same state. The exported per-dwell CSV already
carries an `Is Edge` column; the GUI has no such filter (RF-321).

**The transition-density plot cannot show a density.** Transitions are recorded
with the *model* E of the two states, not the measured E of the dwells either
side, so the TDP is n·(n−1) delta peaks — verified: the set of distinct
"E before" values is exactly the four model efficiencies (RF-323).

**The likelihood-scan dialog is unreadable on real data.** Both axes are hard-set
to 0–1 while the deviance rises over ~0.005 in E, so each profile renders as a
vertical line, the shaded 95 % CI is sub-pixel, and the caption's advice ("a
window-wide CI means the state is poorly identified") cannot be acted on
(RF-325). The bootstrap that ran just before it gives usable numbers
(E₀ = 0.0205–0.0228, E₁ = 0.3875–0.4003, E₂ = 0.785–0.897).

**Smaller things seen in the screenshots.** The dwell-E histogram is weighted by
photons per dwell but its y axis is labelled *Dwells*, so the peak reads 60 000
where the fit has 11 905 dwells (RF-324). In *Channel Definitions* the detector
table gives its width to G-Factor / l1 / l2 and clips the three columns that
matter: the header reads *"tector Nar"*, and the yellow detector's micro-time
range `2048:4095` is shown as `048:4095` (RF-327). At 1600×1000 the default
two-column dock layout is clean and readable; below roughly 1300×600 the axis
tick labels of the six stacked plots collide.

Screenshots: `01_opened`, `03_folder_dropped`, `07_after_run`,
`08_plot_*` (all seven docks), `11_llscan`, `22_channel_tab_big`,
`25_run2_*` (scratch, not committed).

## UX / UI suggestions

- **Mark the selected model on the *Model selection* plot** and label the point
  (`n = 3, BIC = 255110`). Use integer ticks on "Number of states" — the axis
  currently reads 1.0, 1.5, 2.0, 2.5, 3.0.
- **Warn on a boundary solution.** Run A selected 3 states out of a maximum of 3
  with BIC still falling; the honest reading is "increase Max states", but
  nothing says so. A one-line note under the status message ("criterion still
  decreasing at the maximum state count") would prevent an over-confident
  conclusion.
- **Put units on the transition-rate matrix** (s⁻¹) and add a colour bar; "685"
  with no unit is not quotable. The same numbers appear as arrows on the
  dwell-FRET panel with no scale at all.
- **Plot dwell times on a log y axis** (as *Per-state decay* already does) with a
  common bin grid across states and, ideally, an exponential fit — the linear
  panel puts all the mass in the first bin and is unreadable.
- **Label the micro-time axis in ns.** `bundle.micro_time_ns` is known
  (3.2959 ps × binning), yet *Per-state decay* is plotted against "Micro time
  (channel)".
- **Fix the state-path axis label:** it reads "Time in burst (ms) (x0.001)" —
  a hand-written unit plus pyqtgraph's auto scale factor. Passing `units='s'` and
  letting pyqtgraph choose the SI prefix would give a single unambiguous label.
- **Default the state-path viewer to the first dynamic burst.** It starts on
  burst 0, which in this data has 0 transitions, so the panel's headline feature
  looks broken until *dynamic bursts only* is ticked.
- **Say what an empty plot is waiting for.** All seven docks show empty axes at
  startup; a centred "Run a fit to populate" placeholder would orient a first-time
  user.
- **Raise the *Min photons/burst* default.** 5 photons cannot inform a
  multi-state model; burstH2MM practice is a few tens. At minimum, report how
  many bursts the threshold discarded.
- **Give the settings column less width.** The default layout asks for a 300:1200
  split but the form's minimum width takes ~40 % of the window, squeezing all
  seven plots into the remainder.
- **Surface the per-state-count fit report** (iterations, convergence, restart
  spread) in a small table beside the model-selection curve — the data is
  already in `H2mmResult.scan`.

## Bugs filed

- **RF-321** — dwell-time histogram and `dwell_mean_s` pool burst-edge-censored
  dwells with complete ones; for slow states nearly every dwell is censored, so
  the panel contradicts the transition-rate matrix by ~50×.
- **RF-322** — the selected model's `converged` flag is stored and never read:
  a non-converged, ICL-rejected 4-state fit is reported as the result with no
  qualification.
- **RF-323** — the transition-density plot is built from model E instead of
  measured dwell E, so it can only ever be n·(n−1) delta peaks.
- **RF-324** — the dwell-E histogram is photon-weighted but its y axis says
  "Dwells".
- **RF-325** — `LikelihoodScanDialog` hard-codes the axis ranges, so profiles and
  their confidence intervals are invisible on any real-sized dataset.
- **RF-326** — the *Acceptor (Aex)* combo auto-selects a third detector, silently
  switching the primary panel to an E–S scatter and reporting a meaningless
  stoichiometry for non-ALEX data.
- **RF-327** — in *Channel Definitions* the detector table clips the detector
  name and micro-time-range columns (`2048:4095` → `048:4095`) while stretching
  G-Factor / l1 / l2.
