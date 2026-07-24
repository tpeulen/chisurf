(concept-h2mm)=
# Photon-by-photon HMM (H2MM)

Burst-averaged smFRET readouts — the FRET-efficiency histogram, the E–S ALEX
map, BVA — collapse each burst to a single value and cannot see dynamics that
happen *inside* a burst. A molecule that hops between a high-FRET and a low-FRET
conformation several times during its ~1 ms transit appears only as a broadened
or bridged histogram, not as a resolved kinetic scheme. **Photon-by-photon
hidden Markov modeling (H2MM)** fits a Markov state model directly to the raw
photon record, recovering the number of conformational states, their FRET
efficiencies, and the transition rates between them on the microsecond-to-
millisecond timescale.

For the step-by-step workflow in ChiSurf, see the guides
{doc}`/guides/19_h2mm_hidden_markov`, {doc}`/guides/30_h2mm_workflow_results`,
and {doc}`/guides/31_h2mm_simulation_validation`. The theory here is the
user-facing rendering of the maintained OKF concept
`okf/references/h2mm-theory.md`.

## A hidden Markov model for a photon stream

A hidden Markov model (HMM) has two parts. First, a **Markov chain of hidden
states**: the system is in one of $K$ discrete states at any instant and jumps
between them stochastically, memorylessly (the next jump depends only on the
current state) and *hiddenly* (the state is a latent conformation, never
observed directly). Second, **state-dependent emission**: each state emits
observables with its own probabilities. Here the observables are photons, each
tagged with a **detection channel**: donor-excitation/donor-emission ($DD$),
donor-excitation/acceptor-emission ($DA$), and — for µsALEX/PIE data —
acceptor-excitation/acceptor-emission ($AA$). A high-FRET state emits mostly
$DA$ photons, a low-FRET state mostly $DD$.

The model is specified by three arrays:

$$
\pi_i = P(\text{start in } i), \qquad
A_{ij} = P(j \text{ next} \mid i \text{ now}), \qquad
B_{ic} = P(\text{channel } c \mid \text{state } i),
$$

with $\boldsymbol\pi$ the length-$K$ **initial-state** vector, $\mathbf{A}$ the
$K\times K$ **transition** matrix (rows sum to 1), and $\mathbf{B}$ the
$K\times C$ **emission** matrix over $C$ channels (rows sum to 1). The per-state
apparent FRET efficiency is read straight off $\mathbf{B}$,

$$
E_i^{\text{app}} = \frac{B_{i,DA}}{B_{i,DD} + B_{i,DA}},
$$

and with the $AA$ channel the per-state stoichiometry $S_i$ follows too, so
states separate FRET dynamics from acceptor photophysics on the E–S map.

## Why binning loses information

Classical HMM on TIRF/camera smFRET assumes a **constant data rate** — one frame
every fixed interval. Confocal single-photon data breaks that assumption:
photons arrive sparsely and irregularly, with inter-photon times spanning orders
of magnitude. Forcing them onto a fixed time grid is lossy either way — coarse
bins average out fast transitions, while fine bins are mostly empty yet still
enter the likelihood and inject an arbitrary timescale.

H2MM removes the bin entirely and treats the **inter-photon time itself** as the
timing observable. Between two consecutive photons separated by $\Delta t$ clock
ticks the hidden chain makes $\Delta t$ *unobserved* Markov steps, so the
propagator over that gap is the matrix power

$$
\mathbf{A}^{\Delta t},
$$

not a single $\mathbf{A}$. Every photon contributes both its channel and its
arrival gap; nothing is discarded and no external bin is imposed. (Because only
the distinct gap values matter, $\mathbf{A}^{\Delta t}$ is computed once per
unique $\Delta t$ and cached, so cost scales with the photon count, not the
number of clock ticks.)

## Likelihood, forward-backward and Baum-Welch

For a photon stream $\mathbf{o}$ of channels with gaps, the **likelihood** of a
model $\lambda = (\boldsymbol\pi, \mathbf{A}, \mathbf{B})$ is a product over
photons of emission and gap-propagation factors, evaluated by the scaled
**forward** recursion

$$
\alpha_1(i) = \pi_i\, B_{i,c_1}, \qquad
\alpha_{t}(j) = \Big[\textstyle\sum_i \alpha_{t-1}(i)\, (\mathbf{A}^{\Delta t_t})_{ij}\Big]\, B_{j,c_t},
\qquad
\mathcal{L} = \sum_i \alpha_T(i),
$$

with a matching **backward** pass $\beta$. Renormalizing $\alpha$ and $\beta$
per photon prevents underflow over thousands of photons; $\ln\mathcal{L}$ is
accumulated from the scaling factors.

Fitting maximizes $\mathcal{L}$ at fixed $K$ with the **Baum-Welch** algorithm
(EM for HMMs):

