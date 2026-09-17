---
type: Concept
title: 'ebFRET: variational-Bayes HMM of binned traces'
description: Wide-field single-molecule FRET — immobilized molecules on a TIRF surface, or a long confocal trace of one tethered molecule — is recorded as an intensity (or FRET-efficiency) versus time trajectory sampled at a fixed camera frame rate.
tags: [concepts, kinetics, hmm, fret]
anchor: concept-ebfret
---

(concept-ebfret)=
# ebFRET: variational-Bayes HMM of binned traces

Wide-field single-molecule FRET — immobilized molecules on a TIRF surface, or a
long confocal trace of one tethered molecule — is recorded as an **intensity
(or FRET-efficiency) versus time trajectory** sampled at a fixed camera frame
rate. Each trace is a noisy staircase: the molecule sits in a conformational
state for a while, then hops to another, and the apparent FRET efficiency jumps
between discrete levels buried in shot and background noise. **ebFRET**
({cite}`vandemeent2014`) recovers the hidden staircase — the number of states,
their FRET levels, and the transition rates between them — by fitting a
Gaussian-emission hidden Markov model to the binned signal, with an
**empirical-Bayes** prior shared across the whole set of traces so that
information from many short, noisy molecules is pooled into one robust answer.

For the step-by-step workflow in ChiSurf, see the guide
{doc}`/guides/20_ebfret_binned_hmm`. ebFRET is the binned-trace complement to
photon-by-photon {ref}`H2MM <concept-h2mm>`; the two share the hidden-Markov
idea but consume different data.

## A hidden Markov model for a binned FRET trace

The system occupies one of $K$ discrete conformational states at each frame and
jumps between them memorylessly — a **Markov chain** that is *hidden* because
the state is never observed directly, only the noisy FRET readout. Unlike the
photon stream in {ref}`H2MM <concept-h2mm>`, the observation here is a
**real-valued** number per frame (an apparent FRET efficiency $z_t$), so each
state emits with a **Gaussian** whose mean is its FRET level and whose variance
absorbs the per-frame shot/background noise. The model is

$$
\pi_i = P(\text{start in } i), \qquad
A_{ij} = P(j \text{ next} \mid i \text{ now}), \qquad
p(z_t \mid s_t = i) = \mathcal{N}\!\left(z_t \mid \mu_i, \lambda_i^{-1}\right),
$$

with $\boldsymbol\pi$ the **initial-state** vector, $\mathbf{A}$ the $K\times K$
**transition** matrix (rows sum to 1), and each state $i$ carrying an emission
**mean** $\mu_i$ (its FRET level) and **precision** $\lambda_i = 1/\sigma_i^2$.
Because the frame rate is constant, one row of $\mathbf{A}$ is one frame — no
inter-photon-gap propagator is needed, which is exactly what makes binned data
simpler to model but also lower in time resolution.

## Variational Bayes instead of Baum-Welch point estimates

Classic HMM fitting (Baum-Welch / maximum likelihood, as vbFRET's predecessor
HaMMy used) returns a single best $(\boldsymbol\pi, \mathbf{A}, \mu, \lambda)$
and then needs an external criterion to decide $K$. It also **over-fits** short
noisy traces: with enough states it can carve one molecule's noise into spurious
sub-levels. vbFRET ({cite}`bronson2009`) replaced point estimates with
**variational Bayes**: it places conjugate priors on the parameters — a
**Dirichlet** prior on $\boldsymbol\pi$ and on each row of $\mathbf{A}$, and a
**Normal-Gamma** prior on each state's $(\mu_i, \lambda_i)$ — and infers full
*posterior distributions* rather than single values.

Exact Bayesian inference is intractable, so variational Bayes maximizes a
tractable lower bound on the log model evidence, the **evidence lower bound
(ELBO)**:

$$
\ln p(z) \;\ge\; \mathcal{L}(q) \;=\;
\mathbb{E}_q\!\left[\ln p(z, s, \theta)\right] - \mathbb{E}_q\!\left[\ln q(s,\theta)\right],
$$

