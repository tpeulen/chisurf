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
{doc}`/guides/09_diffusion_fcs`; correlating a photon file directly is
{doc}`/guides/73_tttr_decay_and_correlation`.

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

(concept-fcs-photon-correlation)=
## Correlating photon time tags

A TTTR file holds no intensity trace to correlate, only arrival times
$t^{(1)}_i$ and $t^{(2)}_j$ in two channels (the same channel for an
autocorrelation). The correlator counts photon pairs whose separation falls in
lag bin $k$, $[\tau_k, \tau_k+\Delta\tau_k)$,

$$
n_k = \sum_{i,j} w^{(1)}_i\, w^{(2)}_j\;
      \mathbb{1}\!\left[\tau_k \le t^{(2)}_j - t^{(1)}_i < \tau_k + \Delta\tau_k\right],
$$

with photon weights $w$ (all one for plain FCS), and normalizes by the pairs
uncorrelated photons would give:

$$
G(\tau_k) = \frac{n_k}{r_1\, r_2\, \Delta\tau_k\, (T - \tau_k)},
\qquad r_c = N_c / T .
$$

$T-\tau_k$ is the stretch of the measurement over which a pair at that lag can
occur. This $G$ plateaus at **1**, the convention with $G_\infty = 1$ above.

- **Multiple-tau binning.** The lag axis is $n_\text{casc}$ cascades of $B$
  equal bins; each cascade doubles the bin width. Between cascades the time tags
  are halved (integer division), and photons that fall on the same coarse tag are
  merged by adding their weights, so every cascade costs about the same
  {cite}`wahl2003`. The longest lag is roughly $B\,2^{\,n_\text{casc}}$ clock
  ticks, and the relative lag resolution is constant on a logarithmic axis
  (this is tttrlib's `wahl` method).
- **Arbitrary bins.** Counting pairs directly against a sorted list of lag edges
  gives any bin layout at comparable speed {cite}`laurence2006` (`laurence`).
  Its normalization is *symmetric*: the rates $r_1$, $r_2$ are taken only over
  the photons that can have a partner at that lag (channel 1 before
  $T_\text{end}-\tau$, channel 2 after $T_0+\tau$), which removes the long-lag
  upturn a slowly decaying intensity produces with the global rates
  {cite}`schatzel1990`.
- **Macro plus micro time.** Replacing each macro time by
  $t = t_\text{macro}\, n_\text{TAC} + \mu$ makes the clock one TAC channel
  wide, so one curve spans picoseconds (antibunching, rotation) to seconds
  {cite}`felekyan2005` (`felekyan`, and **Fine** in **TTTR: Correlate**). It
  needs the macro clock to be the laser period, and $n_\text{casc}$ must grow by
  $\log_2 n_\text{TAC}$ to reach the same longest lag.
- **Weights are filters.** Non-unit weights give time-gated FCS (weight 1 inside
  a micro-time window, 0 outside) and lifetime- or species-filtered FCS
  {cite}`boehmer2002,kapusta2007,felekyan2012`; see
  {ref}`concept-filtered-fcs`.

### Afterpulsing and dead time: cross-correlate two detectors

A single detector adds two artefacts of its own. An **afterpulse** is a second,
spurious count a few hundred nanoseconds to microseconds after a real one; it is
correlated with that photon, so the autocorrelation gains an additive term at
exactly the lags of triplet blinking. **Dead time** removes pairs closer than
$t_d$, a hole in $G(\tau)$ at $\tau < t_d$
({ref}`fundamentals-photon-counting`).

Splitting the fluorescence 50/50 onto two detectors and **cross-correlating**
them removes both, because one detector's afterpulses and dead time are
uncorrelated with the other's photons. For identical detection volumes the
cross-correlation equals the true autocorrelation; this split-beam arrangement
is that of {cite}`hanburybrown1956`. The price is half the photons per channel,
not a smaller amplitude. Where only one detector is available, the afterpulse
term can be measured and subtracted {cite}`zhao2003`, or filtered out using the
micro time — afterpulses are flat in micro time, unlike fluorescence
{cite}`enderlein2005afterpulsing`.

### Error bars

$G$ at each lag is an average over photon pairs, so its noise depends on the
measurement time, the count rate, $N$ and the bin width; long lags, with wide
bins, are better determined than short ones. {cite}`koppel1974` gives the
standard deviation for a Gaussian volume; the multiple-tau correlator's own
noise is analysed in {cite}`schatzel1990`. **TTTR: Correlate** cuts the
measurement into equal-time **splits**, correlates each, averages them, and
takes the error bar from the Koppel-type model evaluated for one split's
duration and count rate (`w.res = Koppel`; `none` gives uniform weights). The
scatter between splits is the model-free check: a split that disagrees with the
rest is an aggregate, a bleaching step or a focus drift. The three ways of
getting $\sigma$ are compared in {ref}`concept-fcs-error-bars`.

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

The detection volume is a **confocal PSF** — the point-spread function of a
focused excitation spot observed through a pinhole — and is only approximated
by a 3-D Gaussian with lateral $1/e^2$
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

(concept-fcs-error-bars)=
## Error bars on a measured curve

This expands the short *Error bars* note under
{ref}`concept-fcs-photon-correlation`. A fit minimizes $\chi^2 = \sum_i w_i^2\,[G_i - G_\text{model}(\tau_i)]^2$ with
$w_i = 1/\sigma_i$ — ChiSurf stores the weight, not the variance
(`correlation_amplitude_weights`, the inverse of the `ey` column). Without
$\sigma_i$ the short-lag points, which are noisy by orders of magnitude more
than the tail, decide the fit. The weights are only approximately right in any
case: neighbouring multi-tau channels share photons, so their errors are
correlated and a diagonal $\chi^2$ is not a true likelihood
{cite}`schatzel1990`.

There are three ways to get $\sigma_i$, in order of trust.

**From repeats.** Split the measurement into $n$ chunks (or record $n$
measurements), correlate each, and take the standard error of the mean,

$$
\bar G(\tau) = \frac{1}{n}\sum_{k=1}^{n} G_k(\tau), \qquad
\sigma(\tau) = \frac{s_G(\tau)}{\sqrt{n}},
$$

with $s_G$ the sample standard deviation across chunks. Averaging independent
measurements gives the most accurate $\sigma$ {cite}`wohland2001`; its cost is
that a chunk must be long compared with $\tau_D$ and the slowest process, or the
long-lag points of every chunk are poorly sampled. The acquisition times of the
chunks add, and the count rate is their duration-weighted mean. The chunks are
also the place to reject what the photon statistics cannot see — an aggregate
passing the focus spoils one chunk, not the average of ten. Where the chunks
happen to agree exactly (common at long lags) $s_G = 0$; a zero $\sigma$ inverts
into an infinite weight, so such points are completed from the model below.

**From photon statistics.** For a curve with amplitude $G_0$ decaying roughly
exponentially, Koppel's result gives the variance of the point at lag
$\tau = m\,\Delta\tau$ measured with lag-channel width $\Delta\tau$ over an
acquisition $T$ {cite}`koppel1974`:

$$
\sigma^2(\tau) = \frac{1}{M}\left\{ G_0^2\left[\frac{(1+q^2)(1+q^{2m})}{1-q^2}
 + 2m\,q^{2m}\right] + \frac{2G_0\,(1+q^{2m})}{\langle n\rangle}
 + \frac{1+G_0\,q^{m}}{\langle n\rangle^{2}}\right\},
$$

with $M = T/\Delta\tau$ samples, $\langle n\rangle = I\,\Delta\tau$ the mean
counts per channel at count rate $I$, and $q = e^{-\Delta\tau/\tau_D}$ (the curve
approximated by $G_0 e^{-2\tau/\tau_D}$). The three terms are the intrinsic
fluctuation of the particle number, shot noise times signal, and pure shot
noise. Two consequences worth knowing: at the low occupancies FCS uses, the
signal-to-noise ratio is set by the counts per molecule per channel, not by the
concentration {cite}`koppel1974,qian1990c`; and at lags approaching the chunk
length a further *particle noise* — too few molecules entered and left during
the dwell — takes over {cite}`saffarian2003`. The formula needs $T$ and $I$,
which is why ChiSurf's `.cor` files carry both in their third column.

**From the curve itself.** Without repeats or acquisition metadata, the local
scatter of the curve about a smooth spline on a log-lag axis estimates $\sigma$
{cite}`mueller2014`; empirical models with correlator-specific constants are
the alternative {cite}`starchev2001`. Both are last resorts: a spline cannot
tell noise from a real fast process.

Two conventions matter when curves change hands. The offset question — $G$
plateauing at $1$ or at $0$ — is the one discussed at the top of this page, and
file formats differ on it. And a stored uncertainty column may be a standard
error of the mean over repeats, a model $\sigma$, or absent; a reader that finds
none has to fall back to a model, so the numbers in a fit report depend on which
it was.

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

- {cite}`wahl2003`, {cite}`laurence2006`, {cite}`felekyan2005` — the three
  time-tag correlators tttrlib implements (multiple-tau, arbitrary bins, macro
  plus micro time).

- {cite}`sheppard1977` — the theoretical foundation of confocal image formation; the PSF that FCS measures in.
- {cite}`koppel1974` — the variance of a measured curve from counting
  statistics; {cite}`wohland2001` — which way of estimating it to trust.

## See also

- Fundamentals: {ref}`fundamentals-quenching` (the triplet term) ·
  {ref}`fundamentals-instrumentation` (afterpulsing, and why two detectors).
- Guide: {doc}`/guides/09_diffusion_fcs` · photon-file correlation:
  {doc}`/guides/73_tttr_decay_and_correlation` · two-focus & absolute volume:
  {doc}`/guides/05_enderlein_mdf_two_focus_fcs` · filtered FCS:
  {doc}`/guides/17_filtered_fcs` · correlating, merging and converting
  curves: {doc}`/guides/75_fcs_toolbox`.
- Model catalogue: {src}`chisurf/core/models/fcs/models.yaml`; correlator plugin
  `chisurf/plugins/fcs/fcs_correlator/`.
- Tools in ChiSurf: the **Diffusion/Volume Calculator** (`chisurf/plugins/fcs/fcs_calculator/`) converts between $\tau_D$, $D$, $r_h$ and a concentration; **FCS-Merger** (`chisurf/plugins/fcs/fcs_merger/`) averages repeats; **Burst-wise FCS** (`chisurf/plugins/burst/burst_fcs_correlator/`) correlates inside bursts.
