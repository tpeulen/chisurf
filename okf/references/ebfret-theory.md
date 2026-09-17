---
type: Reference
title: "ebFRET theory — empirical-Bayes variational HMM of binned single-molecule FRET traces"
description: The theory behind ChiSurf's binned-trace hidden Markov analysis (ebFRET/vbFRET-style) — the Gaussian-emission HMM on binned FRET-vs-time trajectories, variational Bayes and the evidence lower bound in place of Baum-Welch point estimates, the empirical-Bayes outer loop that shares one prior across all traces, evidence-based state-count selection, and Viterbi dwell/transition-density outputs. Maps to the burst_ebfret plugin and contrasts with photon-by-photon H2MM.
tags: [reference, smfret, tirf, ebfret, vbfret, hidden-markov, variational-bayes, dynamics, pedagogy]
timestamp: '2026-07-24T00:00:00Z'
---

# ebFRET theory — empirical-Bayes variational HMM of binned single-molecule FRET traces

Wide-field single-molecule FRET (immobilized molecules on a TIRF surface, or a
long confocal trace of one tethered molecule) is recorded as an **intensity- or
FRET-efficiency-versus-time trajectory** sampled at a fixed camera frame rate.
Each trace is a noisy staircase: the molecule dwells in a conformational state,
then hops to another, and the apparent FRET efficiency jumps between discrete
levels buried in shot and background noise. **ebFRET** (van de Meent et al.
2014) recovers the hidden staircase — the number of states, their FRET levels,
and the transition rates between them — by fitting a Gaussian-emission hidden
Markov model to the binned signal, with an **empirical-Bayes** prior shared
across the whole set of traces so that many short, noisy molecules are pooled
into one robust answer.

This concept is the **science/pedagogy layer** for ChiSurf's `burst_ebfret`
plugin. It explains what the model *is*, why variational Bayes replaces
Baum-Welch point estimates, how the shared prior regularizes state recovery,
how the state count is chosen, and what the outputs mean. The plugin's own
README documents the *implementation* (the two nested loops, the
`(m, beta, a, b)` Normal-Gamma convention, the client–server layout, the
`simulated-K04-N350` validation); this document does not duplicate it.

The pedagogy and terminology follow the binned-HMM smFRET literature — Bronson
et al. 2009 (vbFRET, the variational-Bayes formulation), van de Meent et al.
2014 (the empirical-Bayes extension), and Blanco & Walter 2010 (transition-
density plots) — with the ebFRET package documentation as **documented prior
art**. Formulas are stated independently here; nothing is a verbatim copy. This
is the binned-trace complement to [h2mm-theory.md](h2mm-theory.md); the two
share the hidden-Markov idea but consume different data.

## A hidden Markov model for a binned FRET trace

The system occupies one of $K$ discrete conformational states at each frame and
jumps between them memorylessly — a Markov chain that is *hidden* because the
state is never observed directly, only the noisy FRET readout. Unlike the
photon stream in H2MM, the observation is a **real-valued** number per frame (an
apparent FRET efficiency $z_t$), so each state emits with a **Gaussian** whose
mean is its FRET level and whose variance absorbs the per-frame noise:

$$
\pi_i = P(\text{start in } i), \qquad
A_{ij} = P(j \text{ next} \mid i \text{ now}), \qquad
p(z_t \mid s_t = i) = \mathcal{N}\!\left(z_t \mid \mu_i, \lambda_i^{-1}\right),
$$

with $\boldsymbol\pi$ the initial-state vector, $\mathbf{A}$ the $K\times K$
transition matrix (rows sum to 1), and each state carrying an emission mean
$\mu_i$ (its FRET level) and precision $\lambda_i = 1/\sigma_i^2$. Because the
frame rate is constant, one row of $\mathbf{A}$ is one frame — there is no
inter-photon-gap propagator ($\mathbf{A}^{\Delta t}$) as in H2MM, which makes
binned data simpler to model but caps time resolution at the frame time.

## Variational Bayes instead of Baum-Welch point estimates

Maximum-likelihood HMM fitting (Baum-Welch, as the predecessor HaMMy used)
returns a single best parameter set and needs an external criterion for $K$; it
also **over-fits** short noisy traces, carving one molecule's noise into
spurious sub-levels. vbFRET (Bronson et al. 2009) replaced point estimates with
**variational Bayes**: conjugate priors — a **Dirichlet** on $\boldsymbol\pi$
and on each row of $\mathbf{A}$, and a **Normal-Gamma** on each state's
$(\mu_i, \lambda_i)$ — and inference of full posterior *distributions* rather
than single values. Exact inference is intractable, so VB maximizes a tractable
lower bound on the log evidence, the **evidence lower bound (ELBO)**:

$$
\ln p(z) \;\ge\; \mathcal{L}(q) \;=\;
\mathbb{E}_q\!\left[\ln p(z, s, \theta)\right] - \mathbb{E}_q\!\left[\ln q(s,\theta)\right],
$$

