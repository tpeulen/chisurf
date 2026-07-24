(concept-fcs-correlation)=
# FCS: the correlation curve and its models

Fluorescence correlation spectroscopy (FCS) measures the **temporal
autocorrelation of fluorescence-intensity fluctuations** as molecules diffuse
through a small confocal detection volume. This page explains what a correlation
curve *is*, how ChiSurf's fit-model catalogue is built from independent physical
factors, and how the fit parameters map onto physical quantities.

For the step-by-step workflow in ChiSurf, see the guide
{doc}`/guides/09_diffusion_fcs`. The theory here is the user-facing rendering of
the maintained OKF concept `okf/references/fcs-model-theory.md`.

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

## See also

- Guide: {doc}`/guides/09_diffusion_fcs` · two-focus & absolute volume:
  {doc}`/guides/05_enderlein_mdf_two_focus_fcs` · filtered FCS:
  {doc}`/guides/17_filtered_fcs`.
- Model catalogue: `chisurf/core/models/fcs/models.yaml`; correlator plugin
  `chisurf/plugins/fcs/fcs_correlator/`.
- OKF concepts: `okf/references/fcs-model-theory.md`, `fcs-pam-port.md`,
  `two-focus-fcs.md`.
