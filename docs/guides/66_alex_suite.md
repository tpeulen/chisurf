---
type: Guide
title: Coming from ALEX-Suite
description: The ALEX-Suite workflow, step by step, in ChiSurf — where each old window went, what is now measured instead of typed, and what comes out.
tags: [guides, fret, smfret, alex, titration]
---

# Coming from ALEX-Suite

:::{admonition} Theory
:class: seealso
The alternation, the four ALEX streams and the titration model are in
{ref}`concept-us-alex`; the burst observables in {ref}`concept-smfret-bursts`.
:::

## What it is

**Tools → ALEX Suite** is the workflow the old ALEX-Suite program had, in the
order it had it. Every step is one of ChiSurf's own tools underneath, so the
result is an ordinary ChiSurf burst analysis — one **`.pto` container per
measurement** holding the photons, the bursts found in them and the companion
tables written beside them. There is no ALEX-shaped result format, and an
analysis started here can be continued in **Burst Analysis** (2CDE, per-burst
lifetimes, H2MM segmentation, burst fusion) and brought back, with nothing to
convert.

## Where each window went

| ALEX-Suite | here |
|---|---|
| the channel table inside *Burst Search Settings* | **1. Setup** — the detector setup, chosen or edited |
| *Select Directory* + file list | **2. Files** — drop files or folders; `.sm` reads directly |
| *Burst Search Settings → Microscope* | **3. Alternation** — one button, all seven numbers measured |
| *Burst Search → APBS / DCBS* | **4. Burst search** |
| `bkg_DD` / `bkg_DA` / `bkg_AA` fields | **5. Background** — measured from the inter-photon times |
| *Accurate FRET* (`E_donly`, `S_aonly`, γ, β) | **6. Accurate FRET** — α, δ, γ, β from your own populations |
| *E vs S Histogram* **and** *Dataset Viewer* | **7. E–S histogram** (ndX) |
| *Burst Properties* | **Burst properties** |
| *Titration* | **Titration** |
| *BVA* | **BVA** |
| *Export* (five CSVs) | **Export (ALEX-Suite CSV)** |

Two things are gone rather than moved. The **channel-flip** checkbox: the
alternation step works out which detector is which from which laser window it is
brighter in. And the **`sm2burst` cache**: bursts live in the measurement's own
`.pto`, so nothing can go stale against a settings change.

## 1 — Setup

**Where the detector setup is chosen.** Which routing channels are the donor and
the acceptor, and which micro-time window is which excitation. Every later step
reads it, and it is the one thing that cannot be worked out from the data alone.

Already PIE / ns-ALEX? Pick or edit your setup here and skip step 3. µs-ALEX?
Leave it — step 3 measures it and fills this step in, and you come back and
check what it decided.

## 2 — Files

Drop the measurements, or a folder of them. Any container `tttrlib` reads works,
including the `.sm` files the old program used — no conversion step, no cache
files appearing beside them. Everything later reads what you select here.

Dropping a vendor file elsewhere in ChiSurf offers to embed it in a `.pto` there
and then; **here it does not**, deliberately. A µs-ALEX measurement converted
before step 3 still has its alternation in the macro time, so the container's
micro-time is empty and step 3 would convert that container again into a second
file. The conversion this workflow needs is step 3's.

## 3 — Alternation, measured rather than typed

This replaces the microscope dialog: alternation period, phase shift, four laser
on/off edges, channel flip. Press **Detect alternation and convert** and look at
the plot; the channel fields say `auto` and fill themselves in, and the detected
setup lands in step 1.

```{figure} figures/alex_suite_alternation.png
:name: fig-alex-suite-alternation
:width: 95%

The alternation step. The folded *intensity* is nearly flat — real µs-ALEX has
no laser-off gap — but the two detectors swap: donor bright in the first shaded
gate, acceptor in the second. That swap is what the detection uses, and what you
check.
```

**The gates are yours to adjust.** Detection fills the period and the two laser
gates into the boxes below the plot, and the shaded bands *are* those numbers:
drag a band or type an edge, and the other follows. Changing a gate republishes
the detector setup for the whole pipeline and converts nothing again — the fold
into the micro-time depends on the period alone, so a gate is free to move
afterwards. (Changing the period is not: press **Detect** again for that.)

**That crossover is the check.** If the two curves track each other instead, the
period is wrong or the channels are swapped. Contrast below about 50× means the
same thing, and the step refuses to convert rather than folding a meaningless
micro-time into every file.

