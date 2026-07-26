---
type: Reference
title: Use case — PCH molecular brightness and occupancy
description: Turn a photon stream into a photon counting histogram and fit it for molecular brightness (ε) and mean occupancy (⟨N⟩) — load a TTTR file, choose channels and bin time, compute P(k), fit one or more species, restrict the k range, export.
tags: [usecase, pch, single-molecule, brightness, tttr, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: PCH — molecular brightness and occupancy

**Goal:** the "burst analysis / single-molecule" coverage list item that FCS
cannot answer. FCS gives the *number* of molecules and how fast they move; the
**photon counting histogram** gives how *bright* each one is. The user bins the
photon stream into short counting intervals (typically 10–100 µs, well below the
diffusion time), histograms "how many bins saw exactly *k* photons", and fits
that P(k) with a super-Poissonian model whose parameters are the molecular
brightness ε (counts per bin per molecule) and the mean occupancy ⟨N⟩ of the
detection volume. Two species with the same diffusion time but different
brightness — a monomer and its dimer, a labelled and an unlabelled fraction —
separate here and nowhere else. Concretely the user must: pick the detection
channels, pick a bin time, compute P(k), choose how many species to fit, give
starting values, restrict the k range away from the noise tail, judge χ²ᵣ, and
export.

**Tool:** `chisurf.plugins.pch` (`PCHApp`), a standalone `QMainWindow` reached
from the ribbon at **Spectroscopy → Single-Molecule → PCH**. Backend as three
ZMQ/JSON-RPC services (`pch.load_tttr`, `pch.compute`, `pch.fit`) behind a
`PCHClient`; headless path `csc pch analyze <file>` / `csc pch refit <npz>`.

**Data:** any TTTR file the reader accepts. This walk used
`test/data/clsm/Leica_SP5.ptu` (6 714 549 photons, 150 s, routing channels
0/1/2/4/6, 50 ns macro-time resolution) and `test/data/clsm/Leica_SP8.ptu`
(3 104 829 photons, 130 s, routing channels **1** and 15) as the "wrong
channels" case. Both are confocal *scans* rather than a solution measurement, so
their P(k) carries the scan structure — fine for exercising the tool, not a
physics reference.

## Steps

1. Open **Spectroscopy → Single-Molecule → PCH**. The window is a toolbar
   (**📥 Load TTTR**, **📊 Compute PCH**, **🧪 Fit Model**, **💾 Save Results**,
   and **ℹ Help** pushed to the right) over a splitter: two stacked plots on the
   left (*Intensity Trace*, *Photon Counting Histogram*) and a settings column on
   the right (*Data Settings*, *Model Fit*). Compute/Fit/Save start disabled.
2. Click **📥 Load TTTR** and pick the file. The status bar reports
   `Loaded: … (6,714,549 photons)` and **📊 Compute PCH** becomes enabled. The
   file path appears in the read-only *File:* field.
3. In *Data Settings* set **Channels** (comma-separated routing channels;
   defaults to `0,2`), **Bin Time** (default `100.00 µs`) and the **Micro Time**
   acceptance window (default `0` to `65535`, i.e. no gating). Micro-time gating
   is how a lifetime-selected PCH is done.
4. Click **📊 Compute PCH**. The *Intensity Trace* fills with the binned photon
   trace and the *Photon Counting Histogram* with P(k) on a log y axis; the
   status bar reports `Computed PCH: 1,501,367 bins, 126 k-values`. **🧪 Fit
   Model** and **💾 Save Results** become enabled.
5. In *Model Fit* set **Components** (1–10). One ε and one ⟨N⟩ spin box appear
   per species; type starting values (defaults ε = 2.0, ⟨N⟩ = 3.0).
6. Drag the region selector on the histogram to the k range to be fitted — this
   is how the noise tail is excluded.
7. Click **🧪 Fit Model**. The fitted P(k) should be drawn over the data in red,
   the fitted ε and ⟨N⟩ written back into the spin boxes, the *Fit Results* box
   filled with per-component ε / ⟨N⟩ / fraction and χ², red. χ², dof, and the
   status bar updated with the χ² summary.
8. Re-drag the region: χ² is re-scored over the new range without re-fitting.
9. Click **💾 Save Results**, give a base name, and get `.npz` (trace, k, P_exp,
   P_fit, the result text), `.csv` (k, P_exp, P_fit), `.txt` (the result text)
   and two `.png` screenshots.

## Expected

- P(k) normalised (Σ P(k) = 1) with a monotonically falling tail on a log axis.
- A fitted curve visible on top of the data, the fitted parameters in the boxes
  *and* in the *Fit Results* text, and a χ²ᵣ near 1 for a well-modelled
  measurement — the fitted ε·⟨N⟩ should reproduce the measured mean counts per
  bin.
- Raising **Components** to 2 adds a second ε/⟨N⟩ pair; the fit then reports two
  species with fractions.
- A channel list that matches no photon in the file gives a comprehensible
  message ("no photons in channels 0, 2 — the file has 1, 15"), not a numpy
  traceback, and does not leave the previous file's histogram on screen.

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env) by constructing
`PCHApp`, stubbing the two file dialogs, triggering the real `QAction`s in order
and grabbing the window at every step. **Steps 1–4 and 9 work. Steps 5–8 — the
entire fitting half of the tool, which is its whole purpose — do not.**

