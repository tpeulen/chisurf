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

The native host declares **1100 × 720** pixels on first use; saved geometry
takes precedence. Resizing or visiting tabs does not change the photons,
channel pairs, padding or correlator settings that produced a displayed curve.
A command-line `--size` explicitly requests another host size. Use the tool’s
settings and curve exports for analysis records; window geometry alone is not
a saved correlation result.


**Spectroscopy ▸ Correlation ▸ Burst-wise FCS** (also
the *Burst FCS* tool of **Spectroscopy ▸ Burst Analysis**, and *Burst-wise FCS*
in the [FCS hub](75_fcs_toolbox.md)) correlates each burst
separately, using only the photons of that burst ± **Padding**. The window has
**Run FCS**, **Stop**, **Example**, **Guide** and **Help** on top, three tabs on
the left and the plots on the right. All three entry points host the same native
app. For a GPU desktop, the standalone launch is
`pixi run -e test python -m chisurf.emtk --plugin burst_fcs_correlator --size 1200x800`;
headless calculations use the core API below, without launching a window:

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
  (log10)** over **tau_D min/max**, GUI presets **0.001 / 20 ms**, with 0
  explicitly requesting a data-dependent automatic bound) and the fit window **t_min /
  t_max** in ms (the GUI defaults to **t_min = 0.002 ms**, **t_max = 0**, with
  zero meaning no bound; the two vertical lines on the correlation plot drag
  it); **Load settings...** / **Save settings...**;
- **Detector setup** — the shared detector editor; **Use setup for pairs** turns
  the setup (its stored FCS pairs, else one auto-correlation per detector) into
  channel pairs.

Burst FCS pair gates use **half-open micro-time windows**: include the start
channel and exclude the stop channel, matching the detector windows used for
BUR counts. An empty list leaves a side ungated. Adjacent windows share no
boundary photon; overlapping windows accept each photon once. Check the complete
reader definition too, because LUTs and channel shifts can move a photon across
a gate boundary before the correlation is calculated.

```{figure} figures/burst_fcs_native_primary_window.png
:width: 100%

The native demo produces 24 correlations from eight bursts and three pairs.
Simple mode shows one fitted-time marker; it is not a probability distribution.
The simulated burst envelope illustrates the workflow rather than proving a
physical diffusion constant or kinetic rate.
```

**Run FCS** correlates every ticked file × pair × burst, with a progress bar.
The right side shows the correlation of the selected curve with its fit, the
**Curves** list (`burst · pair · tau_D`, filterable by text) and the **Distribution
P(tau_D)** in MaxEnt mode. In Simple mode that panel shows a single estimate
marker at the fitted diffusion time; it is not a probability distribution.
**Export curves...** saves the curves as JSON.
**Example** writes a small seeded demonstration data set (eight bursts on two
detectors) and adds it, so the **Guide** can be walked without data. It waits
for your **Example** click; correlation starts only when you press **Run FCS**.
`make_demo()` from `chisurf.plugins.burst.burst_fcs_correlator.demo` returns
the primary BST path; the photon file is alongside it as `SPC_FILENAME`. The
files and JSON parameters live in `demos/burst_fcs_correlator` under the
ChiSurf settings folder (`overwrite=True` regenerates them).

The Run worker also publishes `<stem>.pto`, `td4/<stem>.td4` and
`td4/td4_settings.json` beside the measurement/analysis inputs. The TD4
companion keeps one row per input burst, including NaN sentinel values where a
burst or channel pair produced no estimate, with zero-interleaved numeric
columns. The PTO stores produced rows keyed by **Burst Index**, with per-pair
diffusion-time columns in milliseconds, settings and lineage derived from the
bursts. Extending an existing PTO preserves its earlier scientific lineage.
Outputs are prepared before publication; cancellation or failure preserves
previous outputs. **Stop**, or closing the native app or its Qt host, requests
worker cancellation; closing also shuts down its owned executor.

```{figure} figures/fcs_native_bh132_burst_simple.png
:name: fig-16-burst-fcs
:width: 100%

Measured BH132 fixture, with three explicitly indexed BST ranges and one
`green_ACF` pair (channels 0, 1 on both sides), zero padding, three bins and
twelve cascades, with full 0–4095 micro-time gates. The Simple run produced
three curves and TD4/PTO outputs;
the selected curve's diffusion-time estimate is the yellow marker. This
single-pair capture does not demonstrate a FRET exchange fit.
```

```{figure} figures/fcs_native_bh132_burst_settings.png
:name: fig-16-burst-fcs-settings
:width: 100%

The same measured run's Settings tab: the 0.002 ms lower fit bound and
0.001 / 20 ms MaxEnt grid presets are visible. The Simple result above does
not establish numerical parity of a MaxEnt distribution.
```

For a headless calculation, supply the same photon-index ranges explicitly.
The core `BurstFcsSettings` defaults to `tmin_fit=None` and `tmax_fit=None`
(unbounded), so set 0.002 ms explicitly to reproduce the GUI fit window.

The core MaxEnt grid bounds also default to `None`, retaining their
data-dependent automatic choice. In the GUI, enter **0** for either grid bound
to request Auto rather than its 0.001 / 20 ms preset:

```python
from pathlib import Path
from chisurf.plugins.burst.burst_fcs_correlator.core import (
    BurstFcsSettings, PairConfig, correlate_burst_file,
)

settings = BurstFcsSettings(n_bins=3, n_casc=12, padding_ms=0,
                            fit_mode="simple", tmin_fit=0.002)
curves = correlate_burst_file(
    Path("test/data/tttr/BH/132/BH_SPC132.spc"),
    [(0, 5000), (6000, 11000), (12000, 17000)],
    [PairConfig("green_ACF", [0, 1], [0, 1])], settings,
)
```

This core call returns curves; it does not publish TD4/PTO files. The native
Run worker performs that publication separately.

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