alternating a variational E-step (forward-backward over the hidden states,
using the *expected* emission and transition parameters) with a variational
M-step (updating the Dirichlet and Normal-Gamma posteriors). The gap between
$\ln p(z)$ and $\mathcal{L}$ is a Kullback-Leibler divergence that vanishes as
the approximation tightens. Crucially, $\mathcal{L}$ is a **built-in
Occam-razor score**: it rewards fit but automatically penalizes model
complexity, so states that a trace does not actually support are driven to zero
occupancy instead of soaking up noise.

## The empirical-Bayes step: sharing a prior across traces

A single immobilized-molecule trace is often too short to pin down all $K$
states — a molecule may never visit the rarest state during its bleach-limited
lifetime. ebFRET's key addition over vbFRET is the **empirical-Bayes** outer
loop: instead of fixing the prior by hand, it **learns one prior shared by every
trace** in the dataset and re-estimates it from the pooled posteriors. Two
nested loops run:

$$
\underbrace{\text{per-trace VBEM}}_{\text{inner: fit each trace to the current prior}}
\;\longrightarrow\; \\
\underbrace{\text{hyperparameter update}}_{\text{outer: re-estimate the prior from all posteriors}}
\;\longrightarrow\; \\
\text{repeat until }\textstyle\sum_n\mathcal{L}_n\text{ converges.}
$$

The outer h-step matches the Dirichlet and Normal-Gamma prior hyperparameters to
the aggregate of all per-trace posteriors (Dirichlet by a Newton update,
Normal-Gamma by moment matching). Tying every trace to one prior lets a
well-behaved molecule inform a noisy one: the shared prior regularizes state
number and position, so state levels come out consistent across the population
rather than drifting trace by trace. This pooling is what makes ebFRET robust on
heterogeneous, short-lived TIRF data where per-trace fitting alone is unstable.

## Choosing the number of states

Because the ELBO already penalizes complexity, model selection is a **scan**:
fit the whole dataset at $K = 2, 3, 4, \dots$ and keep the $K$ with the highest
converged evidence $\sum_n \mathcal{L}_n$. There is no separate BIC/ICL penalty
to add (contrast {ref}`H2MM <concept-h2mm>`, whose maximum-likelihood core needs
an external BIC/ICL term) — the variational bound *is* the selection score, so
the model that best trades fit against parsimony wins the scan directly.

## The transition-density plot

