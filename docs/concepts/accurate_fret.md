(concept-accurate-fret)=
# Accurate FRET: correction factors, FRET lines, and where they come from

A single-molecule FRET histogram is a histogram of *photon ratios*. Turning it
into a number another laboratory can reproduce — an **accurate** efficiency, and
from it a distance — requires four correction factors. The multi-laboratory
benchmark of Hellenkamp *et al.* (2018) showed that once these
are applied consistently, twenty laboratories agree on the same duplex to within
a few per cent; without them they do not. The systematics, not the counting
statistics, are what separate laboratories.

This page explains what each factor is, which measurement identifies it, why the
**optics predict them before any data is taken**, and how the donor lifetime adds
an independent route through the *FRET lines*. For the step-by-step workflow see
the {doc}`guide </guides/41_accurate_fret>`; for the Förster mechanism itself,
{ref}`concept-fret`; for burst selection, {ref}`concept-smfret-bursts`.

## The four factors

Write a measured channel as $I_{ij}$ — photons emitted by chromophore $j$ under
excitation of chromophore $i$. For a donor/acceptor pair with alternating
excitation (ALEX/PIE) there are three:

| channel | alias | what it holds |
|---|---|---|
| $I_{11}$ | `i_dd` | donor emission under donor excitation ("green") |
| $I_{12}$ | `i_da` | acceptor emission under donor excitation ("red", FRET) |
| $I_{22}$ | `i_aa` | acceptor emission under acceptor excitation ("yellow") |

The FRET channel is contaminated twice over: some donor photons land in the
acceptor detector (**leakage** $\alpha$), and the donor laser excites the
acceptor directly (**direct excitation** $\delta$). What remains still has to be
compared against the donor channel on a common scale, which the two dyes do not
share — they differ in quantum yield and in detection efficiency (**detection
factor** $\gamma$). Finally the two lasers do not deliver the same photon flux
per absorbing molecule, which shifts the stoichiometry axis (**excitation-flux
ratio** $\beta$):

$$
F_{11} = I_{11}-B_{11}, \qquad F_{22} = I_{22}-B_{22},
$$
$$
F_{12} = (I_{12}-B_{12}) - \alpha F_{11} - \delta F_{22},
$$
$$
E = \frac{F_{12}}{F_{12} + \gamma F_{11}}, \qquad
S = \frac{\gamma F_{11} + F_{12}}{\gamma F_{11} + F_{12} + F_{22}/\beta} .
$$

$\alpha$, $\delta$ and $\gamma$ change the efficiency; $\beta$ only moves the
stoichiometry, which is why a 1:1 labelled species is conventionally placed at
$S = 0.5$.

The four scalars are the **two-colour reduction** of a more general statement.
Physically, leakage and detection live in the emission crosstalk matrix and
direct excitation in the excitation crosstalk matrix; correcting straight from
those matrices also handles three or more chromophores and acceptor↔acceptor
bleed that no scalar can express (see the
{doc}`calibration how-to </guides/fret_calibration>`).

## Where the factors come from

Three independent sources, in increasing order of how much they depend on the
sample:

### 1. The optics (the prior)

$\gamma$, $\alpha$ and $\delta$ are not free parameters of a fit — they are
consequences of the light path. With $c_{jm}$ the probability that a photon from
dye $j$ reaches detector $m$ (spectra × filters × detector response) and
$x_{lj}$ the probability that laser $l$ excites dye $j$ (absorption spectrum at
the laser wavelength),

$$
\gamma = \frac{g_R\,c_{A,\mathrm{red}}\,\Phi_A}{g_G\,c_{D,\mathrm{green}}\,\Phi_D},
\qquad
\alpha = \frac{g_R\,c_{D,\mathrm{red}}}{g_G\,c_{D,\mathrm{green}} + g_R\,c_{D,\mathrm{red}}},
\qquad
\delta = \frac{x_{G,A}}{x_{G,D}} .
$$

ChiSurf's light-path calculator computes those matrices from the actual spectra,
filters and detectors. The result is a genuine *prediction* — but one carrying
the uncertainty of the optical model (spectra of the dye in its real
environment, filter tolerances, detector curves). It is therefore used as a
**Gaussian prior**, not as truth.

