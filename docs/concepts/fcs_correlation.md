---
type: Concept
title: 'FCS: the correlation curve and its models'
description: Fluorescence correlation spectroscopy (FCS) measures the temporal autocorrelation of fluorescence-intensity fluctuations as molecules diffuse through a small confocal detection volume.
tags: [concepts, fcs, correlation]
anchor: concept-fcs-correlation
---

(concept-fcs-correlation)=
# FCS: the correlation curve and its models

Fluorescence correlation spectroscopy (FCS) measures the **temporal
autocorrelation of fluorescence-intensity fluctuations** as molecules diffuse
through a small confocal detection volume. This page explains what a correlation
curve *is*, how ChiSurf's fit-model catalogue is built from independent physical
factors, and how the fit parameters map onto physical quantities.

For the step-by-step workflow in ChiSurf, see the guide
{doc}`/guides/09_diffusion_fcs`.

## What the correlation function is

Write the detected intensity as a mean plus a fluctuation,
$I(t) = \langle I\rangle + \delta I(t)$. The **normalized autocorrelation
function** asks how much a fluctuation at time $t$ still resembles the
fluctuation a lag $\tau$ later:

$$
G(\tau) = \frac{\langle \delta I(t)\,\delta I(t+\tau)\rangle}{\langle I\rangle^{2}}
        = \frac{\langle I(t)\,I(t+\tau)\rangle}{\langle I\rangle^{2}} - 1 .
$$

Two conventions are in circulation and differ by exactly one: the form above
decays to $0$, while $G(\tau) = \langle I(t)I(t+\tau)\rangle/\langle I\rangle^2$
plateaus at $1$. ChiSurf carries the offset as a fitted parameter ($G_\infty$,
`b`/`y_0`) precisely so either convention can be fitted without rescaling the
data — but it means you must know which one your correlator produced before
comparing amplitudes between programs.

The central result is that the **zero-lag amplitude counts molecules**. For a
Poisson-distributed number of independent particles in the volume,
$\langle\delta N^2\rangle = \langle N\rangle$, so

$$
G(0) = \frac{\langle \delta N^{2}\rangle}{\langle N\rangle^{2}} = \frac{1}{N} .
$$

This is why FCS is a *concentration* method and why it only works at low
occupancy: at $N = 1000$ the relative fluctuation is 3 %, and the correlation
amplitude vanishes into the noise. FCS wants $N \sim 0.1$–$10$, i.e. nanomolar
concentrations in a femtolitre volume — if a curve has almost no amplitude, the
sample is usually simply too concentrated.

Two practical consequences follow from $G$ being a *statistical* quantity:

- **Anything that adds uncorrelated photons lowers the amplitude** without
  changing its shape, so an uncorrected background makes $N$ too large and the
  brightness too low. Hence the $X_\text{back}$ factor below.
- **Anything correlated that is not the process of interest is
  indistinguishable by shape alone** — detector afterpulsing mimics fast
  photodynamics, and a slow drift mimics a slow diffusing component.

## The anatomy of a correlation curve

Every model in ChiSurf's catalogue
({src}`chisurf/core/models/fcs/models.yaml`) is a **product of independent factors**,
each describing a different physical process on a different timescale:

$$
G(\tau) = G_\infty \;+\; \frac{1}{N}\cdot X_\text{back}\cdot
\underbrace{P(\tau)}_{\text{photodynamics}}\cdot
\underbrace{D(\tau)}_{\text{diffusion}}
$$

- **$G_\infty$ (offset, `b` / `y_0`)** — the baseline as $\tau\to\infty$.
  Normalized ACFs plateau at $G_\infty=1$; background-subtracted curves at $0$.
- **$1/N$ (amplitude)** — the zero-lag amplitude is inversely proportional to the
  number of molecules $N$ in the volume. *Fewer molecules → larger fluctuations →
  higher $G(0)$.* This is the basis of concentration measurement by FCS.
- **$X_\text{back}$ (background correction)** — uncorrelated background photons
  dilute the amplitude by $X_\text{back} = (1-B/I)^2$ ($I$ total, $B$ background
  count rate); the `(1-BG/Counts)**2` factor in the `… + background` models.
