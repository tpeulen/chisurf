---
type: Reference
title: "FCS model theory — reading the correlation-function catalogue"
description: The physics behind ChiSurf's FCS fit-model catalogue — the G(τ) decomposition, the confocal Gaussian MDF, the two diffusion parameterizations, the triplet/bunching/anti-bunching/flow/two-focus factors, and the derived quantities (Veff, concentration, cpm, focus calibration). Pedagogy and terminology drawn from QuickFit3's help.
tags: [reference, fcs, diffusion, models, pedagogy]
timestamp: '2026-07-24T00:00:00Z'
---

# FCS model theory — reading the correlation-function catalogue

ChiSurf's FCS fit-model catalogue (`chisurf/core/models/fcs/models.yaml` plus the
composable model in `chisurf/core/models/fcs/general.py`) is large — dozens of
diffusion × photodynamics combinations. The names (`3D Gauss, 2 bunching`,
`3D diffusion + afterpulsing (D, triplet)`, …) only make sense once the shared
skeleton of a fluorescence-correlation curve is understood. This concept is the
**science/pedagogy layer** for that catalogue: what each factor in
$G(\tau)$ means, why the same physics appears under two parameterizations, and
how the fit parameters map to physical quantities.

It complements — does **not** duplicate — the two adjacent references:
[fcs-pam-port.md](fcs-pam-port.md) records *port status* (which models exist,
A/B-verified against PAM) and [quickfit3-mining.md](quickfit3-mining.md) records
the *forward roadmap* (TIRF/SPIM/imaging gaps). This one explains the models
that are already there.

The pedagogy, terminology, and formula structure follow QuickFit3's help system
(Krieger & Langowski, DKFZ B040; `junk/quickfit3/plugins/fcs_fitfuctions/help/`,
`fcsfit/help/`), used as **documented prior art** — the same footing as PAM in
[fcs-pam-port.md](fcs-pam-port.md). QuickFit3 is written for the identical
audience (biophysicists fitting FCS/imaging data), so its exposition transfers
directly. Formulas are reimplemented independently in ChiSurf; nothing is a
verbatim code copy.

## The anatomy of a correlation curve

Every model in the catalogue is a product of independent factors, each a
different physical process acting on a different timescale:

$$
G(\tau) = G_\infty \;+\; \frac{1}{N}\cdot X_\text{back}\cdot
\underbrace{P(\tau)}_{\text{photodynamics}}\cdot
\underbrace{D(\tau)}_{\text{diffusion}}
$$

- **$G_\infty$ (offset, `b` / `y_0`)** — the correlation baseline as
  $\tau\to\infty$. Normalized ACFs (e.g. Kristine-format data) plateau at
  $G_\infty=1$, not $0$; background-subtracted curves plateau at $0$. ChiSurf's
  composable model defaults `b=1` for exactly this reason.
- **$1/N$ (amplitude)** — the zero-lag correlation amplitude is inversely
  proportional to the number of molecules $N$ in the effective volume. This is
  the whole basis of concentration measurement by FCS: *fewer molecules → bigger
  fluctuations → higher $G(0)$*.
- **$X_\text{back}$ (background correction)** — uncorrelated background photons
  (dark counts, buffer scatter) dilute the fluctuation amplitude without
  changing its shape. The standard correction scales the amplitude by
  $X_\text{back} = (I-B)^2/I^2 = (1-B/I)^2$, with $I$ the total and $B$ the
  background count rate. In the catalogue this is the `(1-BG/Counts)**2` factor
  (the `… + background` models).
- **$P(\tau)$ (photodynamics)** — fast processes that make a *single* molecule
  blink between bright and dark: triplet crossing, protonation, isomerization,
  antibunching. These raise or dip the curve at short lag but leave the
  diffusion shoulder untouched.
- **$D(\tau)$ (diffusion / transport)** — the slow decay from molecules leaving
  the detection volume by diffusion (and optionally flow, scanning, or a second
  focus).

Reading a model name is just reading which $P$ and $D$ factors it switches on.

