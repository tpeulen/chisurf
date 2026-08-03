---
type: Reference
title: Photon Distribution Analysis (PDA) — theory and chisurf mapping
description: The shot-noise / binomial forward model behind single-molecule FRET histograms, its background/crosstalk/gamma corrections, distance-distribution and dynamic (interconversion) extensions, and how each piece maps onto chisurf's PDA models and the tttrlib.Pda engine.
resource: chisurf/core/models/pda2c/
tags: [pda, smfret, shot-noise, binomial, dynamic-pda, mfd, tttrlib, seidel]
timestamp: '2026-07-24T00:00:00Z'
---

# Purpose

This reference records the physics of **Photon Distribution Analysis (PDA)** and
maps each concept onto the chisurf implementation, so future work on the PDA
models does not have to re-derive the forward model. The user-facing version of
this material is `docs/concepts/pda2c.md`; this note is the internal companion that
names files, classes and correction parameters explicitly. PDA sits alongside the
other single-molecule FRET burst tools; see also the BVA and 2CDE theory notes in
this group and the FRET-calibration note for the correction-factor conventions.

# The core idea: shot noise is exactly known

A freely diffusing single molecule is observed one **burst** at a time. Each
burst has a finite photon budget $N = F_D + F_A$ (donor + acceptor counts), so
the apparent efficiency $E_\text{app} = F_A / N$ is a ratio of small integers.
For a fixed true efficiency $E$ the acceptor count follows a **binomial** law

$$P(F_A \mid N, E) = \binom{N}{F_A} E^{F_A} (1-E)^{N-F_A},$$

whose spread $\sqrt{E(1-E)/N}$ is the entire origin of the smFRET histogram
width for a static, homogeneous population. Because that width is *computed, not
fitted*, PDA can separate stochastic (shot-noise) broadening from genuine
structural heterogeneity — this is the point of Antonik et al. 2006.

# Ingredients of the forward model

1. **Burst-size distribution $P(N)$** — supplied by the experiment (photons per
   time window / per burst), not a free parameter. The predicted joint count
   distribution averages the per-burst binomials over $P(N)$:
   $P(F_D,F_A)=\sum_N P(N)\,P(F_A\mid N,E)$.
   In chisurf this is `fit.data.pda['ps']` (aka `pF`), passed to
   `tttrlib.Pda(pF=...)`; the photon-number window is
   `minimum/maximum_number_of_photons` → `hist2d_nmin`/`hist2d_nmax` and the
   `Pda2cPhotonRange` group (`nPh_min`, `nPh_max`).

2. **Per-photon green probability $p_G(E)$** — the ideal binomial parameter $E$
   is replaced by a realistic detection probability that folds in all
   corrections. Implemented in
   `chisurf/core/models/pda2c/common.py::green_probability_from_efficiency`:
   with donor/acceptor "quenched" signals $S_{DQ}=Q_D\,\mathrm{Ex}_{DG}(1-E)$ and
   $S_{AQ}=Q_A(\mathrm{Ex}_{DG}E+\mathrm{Ex}_{AG})$,
   $G=g_G(c_{GD}S_{DQ}+c_{GA}S_{AQ})$, $R=g_R(c_{RD}S_{DQ}+c_{RA}S_{AQ})$,
   $p_G=G/(G+R)$. The species handed to the engine are `(amplitude, p_G)` pairs
   (`ProbCh0.pch0_spectrum`, interleaved).

3. **Background** — uncorrelated Poisson counts per channel ($B_D$/`bg0`,
   $B_R$/`bg1` in `Background`; `BG`/`BR` in `Pda2cFretNuisance`). The signal
   distribution is convolved channel-by-channel with a Poisson background:
   $P=\sum P_\text{sig}(s_D,s_A)\,\mathrm{Pois}(b_D\mid B_D)\,\mathrm{Pois}(b_A\mid B_R)$.
   `tttrlib.Pda.background_ch1/ch2`.

