---
type: Guide
title: FIDA — photon-counting histograms
description: The photon-counting histogram — how often a time bin contains $k$ photons — carries the molecular brightness and concentration, which an intensity trace alone does not.
tags: [guides, photons, fida]
---

# FIDA — photon-counting histograms

:::{admonition} Theory
:class: seealso
How the photon-count amplitude distribution separates molecular brightness
$\epsilon$ from the number of molecules $N$ (independently of diffusion), the
single- and multi-species PCH, and FIDA's generating-function formulation are in
the concept page {ref}`concept-pch-fida`.
:::

## What it does

The **photon-counting histogram** — how often a time bin contains $k$ photons —
carries the molecular **brightness** and **concentration**, which an intensity
trace alone does not. A single bright species gives a *super-Poissonian*
histogram (broader than Poisson at the same mean); mixtures broaden further.

**FIDA** (fluorescence-intensity distribution analysis; {cite}`kask1999`) fits the histogram through the probability **generating function** with an
explicit spatial brightness profile $w(x)$ (the `dV/dx`):

$$G(\xi) = \exp\!\Big\{\sum_i N_i\!\int_0^1\! w(x)\big[e^{(\xi-1)q_i x}-1\big]dx
          + (\xi-1)\lambda_\text{bg}\Big\},$$

and $P(k)$ is recovered as the Taylor coefficients of $G$ (evaluate on the
complex unit circle, inverse-FFT). This handles arbitrary (non-Gaussian)
detection volumes and multiple species cleanly, recovering each species'
brightness $q$ and mean number $N$.

## In ChiSurf

There are two GUI routes, and only one of them is FIDA.

### The PCH tool (classical PCH, not FIDA)

*Spectroscopy:Single-Molecule:PCH* (`chisurf/plugins/pch/`) bins a TTTR
stream and fits the multi-species PCH of {cite}`chen1999` — a 3-D Gaussian
volume, no brightness profile. **Load TTTR** → set **Channels**, **Bin Time**
and the **Micro Time** window → **Compute PCH** draws the intensity trace (top)
and the histogram (bottom); **Components** and the ε/⟨N⟩ start values set the
fit, the shaded region on the histogram the fit range, and **Fit Model** runs
it.

```{figure} figures/04_pch_tool.png
:name: fig-pch-tool
:width: 100%

The PCH tool on `test/data/tttr/BH/132/BH_SPC132.spc`, green detectors
(channels 0, 8), 50 µs bins: 1 246 577 bins, counts 0–24 per bin. The long tail
is single-molecule bursts on a nearly empty focus.
```

The default **Channels** is `0,2` and **Bin Time** 100 µs; set the channels to
your detectors. Do not trust this tool's χ² — see *Known defects*.

### FIDA in the PCH experiment

FIDA is the **FIDA** model (`FidaModel`) of ChiSurf's **PCH** experiment,
beside the multi-component PCH model; the **PCH (TTTR)** reader builds the
histogram from a TTTR intensity trace, so it plugs into the standard
experiment → model → fit workflow like TCSPC or PDA. The editor pairs each
species' brightness `q` and number `N` in one row; a zero in either switches the
species off. **Background & totals** holds `bg` and the computed mean count per
bin.

```{figure} figures/04_fida_editor.png
:name: fig-fida-editor
:width: 80%

FIDA fitted to the PCH in {numref}`fig-pch-tool` (y = P(k)): two species,
species 3 fixed at 0, bounds on. χ²ᵣ = 1.45 with a dim species
(`q` = 1.72, `N` = 0.92), a bright one (`q` = 10.3, `N` = 0.35) and
`bg` = 0.073 counts/bin; the computed mean, 0.1088, equals the data's.
```

Switch **Bounds** on for every `q` and `N` before fitting: with the default
(off) the same fit drives both `N` negative, which silently switches both
species off and leaves a pure background (χ²ᵣ = 407).

### Headless

```python
import numpy as np
from chisurf.core.models.pch import fida

# Forward model: P(k) for one or several (brightness q, number N) species
p1 = fida.fida_pch(k_max=40, species=[(3.0, 2.0)])
p2 = fida.fida_pch(40, species=[(1.0, 4.0), (6.0, 0.3)], background=0.2)

# Fit a measured histogram (Levenberg-Marquardt on the multinomial residuals)
res = fida.fit_fida(counts, species_guess=[(1.5, 1.0)])
res["species"], res["chi2r"]      # recovered (q, N) and reduced chi^2
```

`counts` is the number of bins with $k = 0, 1, \dots$ photons. On the
histogram above, one species gives χ²ᵣ = 8.4 × 10⁶; two species
(`species_guess=[(0.5, 0.2), (5.0, 0.01)]`) give χ²ᵣ = 7.47 with
(q, N) = (0.098, 120) and (10.8, 0.38) — the bright species agrees with the
editor fit, the dim one trades `q` against `N`.

## Result

The FIDA forward model for a single bright species (blue) and a two-species
mixture (red), against a Poisson distribution of the same mean (dashed). The
extra width beyond Poisson is exactly the brightness information FIDA extracts.

```{figure} figures/fida.png
:name: fig-fida
:width: 90%

FIDA photon-counting histograms.
```

## See also

- {src}`chisurf/core/models/pch/fida.py` (`fida_pch`, `fit_fida`, `dvdx_gaussian`, `fida_residuals`)
- Model: {src}`chisurf/core/models/pch/fida_model.py` (`FidaModel`, editor `fida.view.json`).
- Tool: **PCH** (`chisurf/plugins/pch/`) — classical multi-species PCH.

## Known defects

- **The PCH tool's fit is unweighted and its χ² meaningless.** The backend
  (`chisurf/plugins/pch/backend/services.py`, `pch.fit`) minimises
  `pmod − p_exp` with no weights, so P(0) and P(1) decide the fit and the tail
  is ignored; χ² is then Pearson's over every bin with a positive expected
  count, including tail bins with expected counts near 10⁻¹⁴. On the data of
  {numref}`fig-pch-tool` one component gives ε = 0.332, ⟨N⟩ = 1.83 and
  χ²ᵣ = 1.5 × 10²⁰ over the full range (1.1 × 10¹⁰ over k ≤ 13), with the model
  falling ten decades below the data at k = 13. A two-component fit did not
  return within 5 minutes. Use FIDA in the PCH experiment.
- **`FidaModel` parameters have bounds off** (`fida_model.py`, `_p(..., bounds_on=False)`),
  so an unattended fit can run `N` negative; see above.
- **`fida.fida_pch` ignores `profile` and `oversample`.** Both are documented
  arguments, but the function calls `tttrlib.fida_pch(k_max, species, n, bg)`
  without them, so a custom brightness profile has no effect.