## The diffusion factor and the confocal Gaussian MDF

The detection volume — the molecular detection function (MDF) — is approximated
by a 3-D Gaussian with lateral $1/e^2$ half-axis $w_{xy}$ (ChiSurf: `w_r`) and
axial half-axis $w_z$. Their ratio is the **structure / aspect parameter**

$$
\gamma \;=\; p \;=\; s \;=\; \frac{w_z}{w_{xy}},
$$

which appears in the catalogue variously as `s` (legacy `3D Gauss` family) or
`p` (PAM-derived family) — the same quantity under different letters. For one
freely diffusing 3-D species:

$$
g(\tau) = \left(1 + \frac{\tau}{\tau_D}\right)^{-1}
          \left(1 + \frac{1}{\gamma^2}\,\frac{\tau}{\tau_D}\right)^{-1/2}.
$$

The two factors are the lateral and axial escape; the axial term is weaker
(exponent $-1/2$) and $\gamma$-suppressed because the volume is elongated along
the optical axis.

### Two parameterizations of the same physics

The catalogue carries each core model twice because two communities parameterize
the shoulder differently:

- **Diffusion time $\tau_D$** (`… (tauD, …)` models) — the mean residence time
  in the focus. Model-intrinsic, needs no focus calibration, directly
  comparable between curves on the same instrument. Here $\tau/\tau_D$ replaces
  $4D\tau/w_{xy}^2$.
- **Absolute diffusion coefficient $D$** (`… (D, …)` models) — the physical
  transport coefficient, via $4D\tau/w_{xy}^2$. Requires a *calibrated* $w_{xy}$
  (see below) but yields a µm²/s number comparable across instruments and to
  the literature.

They are linked by

$$
\boxed{\;\tau_D = \frac{w_{xy}^2}{4D}\;}
$$

so absolute-$D$ models need a known $w_{xy}$; $\tau_D$ models do not. Choose
$\tau_D$ when you only compare curves on one setup; choose $D$ when you report a
transport coefficient. (For 2-D membrane models the axial factor drops out and
$\tau_D = w_{xy}^2/(4D)$ still holds in-plane.)

### Anomalous diffusion

`… anomalous …` / `Abnormal diffusion` models replace $\tau/\tau_D$ with
$(\tau/\tau_D)^{\alpha}$. The **anomaly exponent** $\alpha$ classifies transport:
$\alpha=1$ is Brownian, $\alpha<1$ sub-diffusion (crowding, obstacles, transient
trapping — common in membranes and cytoplasm), $\alpha>1$ super-diffusion
(active/directed transport).

> **Pedagogical caveat (from QuickFit3):** a measured curve can often be fit
> *equally well* by one anomalous component **or** by two normal-diffusion
> components. Anomaly and heterogeneity are partially degenerate; distinguishing
> them needs orthogonal evidence (concentration series, a diffusion-law plot),
> not goodness-of-fit alone.

### Dimensionality and geometry

- **2-D (`Simple 2D diffusion`, membrane models)** — drop the axial factor:
  $g(\tau)=(1+\tau/\tau_D)^{-1}$. For lipid bilayers, supported membranes,
  adsorbed species.
- **Flow (`… + flow`)** — multiply by
  $\exp\!\big[-(\tau v/w_{xy})^2/(1+4D\tau/w_{xy}^2)\big]$; the flow speed $v$
  adds a Gaussian cutoff at the transit time $w_{xy}/v$.
- **Two-focus (`Two-focus 3D diffusion`)** — the cross-term
  $\exp\!\big[-d^2/(w_{xy}^2+4D\tau)\big]$ encodes a *known* focus separation
  $d$ (`diam`), turning that distance into an internal ruler and making $D$
  absolute *without* a $w_{xy}$ calibration. Set $d=0$ to recover the
  single-focus auto-correlation. See [two-focus-fcs.md](two-focus-fcs.md) for
  the Gaussian-vs-Dertinger-MDF status.