alternating a variational E-step (forward-backward over hidden states using the
*expected* emission/transition parameters) with a variational M-step (updating
the Dirichlet and Normal-Gamma posteriors). The gap between $\ln p(z)$ and
$\mathcal{L}$ is a KL divergence that vanishes as the approximation tightens.
$\mathcal{L}$ is a built-in Occam-razor score — it rewards fit but penalizes
complexity, so unsupported states are driven to zero occupancy instead of
absorbing noise. In the plugin this converged bound is the per-trace
`lower_bound`, summed across traces into `evidence`.

## The empirical-Bayes step: one prior shared across traces

A single bleach-limited trace is often too short to pin down all $K$ states.
ebFRET's addition over vbFRET is the **empirical-Bayes** outer loop: rather than
fixing the prior by hand, it **learns one prior shared by every trace** and
re-estimates it from the pooled posteriors. Two nested loops run until the
summed evidence converges:

$$
\underbrace{\text{per-trace VBEM}}_{\text{inner: fit each trace to the current prior}}
\;\longrightarrow\;
\underbrace{\text{hyperparameter h-step}}_{\text{outer: re-estimate the shared prior from all posteriors}}
\;\longrightarrow\;\text{repeat.}
$$

The h-step matches the Dirichlet and Normal-Gamma prior hyperparameters to the
aggregate of all per-trace posteriors (Dirichlet by a Newton update,
Normal-Gamma by moment matching). Tying every trace to one prior lets a
well-behaved molecule inform a noisy one, so state levels come out consistent
across a heterogeneous population instead of drifting trace by trace. This
pooling is what makes ebFRET robust where per-trace fitting alone is unstable.

## Choosing the number of states

Because the ELBO already penalizes complexity, model selection is a **scan**:
fit the dataset at $K = 2, 3, 4, \dots$ and keep the $K$ with the highest
converged $\sum_n \mathcal{L}_n$. There is no separate BIC/ICL penalty to add
(contrast H2MM, whose ML core needs an external BIC/ICL term) — the variational
bound *is* the selection score. In the plugin, `analyse()` runs this scan and
returns `scan = {K: evidence}` with the argmax selected.

## Outputs — Viterbi paths, dwells, transition-density plot

The selected model is decoded per trace to its most-probable state path by the
**Viterbi** algorithm, and each path is segmented into **dwells** (maximal
same-state runs, each with a dwell time and its FRET level). The canonical
summary is the **transition-density plot** (Blanco & Walter 2010): a 2-D
histogram of FRET-before against FRET-after at every transition, pooled over all
molecules — each off-diagonal peak is one interconversion $i \to j$, its
position reading the two state levels and its density the frequency. Per-state
dwell-time distributions (exponential with each state's exit rate) quantify the
rates.

## Mapping to ChiSurf

The `chisurf/plugins/burst/burst_ebfret/` plugin is a plain port of the ebFRET
GUI and its MATLAB analysis (single-prior, `D = 1`, as the GUI runs it):

- **Per-trace VBEM with restarts.** `core/hmm.py` — `e_step`, `forwback`,
  `m_step`, `kl_div`, `vbayes` in ebFRET's Normal-Wishart names
  (`mu, beta, W, nu, A, pi`; `a = nu/2`, `b = 1/(2W)`), and `vbayes_series`, the
  body of `run_vbayes.m`: previous posterior, an uninformative start and random
  prior draws, best lower bound wins.
- **Empirical Bayes.** `core/ebayes.py` — `run_ebayes.m`'s loop; the prior
  update is `h_step` with the expected sufficient statistics (Dirichlet Newton +
  Normal-Gamma moment matching, `core/dist.py`).
- **Priors.** `guess_prior` (histogram-spread centers, noise from the state
  spacing, dwell half the mean trace length) and `init_prior` (the Set Priors
  dialog).
- **Decoding, report, scan.** `viterbi_vb`; `report` (the Analysis Summary);
  `core/analysis.py::analyse` scans state counts headless and adds dwell
  segments and transition counts.
- **Interfaces.** The ebFRET window (`gui/`), `burst_ebfret.session.*` RPC
  methods, `ebfret compute` CLI; formats in `io.py`.

Validated against ebFRET under Octave and MATLAB — see
[burst-ebfret](../plugins/burst-ebfret.md). The prior-mixture (subpopulation)
model of the ebFRET paper is not reachable from the ebFRET GUI and not ported.

## Pointers

- Plugin: `chisurf/plugins/burst/burst_ebfret/` (README; `core/hmm.py`,
  `core/ebayes.py`, `core/session.py`, `core/analysis.py`, `io.py`) and its
  record [burst-ebfret](../plugins/burst-ebfret.md).
- Photon-by-photon complement: [h2mm-theory.md](h2mm-theory.md).
- User-facing rendering of this theory: `docs/concepts/ebfret.md`.
- Key literature: Bronson, Fei, Hofman, Gonzalez & Wiggins 2009 (Biophys. J.
  97:3196; vbFRET, variational-Bayes HMM); van de Meent, Bronson, Wiggins &
  Gonzalez 2014 (Biophys. J. 106:1327; ebFRET, empirical-Bayes extension);
  Blanco & Walter 2010 (Methods Enzymol. 472:153; transition-density plots).
