---
type: Reference
title: Use case — FRET-2CDE, is that burst population dynamic?
description: Compute the two-channel kernel-density burst feature over an existing burst-analysis folder and read the sub-population that inter-converts inside the burst, standalone and as step 4 of the Burst Analysis shell.
tags: [usecase, burst, smfret, dynamics, 2cde, tttr, gui]
timestamp: '2026-07-29T00:00:00Z'
---

# Use case: FRET-2CDE — is that population dynamic, or just an intermediate?

**Goal:** the question a FRET histogram cannot answer. A burst sitting at
E ≈ 0.5 is either a genuinely static intermediate state or a molecule that
inter-converted between a low- and a high-FRET state while it crossed the
confocal spot — the two are indistinguishable on the histogram. **2CDE** (Tomov
et al., *Biophys. J.* 2012) scores every burst from the *local* donor and
acceptor brightness around each of its photons: ≈ 10 for a static burst, rising
to 30–100 under millisecond dynamics, with no kinetic model. The user wants that
score for the bursts they already selected, plotted against E, and joined back to
the burst table so a later analysis can gate on it.

**Tool:** *Spectroscopy → Single-Molecule → 2CDE*
(`chisurf/plugins/burst/burst_2cde`, `BurstTwoCdeTool`), which is also **step 4.
Burst 2CDE** of the [Burst Analysis](/usecases/burst-selection-fret.md) shell.
The estimator is the `tttrlib.TwoCDE` burst feature (a parallel, bit-exact port
of the FRETBursts reference), with a pure-NumPy fallback. Headless siblings:
`2cde compute` (CLI), `burst_2cde.jobs.compute` (RPC) and
`Bursts.two_cde(...)` in the guided workflow API.

**Data:** the burst folder produced by the
[burst-selection workflow](/usecases/burst-selection-fret.md) —
`chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15/`
(10 Becker & Hickl SPC-130 measurements `m000`–`m009` of freely diffusing
doubly-labelled dsDNA, `bi4_bur/*.bur`, **2980 bursts**; green = routing channels
0/8, red = 1/9). The raw `.spc` files must sit beside the analysis folder: 2CDE
correlates photon arrival times, so it re-reads them. This run worked on a copy
under `/tmp` so the repo's test data stayed clean.

## Steps

1. Open **Spectroscopy → Single-Molecule → 2CDE** (or click **4. Burst 2CDE** in
   the Burst Analysis window). The panel is one column: a toolbar
   (**▶ Run**, **🔁 Restart**, **⏹ Stop**, **📁 Folder**), a *Folder* box, a
   six-row settings form (*Variant*, *Kernel*, *τ*, *Donor ch.*, *Acceptor ch.*,
   *File type*), a plot and a status line.
2. Drag the burst-analysis folder (the one holding `bi4_bur/`) onto the window,
   or pick it with **📁**. Naming the folder *is* the request: the computation
   starts by itself, off the GUI thread. Dropping a *file* is refused with an
   inline note ("2CDE reads a burst-analysis folder; m000.bur is not one.").
3. Check the settings the panel came up with: **Variant** `fret`, **Kernel**
   `laplace` (the Tomov original), **τ** `100.0 µs`, **Donor ch.** `0,8`,
   **Acceptor ch.** `1,9`, **File type** `SPC-130`. These are hard-coded
   defaults — they are *not* taken from the detector setup, in either the
   standalone window or step 4 (RF-988).
4. Read the result: the plot draws 2CDE against the per-burst proximity ratio,
   and the status line reports `FRET-2CDE: 2603 / 2980 bursts valid`.
5. Vary the kernel time constant — set **τ** to `500.0 µs` and press **▶ Run**
   again — to see how far the answer depends on the timescale the kernel probes.
   Pressing **▶** with nothing changed answers *"Unchanged — kept the previous
   2CDE result (🔁 Restart recomputes it)"* and highlights **🔁**, which forces a
   recomputation.
6. Switch **Kernel** to `gaussian` for the smooth variant; switch **Variant** to
   `alex` for ALEX-2CDE — but see RF-987: the panel has no control for the
   acceptor-excitation stream, so on this (non-PIE) data it silently scores the
   FRET channels instead.
7. Leave the panel. The per-burst values have been written beside the bursts as
   `2c4/<stem>.2c4` (one companion per measurement, joined back to the burst
   table by position) together with `2c4/2cde.stamp.json`, which records the
   settings, inputs and code version the result came from. Nothing in the window
   says so.
