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

tttr = tttrlib.TTTR("measurement.ptu")
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

The FCS model catalogue includes explicit 2-state FRET-FCCS kinetic models
(`FRET-FCCS, 2-state (D)`); the correlator plugins compute the auto/cross curves
from the burst or full photon streams.

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