- **$P(\tau)$ (photodynamics)** — fast blinking of a *single* molecule (triplet,
  protonation, antibunching): raises/dips the curve at short lag.
- **$D(\tau)$ (diffusion / transport)** — the slow decay from molecules leaving
  the volume by diffusion (plus optional flow, scanning, or a second focus).

Reading a model name is reading which $P$ and $D$ factors it switches on.

```{figure} figures/fcs_factors.png
:name: fig-fcs-factors
:width: 100%

**A correlation curve is a product, not a shape.** The diffusion factor alone ($\tau_D = 38$ µs, $\gamma = 5$), the photodynamics factor alone (an 18 % triplet at $\tau_\mathrm{trip} = 3$ µs), and the curve a correlator actually returns — their product, scaled by $1/N$ with $N = 2$. The two processes sit on separate timescales, which is what makes them separable; when they overlap the two factors trade against one another.
```

## The diffusion factor and the confocal Gaussian volume

The detection volume is approximated by a 3-D Gaussian with lateral $1/e^2$
half-axis $w_{xy}$ (ChiSurf `w_r`) and axial $w_z$; their ratio is the
**structure / aspect parameter** $\gamma = p = s = w_z/w_{xy}$ (the same quantity
appears as `s` in the legacy `3D Gauss` models and `p` in the PAM-derived ones).
For one freely diffusing 3-D species,

$$
g(\tau) = \left(1 + \frac{\tau}{\tau_D}\right)^{-1}
          \left(1 + \frac{1}{\gamma^2}\,\frac{\tau}{\tau_D}\right)^{-1/2}.
$$

### Two parameterizations of the same physics

The catalogue carries each core model twice:

- **Diffusion time $\tau_D$** (`… (tauD, …)`) — the mean residence time in the
  focus; model-intrinsic, needs no calibration, compares curves on one setup.
- **Absolute diffusion coefficient $D$** (`… (D, …)`) — the physical transport
  coefficient via $4D\tau/w_{xy}^2$; needs a *calibrated* $w_{xy}$ but yields a
  µm²/s value comparable across instruments.

They are linked by

$$
\boxed{\;\tau_D = \frac{w_{xy}^2}{4D}\;}
$$

Choose $\tau_D$ to compare curves on one setup; choose $D$ to report a transport
coefficient. Calibrate $w_{xy}$ from a reference dye of known $D$ via
$w_{xy}=\sqrt{4D\,\tau_D}$.

### Anomalous, 2-D and geometry variants

- **Anomalous** (`… anomalous`, `Abnormal diffusion`) replace $\tau/\tau_D$ with
  $(\tau/\tau_D)^{\alpha}$; $\alpha<1$ is sub-diffusion (crowding), $\alpha>1$
  super-diffusion. Inside a cell $\alpha<1$ is the rule rather than the
  exception — macromolecular crowding alone produces it {cite}`banks2005` — and
  $\alpha$ is not a constant of the sample: it depends on the length scale the
  measurement probes, so a single $\alpha$ fitted over one focal volume is a
  summary, not a transport coefficient {cite}`hofling2011`. *Caveat:* one
  anomalous component often fits as well as two normal components — distinguish
  them with orthogonal evidence, not $\chi^2$.
- **2-D membrane** models drop the axial factor.
- **Flow / two-focus / scanning** multiply in a transit-time, a known-distance
  cross-term (an internal ruler for absolute $D$; see
  {doc}`/guides/05_enderlein_mdf_two_focus_fcs`), or a periodic scan term.
  Moving the beam decouples the observation time from diffusion, which is what
  makes slow membrane dynamics measurable at all — a stationary focus would
  bleach the molecule before it left {cite}`ruan2004`. Scanning many foci in
  parallel turns the same idea into a spatial map {cite}`sisan2006`.

## The photodynamics factor

- **Triplet / blinking** (`… bunching`, `… triplet`) — a transiently dark
  fraction *bunches* photons, raising the curve at short lag:
  $\big(1+\tfrac{\Theta}{1-\Theta}e^{-\tau/\tau_\text{trip}}\big)$.
- **Anti-correlation** — a short-lag *dip* from reversible reaction/conformational
  exchange, relaxation time $\tau_R=(k_\text{on}+k_\text{off})^{-1}$.