### 2. The reference populations (the data)

A measurement usually contains its own references. A donor-only molecule emits
nothing under acceptor excitation, so it sits at $S \approx 1$; an acceptor-only
molecule at $S \approx 0$; doubly labelled molecules in between. From those,

$$
\alpha = \frac{\langle F_{12}\rangle_{\text{donor-only}}}{\langle F_{11}\rangle_{\text{donor-only}}},
\qquad
\delta = \frac{\langle F_{12}\rangle_{\text{acceptor-only}}}{\langle F_{22}\rangle_{\text{acceptor-only}}} .
$$

$\gamma$ and $\beta$ need populations of *different* efficiency. After leakage
and direct excitation are removed, the apparent stoichiometry and efficiency of
doubly labelled molecules obey a straight line (Lee *et al.*, 2005)

$$
\frac{1}{S} = \Omega + \Sigma\,E,
\qquad
\gamma = \frac{\Omega-1}{\Omega+\Sigma-1},
\qquad
\beta = \Omega+\Sigma-1,
$$

so two or more FRET populations calibrate each other. A sample with a single
population does not identify $\gamma$ this way at all.

### 3. The donor lifetime and the static FRET line

This is where lifetime information earns its keep. Plot each burst's efficiency
against its **fluorescence-averaged** donor lifetime in the presence of the
acceptor, $\langle\tau_{D(A)}\rangle_F$ — the lifetime a mono-exponential fit of
the burst returns. A structurally homogeneous population cannot sit anywhere in
that plane: it must lie on the **static FRET line**
(Sisamakis *et al.*, 2010; Kalinin *et al.*, 2010).

```{figure} ../guides/figures/accurate_fret_lines.png
:alt: static and dynamic FRET lines, and a population displaced by a wrong gamma
:width: 100%

Left: the static FRET line for a 6 Å linker distribution, the no-linker
diagonal, and the dynamic line between two limiting distances. Right: the same
static population corrected with a 40 % too large $\gamma$ falls below its own
line — the residual the lifetime route removes.
```

Why the line is *not* the diagonal $E = 1 - \tau/\tau_{D(0)}$: the efficiency is
an amplitude-weighted quantity and therefore follows the **species-averaged**
lifetime, while the measured axis is the fluorescence-averaged one,

$$
\langle\tau\rangle_x = \frac{\sum_i a_i\tau_i}{\sum_i a_i},
\qquad
\langle\tau\rangle_F = \frac{\sum_i a_i\tau_i^2}{\sum_i a_i\tau_i},
\qquad
E = 1 - \frac{\langle\tau\rangle_x}{\tau_{D(0)}} .
$$

Any distribution of distances — even the fast linker jitter around a single mean
distance — makes $\langle\tau\rangle_F > \langle\tau\rangle_x$ and bends the line
upwards. The line is generated by sweeping the mean distance of a Gaussian
distribution of width $\sigma$ (the linker width) and averaging
$\tau(R) = \tau_{D(0)}/(1+(R_0/R)^6)$ over it and over the donor's own decay.

Reading it backwards makes it a calibration. If a population is static, its
lifetime already fixes its efficiency, and the detection factor is whatever makes
the intensity-based efficiency agree:

$$
\gamma = \frac{F_{12}}{F_{11}} \cdot \frac{1 - E_\text{line}}{E_\text{line}},
\qquad E_\text{line} = \text{line}\big(\langle\tau_{D(A)}\rangle_F\big) .
$$

One population is enough, and no acceptor-excitation channel is needed. Because
$E = F_{12}/(F_{12}+\gamma F_{11})$ *falls* with $\gamma$, a systematically
too-large $\gamma$ shows up as a population below its own static line — the
right-hand panel above.

### The dynamic line