8. Headless equivalent:
   `2cde compute "<analysis folder>" --variant fret --kernel laplace --tau 100e-6
   --file-type SPC-130`, or in the guided workflow API
   `bursts.two_cde(donor="green", acceptor="red", tau=100e-6).dynamic_fraction(12.0)`.

## Expected

- Every burst with photons in **both** streams gets a finite score; bursts with
  an empty donor or acceptor stream are `NaN` by construction.
- The bulk of a static sample sits near **10**; a dynamic sub-population is
  elevated, and the API's `dynamic_fraction(threshold=12.0)` names it.
- The result is joined back to the burst table through a `…4` companion that
  obeys the [burst-companion contract](/subsystems/burst-companions.md): one row
  per burst including the skipped ones, zero-interleaved, all-numeric.
- A run that could not read its photons is reported as a failure, not as a
  result, and does not overwrite a good one.

## Observed (last run: 2026-07-29)

**The estimator is the good part.** 2980 bursts across ten measurements were
scored in **0.33–0.44 s** (laplace, τ = 100 µs), including re-reading all ten
`.spc` files; the whole thing runs off the GUI thread with a progress window and
a working **Stop**. The numbers are sane and reproduce the physics:

| run | valid | min | median | max |
|---|---|---|---|---|
| `fret`, laplace, τ = 100 µs | 2603 / 2980 | −0.78 | **11.53** | 110.00 |
| `fret`, laplace, τ = 500 µs | 2603 / 2980 | 4.60 | 12.57 | 46.56 |
| `fret`, gaussian, τ = 100 µs | 2603 / 2980 | 7.78 | 16.94 | 110.00 |
| `fret`, laplace, τ = 1 µs | 2603 / 2980 | −15.00 | 74.81 | 110.00 |
| `alex`, laplace, τ = 100 µs | 2603 / 2980 | 2.95 | 94.09 | 163.85 |

The median of 11.53 at the default settings is the documented static baseline,
and the 377 invalid bursts are exactly the single-colour ones (370 with zero red
photons, 7 with zero green) — nothing is silently dropped. 46.4 % of the finite
bursts exceed the API's dynamic threshold of 12, which for this sample says more
about the photon budget (median burst: 22 green / 7 red photons) than about
dynamics: the score is shot-noise dominated at these counts, and the panel gives
the user nothing to judge that with. The `2c4/` companions match their `.bur`
files row for row (408, 622, … physical lines) and the analysis stamp is written.

**What a user runs into.** Six of the seven controls can put the panel into a
state that looks like a result and is not:

- A stray character in *Donor ch.* / *Acceptor ch.* — `0, x` — throws
  `ValueError: invalid literal for int() with base 10: ' x'` straight out of the
  **Run** click, unhandled (RF-985).
- A container name the reader does not know (`SPC-132`, `PQ-PTU` — *File type* is
  free text) reads ten empty photon streams, and the panel reports
  `FRET-2CDE: 0 / 2980 bursts valid` **and overwrites the good `2c4/` companion
  with an all-`NaN` one**. Re-reading the folder afterwards through
  `read_bur_with_companions` returns a 2CDE column that is NaN for every real
  burst; the only trace of the failure is a `Container type … not supported`
  line on stderr (RF-986). Clearing *Acceptor ch.* does the same thing.
- **Variant = `alex`** produces a confident, smooth curve — median 94.09,
  correlated with E at **r = 0.81** (FRET-2CDE: r = 0.18) — on data that has no
  acceptor excitation at all, because there is no control for the Aex stream and
  the code falls back to the acceptor channels (RF-987). Screenshot
  `05_alex.png`: a clean deterministic band, which is exactly what a
  mis-specified ALEX-2CDE looks like.
- In the **Burst Analysis shell** the step inherits only the folder. With a
  workflow context declaring detectors on channels 4,5 / 6,7 and file type
  `PQ-PTU`, step 4 still showed `0,8` / `1,9` / `SPC-130` and computed with them
  (RF-988) — every sibling step (BVA, H2MM, MLE) is handed `channel_settings`.
- **Stop** works and leaves the on-disk companion intact (2603 filled rows
  before and after a stopped 3.7 s run), but the status line stays *"Stopping the
  2CDE computation …"* for good; only leaving and re-entering the panel produces
  a terminal message (RF-989).
