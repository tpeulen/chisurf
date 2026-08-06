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
and {doc}`/guides/31_h2mm_simulation_validation`.

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
restarts are used and the best converged fit is kept. {cite}`pirchi2016`
supplied the Baum-Welch reformulation guaranteeing per-iteration improvement,
which made H2MM practical on the estimator of {cite}`gopich2009`.

## How many states — BIC and ICL

The optimizer needs $K$ fixed, so the state count is found by running $K = 1, 2,
3, \dots$ and comparing. Raw likelihood always rises with $K$, so two penalized
criteria decide instead:

$$
\mathrm{BIC} = -2\ln\mathcal{L} + p\ln n,
$$

with $p$ free parameters and $n$ photons (**Bayesian Information Criterion**,
adapted to H2MM in {cite}`lerner2018`), and the **Integrated Complete
Likelihood** ($\mathrm{ICL}$), which adds a term for the entropy of the Viterbi
state assignment — rewarding models whose states are *cleanly separable* and
distrusting extra states that merely overlap. Plot both against $K$ and take the
minimum; where they disagree, ICL's separability penalty ({cite}`harris2022`)
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

### Decoding: "most likely path" is not "how the photons distribute"

Viterbi maximises $P(\mathbf{s}\mid\mathbf{y},\lambda)$ over *whole sequences*.
That is the right answer for a single trajectory, and the wrong one for the
question most downstream products actually ask — an occupancy, a per-state
decay, a per-state spectrum all want *how many photons belong to each state*,
and the argmax answers that with a bias that does not average out. If every
photon in a burst has $\gamma = (0.7, 0.3)$, Viterbi assigns all of them to
state 0 and the 30 % is erased; well-separated states come out inflated, and
ambiguous or short-lived ones can vanish entirely.

The unbiased quantity is the **per-photon posterior**

$$\gamma_t(i) = P(s_t = i \mid \mathbf{y}, \lambda)
             = \frac{\alpha_t(i)\,\beta_t(i)}{\sum_j \alpha_t(j)\,\beta_t(j)},$$

already formed inside the forward-backward E-step. Its column means are the
state occupancy, and ChiSurf reports them as `posterior_populations` whatever
decoder ran.

When the output must be one integer state per photon — a channel id, an
integer-count histogram — $\gamma$-weighting is not available and the choice is
between the argmax and a **draw** from $\gamma$. Drawing wins, because it
reproduces the marginal by construction:

| decoder | draws from | photon distribution | dwell / transition structure |
|---|---|---|---|
| `viterbi` | — (argmax) | biased (winner-takes-all) | consistent (it *is* the ML path) |
| `jitter` | marginal $\gamma$, per photon | **faithful** | fragmented — do not use |
| `ffbs` | joint posterior, whole path | **faithful** | **valid** |

`jitter` draws each photon independently, so the sampled path keeps none of
$\gamma$'s temporal correlation: a solidly occupied state at
$\gamma = (0.9, 0.1)$ still sees one photon in ten flipped at random, turning
one dwell into dozens. It is therefore right for per-photon products and wrong
for dwell times — ChiSurf enforces this by deriving dwells and transitions from
a Viterbi path even when `jitter` is selected, and recording that it did.

`ffbs` (forward filtering, backward sampling) draws a whole trajectory from
$P(\mathbf{s}\mid\mathbf{y})$ via $s_N \sim \alpha_N$ and
$s_t \sim \alpha_t(i)\,A^{\Delta t}[i, s_{t+1}]$, so it reproduces the marginal
*and* keeps the dwell structure. Averaging over several draws is multiple
imputation: the spread across draws is the decoding uncertainty a single Viterbi
path reports as zero.

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
dwell-filtering acts on).

The **decoder** is a separate choice from the fitting engine, and the run can
write its assignment **back into the photon stream** — a PTU whose routing
channels encode `(stream, state)`, and a msgpack state sidecar carrying the
per-photon states with the model, decoder, seed and channel map. That turns a
per-state decay or per-state FCS into an ordinary channel or mask selection in
any tool, with no H2MM-aware plumbing. See
{doc}`/guides/19_h2mm_hidden_markov`.