The **channel assignment is decided, not asked**. One physical fact settles it:
under acceptor excitation the donor detector sees essentially nothing, whatever
the sample's efficiency or labelling. On the µs-ALEX calibration measurement this
was built against — a 300 s Cy3B/ATTO647N dsDNA file — the donor turns out to be
routing channel **1** and is 5 % as bright under acceptor excitation, i.e. the
"flipped" case the old program needed a checkbox for. The detected period (8000
macro-time units = 100.0 µs) and gates (616–3784, 4278–7762) reproduce what that
program was configured with (100 µs; 240–3760 and 4160–7680) to within the guard
band trimmed off the laser rise and fall.

Afterwards the measurement is **one `.pto`** whose micro-time *is* the
alternation phase — ordinary PIE data — and a detector setup named
**ALEX Suite (auto)** is written into step 1 and published for the rest of the
pipeline.

One container for the whole set, not one per file. A run saved as `001.sm` …
`006.sm` is one measurement the acquisition software chopped up, and the
container is ChiSurf's unit of *measurement*: separate containers would make six
analyses of one experiment, six burst searches to run and six sets of results to
pool by hand. The period and the gates are measured once, from the first file,
because they are properties of the instrument rather than of the sample — which
is also what makes the pieces comparable. Its windows are `prompt` and `delayed`,
its detectors `green`, `red` and `yellow`, so the four ALEX streams appear in the
burst table under the names every ChiSurf reader already knows:

| stream | burst-table column |
|---|---|
| $I_{DD}$ | `S prompt green (photons)` |
| $I_{DA}$ | `S prompt red (photons)` |
| $I_{AA}$ | `S delayed yellow (photons)` |

Skip this step entirely if your data is already PIE / ns-ALEX.

## 4 — Burst search

The old *APBS* is a search over all photons; *DCBS* additionally demands a
coincident rate rise in **both** excitation streams, throwing out singly-labelled
molecules before they reach the histogram.

One habit worth changing: **search permissively and cut on burst size
afterwards**. A minimum-photon cut inside the search interacts with the threshold
and biases which molecules you ever see — dim ones go first, and dim usually
correlates with something you care about.

## 5–6 — Background and the correction factors

Both used to be numbers you read off a plot and typed in. The background comes
from the inter-photon-time distribution of the measurement itself; α, δ, γ and β
come from a mixture fitted to your own donor-only, acceptor-only and FRET
populations, iterated until the classification and the factors agree
([tutorial 41](41_accurate_fret.md)).

The check that catches most errors is the one you already use: **donor-only must
land at $S \approx 1$, $E \approx 0$**.

## 7 — E–S, and any parameter against any other

ndX is both of the old windows at once. Drawing a region selects those bursts
everywhere, so a population you gate is a population the other tools see; fitting
the map with Gaussians and giving each population its own γ are here too
([tutorial 28](28_selecting_fret_populations.md),
[tutorial 26](26_2d_peak_fitting.md)).

## Titration

One burst file per ligand concentration. The whole series is fitted **together**,
with the population positions and widths shared and only their amounts free — the
old "fixed x0 and sigma" preset, made the default because it is nearly always
what you want. The fraction of the population that grows with ligand, against
concentration, is the binding isotherm.

```{figure} figures/alex_suite_titration.png
:name: fig-alex-suite-titration
:width: 95%

A simulated seven-point titration with $K_d = 50$. Top: the stack plot, one
efficiency histogram per concentration with the shared-shape fit dashed over it.
Bottom: the isotherm read from the high-FRET population.
```

Fitting each histogram on its own lets a noisy condition move a peak by more than
the amplitude change you are measuring, and the isotherm then reports that wander
as affinity. And if the series has not reached saturation, treat $K_d$ with
suspicion — an unsaturated curve lets $K_d$ and the plateau trade off, and both
come back precise and wrong.

## Export

The last step writes the five CSV files the old program wrote — `_meta`,
`_hist_E`, `_hist_S`, `_hist_2D`, `_original_bursts` — with the same section
headers, so scripts and spreadsheets built on that layout keep working. It is a
convenience, not the storage: the analysis is in the `.pto`.

## Headless

```bash
csc alex-suite alternation *.sm --donor 0 --acceptor 1
csc burst-selection --help                       # the ordinary burst search
csc alex-suite histogram bursts.bur --export run
csc alex-suite titration series.csv --populations 2
```

`series.csv` is `concentration,burst_file` rows, paths relative to the file.

## See also

- {src}`chisurf/plugins/burst/alex_suite/manifest.json` — the plugin; its `api/` is Qt-free.
- [The µs-ALEX workflow, as a notebook](27_alex_smfret_workflow.md).
- [Finding bursts, step by step](13_burst_identification.md),
  [background rates](15_background_rates.md),
  [burst variance analysis](08_burst_variance_analysis.md).
