---
type: Guide
title: RCM from FRET-labelled samples (PIE/ALEX)
description: The dye-solution RCM calibration needs separate donor-only and acceptor-only reference solutions.
tags: [guides, fret, calibration]
---

# RCM from FRET-labelled samples (PIE/ALEX)

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for the E/S corrections and the calibration factors.
:::

## What it does

The [dye-solution RCM calibration](07_rcm_calibration.md) needs separate
donor-only and acceptor-only reference solutions. When only **doubly-labelled
FRET samples** measured under **PIE/ALEX** are available, the detection-correction
matrix can instead be obtained from the sample itself: the acceptor-excitation
(Aex) period isolates the acceptor detection, and the donor-excitation (Dex)
period the donor + sensitised-acceptor, so the same linear relations between
channel rates that define the RCM can be solved from the ALEX sub-populations
(donor-only, acceptor-only and FRET species that the [E–S histogram](14_multiparameter_es.md)
separates).

## In ChiSurf

The correction machinery lives in {src}`chisurf/core/fluorescence/fret/calibration.py`
(γ/β, leakage, direct excitation, and the routing-correction matrix), and the
ALEX/PIE stream handling in tttrlib (`tttrlib.corrected_es`). The
E–S-based `tttrlib.global_es_correction` / `refine_calibration` derive the correction
factors from the sample's own donor-only / acceptor-only / FRET populations; the
`ptu_alex_creator` and micro-time-gating tools prepare PIE/ALEX streams.

```python
from chisurf.core.fluorescence.fret import calibration as cal

# per-burst photon counts (arrays), labels = FRET population index per burst
calib = cal.calibrate_from_samples(
    cal.CalibrationParameters(),
    (i_dd, i_da, i_aa, labels),                 # >= 2 FRET populations
    donor_only=(do_dd, do_da),                  # -> alpha
    acceptor_only=(ao_da, ao_aa, ao_dd),        # -> delta (note the order)
)
calib["alpha"], calib["delta"], calib["gamma"], calib["beta"]
```

On simulated counts with $\gamma=1.35$, $\alpha=0.09$, $\delta=0.06$,
$\beta=0.95$ (two FRET populations at E = 0.30 / 0.70 of 1500 bursts each,
500 donor-only, 500 acceptor-only, ~400 photons per burst) this returns
α = 0.0905, δ = 0.0595, γ = 1.3498, β = 0.9483. Passing the acceptor-only
tuple in the donor-only order `(dd, da, aa)` does not fail — it returns
δ = 0 and a biased β (0.898), so check the order.

### In the Accurate FRET tool

**Spectroscopy ▸ FRET ▸ Accurate FRET** does the same from a burst table:
pick the **Burst table** and map its columns (**I_DD**, **I_DA**, **I_AA**,
optional **Donor lifetime**), optionally fill *Dyes (database)*,
*Photophysics*, *Background*, *Optics prior (light path)* and *Procedure*, and
press **🎯 Calibrate**. It finds the donor-only, acceptor-only and FRET
populations itself (stoichiometry cuts plus clustering), reports the factors
with bootstrap errors and what determined each, and shows *Populations*,
*E–S*, *E–lifetime* and the *E histogram*. **Store on setup** saves the
factors on the detector setup so later sessions (e.g. the filter calculator's
Instrument dock) start from them; **To ndX** / **From ndX** and **Export CSV**
move the corrected table.

```{figure} figures/25_accurate_fret_factors.png
:name: fig-25-accurate-fret-factors
:width: 100%

Accurate FRET on a simulated PIE/ALEX burst table with the instrument of the
figure below (γ = 1.35, α = 0.09, δ = 0.06, β = 0.95; 20 bootstrap
replicates): α = 0.0903 ± 0.0008 (donor-only bursts), β = 0.9498 ± 0.0027
and γ = 1.3488 ± 0.0079 (E–S fit), δ = 0.0580 ± 0.0005 (acceptor-only
bursts); 485 donor-only, 484 acceptor-only and 3000 FRET bursts found.
```

```{figure} figures/25_accurate_fret.png
:name: fig-25-accurate-fret
:width: 100%

The *E–S* view of the same run: corrected FRET populations at E ≈ 0.30 and
0.70, S ≈ 0.5; donor-only at S = 1; acceptor-only at S = 0. The black
polylines through the clusters and along S = 0 are a rendering defect (see
*Known defects*), not data.
```

## Result

Applying the factors recovered from the sample's own ALEX sub-populations moves
each FRET population from its *apparent* efficiency to its *accurate* one. The
donor-only and acceptor-only corners are what pin $\alpha$ and $\delta$; the two
FRET populations pin $\gamma$ and $\beta$.

```{figure} figures/rcm_alex.png
:name: fig-rcm-alex
:width: 95%

Simulated PIE/ALEX data with a known instrument
($\gamma=1.35$, $\alpha=0.09$, $\delta=0.06$, $\beta=0.95$). **Left:** the raw
$E_\text{app}$/$S_\text{app}$ map. **Right:** after correction — the two FRET
populations land on their true efficiencies (dashed lines at E = 0.30 and 0.70),
computed with the real `corrected_es`.
```

## See also

- {src}`chisurf/core/fluorescence/fret/calibration.py`, tttrlib `corrected_es`; the dye-solution route: [RCM calibration](07_rcm_calibration.md).
- The full correction algebra and the general crosstalk-matrix form: [accurate FRET calibration](fret_calibration.md).
- The E–S map these populations are read from: [multi-parameter E–S](14_multiparameter_es.md).
- Tool: **Accurate FRET** (`chisurf/plugins/burst/accurate_fret/`).

## Known defects

- **Marker-only scatter series are drawn with black joining lines.** The
  AutoForm plot section (`chisurf/gui/autoform/sections/builtin.py`, the
  `no_line` branch of `PlotWidget.refresh`) passes a transparent pen
  `(0, 0, 0, 0)`; it is drawn opaque black, so every class series in the E–S
  and E–lifetime views is joined in data order and the legend swatches are
  black.
- Opening the tool logs `bound control commit failed (Donor/Acceptor):
  AccurateFretViewModel.apply_dye_selection() takes 1 positional argument but 2
  were given`: the view spec's `call` passes the new value, the method takes
  none, so a chosen dye pair is not applied.