- **Scanning (`Scanning FCS`)** — a periodic $\sin^2(\pi f \tau)$ term in the
  cross-term encodes a circular scan of frequency $f$; the scan radius plays the
  role of the two-focus ruler.

## The photodynamics factor

These act on a single molecule, on timescales below the diffusion shoulder.

- **Triplet / blinking (`… bunching`, `… triplet`)** — a fraction of molecules
  is transiently dark (triplet, protonation). This *bunches* photons (bright
  runs cluster), raising the curve at short lag:
  $\big(1 + \frac{\Theta}{1-\Theta}e^{-\tau/\tau_\text{trip}}\big)$ in the PAM
  form, or the equivalent normalized $(1-\Theta+\Theta e^{-\tau/\tau_b})$ in the
  legacy `3D Gauss` form. Multiple relaxations (`2 bunching`, `3 bunching`, …)
  stack independent dark states. In ChiSurf's composable model, added terms
  default to **decade-spaced** time constants (1, 10, 100 µs …) so they start
  usefully separated rather than degenerate.
- **Anti-correlation (`… anticorrelation`)** — a *dip* at short lag from
  reversible reaction/conformational exchange that anti-correlates two states
  (e.g. FRET high/low). Amplitude $-aR\,e^{-\tau/\tau_R}$; the relaxation time
  is $\tau_R = (k_\text{on}+k_\text{off})^{-1}$ and the amplitude carries the
  equilibrium constant.
- **Photon antibunching (`… antibunching`, `ns-FCS`)** — the quantum dip at
  nanosecond lag: a single emitter cannot emit two photons at once, so
  $G(\tau)\to 0$ as $\tau\to 0$. Factor $(1-A_\text{ab}e^{-\tau/\tau_\text{ab}})$
  about $\tau_0$. Reports the excited-state lifetime and the number of
  independent emitters. `Full FCS` models span all three regimes at once
  (antibunching ns → bunching µs → diffusion ms).
- **Afterpulsing (`… + afterpulsing`)** — a detector artifact (a photon
  triggers a spurious second count), not molecular. Modeled as an *additive*
  (stretched-)exponential $A_\text{ap}e^{-(\tau/\tau_\text{ap})^\beta}$ tail at
  short lag. The rigorous alternative is to remove it upstream with an FLCS
  uniform-pattern filter — see [fcs-pam-port.md](fcs-pam-port.md).
- **Bleaching (`… + bleaching`)** — photobleaching during acquisition adds a
  slow amplitude decay $(1-AB+AB\,e^{-\tau/\tau_B})$; a measurement artifact to
  correct, not a molecular observable.

## Derived quantities and calibration

FCS fits yield $N$, $\tau_D$ (or $D$), $w_{xy}$, $\gamma$; the physically
interesting numbers are derived from them. ChiSurf's composable model exposes
several as read-only outputs.

- **Effective volume** — $V_\text{eff} = \pi^{3/2}\,\gamma\,w_{xy}^3$
  (equivalently $\pi^{3/2} w_{xy}^2 w_z$). The $\gamma=1/\sqrt{8}$-type
  prefactors in the PAM models fold this normalization into $G(0)$.
- **Concentration** — $c = N/(N_A V_\text{eff})$ with Avogadro's
  $N_A = 6.022\times10^{23}$; gives nM directly from $N$ and the calibrated
  volume.
- **Counts per molecule (molecular brightness)** —
  $\text{cpm} = (I-B)/N$, the background-corrected count rate per molecule
  (kHz/molecule). A key quality/aggregation readout: brightness rises with
  oligomerization and is the observable behind Number & Brightness. ChiSurf's
  `compute_brightness` returns $(CR_\text{total}-\text{bg})/N$.

### Focus calibration — turning $\tau_D$ into $D$

One-focus FCS has no intrinsic ruler, so $w_{xy}$ must be calibrated against a
reference before absolute $D$ (or concentration) is meaningful. Measure a dye of
**known $D$** (or known concentration), fit a plain normal-diffusion model, then
invert:

