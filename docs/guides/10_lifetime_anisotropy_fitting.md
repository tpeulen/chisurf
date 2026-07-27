# Fluorescence lifetime and anisotropy decay fitting

## What it does

Time-correlated single-photon counting (TCSPC) records the arrival time of each
photon relative to the excitation pulse, building a **fluorescence decay**. The
decay is the fluorophore's intensity response convolved with the instrument
response function (IRF):

$$I(t) = \mathrm{IRF}(t) \ast \sum_i a_i\,e^{-t/\tau_i}.$$

Fitting the lifetime spectrum $\{a_i, \tau_i\}$ reports on the environment and,
for a FRET donor, on the transfer efficiency — a shorter average lifetime means
higher FRET. Polarised detection additionally gives the **anisotropy decay**
$r(t) = r_0\,e^{-t/\rho}$, whose rotational correlation time $\rho$ reports on
rotational mobility (and on dye/protein tumbling).

:::{admonition} Theory
:class: seealso
The reconvolution model, IRF, multi-exponential decay, average-lifetime
definitions, and the scatter/background/pile-up nuisances are covered in
{ref}`concept-tcspc-lifetime`; the anisotropy decay, the G-factor, and the
rotational-correlation-time model are in {ref}`concept-anisotropy`. This guide
shows how to fit in ChiSurf.
:::

## In ChiSurf

TCSPC is the most mature part of ChiSurf: the **TCSPC experiment** offers lifetime,
FRET (including the [SAW-ν / Ising / WLC](03_polymer_distance_distributions.md)
distance-distribution and structural FRET models), anisotropy, and
mixture models, all built on the fast convolution kernels in
`chisurf/core/fluorescence/tcspc/`.

The lifetime model editor exposes the whole decay model as grouped parameter
tables:

```{figure} figures/tcspc_lifetime_editor.png
:name: fig-tcspc-lifetime-editor
:width: 90%

The TCSPC lifetime model editor. **Convolution** selects the IRF curve and the
convolution mode (`per`iodic / `exp` / `full`); **Generic** holds the scatter
`sc`, background `bg`, and constant-background `tBg` nuisances; **Lifetimes** is
an add/remove table of amplitude–lifetime pairs ($x_L$, $\tau_L$) with
normalization and linking; **Anisotropy** adds the polarised $r(t)$ model.
```

Each group in {numref}`fig-tcspc-lifetime-editor` corresponds to a factor in the
reconvolution model of {ref}`concept-tcspc-lifetime`: the **Lifetimes** table is
the $\sum_i a_i e^{-t/\tau_i}$ spectrum, **Convolution** applies the
$\mathrm{IRF}\ast(\cdot)$, and **Generic** adds the scatter/background terms.
Unticking the checkbox of the **Convolution** group drops the
$\mathrm{IRF}\ast(\cdot)$ factor — the model is then the ideal decay itself (tail
fitting), with the inter-pulse tail kept in the `per`iodic mode.

```python
import numpy as np
from chisurf.core.fluorescence.tcspc.convolve import convolve_lifetime_spectrum

n, dt = 4096, 0.016                        # channels, ns/channel
t = np.arange(n) * dt
irf = np.exp(-0.5 * ((t - 0.6) / 0.05) ** 2); irf /= irf.sum()

def decay(spectrum):                       # spectrum = [a1, tau1, a2, tau2, ...]
    out = np.zeros(n)
    convolve_lifetime_spectrum(out, np.asarray(spectrum, float), irf, -1, t)
    return out

d_noFRET = decay([1.0, 3.5])               # single 3.5 ns donor
d_FRET   = decay([0.6, 3.5, 0.4, 0.7])     # + a 0.7 ns FRET-quenched fraction
```

## Result

**Left:** IRF-convolved lifetime decays — the FRET decay (fast 0.7 ns component)
falls off faster than the unquenched 3.5 ns donor. **Right:** anisotropy decays
for three rotational correlation times.

```{figure} figures/lifetime_anisotropy.png
:name: fig-lifetime-anisotropy
:width: 90%

Fluorescence lifetime and anisotropy decays.
```

## See also

- Concept: {ref}`concept-tcspc-lifetime`.
- `chisurf/core/models/tcspc/` (lifetime, FRET, anisotropy, mixture, structural models).
- Lifetimes from single-molecule bursts: {doc}`21_lifetime_from_bursts`;
  ns-ALEX/PIE lifetimes: {doc}`32_nsalex_lifetime`.
- Distance-distribution FRET models: [Polymer distance distributions](03_polymer_distance_distributions.md).
