---
type: Guide
title: FRET-FCS
description: Correlating the donor and acceptor signals of freely-diffusing FRET molecules adds dynamics information to FCS. If the molecule inter-converts between FRET states while in the focus…
tags: [guides, fret, fcs, dynamics]
---

# FRET-FCS

:::{admonition} Theory
:class: seealso
See {ref}`concept-fcs-correlation` for the correlation function and FRET-FCCS kinetics.
:::

## What it does

Correlating the donor and acceptor signals of freely-diffusing FRET molecules
adds **dynamics** information to FCS. If the molecule inter-converts between FRET
states while in the focus, the donor and acceptor intensities fluctuate in
**anti-phase** (more FRET → less donor, more acceptor). So on top of the
diffusion decay:

- the donor and acceptor **auto-correlations** show a positive relaxation
  (bunching) term at the exchange time,
- the donor–acceptor **cross-correlation** shows a negative (anti-correlated)
  term at the same time.

The relaxation time gives the sum of the forward and backward rate constants,
independent of the (much slower) diffusion time.

## In ChiSurf

```python
# correlate two photon streams (donor, acceptor) with the FCS correlator, then
# fit the auto/cross curves globally with the FRET-FCCS models in models.yaml.
import numpy as np
import tttrlib

tttr = tttrlib.TTTR("test/data/tttr/BH/132/BH_SPC132.spc", "SPC-130")
donor = np.isin(tttr.routing_channels, [0, 8]).astype(float)
acceptor = np.isin(tttr.routing_channels, [1, 9]).astype(float)
mt = tttr.macro_times
dt_ms = tttr.header.macro_time_resolution * 1e3


def g(w_a, w_b):
    corr = tttrlib.Correlator(n_bins=4, n_casc=26, make_fine=False)
    corr.set_macrotimes(mt, mt)
    corr.set_weights(w_a, w_b)
    return corr.x_axis * dt_ms, np.asarray(corr.correlation)


tau, G_dd = g(donor, donor)
_, G_aa = g(acceptor, acceptor)
_, G_da = g(donor, acceptor)
# G_dd, G_aa, G_da  ->  fit sharing the exchange rate k = k12 + k21
```

(`tttr.header.macro_time_resolution` is in seconds, so `tau` is in ms.) The FCS
model catalogue includes explicit 2-state FRET-FCCS kinetic models
(`FRET-FCCS, 2-state (D)`); the correlator plugins compute the auto/cross curves
from the burst or full photon streams.

### Burst-wise FCS

**Spectroscopy ▸ Fluorescence Correlation Spectroscopy ▸ Burst-wise FCS** (also
the *Burst FCS* tool of **Spectroscopy ▸ Burst Analysis**) correlates each burst
separately, using only the photons of that burst ± **Padding**. Left, top to
bottom:

- the **detector setup**; its stored FCS pairs fill **FCS channel pairs**
  (tick the pairs to compute — GG, RR and the GR cross term for FRET-FCS);
- **Correlator**: **FCS bins (B)** (linear bins per cascade, 3), **cascades**
  (20), **Fine grid** (micro-time-resolved lags), **Padding ±[ms]** (100);
- **Fitting**: **Mode** *None* / *Simple* (one diffusion component) /
  *MaxEnt* (a diffusion-time distribution, regularised by **MaxEnt reg
  (log10)** over **τ_D min/max**, 0 = automatic), and the fit window
  **t_min / t_max** (0 = the full lag range);
- **Burst folders or BUR/BST files**: a burst-analysis folder (its `bi4_bur/`
  or `BID/` files point back at the TTTR measurement).

**▶ Run** correlates every checked file × pair × burst. The right side lists the
curves (`file · b<burst> · pair`, filterable by text) and plots the selected one
with its fit; *Diffusion-time distribution* holds $P(\tau_D)$ in MaxEnt mode.
**≡ Settings** saves/loads the settings as JSON and shows the resolved pairs.

```{figure} figures/16_burst_fcs.png
:name: fig-16-burst-fcs
:width: 100%

Burst-wise FCS on the 10 BH SPC-132 smFRET files of the burst-selection test
folder, pairs GG (0/8), RR (1/9) and GR: 8940 curves. Shown is the GG
auto-correlation of the longest burst of `m000.spc` (598 photons) with the
*Simple* diffusion fit; a single burst's curve is shot-noise limited at short
lags, which is why the kinetic terms are fitted globally over many bursts.
```

## Result

Donor and acceptor auto-correlations (positive relaxation) and the
donor–acceptor cross-correlation (anti-correlated dip) riding on the common
diffusion decay — the FRET-FCS signature of conformational exchange.

```{figure} figures/fret_fcs.png
:name: fig-fret-fcs
:width: 90%

FRET-FCS auto and cross correlations.
```

## Known defects

- After **▶ Run** the *Computing burst-wise FCS…* progress bar stays in the
  status bar (visible in the figure): `_on_run` in
  `chisurf/plugins/burst/burst_fcs_correlator/gui/tool.py` sets the final value
  but never closes the `ChiSurfProgress`.

## See also

- FCS models {src}`chisurf/core/models/fcs/models.yaml`; [Diffusion FCS](09_diffusion_fcs.md).
- Tool: **Burst-wise FCS** (`chisurf/plugins/burst/burst_fcs_correlator/`).
