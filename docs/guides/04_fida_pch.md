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

**FIDA** (fluorescence-intensity distribution analysis; Kask et al., *PNAS*
1999) fits the histogram through the probability **generating function** with an
explicit spatial brightness profile $w(x)$ (the `dV/dx`):

$$G(\xi) = \exp\!\Big\{\sum_i N_i\!\int_0^1\! w(x)\big[e^{(\xi-1)q_i x}-1\big]dx
          + (\xi-1)\lambda_\text{bg}\Big\},$$

and $P(k)$ is recovered as the Taylor coefficients of $G$ (evaluate on the
complex unit circle, inverse-FFT). This handles arbitrary (non-Gaussian)
detection volumes and multiple species cleanly, recovering each species'
brightness $q$ and mean number $N$.

## In ChiSurf

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

FIDA is registered as the **“FIDA”** fit model in ChiSurf's **PCH experiment**,
alongside the reader that builds the histogram from a TTTR intensity trace — so
it plugs into the standard experiment → model → fit workflow like TCSPC or PDA.

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
- Model widget: {src}`chisurf/gui/widgets/models/pch/fida_widget.py`.
- Tool: **PCH** (`chisurf/plugins/pch/`).
