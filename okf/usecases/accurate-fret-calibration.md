---
type: Reference
title: Use case — Accurate FRET (automatic α/β/γ/δ from the bursts)
description: Turn a per-burst table into a *quotable* efficiency — let the tool find the burst populations itself, determine the four Hellenkamp correction factors from them, and read the corrected E–S, E–lifetime and distance with error bars.
tags: [usecase, smfret, fret, burst, calibration, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: Accurate FRET calibration

**Goal:** the step between a burst search and a quotable number. A raw
proximity ratio is not an efficiency: donor leakage α, direct acceptor
excitation δ, the detection/quantum-yield ratio γ and the excitation-flux ratio β
all sit between the counts and E. This tool determines all four **from the
measurement itself** — no hand-drawn population gates — and reports the accurate
E, S and distance of every population it finds, with the static and dynamic FRET
lines to judge the result against.

**Plugin:** `accurate_fret` v1.0.0,
`chisurf.plugins.burst.accurate_fret.gui.tool:AccurateFretTool`, menu
**Spectroscopy → FRET → Accurate FRET** (`menu_hidden: false`, verified through
`PluginRegistry.discover`). Docs: guide
[`docs/guides/41_accurate_fret.md`](../../docs/guides/41_accurate_fret.md).

**Data:** two sources were driven this run.

* **Simulated ALEX** — the tool's own demo path, `csc accurate-fret --simulate
  demo_bursts.csv --simulate-photons 350000`, which writes 1508 bursts with the
  declared truth in the file header (γ = 0.65, α = 0.08, β = 1.40, δ = 0.06,
  E = 0.30 / 0.75, τ_D(0) = 4.0 ns, R₀ = 52 Å) and columns
  `i_dd, i_da, i_aa, tau_f, n_photons, species`.
* **Real MFD `.bur`** —
  `chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15/bi4_bur/*.bur`
  (Becker & Hickl SPC-132, freely diffusing doubly-labelled dsDNA; 10 files,
  407 bursts and 32 columns in `m000.bur`).

## Steps

1. Open **Spectroscopy → FRET → Accurate FRET**. The window is a toolbar
   (**🎯 Calibrate**, **📥 From ndX**, **📤 To ndX**,
   **🔗 Share in session**, **🔬 Store on setup**, **💾 Export CSV**, **?**) over
   a two-dock AutoForm: a *Settings* column in workflow order on the left and a
   *Views* tab set (Correction factors / Populations / E–S / E–lifetime /
   E histogram) on the right.
2. Optionally pick a **Setup** at the top. Its named windows (`green`, `red`,
   `yellow`) are supposed to help the channel columns map themselves.
   **Do not do this for a Seidel-style `.bur` table** — see RF-305.
3. Drop the burst table on the window (or use the **Burst table** file row).
   The status line under *Settings* reports
   `demo_bursts.csv: 1508 bursts, 6 columns. Press Calibrate.`
4. Check the four **Channels** combos. On the simulated table they map
   themselves correctly: `i_dd → I_DD`, `i_da → I_DA`, `i_aa → I_AA`,
   `tau_f → Donor lifetime`. Only I_DD and I_DA are mandatory — the *Calibrate*
   action refuses to run without I_DD (`"The donor channel (I_DD) column is not
   mapped."` in the status bar).
5. Optionally pick the **Donor** / **Acceptor** in *Dyes (database)*; that fills
   R₀, both quantum yields and τ_D(0) from the fluorophore database.
6. Set the **Photophysics**: `τ_D(0) = 4.000 ns`, `R₀ = 52.00 Å`,
   `Linker width = 6.00 Å`, *Dynamic line* ticked. Backgrounds live in the
   collapsed **Background** panel.
7. Leave **Use the optics prior** on and pick a **Light path** if the light-path
   simulator has saved one. With none saved the combo holds only its empty entry
   and the calibration is a pure data estimate (nothing says so — see the UX
   notes).
8. Press **🎯 Calibrate**. The run happens on a worker thread; the status bar
   shows `Calibrating…` and then the four factors.
9. Read the result in four places: the **status bar** one-liner, the scrolling
   **report** under *Settings*, the **Correction factors** table and the
   **Populations** table, then judge it on the **E–S** and **E–lifetime** plots.
10. Use it: **🔗 Share in session** publishes the calibration as a linkable
    pseudo-fit, **🔬 Store on setup** is meant to attach it to the detector setup,
    **📤 To ndX** pushes it into an open ndX window, **💾 Export CSV**
    writes the per-burst values with the report in the file header.

## Expected

- On the simulated table the recovered factors sit within a few percent of the
  declared truth and both populations land on the static FRET line.
- Every factor the engine could **not** determine is visibly marked as such,
  wherever the user reads it.
- A real `.bur` measurement maps its intensity columns (count rates), not its
  bookkeeping columns.

## Observed (last run: 2026-07-26)

**The happy path is genuinely good.** On the simulated ALEX table the whole
sequence — drop, auto-map, calibrate, read, export — took under a second of
compute and returned

```text
  alpha  = 0.0738 ± 0.0041      (declared 0.080)
  delta  = 0.0634 ± 0.0032      (declared 0.060)
  gamma  = 0.6361 ± 0.0203      (declared 0.650)
  beta   = 1.4039 ± 0.0258      (declared 1.400)
  bursts: 118 donor-only, 67 acceptor-only, 1317 FRET in 2 population(s)
  gamma [E-S population fit] = 0.6361
  gamma [static FRET line]   = 0.6627
  population 0: n = 737, E = 0.302 ± 0.009, R = 59.8 Å, tau_f = 2.874 ns, off-line by -0.001
  population 1: n = 580, E = 0.758 ± 0.007, R = 43.0 Å, tau_f = 1.325 ns, off-line by +0.011
  converged after 3 iteration(s)
```

E = 0.302 / 0.758 against a declared 0.30 / 0.75. The **E–S** plot shows
donor-only at S = 1, acceptor-only at S = 0 and the two FRET populations centred
on S = 0.5; the **E–lifetime** plot shows both populations straddling the white
static line with the red dashed dynamic line between them — exactly the picture
the guide promises. The status bar, the factor table, the population table and
the exported CSV (which carries the full report as `#` header lines) all agree.
The GUI numbers reproduce the documented `csc accurate-fret` CLI run bit for bit.

**Where it goes wrong is the real data.** Five problems, all seen this run:

1. **The setup breaks the column mapping (RF-305).** Selecting a detector setup
   — the thing step 2 of the guide recommends *to help the mapping* — turns the
   window names into bare substring hints, and on the canonical `.bur` header the
   first column containing "green" is `First Photon (green)`, a photon index.
   With the shipped `BS` setup selected, `m000.bur` maps
   `I_DD ← First Photon (green)` (min −1, mean 4.5 × 10⁴),
   `I_DA ← First Photon (red)`, `I_AA ← First Photon (yellow)`; the tool then
   calibrates them without complaint and reports α = 0.5596 ± 0.0650,
   β = 0.6950, a 119-burst "FRET population" at E = 0.312 ± 0.032, R = 59.3 Å,
   *converged after 2 iterations*. Deselecting the setup restores the correct
   `Green Count Rate (KHz)` / `Red Count Rate (KHz)` /
   `S delayed yellow (kHz) | 2048-4095` mapping.
2. **The factor table asserts a provenance the engine denied (RF-306).** On the
   same file with the *correct* mapping the report ends in
   `! gamma could not be determined from the data; prior value kept` and
   `! gamma was neither identified by the data nor constrained by the light
   path; it keeps its current value` — while the *Correction factors* tab, the
   default view, reads `γ | 1.0000 | — | E-S fit / FRET line`. Unmapping I_AA
   produces `α | 0.0000 | — | donor-only bursts` and
   `δ | 0.0000 | — | acceptor-only bursts` against a report that says neither was
   identified. The status-bar summary repeats the numbers with no warning.
3. **The warnings are below the fold (RF-307).** The report widget measured
   554 × 192 px — 8 of 15 lines, `verticalScrollBar().maximum() = 135` — and
   every `!` line sits in the hidden part, while the Views pane next to it is
   919 × 867 px and mostly empty when the 5-row factor table is shown.
4. **A dropped measurement silently loses 90 % of itself (RF-308).** Dropping
   all ten `.bur` files of the measurement loaded `m000.bur` only (407 bursts),
   with an empty status bar and an info line that mentions no other file.
   Dropping the `bi4_bur` folder — the unit the burst search actually writes —
   gives the raw `Could not read bi4_bur: [Errno 21] Is a directory`.
5. **🔬 Store on setup is a dead control (RF-309).** For every setup the picker
   offers, including the shipped `BS`: `"No detector setup named 'BS' to store
   the calibration on."` The picker reads setups through the MMFDB-backed wizard
   loader while the writer reads and writes `~/.chisurf/detector_setups.json`,
   which does not exist on a normal install.

Smaller things that behaved well: bad input is handled cleanly (a prose file
gives `Could not read …: no numeric columns found in …` and *Calibrate* stays
blocked); the no-ALEX degradation is honest in the report (`! no
acceptor-excitation channel: every burst is taken to be doubly labelled …` and
γ = 0.9162 ± 0.0198 from the lifetime route alone), though the **E–S** tab then
renders as an empty black panel with axes and no explanation (`es_series()`
returns `[]`) — RF-310. **🔗 Share in session** reported success.

Screenshots inspected this run: the loaded form, the calibrated factor table,
E–S, E–lifetime, E histogram, the `.bur` mis-mapping, and the empty E–S.

## UX / UI suggestions

- **Draw the E histogram as a histogram.** `efficiency_histogram()` returns one
  60-point series with `width: 2` and it renders as a spiky polyline. The
  smFRET efficiency histogram is *the* recognisable plot of the field and is
  always drawn as bars or a step curve; a line at 60 bins reads as noise and
  implies a continuous quantity between the bins.
- **Say when the optics prior is inert.** *Use the optics prior* is ticked by
  default while the **Light path** combo holds only its empty entry, so the
  section is decorative until the light-path simulator has saved something.
  Either disable the panel with a one-line hint ("no light path saved —
  calibrating from the data alone") or untick the box when the list is empty.
- **Φ_D, Φ_A, g_G, g_R all default to 1.000**, which is not a possible quantum
  yield. Seed them from the selected dyes / setup, or leave them blank until a
  light path is picked.
- **Accept a measurement, not a file.** A single `.bur` gave 26 usable FRET
  bursts; the measurement is the folder. Let the *Burst table* row take several
  files (or a folder) and concatenate them, the way the burst-selection output
  is organised — see also RF-308.
- **Document the exported `label` column.** The CSV writes `label` as
  `-1` / `-2` / `0` / `1`; the header carries the calibration report but no
  legend for the class encoding.
- **Rebalance the factor table.** *Determined by* gets ~900 px of a 919 px pane
  for strings like "E-S fit", while *Value* and *±* are capped at 110/90 px.
- **Surface the two γ routes.** The report prints `gamma [E-S population fit]`
  and `gamma [static FRET line]` and the guide calls their agreement "the
  consistency check worth doing on every new sample" — but they appear only in
  the hidden part of the report, not as a row or a badge in the factor table.

## Bugs filed

- RF-305 — a selected detector setup maps `First Photon (green/red/yellow)` as
  the intensity channels of a `.bur` table, and the calibration runs on photon
  indices.
- RF-306 — the *Correction factors* table names a determination route for
  factors the engine reports as not determined.
- RF-307 — the calibration report, where those warnings live, shows 8 of 15
  lines in a 554 × 192 box beside a mostly empty 919 × 867 pane.
- RF-308 — a multi-file drop silently keeps only the first file; a folder drop
  surfaces a raw `[Errno 21] Is a directory`.
- RF-309 — **🔬 Store on setup** fails for every setup the picker offers
  (picker reads MMFDB, writer reads `~/.chisurf/detector_setups.json`).
- RF-310 — with I_AA unmapped the **E–S** tab renders empty axes with no
  explanation.
