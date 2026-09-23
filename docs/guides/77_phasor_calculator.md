---
type: Guide
title: 'The phasor calculator: where a lifetime lands before you measure it'
description: Placing reference lifetimes, a FRET trajectory, a two-component mixing line and a gating cursor on the universal semicircle at a chosen frequency and harmonic, reading the reference table, and reproducing every overlay and a measured, IRF-corrected phasor headlessly.
tags: [guides, imaging, flim, phasor, lifetime]
---

# The phasor calculator: where a lifetime lands before you measure it

Before a phasor plot of real data can be read, you need to know where the things
you expect would sit on it: a 4 ns donor at 80 MHz, the same donor at 50 % FRET,
a 50:50 mixture of a short and a long species. The phasor calculator draws that
reference geometry on the universal semicircle for any frequency and harmonic.
It needs no data and changes none.

For the theory (the transform, the semicircle, apparent lifetimes, harmonics, the
lever rule and calibration), see {ref}`concept-imaging-flim-phasor`. The per-pixel
phasor of a real image is {doc}`24_scan_images`.

## Open the tool

**Main → Tools → Calculators**, entry **◐ Phasor plot**. The manifest name
`Main:Tools:Phasor-Calculator` is hidden from the menu; the Calculators hub is
the only way in. The window has two dock tabs, **Controls** and **Phasor plot**.
The plot redraws whenever a field is committed (Enter or focus change) or a box
is ticked. **❓** (top right) opens a short explanation of the plot.

```{figure} figures/phasor_calculator.png
:name: fig-phasor-calculator
:width: 100%

The **Phasor plot** tab at 80 MHz, harmonic 1. Yellow: reference lifetimes on
the semicircle (0.5–8 ns), with their iso-phase rays and iso-modulation arcs.
Red: the FRET trajectory of a 4 ns donor, running along the circle to $(1, 0)$.
Blue: the chord between a 0.6 ns (C1) and a 5 ns (C2) species. The red cross is
their 50:50 photon mixture, at $(0.527, 0.310)$, inside the orange gating cursor.
```

## Set it up

```{figure} figures/phasor_calculator_controls.png
:name: fig-phasor-calculator-controls
:width: 100%

The **Controls** tab in the same state, with **Results** expanded: the phasor
coordinates of each reference lifetime at the effective frequency.
```

**Frequency and harmonic**

* **Frequency** (MHz) — the laser repetition rate, or the modulation frequency
  of a frequency-domain instrument. For TCSPC use the real repetition rate, not
  the TAC window (see *Using it well*).
* **Harmonic** — $n$; everything is drawn at $n \times$ frequency. The
  effective frequency heads the **Results** table.

**Reference lifetimes**

* **Lifetimes (ns)** — comma-separated; semicolons also work. Tokens that are
  not numbers are dropped silently, and a field with no valid number falls back
  to 1 ns.
* **Iso-lifetime grid** — for each lifetime, the ray of constant phase lifetime
  $\tau_\varphi$ from the origin and the arc of constant modulation lifetime
  $\tau_M$ from the $g$ axis. They cross on the semicircle.
* **Lifetime ticks** — labelled markers on the semicircle.
* **Polar grid** — circles of modulation 1/3, 2/3, 1 and radial spokes, for
  reading $\varphi$ and $M$ directly.

**FRET**

* **FRET trajectory** and **Donor τ0** — the phasor of a single-exponential
  donor with $\tau_{DA} = \tau_{D0}(1 - E)$ for $E = 0 \dots 0.99$. It runs along
  the semicircle from $\tau_{D0}$ towards $(1, 0)$: this is the idealized case of
  a fully labelled, mono-exponential donor with a single distance. A donor-only
  fraction or background pulls real data off the circle towards those phasors
  ({ref}`concept-imaging-flim-phasor`, *Fit-free FLIM and FRET*).

**Two components**

* **Two-component line** — the chord between $(g_1, s_1)$ and $(g_2, s_2)$.
* **g1, s1, g2, s2** — the component phasors. To place a known lifetime, copy
  its $g, s$ from the **Results** table (set it in **Lifetimes** first).
* **Mixing region** and **Fraction c1** — the point
  $f_1 P_1 + (1 - f_1) P_2$ with lines to both components. $f_1$ is the
  **fractional intensity** (photon fraction) of component 1, not its amplitude.

**Cursor**

* **Cursor**, **Cursor g / s / radius** — a circular gate outline, the same
  shape the imaging plugin uses to select pixels. Here it only marks a region;
  there are no pixels to select.

## Read the result

The **Results** panel lists $g$ and $s$ for each reference lifetime at the
effective frequency. For the default 80 MHz: 0.5 ns → $(0.941, 0.236)$, 1 ns →
$(0.798, 0.401)$, 2 ns → $(0.497, 0.500)$ (the apex, $\omega\tau = 1$), 4 ns →
$(0.198, 0.399)$, 8 ns → $(0.058, 0.234)$.

The table does not report the apparent lifetimes of the mixture point or the
cursor centre (see *Known defects*); compute them headlessly. For the 50:50
mixture of 0.6 and 5 ns in the figure, $\tau_\varphi = 1.17$ ns and
$\tau_M = 2.58$ ns — both short of the 2.8 ns mean, and unequal, as a mixture's
always are.

