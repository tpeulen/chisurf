---
type: Reference
title: Use case — photon-by-photon kinetics (Gopich–Szabo)
description: Fit continuous-time rate constants and per-state FRET efficiencies directly to the arrival time and colour of every burst photon — learn the method on the built-in simulator, then run it on a real burst folder, with a transition-time scan and an H2MM cross-check.
tags: [usecase, burst, kinetics, fret, single-molecule, gui]
timestamp: '2026-07-27T00:00:00Z'
---

# Use case: photon-by-photon kinetics (Gopich–Szabo)

**Goal:** a FRET histogram shows *where* the populations sit; it cannot say how
fast a molecule moves between them, because binning destroys everything faster
than the bin. The Gopich–Szabo likelihood is written directly over the arrival
time and colour of every photon, so the exchange it can resolve is limited only
by the mean interphoton time (~20 µs at 50 kHz), not by any bin the user picked.
The tool returns the **rate constants** between states, the **FRET efficiency**
of each state, the **equilibrium population** each state holds, and — optionally
— an upper bound on how long a transition itself takes, plus an independent
cross-check against the discrete-time H2MM engine.

This is the continuous-time sibling of [H2MM](/usecases/h2mm-burst-dynamics.md):
same photons, same question, deliberately different parameterisation of time, so
that agreement between them is evidence rather than a shared bug.

**Data:** two sources, and the tool is designed to be used in that order.

1. **The built-in two-state simulator** (*Simulate instead* panel) — a molecule
   with known `k(1→2)`, `k(2→1)`, `E₁`, `E₂` and photon rate. The only way to
   know the right answer, and the honest way to learn what the method can
   resolve on a given photon budget.
2. **A real burst folder** — the burst analysis shipped with the burst-selection
   plugin,
   `chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15/bi4_bur/`
   (10 `.bur` tables, 2 980 real bursts, mean burst duration 1.33 ms) over the
   raw `bh_spc132_sm_dna/m00*.spc` streams (BH SPC-132, 13.5 ns macro-time tick).
   The same folder the [burst selection](/usecases/burst-selection-fret.md) use
   case produces.

**Entry point:** *Spectroscopy ▸ Single-Molecule ▸ Photon-by-photon kinetics*
(`burst_gs`, menu-visible). Headless: `burst-gs` CLI and the
`burst_gs.jobs.fit` / `burst_gs.jobs.log_likelihood` /
`burst_gs.jobs.transition_time_scan` RPC methods.

## Steps

### A — learn it on the simulator (no data file needed)

1. Open the tool. The left dock holds four folding panels — **Photons**,
   **Simulate instead**, **Model**, **Extras**; the right dock holds a
   **Report** and a **Views** tab bar (*Rates*, *States*, *State populations*,
   *Transition time*). The toolbar carries **▶ Fit**, **💾 Export CSV** and a
   **?** help modal.
2. Click the **Simulate instead** header to unfold it and tick **Simulate**.
   Leave the defaults: `k(1→2)` = 3 000 /s, `k(2→1)` = 1 000 /s, `E₁` = 0.25,
   `E₂` = 0.75, 50 kHz, 200 bursts × 200 photons, seed 1.
3. Unfold **Extras** and tick **Scan transition time**, **Decode state path** and
   **Cross-check with H2MM**.
4. Press **▶ Fit**. The status bar reports `fitting`, then `logL = … after N
   evaluations`, then `decoding states` and `cross-checking against H2MM`.
5. Read the **Report**: the fit must return the numbers you typed in step 2.
6. Open the **Transition time** tab: a curve that is flat at Δ logL = 0 for short
   durations and falls away for long ones is the normal answer — it bounds the
   crossing time from above rather than measuring it.

### B — run it on a real burst folder