4. **Crosstalk / gamma / direct excitation** — the MFD correction factors are
   *derived* (read-only outputs) from the more general detector/crosstalk
   description in `Pda2cFretNuisance.update_correction_factors`:
   $\alpha = g_R c_{RD}/(g_G c_{GD}+g_R c_{RD})$ (donor leakage),
   $\gamma = g_R c_{RA} Q_A/(g_G c_{GD} Q_D)$,
   $\delta = \mathrm{Ex}_{AG}/\mathrm{Ex}_{DG}$ (direct acceptor excitation).
   These can be populated from a light-path simulation via
   `apply_lightpath_matrices` / `apply_lightpath_to_nuisance`.

The engine assembles $P(F_D,F_A)$ as the **S1S2 matrix** (`Pda.s1s2` /
`get_S1S2_matrix`); fitting compares the model S1S2 to `fit.data.pda['s1s2']`,
collapsed to a 1-D proximity-ratio histogram by a named axis callback
(`_PDA_HISTOGRAM_AXES`, e.g. `S1/(S0+S1)`) via `pda_1d_residuals_from_s1s2`.

# Distance → efficiency and distance distributions

Förster: $E(R)=1/(1+(R/R_0)^6)$, $R_0$ from `chisurf.core.models.tcspc.fret`.
Model hierarchy under `chisurf/core/models/pda2c/`:

- **Discrete** (`simple.py::Pda2cSimpleModel`, `name="PDA-discrete"`) — species as
  `(amplitude, pch0)`; minimal one-state / mixture test.
- **Gaussian** (`pdagauss.py::Pda2cGaussianDistanceModel`, `Pda2cGaussianDistances`)
  — $p(R)$ = sum of Gaussians $(\bar R_i, \sigma_i, a_i)$ on `fret.rda_axis`;
  broadening beyond shot noise, $P=\int p(R)P(F_D,F_A\mid E(R))\,dR$. Optional
  `limited_width` mode reads $\sigma$ as a percentage of $\bar R$.
- **SAW-ν polymer** (`saw_nu.py::Pda2cSawNuModel`) — reuses the Gaussian machinery
  but swaps $p(R)$ for a self-avoiding-walk distribution
  (`math.functions.rdf.saw_nu`, params `Rrms`, `nu`); for disordered/unfolded
  chains.

# What is actually fitted: the projection and the statistic

The forward model is a 2-D **S1S2 count matrix**, but the fit runs on a 1-D
projection of it. Both halves of that sentence are modelling choices, and both
live in `common.py::Pda2cFitSettings` (one instance per model, `model.fit_settings`,
rendered by the "Fit histogram / statistic" panel of every `*.view.json`).

**Which projection** — `PDA_AXES`, built by `build_pda_histogram_function`:

| axis | meaning | needs the model? |
| --- | --- | --- |
| `S1/(S0+S1)` | raw proximity ratio (default) | no |
| `E` | $\gamma$-corrected efficiency, $E=\mathrm{PR}/(\mathrm{PR}+\gamma(1-\mathrm{PR}))$ | yes ($\gamma$) |
| `S0/S1` | intensity ratio, log-binned; spreads out the donor-only / low-FRET overlap | no |
| `R` | distance, inverting Förster on $E$ | yes ($\gamma$, $R_0$) |

Selecting an axis resets the binning to that axis' `PDA_AXIS_RANGES` entry — a
0–1 linear range is meaningless in Ångström. The corrected axes bin *through*
$\gamma$ and $R_0$, so the cached data histogram in
`pda_1d_residuals_from_s1s2` keys on them and re-bins when a correction factor
moves. The same builder serves the distribution plot, so the plotted and the
fitted histogram cannot drift apart.

**Which statistic** — `PDA_STATISTICS`, applied by `pda_weighted_residuals`
after rescaling the model (a normalised probability distribution) to the data's
total counts:

- `poisson` (default) — deviance / likelihood-ratio,
  $r=\mathrm{sign}(d-m)\sqrt{2[m-d+d\ln(d/m)]}$. Empty bins still contribute
  $2m$.
- `neyman` — $(d-m)/\sqrt{\max(d,1)}$, the familiar data-weighted $\chi^2$.
- `pearson` — $(d-m)/\sqrt{\max(m,1)}$, model-weighted.

The three agree at high counts and disagree exactly where PDA operates: a PDA
histogram is a projection of a *sparse* S1S2 matrix, so many bins hold a handful
of bursts. There the Gaussian approximations are biased — a bin that fluctuated
low is handed a small $\sigma$ and therefore a large weight, which drags the
`neyman` estimate. Measured on twenty Poisson realisations of an 800-count
histogram (`test/models/test_pda_statistics.py`), recovering one Gaussian mean
distance: `poisson` $-0.02$ Å, `neyman` $+0.28$ Å, `pearson` $-0.17$ Å, against a
per-fit scatter of $0.27$ Å — i.e. `neyman`'s offset is a full standard deviation
of systematic error, and the deviance is unbiased. Prefer the default; select a
$\chi^2$ only to reproduce a $\chi^2$-based analysis.

# Dynamic PDA (interconversion within the window)

Kalinin et al. 2008: when a molecule switches states *during* the integration
time, the relevant variable is the **fraction of the window** $f$ spent in
state 1 of a two-state telegraph process. For a stationary two-state Markov
system $f$ has law (`dynamic.py`):

$$w(f)=e^{-af-b(1-f)}\big[(p_1 b+p_2 a)I_0(z)+\sqrt{\tfrac{ab}{f(1-f)}}(p_1(1-f)+p_2 f)I_1(z)\big],$$

$z=2\sqrt{abf(1-f)}$, $a=k_1T=K(1-p_1)$, $b=k_2T=Kp_1$, with steady-state
occupancy $p_1$ (`x1`) and one dimensionless exchange parameter
$K=(k_1+k_2)T$ (`k_ex`, mean transitions per window). Two boundary masses +
interior Bessel density. Time-averaged probability $p_G(f)=f\,p_{G,1}+(1-f)p_{G,2}$
(equal-brightness). Limits (used as the headless acceptance test):

- $K\to 0$: only boundary masses → two static populations at $E_1,E_2$
  (weights $x_1,x_2$).
- $K\to\infty$: $w(f)$ collapses to $f=x_1$ → single averaged population at
  $x_1E_1+x_2E_2$.

The intermediate "bridge" of counts between the two static peaks is the
dynamics fingerprint. Variants: `dynamic_mc.py` (Monte-Carlo sampling of the
occupation-time / dwell-time integral, the approach popularized by GPU mcPDA
tools that sample dwell times densely to reach fast interconversion and complex
kinetic matrices), a three-state extension, and `anisotropy.py`
(polarization-resolved PDA with per-channel backgrounds and G/l1/l2 calibration).

# Reading a fit

Single distance, no excess width → static/homogeneous. Excess width → distance
distribution (Gaussian / SAW-ν). Counts between two peaks that a static mixture
cannot reproduce → interconversion during the burst (fit dynamic, read $K$).
Narrowing the photon window raises $N$ and sharpens every peak at the cost of
statistics.

# References

- Antonik, Felekyan, Gaiduk, Seidel, *J. Phys. Chem. B* **2006**, 110, 6970
  (PDA; separating heterogeneity from shot noise).
- Kalinin, Felekyan, Valeri, Seidel, *J. Phys. Chem. B* **2008**, 112, 8361
  (dynamic PDA / multi-state characterization in MFD).

# See also

- User concept: `docs/concepts/pda2c.md`; guide `docs/guides/11_pda2c.md`.
- `/references/bva-theory.md`, `/references/fret-calibration.md`,
  `/references/crosstalk.md` for shared correction-factor conventions.
- Engine: `tttrlib.Pda` (S1S2 histogram, `pF`, background_ch1/ch2).