- from a known $D$: $\;w_{xy} = \sqrt{4D\,\tau_D}\;$ (using the fitted $\tau_D$);
- from a known concentration: solve $c = N/(N_A\,\pi^{3/2}\gamma w_{xy}^3)$ for
  $w_{xy}$ (using fitted $N$ and $\gamma$).

Common calibration dyes (QuickFit3's table; diffusion coefficients in µm²/s at
~22.5 °C in water unless noted):

| Dye | $D$ [µm²/s] | Notes |
|---|---|---|
| Alexa-488 | 435 | 585 at 37 °C |
| Alexa-546 | 341 | |
| Rhodamine 6G | 426 | |
| Fluorescein | 436 | |
| EGFP | 95 | in phosphate-citrate buffer, pH 7.5 |

(Refs: Dross et al. 2009, PLoS ONE 4:e5041; Petrášek & Schwille 2008, Biophys J
94:1437.) The two-focus and scanning models sidestep this calibration entirely
by supplying their own distance ruler.

### The diffusion-law plot (outlook)

Beyond single fits, plotting $\tau_D$ against effective area $A_\text{eff}$
across a range of focus/pixel sizes — the **FCS diffusion law**
(Wawrezinieck et al. 2005) — classifies membrane organization from the intercept
$\tau_0$: $\tau_0\approx 0$ is free diffusion, $\tau_0>0$ indicates domains/
partitioning, $\tau_0<0$ meshwork/hop diffusion. For a Gaussian focus
$A_\text{eff}=w_{xy}^2$; for camera-based imaging FCS it carries an $\mathrm{erf}$
pixel-size correction. ChiSurf has no diffusion-law tool yet; it is the natural
companion to the imaging-FCS correlator tracked in
[quickfit3-mining.md](quickfit3-mining.md).

## Mapping to the catalogue

Two naming families coexist in `models.yaml`:

- **Legacy `3D Gauss` / `2D diffusion` family** — dimensionless $\tau_D$ (`td`),
  aspect `s`, offset `b`, particle number `N`; photodynamics as normalized
  `(1-ba+ba*exp(-x/bt))` bunching and `(1-aab*exp(-x/tab))` antibunching factors.
  This is the composable-model territory (`general.py`) for new work.
- **PAM-derived family** (`… (D, triplet)`, `… (tauD, …)`, `SCCF …`,
  `Full FCS …`) — explicit units (D in µm²/s, `w_r`/`w_z` in µm, `tau_T` in µs,
  `x` in s), the $1/\sqrt{8}$ prefactor, and the $\Theta/(1-\Theta)$ triplet
  form. A/B-verified against PAM; see [fcs-pam-port.md](fcs-pam-port.md).

To read any entry: identify the **transport** factor (2D/3D, $\tau_D$ vs $D$,
normal/anomalous, flow/two-focus/scanning) and count the **photodynamic**
factors (bunching / anti-correlation / antibunching / afterpulse / bleach). The
name is the checklist.

## Pointers

- Models: `chisurf/core/models/fcs/models.yaml`; composable model
  `chisurf/core/models/fcs/general.py` (+ `relaxation.py`, `mdf.py`); parser
  `chisurf/core/models/parse/parse.py`.
- Port status & FLCS filters: [fcs-pam-port.md](fcs-pam-port.md).
- Two-focus status: [two-focus-fcs.md](two-focus-fcs.md).
- Forward roadmap (TIRF/SPIM/imaging/diffusion-law): [quickfit3-mining.md](quickfit3-mining.md).
- QuickFit3 help source: `junk/quickfit3/plugins/fcs_fitfuctions/help/`
  (per-model formula pages), `fcsfit/help/estimate_focus.html` (calibration),
  `imagingfcs/help/difflaw.html` (diffusion law).
- FCS plugin group overview: [/plugins/fcs.md](/plugins/fcs.md); fluorescence
  kernel: [/subsystems/fluorescence-domain.md](/subsystems/fluorescence-domain.md).