Once a model is chosen, each trace is decoded to its most-probable state path by
the **Viterbi** algorithm, and the path is segmented into **dwells** (maximal
same-state runs, each with a dwell time and the FRET level it sat at). The
canonical summary is the **transition-density plot** ({cite}`blanco2010`): a
2-D histogram of FRET-before ($E_{\text{initial}}$) against FRET-after
($E_{\text{final}}$) at every transition, pooled over all molecules. Each
off-diagonal peak is one interconversion $i \to j$; its position reads off the
two state levels and its density the transition frequency, turning thousands of
noisy staircases into a compact map of the kinetic scheme. Per-state
dwell-time distributions (exponential with each state's exit rate) then quantify
the rates.

## Binned ebFRET versus photon-by-photon H2MM

ebFRET and {ref}`H2MM <concept-h2mm>` fit the *same* kind of hidden Markov
model but sit at opposite ends of a **binning trade-off**:

- **ebFRET** consumes **binned** intensity-vs-time traces (constant frame rate)
  and needs the molecule to stay put long enough to accumulate many frames —
  hence immobilization/TIRF or a long tethered confocal trace. Time resolution
  is capped by the frame time; transitions faster than a frame are averaged out.
  Its strengths are the Gaussian-emission simplicity, the empirical-Bayes
  pooling across many molecules, and the evidence-based state selection.
- **H2MM** consumes the **raw photon stream** of freely diffusing molecules,
  treating the variable inter-photon time as the timing observable
  ($\mathbf{A}^{\Delta t}$ propagator). It reaches microsecond resolution and
  needs no immobilization or binning, at the cost of a more intricate likelihood
  and a separate BIC/ICL model-selection step.

Choose ebFRET when your data are already binned camera/TIRF trajectories with a
fixed frame rate; choose H2MM for confocal free-diffusion photon records.

## Practical limits

**The frame time is a hard ceiling, and violating it invents states.** A
transition faster than one frame is *averaged within* that frame, so the frame
lands at an intermediate FRET value. A scattering of such frames looks exactly
like a sparsely populated middle state, and the ELBO will happily accept it —
the Occam penalty guards against fitting noise, not against a systematically
wrong observation model. With 100 ms frames, rates much above ~10 s⁻¹ are
suspect; a "state" whose population is concentrated in single isolated frames
between two others is the signature. Re-binning at two frame rates, or checking
that intermediate-state dwells last more than one frame, distinguishes the two.

**Dwell counts, not frame counts, determine rate precision.** A rate estimated
from $n$ observed transitions carries a relative uncertainty of roughly
$1/\sqrt{n}$, so ~100 transitions are needed for 10 % precision. A trace that
bleaches after 200 frames while sitting in a state with a 50-frame dwell time
contributes only a handful of transitions — which is precisely the regime the
empirical-Bayes pooling exists to rescue. Pooling fixes the *prior*, not the
information content: 500 traces with one transition each still constrain the
rate far less well than the frame count suggests.

**Photobleaching censors the slowest state.** A state whose dwell time is
comparable to the bleaching lifetime is systematically under-observed — its long
dwells are truncated, biasing its exit rate upward. Trace lengths are set by the
dye, not the molecule, so the slowest resolvable rate is bounded by bleaching
regardless of how long you record.

**Gaussian emissions are an approximation that degrades at low counts.** FRET
efficiency is bounded to $[0,1]$, but a Gaussian is not; at few photons per
frame the true per-frame distribution is a skewed ratio of small counts, and the
fitted Gaussians can place appreciable mass outside the physical range. States
near $E = 0$ or $E = 1$ are the most affected, and their fitted widths absorb the
mismatch.

**The ELBO is a bound, so model selection is approximate.** Comparing
$\sum_n \mathcal{L}_n$ across $K$ compares *lower bounds*, not evidences, and the
tightness of the bound need not be equal at every $K$. In practice the scan is
reliable when one $K$ wins clearly; a near-tie between $K$ and $K+1$ should be
resolved on physical grounds — do the extra state's dwells and level make sense —
rather than by a small ELBO difference. ChiSurf's `analyse()` scans
`min_states=2` to `max_states=4` by default and runs from a fixed `seed`, so
repeat runs reproduce exactly; that reproducibility is determinism, not evidence
that a global optimum was found. The random **restarts** are what guard against
a local optimum: on one simulated demo dataset, with a single uninformative restart the
four-state fit settles at E = [0.20, 0.38, 0.50, 0.72], with the default two it
recovers [0.10, 0.35, 0.55, 0.75]. Widen the scan range when the best model sits
at either end of it.

## See also

- Guide: {doc}`/guides/20_ebfret_binned_hmm`; photon-by-photon alternative
  {ref}`concept-h2mm`.
- Plugin `chisurf/plugins/burst/burst_ebfret/` — a port of the ebFRET GUI and
  its MATLAB analysis: per-trace VBEM and restarts
  {src}`chisurf/plugins/burst/burst_ebfret/core/hmm.py`, the empirical-Bayes loop
  {src}`chisurf/plugins/burst/burst_ebfret/core/ebayes.py`, the window's actions
  {src}`chisurf/plugins/burst/burst_ebfret/core/session.py`, file formats
  {src}`chisurf/plugins/burst/burst_ebfret/io.py`, and the state scan
  {src}`chisurf/plugins/burst/burst_ebfret/core/analysis.py#analyse`.
- Key literature: {cite}`vandemeent2014` is ebFRET — the empirical-Bayes
  variational HMM this implements; {cite}`bronson2009` is vbFRET, the per-trace
  variational method it builds on; {cite}`blanco2010` on reading
  transition-density plots.