7. Drag the `bi4_bur/` folder **onto the burst-table list itself** (or press
   **📁 Folder**). It expands to the ten `m00*.bur` tables. Dropping it anywhere
   else in the window does nothing (RF-526), and dropping the `.bur` *files*
   outside the list adds them invisibly and duplicates them on a second drop
   (RF-525) — so always drop on the list.
8. Set **TTTR folder** to the parent `bh_spc132_sm_dna/` (the folder the `First
   File` column of the burst table resolves against). Leave **Container** on
   `auto`.
9. Set **Donor channels** / **Acceptor channels**. These are raw routing-channel
   numbers, not the named detector setup the rest of the burst family uses; the
   defaults `0, 8` and `1, 9` match this measurement's green/red detectors.
   Photons in neither list are dropped.
10. **Type the macro-time tick: 13.5 ns.** The documented "leave it at 0 and it
    is read from the file header" does not work on a burst folder ChiSurf wrote
    itself — the fit dead-ends with *"the macro-time resolution is unknown"*
    (RF-524). Every fitted rate is proportional to this number.
11. Set **Max bursts** to a few hundred for a first look (0 = all).
12. Press **▶ Fit**. 400 bursts / 30 155 photons fit in ~0.5 s.
13. Read the **Rates** and **States** tabs and the **State populations** plot,
    then **💾 Export CSV**.
14. Raise **States** to 3 and refit only if the BIC clearly falls. With the
    default **Max iterations** = 2 000 a three-state fit does *not* converge on
    this data (RF-529); raise it to 20 000.

## Expected

- On the simulator the fit recovers the truth: with `k(1→2)` = 3 000 /s,
  `k(2→1)` = 1 000 /s, `E₁` = 0.25, `E₂` = 0.75 and 40 000 photons it should
  return rates within ~5 % and efficiencies within ~0.01.
- The H2MM cross-check should agree to within a few percent on both rates and to
  ~1 × 10⁻⁴ on the efficiencies — the two engines share no code.
- On the real DNA sample the two states should separate the donor-only
  population (E ≈ 0) from the FRET population (E ≈ 0.5), and the fitted
  relaxation time should come out *longer than a burst*, which is the correct
  answer for a static sample: nothing exchanges within the observation window.
- Export CSV writes the rate matrix, the efficiencies, logL, BIC and the burst /
  photon counts.

## Observed (last run: 2026-07-27)

Driven headlessly offscreen (`QT_QPA_PLATFORM=offscreen`, arm64 env) by
constructing `BurstGsTool()` and using it through the toolbar actions, the
collapsible headers, the real check boxes and spin boxes and the drop handlers.
Screenshots `01_opened`, `05_all_panels_open`, `07_fitted_full`,
`11_tab_*` (all four result tabs), `22_pathlist_after_drop`, `24_real_fitted`,
`31_folder_dropped_on_list`, `32_three_states`, `40_scan_declined_3states`,
`50_help`.

**The maths is right and it is fast.** The simulator with the shipped defaults
(200 bursts, 40 000 photons) fits in **0.1 s** and returns
k(1→2) = 2 879 /s, k(2→1) = 1 017 /s, E = 0.2370 / 0.7493 against a truth of
3 000 / 1 000 and 0.25 / 0.75 — inside the statistical error on that photon
budget. With the scan, the Viterbi decode and the H2MM cross-check switched on
the whole run takes **5.3 s**, and the cross-check agrees to
`ratio_k12 = 1.009`, `ratio_k21 = 0.974`,
`max_efficiency_difference = 1.9 × 10⁻⁴`. The transition-time scan returns the
textbook shape and the report reads it correctly: *"No support for a finite
transition time. The scan bounds it below ~1.00 us."* The two optimisers agree
exactly on the real data (both logL = −23 569.2, k = 129.0 / 99.2). The report
text, the help modal, the tooltips and the panel descriptions are unusually good
— they teach the method, not just the widget.

**Getting real data into it is where it goes wrong.** Three separate problems,
all hit within the first minute of using the tool the obvious way:

