---
type: Guide
title: Burst Variance Analysis (BVA)
description: BVA (Torella et al., Biophys. J. 2011) is a model-free test for sub-burst FRET dynamics, complementary to 2CDE. Each burst is split into short slices of a few photons, the proximity ratio is computed for every slice…
tags: [guides, bursts, fret, dynamics]
---

# Burst Variance Analysis (BVA)

:::{admonition} Theory
:class: seealso
The shot-noise variance baseline $\sigma_\text{sn}=\sqrt{E(1-E)/n}$ and how
excess per-burst variance reveals sub-burst dynamics are explained in the concept
page {ref}`concept-bva`.
:::

## What it does

**BVA** {cite}`torella2011` is a model-free test for sub-burst
FRET dynamics, complementary to [2CDE](01_fret_2cde.md). Each burst is split into
short slices of a few photons, the proximity ratio is computed for every slice,
and the **standard deviation** of the slice proximity ratios is taken per burst.

For a genuinely **static** species the only source of slice-to-slice variation is
shot noise, so the standard deviation follows the analytic shot-noise line
$\sigma = \sqrt{p(1-p)/n}$ (for $n$ photons per slice at proximity ratio $p$). A
**dynamic** species that inter-converts within the burst scatters **above** that
line.

## In ChiSurf

The engine is the `tttrlib.BVA` burst feature (parallel over bursts); the
`burst_bva` plugin wraps it. Open it as step **4. Burst BVA** of
**Spectroscopy → Burst Analysis** — the burst folder and detector setup of step
2 carry over — or on its own as *Spectroscopy:Single-Molecule:BVA*.

Point the plugin at a burst-analysis folder either with the 📂 toolbar button or
by **dropping the folder anywhere on the BVA window**. BVA reads a whole folder,
so dropping a single file is reported in the status line rather than accepted.
With **Auto update** ticked the plot is recomputed as soon as a folder and a
setup are known; ▶ runs it and writes the `bv4/` output.

```{figure} figures/08_bva_tool.png
:name: fig-bva-tool
:width: 100%

The BVA tool on the burst folder Burst Selection wrote for the ten bundled
SPC-132 dsDNA measurements (1130 bursts, 1118 with enough photons for at least
one slice; 10 photons per slice). Red: the static (shot-noise) line; cyan: the
mean slice standard deviation per proximity-ratio column. The donor-only spot
near 0 sits on the line; the FRET population around 0.3–0.7 lies above it.
Rendered with `CHISURF_PLOT_BACKEND=pyqtgraph` — see *Known defects*.
```

| Control | Default | Meaning |
|---|---|---|
| **Min window length (s)** | 0.01 | Alternative slicing by a fixed time. |
| **Photons per slice** | 10 | $n$ of the slices and of the static line. |
| **Setup** | — | Detector setup (also editable on **Channel Definitions**). |
| **Donor detector** / **Acceptor detector** | first two detectors | Which detectors form $p = n_A/(n_D+n_A)$. |
| **Bins X** / **Bins Y** | 31 / 31 | Resolution of the 2-D histogram. |
| **Show static line** / **Auto update** (toolbar) | on / on | Overlay the shot-noise line; recompute on every change. |

The toolbar counter (*1118 / 1130 bursts*) says how many bursts had at least one
full slice.

### Headless

```python
import numpy as np
import tttrlib

tttr = tttrlib.TTTR("m000.spc", "SPC-130")
burst_bounds = tttr.burst_search(L=20, m=10, T=0.5e-3).reshape(-1, 2)  # (start, stop) rows

bva = tttrlib.BVA(tttr)
bva.set_donor([0, 8])              # donor routing channels
bva.set_acceptor([1, 9])           # acceptor routing channels
bva.compute(burst_bounds, 5, 0.01) # photons per slice, min window length (s)

mean = np.asarray(bva.proximity_ratio_mean)    # per burst
std  = np.asarray(bva.proximity_ratio_std)

# the analytic shot-noise line to overlay
grid = np.linspace(0.01, 0.99, 200)
_, shot_noise_std = tttrlib.BVA.compute_static_bva_line(grid, number_of_photons_per_slice=5)
```

`compute` takes the bounds as an `(n, 2)` array and its arguments
**positionally** — a flat `burst_search` result raises *"Array must have 2
dimensions"*, and keywords raise *"unexpected keyword argument"*. On `m000.spc`
this gives 223 bursts, mean proximity ratio 0.280 and mean slice standard
deviation 0.161; the static line at $p = 0.5$, $n = 5$ is 0.2236
($\sqrt{0.25/5}$).

From the guided workflow: `bursts.bva("green", "red", photons_per_slice=5)`
returns a `Bva` result with `.dynamic_fraction` and `.plot()` (0.416 for
`m000`–`m002.spc` searched with `min_photons=20`).

## Result

Simulated static bursts (constant acceptor probability) fall on the shot-noise
limit, while dynamic bursts (alternating high/low FRET within each burst) sit
clearly above it.

```{figure} figures/bva.png
:name: fig-bva
:width: 90%

Burst Variance Analysis.
```

## See also

- Engine `tttrlib.BVA` (base class `tttrlib.BurstFeature`); plugin `chisurf/plugins/burst/burst_bva/`.
- The kernel-density dynamics test: [FRET-2CDE](01_fret_2cde.md).

## Known defects

- **The BVA plot is blank under the default plot backend.** The emtk backend's
  generic `set_data` (`chisurf/gui/chiplot/backends/emtk_backend.py`, the
  handle's `set_data`) replaces `x`/`y` of an error-bar item but ignores `top`
  and `bottom`, so the profile's error bars keep zero-length extents while their
  `x` grows; `_draw_errorbars` then raises `IndexError` on every paint and the
  heat map and axes are never drawn — only the two lines appear. Workaround:
  start ChiSurf with `CHISURF_PLOT_BACKEND=pyqtgraph`.
