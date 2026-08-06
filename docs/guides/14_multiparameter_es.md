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

```python
from chisurf.core.fluorescence.fret import calibration as cal

# leakage & direct-excitation from the donor-only / acceptor-only populations
leak  = cal.leakage_from_donor_only(i_dd, i_da)
dir_a = cal.direct_excitation_from_acceptor_only(i_da, i_aa)

# global gamma/beta from the FRET populations
est = cal.global_es_correction(i_dd, i_da, i_aa, labels, alpha=leak, delta=dir_a)
```

The per-burst $E$/$S$ are computed in {src}`chisurf/core/fluorescence/burst/es.py`
(ALEX/PIE-aware); the burst browser plots the 2-D histogram and the
`fret_calculator` / calibration tools manage the factors. See also the
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
- Tool: the **Burst Browser** (`chisurf/plugins/burst/burst_browser/`).