Switching **Harmonic** to 2 moves every point: 0.6 ns goes from $(0.917, 0.276)$
to $(0.733, 0.442)$ and 5 ns from $(0.137, 0.344)$ to $(0.038, 0.191)$. Short
lifetimes spread away from $(1, 0)$, long ones crowd towards the origin.

## Where the numbers go

Nothing is written. The component phasors you set here are the inputs of the
imaging tool's unmixing and cursor steps (**Pixel Phasor**,
`chisurf/plugins/microscopy/img_pixel_phasor/`), and the same overlay geometry
is available to scripts through the `phasor.overlays` RPC method.

## Headless

The calculator is a thin view over
`chisurf.plugins.microscopy.img_pixel_phasor.analysis`; every overlay and number
comes from these functions:

```python
from chisurf.plugins.microscopy.img_pixel_phasor import analysis

f = 80.0                                   # MHz; for harmonic n use n * f
g1, s1 = analysis.lifetime_to_phasor(0.6, f)
g2, s2 = analysis.lifetime_to_phasor(5.0, f)
g, s = 0.5 * g1 + 0.5 * g2, 0.5 * s1 + 0.5 * s2     # 50:50 photon mixture
print(analysis.phasor_to_apparent_lifetime(g, s, f))          # (1.171, 2.577) ns
print(analysis.phasor_component_fraction(g, s, (g1, s1), (g2, s2)))   # 0.5
overlays = analysis.build_overlays(
    frequency_mhz=f, harmonic=1,
    sets=["semicircle", "lifetime_ticks", "fret", "component_line"],
    taus=[0.5, 1, 2, 4, 8], c1=(g1, s1), c2=(g2, s2), tau_d0=4.0,
)                                          # [{name, kind, x, y, style}, ...]
```

To put a **measured** decay on the plot, divide its phasor by the IRF's
(convolution becomes multiplication). On the repository's donor-only decay:

```python
import numpy as np

def ibh(name):
    return np.loadtxt(f"test/data/tcspc/ibh_sample/{name}", skiprows=9)[:, 1]

decay, irf = ibh("Decay_577D.txt"), ibh("Prompt.txt")
decay = decay - np.median(decay[:500])     # pre-rise background
irf = irf - np.median(irf[-800:])
t = np.arange(decay.size) * 0.0141         # ns
period = decay.size * 0.0141               # the window, as the period here
omega = 2 * np.pi / period

def phasor(y):
    return np.sum(y * np.exp(1j * omega * t)) / np.sum(y)

p = phasor(decay) / phasor(irf)            # g + i s, IRF-corrected
print(p.real, p.imag)                      # 0.832, 0.375
print(analysis.phasor_to_apparent_lifetime(p.real, p.imag, 1e3 / period))
# (4.148, 4.124) ns — a mono-exponential reconvolution fit gives 4.15 ns
```

The same division with the donor–acceptor decay
(`Decay_577D+577A+GTPgS.txt`) lands inside the circle, at $(0.875, 0.305)$,
$\tau_\varphi = 3.21$ ns and $\tau_M = 3.72$ ns. For per-pixel images and
streams the photon library computes the moments directly (`tttrlib.DecayPhasor`,
`CLSMImage.get_phasor`).

## Using it well

**Use the real repetition frequency.** The phasor of a TCSPC decay is only on the
semicircle when $\omega$ is $2\pi$ times the laser rate (or a harmonic of it) and
the decay has relaxed within one period. The headless example uses the TAC window
because this file records no laser rate, and that is only safe because the decay
is fully contained in the window.

**Pick the harmonic that spreads your lifetimes.** Aim for $n\omega\tau \approx 1$
for the lifetimes you want to separate: at 80 MHz that is 2 ns for $n = 1$ and
1 ns for $n = 2$.

**Mixtures are not on the FRET trajectory.** The drawn trajectory assumes every
donor is quenched to the same lifetime. A sample of FRET and donor-only
molecules lies on the chord between the donor-only point and the quenched
point, not on the circle.

**Components are photon fractions.** A fit's pre-exponential amplitudes $a_i$
become the fractions used here via $f_i = a_i\tau_i / \sum_j a_j\tau_j$.

## Known defects

* The **Results** panel is described as showing "apparent lifetimes and mixing
  fractions", but only lists the reference lifetimes' $g, s$. The mixture point
  and the cursor centre have no readout.
* The **Controls** tab flows fields two per row regardless of meaning, so
  **g1** sits beside **Two-component line** and **s1** starts the next row;
  each $(g, s)$ pair is split across rows.
* **Guide** is missing from the toolbar: the tool builds its own **❓** button
  and does not call the shared help/guide seam, so the shipped `guide.json` is
  not reachable from the window yet.

## See also

- Concept: {ref}`concept-imaging-flim-phasor`.
- Guide: {doc}`24_scan_images` for phasor maps of real CLSM data.
- Tool: `chisurf/plugins/calculator/phasor_calculator/`, reached through the
  Calculators hub; the geometry lives in
  `chisurf/plugins/microscopy/img_pixel_phasor/analysis.py`.
