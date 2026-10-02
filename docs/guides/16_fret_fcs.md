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
separately, using only the photons of that burst ± **Padding**. The window has
**Run FCS**, **Stop**, **Example**, **Guide** and **Help** on top, three tabs on
the left and the plots on the right:

- **Inputs** — the **Burst folders or BUR/BST files** table (**Files...**,
  **Folder...**, **Database...**, **All**, **None**, **Remove**, **Clear**; files
  and folders can be dropped on the window) and the **FCS channel pairs** table
  (tick the pairs to compute — GG, RR and the GR cross term for FRET-FCS; double-click
  a cell to edit the channels or the micro-time gates; **Add pair**, **Remove
  pair**, **Load pairs...**, **Save pairs...**, **Show JSON**);
- **Settings** — **Correlator**: **FCS bins (B)** (linear bins per cascade, 3),
  **Cascades** (20), **Fine grid** (micro-time-resolved lags), **Padding ±
  (ms)** (100); **Fitting**: **Mode** *None* / *Simple* (one diffusion component)
  / *MaxEnt* (a diffusion-time distribution, regularised by **MaxEnt reg
  (log10)** over **tau_D min/max**, 0 = automatic) and the fit window **t_min /
  t_max** (0 = the full lag range; the two vertical lines on the correlation plot
  drag it); **Load settings...** / **Save settings...**;
- **Detector setup** — the shared detector editor; **Use setup for pairs** turns
  the setup (its stored FCS pairs, else one auto-correlation per detector) into
  channel pairs.

**Run FCS** correlates every ticked file × pair × burst, with a progress bar.
The right side shows the correlation of the selected curve with its fit, the
**Curves** list (`burst · pair · tau_D`, filterable by text) and the **Distribution
P(tau_D)** in MaxEnt mode. **Export curves...** saves the curves as JSON.
**Example** writes a small seeded demonstration data set (eight bursts on two
detectors) and adds it, so the **Guide** can be walked without data.

```{figure} figures/16_burst_fcs.png
:name: fig-16-burst-fcs
:width: 100%

The demonstration data set (**Example**): eight seeded bursts on two detectors,
channel pairs ACF_0, ACF_1 and cross_01, 24 curves, *Simple* fit. Shown is the
ACF_0 curve of burst 0; a single burst's curve is shot-noise limited at short
lags, which is why the kinetic terms are fitted globally over many bursts. The
photons are generated, not measured.
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

## See also

- FCS models {src}`chisurf/core/models/fcs/models.yaml`; [Diffusion FCS](09_diffusion_fcs.md).
- Tool: **Burst-wise FCS** (`chisurf/plugins/burst/burst_fcs_correlator/`).