If a molecule interconverts between two states faster than the burst lasts, the
two lifetime spectra add as *species* while the plotted lifetime stays
fluorescence-averaged. The population then leaves the static line and lands on
the **dynamic line** connecting the two limiting states, bowing towards longer
lifetimes (Barth *et al.*, 2022). This is the standard sub-burst-dynamics diagnostic,
and it is also the reason the lifetime route to $\gamma$ must be run on a sample
believed to be static: a dynamic population would be mistaken for a
mis-calibration and vice versa. Independent confirmation comes from
{ref}`concept-bva` or {ref}`concept-burst-2cde`.

## Self-consistency: the factors and the gates depend on each other

The reference populations are identified by their stoichiometry — which is
computed with $\gamma$ and $\beta$, which are estimated from the populations. The
resolution is to iterate: classify, estimate, re-classify, until the factors stop
moving (two or three passes in practice). ChiSurf does the classification with a
Gaussian mixture over the stoichiometry rather than with fixed cuts, so the
boundary follows the actual populations and no one has to defend where a box was
drawn.

## From estimates to a posterior

Each route yields a number and an uncertainty: the optics give a prior
$\mathcal{N}(\mu_\text{optics}, \sigma_\text{optics})$, the data a bootstrap
estimate $\mathcal{N}(x_\text{data}, \sigma_\text{data})$. The reported factor is
their precision-weighted combination

$$
x_\text{post} = \frac{x_\text{data}/\sigma_\text{data}^2 + \mu_\text{optics}/\sigma_\text{optics}^2}
                     {1/\sigma_\text{data}^2 + 1/\sigma_\text{optics}^2},
\qquad
\sigma_\text{post} = \left(\frac{1}{\sigma_\text{data}^2}+\frac{1}{\sigma_\text{optics}^2}\right)^{-1/2},
$$

which behaves correctly at both extremes: an informative dataset overrides an
uncertain optical model, and a factor the data cannot identify at all (no
donor-only bursts in the file) falls back to the optical value *with the optical
uncertainty* instead of to a fitted illusion. Because the factors are ordinary
[fitting parameters](../reference/user_models.md) in ChiSurf, the same priors also
regularize them when they are optimized inside a larger model.

## Error bars

Propagating the factor uncertainties into the efficiency gives

$$
\frac{\partial E}{\partial \gamma} = -\frac{E(1-E)}{\gamma},
\qquad
\frac{\partial E}{\partial \alpha} = -\frac{(1-E)^2}{\gamma},
\qquad
\frac{\partial E}{\partial \delta} = -\frac{(1-E)^2 F_{22}}{\gamma F_{11}} .
$$

The $\gamma$ term peaks at mid-range efficiency, the leakage and
direct-excitation terms at low efficiency — the reason inter-laboratory spread is
worst for intermediate distances. Converting to a distance,
$R = R_0\,(1/E - 1)^{1/6}$, the sixth root is forgiving in the middle and
merciless at the ends:

$$
\frac{\sigma_R}{R} = \sqrt{\left(\frac{\sigma_{R_0}}{R_0}\right)^2
                    + \left(\frac{\sigma_E}{6E(1-E)}\right)^2 } .
$$

A FRET distance is therefore only quotable near $R \approx R_0$; outside roughly
$0.2 < E < 0.8$ the error bar grows faster than the information does. Note also
that $R_0$ itself is calibration-dependent — it scales with the donor quantum
yield and with the orientation factor $\kappa^2$ ({ref}`concept-fret`), and its
uncertainty enters every distance directly.

## How well it can work

Simulating the whole experiment from declared parameters — diffusing molecules,
alternating lasers, per-photon micro-times — and running the automatic
calibration on the resulting photon stream puts numbers on the accuracy. At
≈1500 bursts of ≈70 photons the factors come back to a few per cent and the
efficiencies to ≈0.01 (see the {doc}`guide </guides/41_accurate_fret>` for the
table). Two lessons from that exercise generalize:

* **The population finder matters more than the estimators.** A mixture fit that
  lets a small reference population be swallowed by a broad component puts the
  class boundary in the wrong place, and a few per cent of doubly labelled
  bursts leaking into the acceptor-only class inflates $\delta$ by tens of per
  cent. The reference classes are therefore cut to the *core* of their own
  component (purity), while the FRET class keeps the mid-point cut
  (completeness) — the two classes have different jobs.