- The documented default path fails. With **Macro-time tick = 0** ("read it from
  the file header") the fit stops with *"Could not load the photons: the
  macro-time resolution is unknown; pass it explicitly"* — on the burst folder
  ChiSurf's own burst-selection plugin writes. The files are fine
  (`m000.spc` reports 1.35 × 10⁻⁸ s); the loader reads the header of a
  *placeholder* entry created from the `.bur` padding rows, half of which carry
  `First File = "0"` (2 990 of 5 970 rows). tttrlib prints
  `File …/bh_spc132_sm_dna/0 not supported.` to stderr, returns an empty object
  with `macro_time_resolution = −1.0`, and that is the object the resolution is
  read from. **RF-524.**
- Dropping the ten `.bur` files on the window adds them to the analysis but the
  burst-table list stays visibly **empty** — see `24_real_fitted`, a completed
  400-burst fit above a blank file list. A user who drops again (there is no
  other feedback) ends up with 20 entries, and the load then reports **5 944
  bursts / 450 578 photons instead of 2 972 / 225 289** — every burst counted
  twice, every rate fitted to doubled statistics. **RF-525.**
- The list is captioned *"drop .bur files or folders"* and the section is
  configured with `add_folders: true`, but a folder dropped on the window is a
  silent no-op, while the same folder dropped on the list expands to ten files
  correctly. The same gesture works or not depending on where the mouse is
  released. **RF-526.**

**Two controls do not do what they say.** *Fix efficiencies* — offered "when the
efficiencies are known from a static measurement" — pins them to a hard-coded
`linspace(0.2, 0.8, n)`, and there is no control anywhere in the tool to enter
the known values. Ticked on the simulator with a truth of 0.25 / 0.75 it returns
E = 0.2000 / 0.8000 and rates 1 244 / 4 071 /s, presented in the report exactly
like fitted numbers (**RF-527**). *Decode state path* runs a Viterbi decode over
every photon (40 000 of them in the smoke run, with its own progress step) and
the resulting `state_path` array appears in no view, no report line, no
`to_dict()` payload and no CSV column — the checkbox costs time and produces
nothing a user can see (**RF-531**).

**Two silent outcomes.** *Scan transition time* with **States** > 2 does nothing
at all: the *Transition time* tab shows an empty black plot on a bare 0–1 axis,
the report has no scan section, and the explanation the code does compute
(`info["transition_scan_skipped"] = "the transition-state model is defined for
two states only"`) is read by a unit test and by nothing else (**RF-528**). And a
non-converged fit is presented like a converged one — the three-state fit on real
data at the default 2 000 iterations fills the *Rates* and *States* tables, draws
the *State populations* plot, and puts `logL = −21,603.3, k(1→2) = 67 /s,
k(2→1) = 53 /s` in the status bar, while *"Optimiser did not converge: Maximum
number of iterations has been exceeded"* is the **last** line of a report pane
fixed at 300 px that is scrolled to the top (`32_three_states`) (**RF-529**).

**The populations plot is mis-scaled.** *State populations* shows equilibrium
fractions 0.26 and 0.74 on an axis labelled *"equilibrium population (×0.001)"*
running from 0 to 700 (`11_tab_2_State_populations`) — pyqtgraph's automatic SI
prefix applied to a quantity that is a fraction by construction (**RF-530**).

**Error handling and the empty state are good.** Pressing **▶ Fit** with nothing
loaded shows an inline *"⛔ Add at least one .bur burst table, or tick Simulate."*
banner; **💾 Export CSV** before a fit says *"Run a fit first."* in the status
bar; the initial report text tells you what to do and why the method exists.
The **?** modal renders cleanly.

**Physics check on the real sample.** The two-state fit returns E = 0.028 /
0.476 with populations 0.42 / 0.58 — the donor-only and FRET populations, as
expected for this static DNA — and a relaxation time of **6 976 µs against a mean
burst duration of 1 330 µs**. The rates are therefore five times slower than the
longest thing a burst can see, i.e. unmeasurable, and the tool says nothing about
it. See the UX suggestions.

## UX / UI suggestions

- **Say when the answer is outside the observation window.** Compare the fitted
  relaxation time against the burst-duration distribution and mark the report
  when it exceeds it (here 6 976 µs vs a 1 330 µs mean burst): those rates are
  bounded, not measured. The same check at the fast end against the mean
  interphoton time would close the other side.
- **Show the truth next to the fit in simulation mode.** `load()` already stores
  `true_k_forward`, `true_k_backward` and `true_efficiencies` in `info` and the
  report never prints them. A "true / fitted / deviation" block would make the
  panel's own claim — *"the only way to know the right answer"* — actually
  cash out.
- **Mark simulated results as simulated.** With files loaded *and* **Simulate**
  ticked, nothing in the report, the tables, the plots or the status bar says
  the numbers did not come from the files. One line (`source: simulation`) fixes
  it.
- **Let the report breathe.** The `info` pane is fixed at 300 px and renders
  `<pre>`, so it needs both a vertical and a horizontal scrollbar while ~350 px
  of empty grey sits under a two-row *Rates* table. Wrap the text, and let the
  report share the vertical space with the views instead of being capped.
- **Put the convergence status where the numbers are.** A ⚠ in the status-bar
  summary and a marker on the *Rates*/*States* tabs, not only in the last line
  of a scrolled report.
- **Flag rates parked on the optimiser bound.** The three-state fit reports
  `k(1→3) = 1.0 /s → 1/k = 999,360.36 µs`; that is the lower bound, not a
  measurement, and it is printed to two decimals like everything else.
- **Adopt the shared detector setup.** Every other burst tool (H2MM, burst-FCS,
  BVA, the burst browser) picks a named setup and gets `green = 8,0,3`,
  `red = 9,1,2`; this tool asks for raw routing channels and defaults to
  `0, 8` / `1, 9`, which quietly drops channels 3 and 2 on exactly the data set
  the others handle. At minimum, offer the setup as a preset that fills the two
  fields.
- **Put provenance in the CSV.** The export carries no file list, no channel
  assignment, no macro-time tick and no timestamp — yet every rate in it is
  proportional to that tick. The numbers cannot be reproduced from the file.
- **Scale the iteration cap with the model.** 2 000 iterations converges two
  states and not three; the default could be `2000 × n_states²`, or the fit
  could simply restart from its own result until `success` is true.
- **Elide file paths from the left.** The burst-table list shows ten identical
  leading path prefixes and needs a horizontal scrollbar to tell `m000.bur` from
  `m009.bur`.
- **The help modal is 560 × 480** for a long, genuinely useful document; open it
  at something closer to 800 × 700.

## Bugs filed

- **RF-524** — the macro-time tick is read from the placeholder TTTR built from
  the `.bur` padding rows, so `auto` fails on every burst folder ChiSurf writes.
- **RF-525** — files dropped on the window never appear in the list, and a second
  drop silently duplicates them, doubling every burst.
- **RF-526** — a folder dropped on the window is a no-op, though the list itself
  accepts folders and the caption offers them.
- **RF-527** — *Fix efficiencies* pins E to a hard-coded `linspace(0.2, 0.8)`
  that no control can change.
- **RF-528** — *Scan transition time* with more than two states does nothing and
  the reason it computes is never shown.
- **RF-529** — a non-converged fit is reported like a converged one; the default
  iteration cap does not converge three states.
- **RF-530** — the *State populations* axis SI-prefixes a 0–1 fraction to
  "(×0.001)" and reads 0–700.
- **RF-531** — *Decode state path* computes a per-photon Viterbi path that
  reaches no view, no report, no `to_dict()` and no CSV.
