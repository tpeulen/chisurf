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
(`chisurf/core/models/fcs/models.yaml`) is a **product of independent factors**,
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
  super-diffusion. *Caveat:* one anomalous component often fits as well as two
  normal components — distinguish them with orthogonal evidence, not $\chi^2$.
- **2-D membrane** models drop the axial factor.
- **Flow / two-focus / scanning** multiply in a transit-time, a known-distance
  cross-term (an internal ruler for absolute $D$; see
  {doc}`/guides/05_enderlein_mdf_two_focus_fcs`), or a periodic scan term.

## The photodynamics factor

- **Triplet / blinking** (`… bunching`, `… triplet`) — a transiently dark
  fraction *bunches* photons, raising the curve at short lag:
  $\big(1+\tfrac{\Theta}{1-\Theta}e^{-\tau/\tau_\text{trip}}\big)$.
- **Anti-correlation** — a short-lag *dip* from reversible reaction/conformational
  exchange, relaxation time $\tau_R=(k_\text{on}+k_\text{off})^{-1}$.
- **Photon antibunching** (`ns-FCS`) — the quantum dip at ns lag; a single emitter
  cannot emit two photons at once. See {doc}`/guides/06_nsfcs_second_order`.
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

## Assumptions, and when they break

The 3-D Gaussian model is a convenient approximation, not the true confocal
detection profile. Watch for:

- **Wrong structure parameter.** $\gamma$ is strongly correlated with $\tau_D$
  and is poorly determined by the fit itself. Fix it from a dye calibration
  rather than floating it, or the diffusion time absorbs the error.
- **Photobleaching** shortens the apparent transit time — a "faster" diffusing
  species that gets faster still as you raise the laser power is bleaching, not
  diffusing. Check for power dependence.
- **Optical saturation and aberrations** distort the volume away from Gaussian;
  the fitted $N$ then no longer converts to a true concentration. Refractive-index
  mismatch (a coverslip-corrected objective used dry, or deep imaging) is the
  usual cause.
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

- D. Magde, E. L. Elson and W. W. Webb, "Thermodynamic fluctuations in a reacting
  system — measurement by fluorescence correlation spectroscopy", *Physical
  Review Letters* (1972). *The original FCS experiment.*
- E. L. Elson and D. Magde, "Fluorescence correlation spectroscopy. I.
  Conceptual basis and theory", *Biopolymers* (1974). *Where the correlation
  formalism used here is set out.*
- R. Rigler, Ü. Mets, J. Widengren and P. Kask, "Fluorescence correlation
  spectroscopy with high count rate and low background: analysis of translational
  diffusion", *European Biophysics Journal* (1993). *The confocal, single-molecule
  sensitive form of the experiment.*
- J. Widengren, Ü. Mets and R. Rigler, "Fluorescence correlation spectroscopy of
  triplet states in solution: a theoretical and experimental study", *Journal of
  Physical Chemistry* (1995). *The triplet/bunching factor.*
- P. Schwille, J. Korlach and W. W. Webb, "Fluorescence correlation spectroscopy
  with single-molecule sensitivity on cell and model membranes", *Cytometry*
  (1999). *2-D membrane diffusion.*
- E. Haustein and P. Schwille, "Fluorescence correlation spectroscopy: novel
  variations of an established technique", *Annual Review of Biophysics and
  Biomolecular Structure* (2007). *A readable survey of the model variants.*

## See also

- Guide: {doc}`/guides/09_diffusion_fcs` · two-focus & absolute volume:
  {doc}`/guides/05_enderlein_mdf_two_focus_fcs` · filtered FCS:
  {doc}`/guides/17_filtered_fcs`.
- Model catalogue: `chisurf/core/models/fcs/models.yaml`; correlator plugin
  `chisurf/plugins/fcs/fcs_correlator/`.