- **Loading and computing are fast and correct.** 6.7 M photons load in ~0.1 s
  and the 1.5 M-bin histogram is computed in **0.71 s**; Σ P(k) = 1.0 exactly,
  126 k-values, mean 4.43 counts per 100 µs bin, trace length 150.14 s — all
  matching the file. The two plots look right (screenshot `03_computed.png`).
- **Every click on 🧪 Fit Model ends in a modal error box reading
  `name 'np' is not defined`.** `gui/tool.py` never imports numpy at module
  level (only locally inside `_save_outputs`), so `_plot_fit` dies on its first
  `np.array`. The fit *itself* had already succeeded — ε = 0.672 and
  ⟨N⟩ = 2.658 were written back into the spin boxes — but **no curve is ever
  drawn and the *Fit Results* box stays empty for the whole session**
  (`04_fit1.png`). The same `NameError` kills `_update_results_text`, so
  dragging the region (step 8) is silently inert too. Filed **RF-208**.
- **The Components spin box is dead.** Setting it to 2 raises
  `TypeError: object of type 'int' has no len()` inside `_update_species_inputs`
  (`len(self.species_layout.count())`). Qt swallows it, so the panel keeps
  showing a single **ε 1 / ⟨N⟩ 1** pair while the box reads **2** — visible in
  `05_fit2.png` and `10_recovered.png`. Multi-species PCH, the reason the plugin
  exists, cannot be reached from the GUI at all. Filed **RF-209**.
- **The mismatch is not caught anywhere downstream.** Fitting with
  Components = 2 while one species row exists sends `n_components=2` with one ε
  and one ⟨N⟩; the backend splits the flat parameter vector as `p[:2]` = the two
  epsilons and `p[2:]` = *no* occupancies, and returns `ok: True` with
  `avg_Ns: []`, `fractions: []` and `p_fit = [1, 0, 0, …]` — a delta at k = 0 —
  plus a chi2 of 581 023. The GUI then throws `IndexError: list index out of
  range` writing the results back, but `self._fit_result` already holds the
  garbage, and **💾 Save Results happily wrote it out**: the exported
  `p_fit` column is `1, 0, 0, …`, the `.txt` is **0 bytes** and the npz's
  `fit_results` array is empty, under an "Results saved as: …" success dialog.
  Filed **RF-210**.
- **χ²ᵣ is reported as 1.13 × 10¹⁸ with no warning.** The fit minimises
  *unweighted* residuals on P(k), so the first few k (P ≈ 0.4) carry all the
  weight and the k = 10…60 shoulder carries none, while goodness is scored as a
  Pearson χ² on counts. The 1-component result has a model mean of 1.12 counts
  per bin against the data's 4.43, and predicts P ≈ 4 × 10⁻¹⁸ at k = 32…40 where
  4 500–5 700 bins were actually observed. Both the GUI status bar and
  `csc pch analyze` print the number as if it were a fit statistic
  (`red. χ² = 1132474425680562304.000`). Filed **RF-211**.
- **The ℹ Help button is dead** — `HelpDialog` uses `QDialogButtonBox` without
  importing it, so nothing opens. Filed **RF-212**.
- **The documented CLI invocation does not exist.** The README and the (dead)
  Help dialog both say `python -m chisurf pch analyze data.ptu`; that is not a
  subcommand, and `python -m chisurf pch --help` **launches the GUI and hangs**
  (killed after 300 s). The working form is `csc pch analyze …`, which does run
  end to end. Filed **RF-213**.
