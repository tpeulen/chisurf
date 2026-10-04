---
type: Guide
title: Fluorescence lifetime and anisotropy decay fitting
description: Time-correlated single-photon counting (TCSPC) records the arrival time of each photon relative to the excitation pulse, building a fluorescence decay.
tags: [guides, tcspc, lifetime, anisotropy, fitting, decay, photons]
---

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

## First-use behavior

Adding a fit initializes the fit plot and parameter controls without constructing
the hidden Code editor or importing unrelated optional GUI sections. **Code** is
created when first opened and reused on subsequent visits. Other plot tabs remain
available; a first visit may still need to initialize that feature.

The metadata editor keeps the complete key catalog, completion, arbitrary custom
keys and description tooltips, but loads catalog data only when needed. Solid
curves use batched Qt drawing while retaining all samples and nonfinite gaps;
this does not change fitting calculations or perform scientific resampling.

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

## The Anisotropy Wizard (time-resolved anisotropy)

*Spectroscopy → Fluorescence decay → Anisotropy-Wizard* builds the linked VV/VH global fit from four
measured curves. It fits VV and VH themselves, linked, never the ratio $r(t)$ (forming the ratio first
destroys the Poisson weights). The window has the six steps listed on the left, each with a check mark
once it is complete; **Back** and **Next** (bottom right) walk them, **Guide** starts the guided tour and
**Help** opens the background text.

1. **Data.** Type or paste the four paths (IRF VV, IRF VH, Data VV, Data VH), use **Browse**, or drop the
   files on the window (a dropped file fills the next empty path; a dropped `.spk.json` loads spectra).
   *Two stacked VV/VH files* switches to one IRF file and one data file that hold both channels. The
   reader settings (*Bin width*, *Repetition rate*, *Header rows*, *Use file header*, *First column is
   time*) say how the text decays are read; a field that does not apply to the chosen file layout is
   greyed.

   ```{figure} figures/tr_anisotropy_data.png
   :name: fig-tr-anisotropy-data
   :width: 90%

   Data step with four synthetic polarised curves (tau 4 ns, rho 1.5 ns, r0 0.35).
   ```

2. **Normalize IRF.** **Load / reload data** reads the files. Place the green box on a signal-free stretch
   of the IRFs (drag its edges in the plot, or type *Background from* / *Background to*): the mean of
   that region is subtracted from both IRFs and the two are scaled to the same intensity. The mouse wheel
   zooms the plot. **Export corrected IRFs** writes the two corrected curves to a file.

   ```{figure} figures/tr_anisotropy_normalize.png
   :name: fig-tr-anisotropy-normalize
   :width: 90%

   Raw (faint) and corrected (solid) VV and VH IRFs with the background region.
   ```

3. **Corrections.** *g-factor* scales the anisotropy as a whole; *l1* and *l2* correct the polarisation
   mixing of a high-aperture objective (zero on a low-NA setup).
4. **Components.** The lifetime spectrum (amplitude, lifetime) and the rotation spectrum (amplitude,
   correlation time) are shared by the VV and VH fits. Double-click a cell to edit it, select a row and
   press Delete or **Remove selected** to drop it, set *Amplitude* and the time and press **Add component**
   to append one. **Save spectra** writes both tables to a `.spk.json` file, **Load spectra** reads one.

   ```{figure} figures/tr_anisotropy_components.png
   :name: fig-tr-anisotropy-components
   :width: 90%

   The two spectra tables of the Components step.
   ```

5. **Finish.** **Create fits** adds the VV fit, the VH fit and the global fit to the session with the
   amplitudes, lifetimes, rotation components and the three corrections linked; check that r0 is at or
   below 0.4 first. It asks for **Load / reload data** again when the files or reader settings changed
   after loading.

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
- Building the decay from a photon file: {doc}`73_tttr_decay_and_correlation`.
- Lifetimes from single-molecule bursts: {doc}`21_lifetime_from_bursts`;
  ns-ALEX/PIE lifetimes: {doc}`32_nsalex_lifetime`.
- Distance-distribution FRET models: [Polymer distance distributions](03_polymer_distance_distributions.md).
- Tool: the **Anisotropy Wizard** (`chisurf/plugins/fluorescence_decay/tr_anisotropy/`), **VV/VH Anisotropy Decay** (`chisurf/plugins/vv_vh_anisotropy/`) and the **VV/VH G-Factor Calculator** (`chisurf/plugins/vv_vh_g_factor/`).
