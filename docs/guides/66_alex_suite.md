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
| *Select Directory* + file list | **1. Files** — drop files or folders; `.sm` reads directly |
| *Burst Search Settings → Microscope* | **2. Alternation** — one button, all seven numbers measured |
| *Burst Search → APBS / DCBS* | **3. Burst search** |
| `bkg_DD` / `bkg_DA` / `bkg_AA` fields | **4. Background** — measured from the inter-photon times |
| *Accurate FRET* (`E_donly`, `S_aonly`, γ, β) | **5. Accurate FRET** — α, δ, γ, β from your own populations |
| *E vs S Histogram* **and** *Dataset Viewer* | **6. E–S histogram** (ndX) |
| *Burst Properties* | **Burst properties** |
| *Titration* | **Titration** |
| *BVA*, *Trace Viewer* | **BVA**, **Trace viewer** |
| *Export* (five CSVs) | **Export (ALEX-Suite CSV)** |

Two things are gone rather than moved. The **channel-flip** checkbox: the
alternation step works out which detector is which from which laser window it is
brighter in. And the **`sm2burst` cache**: bursts live in the measurement's own
`.pto`, so nothing can go stale against a settings change.

## 1 — Files

Drop the measurements, or a folder of them. Any container `tttrlib` reads works,
including the `.sm` files the old program used — no conversion step, no cache
files appearing beside them. Everything later reads what you select here.

## 2 — Alternation, measured rather than typed

This replaces the microscope dialog: alternation period, phase shift, four laser
on/off edges, channel flip. Name the donor and acceptor routing channels, press
**Detect alternation and convert**, and look at the plot.

```{figure} figures/alex_suite_alternation.png
:name: fig-alex-suite-alternation
:width: 95%

The alternation step on a simulated µs-ALEX measurement. Two plateaus with a gap
between them; the donor detector brighter in the first, the acceptor in the
second. The shaded bands are the detected excitation gates, and the *contrast*
figure is how sharp the alternation line was.
```

**That crossover is the check.** If the two curves track each other instead, the
period is wrong or the channels are swapped. Contrast below about 50× means the
same thing, and the step refuses to convert rather than folding a meaningless
micro-time into every file.

Afterwards each measurement is a `.pto` whose micro-time *is* the alternation
phase — ordinary PIE data — and a detector setup named **ALEX Suite (auto)** is
published for the rest of the pipeline. Its windows are `prompt` and `delayed`,
its detectors `green`, `red` and `yellow`, so the four ALEX streams appear in the
burst table under the names every ChiSurf reader already knows:

| stream | burst-table column |
|---|---|
| $I_{DD}$ | `S prompt green (photons)` |
| $I_{DA}$ | `S prompt red (photons)` |
| $I_{AA}$ | `S delayed yellow (photons)` |

Skip this step entirely if your data is already PIE / ns-ALEX.

## 3 — Burst search

The old *APBS* is a search over all photons; *DCBS* additionally demands a
coincident rate rise in **both** excitation streams, throwing out singly-labelled
molecules before they reach the histogram.

One habit worth changing: **search permissively and cut on burst size
afterwards**. A minimum-photon cut inside the search interacts with the threshold
and biases which molecules you ever see — dim ones go first, and dim usually
correlates with something you care about.

## 4–5 — Background and the correction factors

Both used to be numbers you read off a plot and typed in. The background comes
from the inter-photon-time distribution of the measurement itself; α, δ, γ and β
come from a mixture fitted to your own donor-only, acceptor-only and FRET
populations, iterated until the classification and the factors agree
([tutorial 41](41_accurate_fret.md)).

The check that catches most errors is the one you already use: **donor-only must
land at $S \approx 1$, $E \approx 0$**.

## 6 — E–S, and any parameter against any other

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

- {src}`chisurf/plugins/burst/alex_suite/` — the plugin; its `api/` is Qt-free.
- [The µs-ALEX workflow, as a notebook](27_alex_smfret_workflow.md).
- [Finding bursts, step by step](13_burst_identification.md),
  [background rates](15_background_rates.md),
  [burst variance analysis](08_burst_variance_analysis.md).