- **Rotational depolarization** also fluctuates the detected signal, on the
  correlation time $\rho$ rather than $\tau_D$ {cite}`ehrenberg1974`. In a
  polarized ns-FCS measurement it appears as a further short-lag term, which is
  why an ns-FCS curve is read together with the anisotropy
  ({ref}`concept-anisotropy`) rather than alone.
- **Photon antibunching** (`ns-FCS`) — the quantum dip at ns lag; a single emitter
  cannot emit two photons at once {cite}`paul1982`. The depth of the dip counts
  emitters: $g^{(2)}(0) \approx 1 - 1/n$. Note that a dip at zero lag and
  sub-Poissonian counting statistics are related but not the same property, and
  a measurement of one is not a measurement of the other
  {cite}`zou1990`. See {doc}`/guides/06_nsfcs_second_order`.
- **Afterpulsing** — a detector artifact, modeled as an additive
  (stretched-)exponential; better removed upstream with an FLCS filter
  ({doc}`/guides/17_filtered_fcs`).

## Derived quantities

- **Effective volume** $V_\text{eff} = \pi^{3/2}\gamma\,w_{xy}^3$.
- **Concentration** $c = N/(N_A V_\text{eff})$.
- **Molecular brightness (cpm)** $= (I-B)/N$ — rises with oligomerization; the
  observable behind Number & Brightness.

### A worked calibration

Take a reference dye of known diffusion coefficient — Rhodamine 6G, whose
$D \approx 4.1\times10^{2}\,\text{µm}^2/\text{s}$ at 25 °C — and suppose the
fitted diffusion time is $\tau_D = 38\,\text{µs}$ with a structure parameter
$\gamma = 5$. Then

$$
w_{xy} = \sqrt{4 D \tau_D}
       = \sqrt{4 \times 410\,\text{µm}^2\text{/s} \times 38\times10^{-6}\,\text{s}}
       \approx 0.25\,\text{µm},
$$

so $w_z = \gamma w_{xy} \approx 1.25\,\text{µm}$ and

$$
V_\text{eff} = \pi^{3/2}\,\gamma\,w_{xy}^{3}
             \approx 5.57 \times 5 \times 0.0156\,\text{µm}^3
             \approx 0.43\,\text{µm}^3 \approx 0.43\,\text{fL}.
$$

A fitted $N = 2.0$ in that volume is
$c = N/(N_A V_\text{eff}) \approx 2.0/(6.022\times10^{23} \times 4.3\times10^{-16}\,\text{L})
\approx 7.7\,\text{nM}$. Every later measurement on the same setup reuses this
$w_{xy}$, which is why the calibration must be repeated whenever the alignment,
objective correction collar, or refractive index of the buffer changes.

### Where the reference $D$ comes from

Diffusion is a property of the species, not of the experiment, so ChiSurf keeps
no private dye table: $D(25\,°\text{C}, \text{water})$ is stored in the
metadata database next to the dye's quantum yield and extinction coefficient
(the `d25` probe property, in µm²/s, with its literature citation). The FCS
diffusion/volume calculator and the dye-volume model read the list from there,
and the values are curated in the **MMFDB admin** tool (*Spectra* →
*Fluorophores* → **D₂₅**), so correcting a coefficient once corrects it
everywhere. The shipped set covers the common calibration dyes (rhodamines,
fluorescein, Oregon Green, ATTO, Alexa, Cy5 — mostly from the PicoQuant
absolute-diffusion compilation) plus BSA, sucrose and RNase A.

Values are tabulated at 25 °C; at the measurement temperature they are scaled
with $D \propto T/\eta(T)$, so record the sample temperature and the buffer
viscosity rather than reusing the tabulated number directly.

## Assumptions, and when they break

The 3-D Gaussian model is a convenient approximation, not the true confocal
detection profile — the real one follows from the excitation point-spread
function and the pinhole, and departs from a Gaussian most where it matters
least for $G(0)$ and most for $\tau_D$ {cite}`qian1991`. Watch for:

- **Wrong structure parameter.** $\gamma$ is strongly correlated with $\tau_D$
  and is poorly determined by the fit itself. Fix it from a dye calibration
  rather than floating it, or the diffusion time absorbs the error.
- **Photobleaching** shortens the apparent transit time — a "faster" diffusing
  species that gets faster still as you raise the laser power is bleaching, not
  diffusing. Check for power dependence.
- **Optical saturation and aberrations** distort the volume away from Gaussian;
  the fitted $N$ then no longer converts to a true concentration. Refractive-index
  mismatch (a coverslip-corrected objective used dry, or deep imaging) is the
  usual cause {cite}`hess2002`. Saturation acts in the same direction as
  bleaching — it flattens the centre of the profile, widening the effective
  volume and lengthening the apparent $\tau_D$ — so a power series is the test
  for both {cite}`loman2008`. Two-focus FCS is comparatively robust here, because
  the known separation of the two volumes fixes the length scale even when their
  shape is wrong {cite}`muellercb2008`.
- **Two components need to be well separated before a fit can see them.** Two
  species resolve only when their diffusion times differ by roughly a factor of
  1.6, and even then only at high signal — which, since $\tau_D \propto D^{-1}$
  and $D \propto M^{-1/3}$, means a mass ratio of about four. A fit that
  cheerfully returns two components from a monomer/dimer mixture is reporting the
  starting values, not the sample {cite}`meseth1999`.
- **Too few molecules is also a failure mode.** At very low $N$, rare bright
  events dominate and the curve needs impractically long acquisition to converge.
- **A slowly drifting baseline** (aggregates, focus drift, evaporation) adds
  correlation at long lag that is easily mistaken for a large slow component.
- **Triplet and diffusion must be separated in time.** The triplet term is only
  reliably resolved when $\tau_\text{trip} \ll \tau_D$; if they overlap, the two
  factors trade against one another.

More generally, remember the caveat noted above for anomalous diffusion: FCS
curves are smooth and featureless, so **several physically different models fit
one curve about equally well**. Distinguishing them needs orthogonal evidence —
a concentration series, a viscosity or temperature series, two-focus FCS for an
absolute $D$, or a lifetime/anisotropy measurement — not a marginally better
$\chi^2$.

## References

- {cite}`magde1972` — the original FCS experiment, a chemical relaxation read
  out of intensity fluctuations.
- {cite}`magde1974` — its experimental companion: the correlator, the focal
  geometry and the diffusion fit in the form still used.
- {cite}`elson1974` — the theory: what $G(\tau)$ is and why its amplitude
  counts molecules.
- {cite}`rigler1993` — confocal FCS as it is practised now, and the diffusion
  model fitted above.
- {cite}`widengren1995` — the triplet term, measured and separated from
  diffusion.
- {cite}`schwille1999` — dual-colour cross-correlation, the extension to
  binding.
- {cite}`haustein2007` — a review to read before choosing a model: the
  variations, and what each assumes.
- {cite}`krichevsky2002` — a longer review of the same ground, with the model
  derivations written out.
- {cite}`meseth1999` — how far apart two components must be before a fit can
  resolve them.
- {cite}`hess2002` — the focal volume treated as an optical system: which
  aberrations bias $G(0)$ and which bias $\tau_D$.

## See also

- Fundamentals: {ref}`fundamentals-quenching` (the triplet term) ·
  {ref}`fundamentals-instrumentation` (afterpulsing, and why two detectors).
- Guide: {doc}`/guides/09_diffusion_fcs` · two-focus & absolute volume:
  {doc}`/guides/05_enderlein_mdf_two_focus_fcs` · filtered FCS:
  {doc}`/guides/17_filtered_fcs`.
- Model catalogue: {src}`chisurf/core/models/fcs/models.yaml`; correlator plugin
  `chisurf/plugins/fcs/fcs_correlator/`.
- Tools in ChiSurf: the **Diffusion/Volume Calculator** (`chisurf/plugins/fcs/fcs_calculator/`) converts between $\tau_D$, $D$, $r_h$ and a concentration; **FCS-Merger** (`chisurf/plugins/fcs/fcs_merger/`) averages repeats; **Burst-wise FCS** (`chisurf/plugins/burst/burst_fcs_correlator/`) correlates inside bursts.
