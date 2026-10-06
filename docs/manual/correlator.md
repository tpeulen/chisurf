---
type: Manual Page
title: Correlator
description: The correlator uses the generated photon selection masks and the photon stream to compute correlation functions (Fig.29).
tags: [manual, photons, correlation]
---

# Correlator

The correlator uses the generated photon selection masks and the photon stream to compute correlation functions (**Fig.29**).

```{image} figures/fcs_correlator_step.png
:align: center
```

**Fig.29 The Correlator step of the FCS hub** (**Tools → FCS**, step *4.
Correlator*), here on the hub's simulated two-channel example split into six
subsets. *Correlation Channels* picks the two channels from the setup's channel
definitions (**A**, **B**), or takes detector routing channels typed into
**Ch A**/**Ch B**, each optionally restricted to micro-time windows (**µt A**,
**µt B**, e.g. `0-100;200-300`). *Correlation Settings*: **Bins** linear bins per
cascade and **Cascades** multi-tau cascades set the lag grid, **Splits** the
number of subsets the photon stream is cut into, **Method** the tttrlib algorithm
(*laurence* by default), **Fine** the micro-time-resolved grid with its **µt
bin** factor. **Correlate** computes one curve per subset (right); **FCS
Preset** and **Load filters…** take a saved channel preset and photon filters
from the earlier steps. The curves are written into the `cr5` folder beside the
data, where the next step, the merger, reads them.

The correlation step computes correlation functions from the photons the mask selected. Those photons are split into subsets. For each subset a correlation curve is computed. The output is one curve file per subset in the `cr5` folder, holding the
correlation settings with the curve.