* **Splitting a burst cloud finer than the physics does not help.** Shot noise
  smears two states into a continuum, and a mixture will happily place an extra
  component in the valley between them. That component is a selection on noise,
  not a species; its centre does not lie on the $1/S$-vs-$E$ line, and fitting it
  biases $\gamma$. Sub-populations that hold only a small fraction of the bursts
  are therefore merged, and population centres enter the fit weighted by how many
  bursts they hold.

## Where the dye numbers come from

$\Phi_D$, $\Phi_A$ and $R_0$ are properties of the **dye pair**, and the same
pair should not acquire a different $R_0$ in every analysis. ChiSurf therefore
reads them from the curated fluorophore database rather than from a typed-in
constant: the donor's emission spectrum, the acceptor's absorption spectrum
scaled by its molar extinction coefficient, and the donor's quantum yield give

$$
J = \int F_D(\lambda)\,\varepsilon_A(\lambda)\,\lambda^4\,d\lambda,
\qquad
R_0 = 0.211\,\big(\kappa^2\,n^{-4}\,\Phi_D\,J\big)^{1/6}\ \text{(Å, }J\text{ in M}^{-1}\text{cm}^{-1}\text{nm}^4).
$$

Computed this way from the database's own entries the results reproduce the
literature (EGFP→mCherry 52 Å, ATTO 550→ATTO 643 65 Å), which is the check that
the stored spectra, the extinction coefficients and the overlap integral are
consistent with each other.

Two caveats are worth keeping in view. $\kappa^2 = 2/3$ is an *average over
orientations*, justified when both dyes rotate freely on their linkers within the
fluorescence lifetime; it enters only as $\kappa^{2\,1/6}$, so it is forgiving,
but a genuinely immobilized dye breaks the assumption rather than blurring it.
And the quantum yield of a dye **on a molecule** is not the catalogue value of
the free dye — local quenching is exactly what a donor-only lifetime measurement
reveals — so a curated $\Phi_D$ is a starting point, and the measured
$\tau_{D(0)}$ is the check on it.

Because the catalogue is incomplete, every quantity carries its provenance:
computed from spectra, read from a stored property, or absent. A quantity the
database cannot supply is left as the user set it rather than defaulted — a
calibration resting on a guessed quantum yield is worse than one that says it
does not know.

## Assumptions worth stating

* **The reference populations are what they claim to be.** A donor-only gate
  contaminated by bleached acceptors inflates $\alpha$.
* **$\beta$ from $S = 0.5$ assumes 1:1 labelling.** It is a definition, not a
  measurement, and it never touches $E$.
* **The lifetime route assumes static populations** and a correct $\tau_{D(0)}$
  measured on a donor-only sample.
* **The linker width shapes the static line.** A wrong $\sigma$ tilts the
  lifetime-derived $\gamma$; 6 Å is typical for common dye linkers.
* **Backgrounds must be subtracted first** — they bias the low-efficiency
  populations most.

## References

- Hellenkamp B, Schmid S, Doroshenko O *et al.* (2018) *Precision and accuracy of
  single-molecule FRET measurements — a multi-laboratory benchmark study.* Nat
  Methods 15:669–676.
- Lee NK, Kapanidis AN, Wang Y *et al.* (2005) *Accurate FRET measurements within
  single diffusing biomolecules using alternating-laser excitation.* Biophys J
  88:2939–2953.
- Sisamakis E, Valeri A, Kalinin S, Rothwell PJ, Seidel CAM (2010)
  *Accurate single-molecule FRET studies using multiparameter fluorescence
  detection.* Methods Enzymol 475:455–514.
- Kalinin S, Valeri A, Antonik M, Felekyan S, Seidel CAM (2010) *Detection of
  structural dynamics by FRET: a photon distribution and fluorescence lifetime
  analysis of systems with multiple states.* J Phys Chem B 114:7983–7995.
- Barth A, Opanasyuk O, Peulen T-O *et al.* (2022) *Unraveling multi-state
  molecular dynamics in single-molecule FRET experiments — I. Theory of
  FRET-lines.* J Chem Phys 156:141501.