- **Wrong channels produce a raw numpy traceback and a stale screen.** The
  default `0,2` on a file whose channels are 1 and 15 selects zero photons; the
  backend dies on `times.max()` of an empty array and the dialog reads
  `zero-size array to reduction operation maximum which has no identity`. The
  status bar still showed the previous `Loaded: …` message, and the histogram
  still showed the **previous file's** data (`09_wrongchannels.png`) — a user
  could easily read it as a valid result. `pch.load_tttr` already returns
  `routing_channels`, and the GUI never uses them. Filed **RF-214**.
- Recovering by typing the real channel and a 1000 µs bin time works
  (`10_recovered.png`, 130 358 bins, 23.1 counts/bin).
- The plugin's own GUI test (`chisurf/plugins/pch/test/test_widgets.py`) only
  constructs `PCHApp` and asserts the window title — none of the above is
  reachable by it.

## UX / UI suggestions

- **Discover the channels instead of guessing them.** `pch.load_tttr` already
  returns `routing_channels` and the photon count; after loading, replace the
  free-text `0,2` with the file's actual channels (a checkable list, or at least
  a "file has channels 1, 15" hint under the field) and grey out **Compute** for
  a selection that matches nothing.
- **Say what the settings mean, in units the user thinks in.** *Bin Time* has no
  guidance that it must be well below the diffusion time; *Micro Time* is a
  raw TAC-channel index pair (0–65535) with no ns equivalent and no indication
  that the file's range is only 0–2000, so the default silently means "no
  gating". Both want the `description` tooltip the project standard requires.
- **The region selector is unlabelled and unreadable.** It is a dark blue box
  that by default covers the *entire* histogram, dimming the white data points
  under it, with nothing saying it is the fit range. Show the current `k` range
  as text (or two spin boxes beside it, as the fFCS calculator does), and start
  it at a sensible sub-range rather than the whole axis.
- **The y axis of a probability plot should not get an SI multiplier.** After
  the second compute the histogram axis read `P(k) (×0.001)` with ticks
  `10², 10¹, 1, 0.1` on a log scale — a probability shown as 300. Pin the
  multiplier to 1 for P(k).
- **Nothing marks a result as stale.** Changing *Channels*, *Bin Time* or
  *Micro Time* leaves the old histogram and the old fit on screen
  (`_on_param_changed` is a literal `pass`), and loading a new file leaves the
  previous file's plots up. Clear the plots on load and grey the fit output when
  an input changes.
- **Guard the export.** **💾 Save Results** is enabled as soon as a histogram
  exists and writes a `.txt` of whatever is in the (possibly empty) results box
  plus a `p_fit` column of zeros, then reports success. Either disable the fit
  columns when no valid fit exists or state in the dialog what was actually
  written. Two of the five files are *screenshots of the window* — useful, but
  they should be announced as such, and the base-name dialog gives no extension
  hint.
- **Show the sanity check the user would do by hand.** The measured mean counts
  per bin is already computed; print it next to the fitted Σ ε·⟨N⟩ in the
  results box. A one-line "model mean 1.12 vs measured 4.43" would have made the
  bad fit above obvious without any statistics.
- **Fit progress and bounds.** A multi-species fit over a long k axis runs
  `least_squares` with a numba/FFT model and no progress indication or cancel;
  the ε/⟨N⟩ boxes accept 0 and 10⁶ with no unit suffix (ε is *counts per bin per
  molecule* — say so).

## Bugs filed

- **RF-208** — `numpy` is not imported in `pch/gui/tool.py`, so every **Fit
  Model** click raises `NameError: name 'np' is not defined`: the fit curve is
  never plotted and the *Fit Results* box never fills.
- **RF-209** — `_update_species_inputs` calls `len()` on an `int`, so the
  **Components** spin box never rebuilds the species rows and multi-species PCH
  is unreachable from the GUI.
- **RF-210** — `pch.fit` does not validate `len(initial_epsilons)` /
  `len(initial_Ns)` against `n_components`; it returns `ok: True` with empty
  occupancies and a delta-function `p_fit`, which the GUI then exports.
- **RF-211** — the PCH fit minimises unweighted P(k) residuals but scores a
  Pearson χ² on counts, reporting χ²ᵣ ≈ 1.1 × 10¹⁸ as a normal result in both
  the GUI and the CLI.
- **RF-212** — the **ℹ Help** button is dead: `HelpDialog` uses
  `QDialogButtonBox` without importing it.
- **RF-213** — the README and the in-app help document
  `python -m chisurf pch analyze …`, which is not a subcommand and instead
  launches the GUI and hangs; the real entry point is `csc pch`.
- **RF-214** — a channel selection matching no photon crashes with a raw numpy
  message, leaves the status bar on the previous message and the previous
  file's histogram on screen.