When your data are already binned (TIRF/camera trajectories with a constant
frame rate), the appropriate tool is binned HMM instead — see
{doc}`/guides/20_ebfret_binned_hmm`.

## What H2MM can and cannot resolve

**The kinetic window is bounded at both ends, by photons and by bursts.** A
transition can only be located in time to within roughly one inter-photon
interval, and it can only be *seen* if it happens during a burst. At a typical
per-molecule count rate of 50 kHz the mean gap is $\langle\Delta t\rangle =
20\ \mu\mathrm{s}$, and a 1 ms burst therefore carries ~50 photons. That places
the accessible rate range at roughly

$$
\frac{1}{\text{burst duration}} \;\lesssim\; k \;\lesssim\;
\frac{1}{\langle\Delta t\rangle},
\qquad\text{here } 10^{3}\ \mathrm{s^{-1}} \dots 5\times10^{4}\ \mathrm{s^{-1}} .
$$

Faster exchange is averaged within the photon spacing and shows up as a single
state of intermediate $E$; slower exchange simply never occurs inside a burst,
and the molecule looks static. Raising the excitation power widens the upper
edge but costs photobleaching — which shortens bursts and closes the lower edge.

**Model selection gets conservative fast, because the parameter count grows
quadratically.** ChiSurf counts free parameters as $k = K^2 + (P-1)K - 1$ for
$K$ states and $P$ photon streams:

| $K$ | $k$ ($P=2$, DD/DA) | $k$ ($P=3$, with AA) |
|---|---|---|
| 2 | 5 | 7 |
| 3 | 11 | 14 |
| 4 | 19 | 23 |
| 5 | 29 | 34 |

With $N = 10^5$ photons, $\ln N \approx 11.5$, so going from 3 to 4 states adds
8 parameters and $8 \times 11.5 \approx 92$ to the BIC penalty. The 4-state
model must therefore improve the log-likelihood by more than ~46 just to break
even. This is why state counts above 3–4 need genuinely large photon budgets,
and why a BIC curve that keeps falling is more often a sign of unmodelled
heterogeneity (photophysics, bleaching, aggregates) than of real extra
conformations.

**The efficiencies are apparent, not accurate.** $E_i$ read from $\mathbf{B}$ is
an *uncorrected* proximity ratio — leakage, direct excitation and $\gamma$ have
not been applied (see {ref}`concept-smfret-bursts`). Apply the corrections to
the per-state values afterwards; do not compare raw $\mathbf{B}$-derived
efficiencies against corrected histogram values.

**Baum-Welch finds a local optimum.** The likelihood is multimodal, so the
result depends on the starting model; ChiSurf uses random restarts and keeps the
best converged fit, but reproducibility across restarts is the check that this
worked, not something to assume. Label-permutation degeneracy is expected —
state 1 and state 2 may swap between runs, so match states by $E$, not by index.

**Dwell times are truncated by the burst.** Any dwell longer than the remaining
burst is cut short, which biases the dwell-time distribution toward short
values and the exit rates upward. The first and last dwell of every burst are
censored by construction; excluding them, or accounting for the censoring, is
necessary before reading rate constants off dwell histograms rather than off
$\mathbf{A}$.

## See also

- Guides: {doc}`/guides/19_h2mm_hidden_markov` ·
  {doc}`/guides/30_h2mm_workflow_results` ·
  {doc}`/guides/31_h2mm_simulation_validation`; binned-HMM alternative
  {doc}`/guides/20_ebfret_binned_hmm`.
- Plugin: `chisurf/plugins/burst/burst_h2mm/`; engine `tttrlib.H2MM`.
- Key literature: {cite}`pirchi2016` is H2MM itself; {cite}`harris2022` is
  burstH2MM, whose plots this plugin follows; {cite}`schrimpf2018` a comparable
  framework with its own implementation; {cite}`gopich2009` the photon-by-photon
  theory underneath all three.