- A folder with no `bi4_bur` answers *"Error: No objects to concatenate"* — the
  raw pandas message (RF-990).

**Around the GUI.** The CLI and the RPC both announce their output at
`<folder>/2cde`, while the writer writes `<folder>/2c4`; `--save-settings`
creates the stray `2cde/` directory, whose name does not end in `4` and would
therefore never be discovered as a companion (RF-991). And the companion writer
is hand-rolled rather than `write_companion`, so it appends an empty column to
every row and writes `NaN` as an empty cell — the repo's own `read_companion`
raises `ValueError: could not convert string '' to float64` on the plugin's own
output (RF-992). ChiSurf's pandas-based folder reader tolerates both.

*Environment note:* at the time of this run another working-tree edit had added
`add_arrow` to the chiplot backend ABC without a pyqtgraph implementation, so
every chiplot canvas — and therefore this panel — failed to construct. That is
uncommitted work in the shared tree, not a defect of this plugin; the driver
worked around it and it is recorded here only so a re-run that hits it knows why.

Screenshots (scratch, not committed): `01_empty`, `03_result`, `05_alex`,
`08_wrong_filetype`, `09_dropped_file`, `10_empty_folder`, `11_shell_step4`,
`14_stop_midrun`.

## UX / UI suggestions

- **Say why 377 bursts are not valid.** The status line reports
  `2603 / 2980 bursts valid` and stops there; the reason is knowable and short —
  *"377 bursts had no photon in one channel"*. As it stands the same wording
  covers "one-colour bursts" and "the file could not be read at all".
- **Draw the dynamic threshold.** The score exists to separate a sub-population,
  and the Python API already has `dynamic_fraction(threshold=12.0)`. The panel
  should carry a threshold control, a horizontal line at it, and the flagged
  fraction next to the status — today the GUI user gets a scatter and no verdict.
- **No control has a tooltip.** All seven (*Folder*, *Variant*, *Kernel*, *τ*,
  *Donor ch.*, *Acceptor ch.*, *File type*) return `''` for `toolTip()`, against
  the project rule that every control carries a `description`. *Donor ch.* in
  particular does not say it means routing channels, comma-separated.
- **Make *File type* a combo** of the container names the reader accepts, rather
  than free text. That removes RF-986's whole failure class at the source.
- **Name the settings the plot was computed with.** After changing τ the panel
  shows a 100 ms setting above a 100 µs plot with nothing to say so; the status
  line already names the variant, and should name τ and the kernel too.
- **Warn when τ is implausible.** τ = 1 µs is accepted and returns a median of
  74.8 with values down to −15 — far outside the 10–100 the method is described
  by. τ below the mean interphoton time of the bursts is not a meaningful KDE
  width and could be flagged inline.
- **Say where the result went.** The `2c4/` companion is written on every run and
  the window never mentions it; nor is there any way to save the plot, export the
  per-burst table, or push the flagged sub-population onward (ndX, burst
  browser). The companion is the only outlet and it is invisible.
- **The empty-state plot clips its top tick** (`1.0` sits on the frame edge), and
  the four toolbar buttons are icon-only with no text labels.

## Bugs filed

- RF-985 — a non-numeric character in *Donor ch.* / *Acceptor ch.* raises an
  unhandled `ValueError` out of the **Run** click.
- RF-986 — an unreadable *File type* (or an empty channel list) reports
  "0 / 2980 bursts valid" as a result **and overwrites the good `2c4/` companion
  with an all-`NaN` one**.
- RF-987 — the `alex` variant has no acceptor-excitation control, so ALEX-2CDE is
  computed from the FRET channels and reported as valid.
- RF-988 — the Burst Analysis shell hands the 2CDE step only the folder; the
  detector setup and file type of the workflow never reach it.
- RF-989 — after **Stop** the status line stays "Stopping the 2CDE
  computation …" indefinitely.
- RF-990 — a folder with no burst tables reports the raw pandas message
  "No objects to concatenate".
- RF-991 — the CLI and the RPC report the output directory as `2cde/` while the
  results are written to `2c4/`; `--save-settings` creates the stray `2cde/`.
- RF-992 — the companion writer is hand-rolled instead of `write_companion`, and
  its output cannot be read by the repo's own `read_companion`.