- **E-step.** From $\alpha$ and $\beta$, compute for every photon the posterior
  state probability $\gamma_t(i)$ and for every gap the posterior transition
  probability $\xi_t(i,j)$.
- **M-step.** Re-estimate the parameters as posterior-weighted averages,
  $\pi_i = \gamma_1(i)$, $A_{ij} \propto \sum_t \xi_t(i,j)$,
  $B_{ic} \propto \sum_{t:\,c_t=c} \gamma_t(i)$.

Iterating **monotonically increases** $\mathcal{L}$ to a local optimum; random
restarts are used and the best converged fit is kept. Pirchi & Tsukanov et al.
2016 supplied the Baum-Welch reformulation guaranteeing per-iteration
improvement, which made H2MM practical on Gopich & Szabo's 2009 estimator.

## How many states — BIC and ICL

The optimizer needs $K$ fixed, so the state count is found by running $K = 1, 2,
3, \dots$ and comparing. Raw likelihood always rises with $K$, so two penalized
criteria decide instead:

$$
\mathrm{BIC} = -2\ln\mathcal{L} + p\ln n,
$$

with $p$ free parameters and $n$ photons (**Bayesian Information Criterion**;
Lerner et al. 2018 adapted it to H2MM), and the **Integrated Complete
Likelihood** ($\mathrm{ICL}$), which adds a term for the entropy of the Viterbi
state assignment — rewarding models whose states are *cleanly separable* and
distrusting extra states that merely overlap. Plot both against $K$ and take the
minimum; where they disagree, ICL's separability penalty (Harris et al. 2022)
is the safer default.

## Outputs — reading a fitted model

From the parameters directly: the **per-state $E_i$** (and $S_i$) from
$\mathbf{B}$, and **transition rates** from $\mathbf{A}$ — dividing the
off-diagonal one-step probabilities by the clock period gives physical rate
constants $k_{ij}$ (s⁻¹), an interpretable kinetic scheme rather than static
states.

From decoding the hidden path, the **Viterbi** algorithm returns the single
most-probable per-photon state sequence; segmenting it into maximal same-state
runs gives **dwells**, each carrying its **dwell time** (per-state distribution
exponential with the state's exit rate — a check on $\mathbf{A}$) and the
**measured** E/S of its photons. Histogramming these per state gives the
dwell-E histogram (or dwell **E–S scatter** for ALEX/PIE), and plotting
E-before against E-after at each transition gives the **transition-density
plot**.

## In ChiSurf

The **Burst H2MM** plugin (`chisurf/plugins/burst/burst_h2mm/`) runs H2MM on
`.bur` burst files read through `tttrlib`. The numeric core is a Numba engine
(scaled forward-backward, Baum-Welch, Viterbi, BIC/ICL), with an optional
drop-in **`tttrlib.H2MM`** C++ backend that reaches the same optimum
several-fold faster; both are A/B-verified against the reference `H2MM_C`
library. Detector channels (plus PIE/ALEX micro-time windows and optional
nanotime divisors) map to the H2MM channels, with an optional third $AA$ stream
enabling per-state stoichiometry.

The GUI renders the burstH2MM-style **6-panel dashboard** in one view: the
dwell **E histogram** (or **E–S scatter**), the **transition-density plot**, the
**BIC/ICL model-selection** curve, per-state **dwell-time distributions**,
per-state **fluorescence-decay** (nanotime) histograms, and an interactive
per-burst **Viterbi state-path** viewer. Per-photon, per-burst, and per-dwell
tables are exported for ndxplorer (the per-dwell table is the unit downstream
dwell-filtering acts on). The plugin is marked **experimental** — validated on
simulated data, not yet on experimental measurements.

When your data are already binned (TIRF/camera trajectories with a constant
frame rate), the appropriate tool is binned HMM instead — see
{doc}`/guides/20_ebfret_binned_hmm`.

## See also

- Guides: {doc}`/guides/19_h2mm_hidden_markov` ·
  {doc}`/guides/30_h2mm_workflow_results` ·
  {doc}`/guides/31_h2mm_simulation_validation`; binned-HMM alternative
  {doc}`/guides/20_ebfret_binned_hmm`.
- FRET corrections on the per-state E/S (γ, leakage, direct excitation):
  `okf/references/fret-calibration.md`.
- Plugin: `chisurf/plugins/burst/burst_h2mm/`; engine `tttrlib.H2MM`.
- OKF concept: `okf/references/h2mm-theory.md`.
- Key literature: Pirchi, Tsukanov et al. 2016 (J. Phys. Chem. B 120:13065);
  Schrimpf, Barth, Hendrix & Lamb 2018 (Biophys. J. 114:1518, PAM);
  Harris et al. 2022 (Nat. Commun. 13:1000, burstH2MM).
