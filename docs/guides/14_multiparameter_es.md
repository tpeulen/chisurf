---
type: Guide
title: Multi-parameter E–S histograms and correction factors
description: 'With alternating-laser excitation (ALEX) or pulsed-interleaved excitation (PIE) each burst gets two coordinates: the FRET efficiency $E$ (from the donor-excitation photons) and the stoichiometry $S$ (donor-excitation vs total signal).'
tags: [guides, corrections, bursts, fret]
---

# Multi-parameter E–S histograms and correction factors

:::{admonition} Theory
:class: seealso
The definitions of accurate $E$ and $S$, and the four correction factors
(leakage, direct excitation, $\gamma$, $\beta$) that straighten the FRET line,
are derived in the concept page {ref}`concept-smfret-bursts`.
:::

## What it does

With alternating-laser excitation (**ALEX**) or pulsed-interleaved excitation
(**PIE**) each burst gets two coordinates: the **FRET efficiency** $E$ (from the
donor-excitation photons) and the **stoichiometry** $S$ (donor-excitation vs
total signal). The 2-D $E$–$S$ histogram cleanly separates the FRET
sub-populations (at $S\approx0.5$) from **donor-only** ($S\to1$) and
**acceptor-only** ($S\to0$) species, which are then excluded.

Accurate $E$ requires **correction factors**: donor leakage into the acceptor
channel, direct acceptor excitation, and the $\gamma$ factor (relative detection
efficiency × quantum yield); the stoichiometry additionally needs the excitation
$\beta$ factor. These are estimated from the donor-only and acceptor-only
populations the $E$–$S$ plot isolates.

## In ChiSurf

### In the GUI: Accurate FRET

**Spectroscopy → Burst Analysis → Accurate FRET** (on its own:
*Spectroscopy:FRET:Accurate FRET*) finds all four factors from one burst table.
Pick the **Burst table** (…), map the columns in **Channels** — **I_DD (donor)**,
**I_DA (FRET)**, **I_AA (acceptor)** and optionally **Donor lifetime** — and press
**Calibrate**. The tool classifies donor-only, acceptor-only and doubly labelled
bursts with a Gaussian mixture in $S$, takes α from the donor-only and δ from the
acceptor-only bursts, and γ, β from the $1/S = \Omega + \Sigma E$ fit across the
FRET populations, iterating until the classification is stable. The **Views**
tabs show the factor table, the populations, the corrected $E$–$S$ and
$E$–lifetime plots and the $E$ histogram; **Store on setup** saves the factors
with the detector setup. The full workflow is in
[Accurate FRET](41_accurate_fret.md).

```{figure} figures/14_accurate_fret.png
:name: fig-accurate-fret-es
:width: 100%

Accurate FRET on a simulated ALEX burst table (two FRET populations,
E = 0.28 and 0.72, 500 donor-only and 500 acceptor-only bursts; true
α = 0.08, δ = 0.06, γ = 0.65, β = 1.4) — the test data hold no ALEX/PIE
measurement. Recovered: α = 0.0800, δ = 0.0589, γ = 0.658, β = 1.389, with
488 donor-only and 487 acceptor-only bursts found. The corrected $E$–$S$ plot
puts the FRET populations at $S \approx 0.5$, donor-only at $S \to 1$ and
acceptor-only at $S \to 0$. Rendered with `CHISURF_PLOT_BACKEND=pyqtgraph` —
see *Known defects*.
```

### Headless

```python
from chisurf.core.fluorescence.fret import calibration as cal

# leakage & direct-excitation from the donor-only / acceptor-only populations
leak  = cal.leakage_from_donor_only(i_dd, i_da)
dir_a = cal.direct_excitation_from_acceptor_only(i_da, i_aa)

# global gamma/beta from the FRET populations
est = cal.global_es_correction(i_dd, i_da, i_aa, labels, alpha=leak, delta=dir_a)
```

The three calls take per-burst counts of the respective population
(`labels` marks the FRET sub-populations, at least two). On simulated counts
with α = 0.08, δ = 0.06, γ = 0.65, β = 1.4 they return α = 0.0801,
δ = 0.0609, γ = 0.651 and β = 1.396 (`est` also carries Ω and Σ).

The per-burst $E$/$S$ are computed in {src}`chisurf/core/fluorescence/burst/es.py`
(ALEX/PIE-aware). See also the
[RCM detection calibration](07_rcm_calibration.md) for the full channel matrix.

## Result

A simulated ALEX $E$–$S$ histogram: two FRET populations (low- and high-E) at
mid stoichiometry, a donor-only band at high $S$ and an acceptor-only band at low
$S$.

```{figure} figures/es.png
:name: fig-es
:width: 90%

Multi-parameter E–S histogram.
```

## See also

- {src}`chisurf/core/fluorescence/burst/es.py`, {src}`chisurf/core/fluorescence/fret/calibration.py`.
- Tools: **Accurate FRET** (`chisurf/plugins/burst/accurate_fret/`); the **Burst
  Browser** (`chisurf/plugins/burst/burst_browser/`) plots and gates the burst
  table.

## Known defects

- **Scatter plots are joined by lines under the default plot backend.** The
  AutoForm plot section draws markers-only series with a transparent pen
  (`chisurf/gui/autoform/sections/builtin.py`, `no_line` →
  `pen=(0, 0, 0, 0)`); the emtk backend drops the alpha and draws a black
  polyline through every population, and the legend swatches come out black.
  Workaround: `CHISURF_PLOT_BACKEND=pyqtgraph`.
- **Choosing a dye does nothing.** Opening the tool logs *bound control commit
  failed (Donor): AccurateFretViewModel.apply_dye_selection() takes 1
  positional argument but 2 were given* (and the same for Acceptor): the
  **Dyes (database)** combos pass the selection to a method that takes none.
