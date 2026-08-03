---
type: Reference
title: "H2MM theory — photon-by-photon hidden Markov modeling of single-molecule streams"
description: The theory behind ChiSurf's photon-by-photon HMM (H2MM) burst analysis — the hidden Markov model for a confocal photon stream (per-state emission probabilities × a transition-rate matrix), why binning discards information and H2MM works directly on variable inter-photon times, the Baum-Welch/forward-backward optimization, model selection by BIC/ICL, and the outputs (per-state E/S, transition rates, dwell times, Viterbi state path). Maps to the burst_h2mm plugin and the tttrlib.H2MM engine.
tags: [reference, smfret, bursts, h2mm, hidden-markov, dynamics, pedagogy]
timestamp: '2026-07-24T00:00:00Z'
---

# H2MM theory — photon-by-photon hidden Markov modeling of single-molecule streams

Burst-averaged smFRET readouts — the FRET-efficiency histogram, the E–S ALEX
map, BVA — collapse each burst to one number and so are blind to dynamics that
happen *inside* a burst. A molecule that hops between a high-FRET and a
low-FRET conformation several times during its ~1 ms transit shows up only as a
broadened or bridged histogram, not as a resolved kinetic scheme. **Photon-by-
photon hidden Markov modeling (H2MM)** recovers that hidden kinetics: it fits a
Markov state model directly to the raw photon record, giving the number of
conformational states, their FRET efficiencies, and the transition rates
between them on the microsecond-to-millisecond timescale.

This concept is the **science/pedagogy layer** for ChiSurf's `burst_h2mm`
plugin. It explains what the model *is*, why binned HMM is the wrong tool for
sparse confocal data, how the optimizer finds the best model, how the state
count is chosen, and what the outputs mean. The plugin's own README documents
the *implementation* (the `A^Δt` trick, the client–server layout, the Numba↔
`tttrlib.H2MM` engines, A/B validation); this document does not duplicate it.

The pedagogy, terminology, and model-selection framing follow the H2MM
literature — Gopich & Szabo 2009 (the maximum-likelihood estimator), Pirchi &
Tsukanov et al. 2016 (the Baum-Welch reformulation that made H2MM practical),
Lerner et al. 2018 (the modified BIC), and Harris et al. 2022 (the ICL
criterion, the multiparameter/ALEX extension, and the fast `H2MM_C` reference
implementation) — together with the burstH2MM package documentation
(Harris et al.) used as **documented prior art**. Formulas are stated
independently here; nothing is a verbatim copy.

## A hidden Markov model for a photon stream

A hidden Markov model has two ingredients:

- **A Markov chain of hidden states.** The system occupies one of $K$
  discrete states at any instant and jumps between them stochastically. The
  chain is *memoryless* — the probability of the next jump depends only on the
  current state, not on the history of how it got there — and it is *hidden*
  because the state is a latent conformation (e.g. an open vs. closed
  protein), never observed directly.
- **State-dependent emission.** Each state emits observables with its own
  probabilities. What is actually recorded is a stream of photons, each
  tagged with a **detection channel** (an *index*): donor-excitation/
  donor-emission ($DD$), donor-excitation/acceptor-emission ($DA$), and — for
  µsALEX/PIE data — acceptor-excitation/acceptor-emission ($AA$), optionally
  further split by polarization or by micro-time (nanotime) divisors. A useful
  analogy from the original speech-recognition HMMs: each state is like a topic
  that emits words with characteristic frequencies; here each state emits
  photons in each channel with characteristic probabilities. A high-FRET state
  emits mostly $DA$ photons, a low-FRET state mostly $DD$.

The model is fully specified by three arrays:

- $\boldsymbol{\pi}$ — the **initial-state** probabilities (length $K$);
- $\mathbf{A}$ — the **transition** matrix, $A_{ij} = P(\text{state } j
  \text{ next} \mid \text{state } i \text{ now})$, one Markov step ($K\times K$,
  rows sum to 1);
- $\mathbf{B}$ — the **emission** matrix, $B_{i c} = P(\text{channel } c
  \mid \text{state } i)$ ($K \times C$ for $C$ channels, rows sum to 1).

The per-state FRET efficiency is read straight off $\mathbf{B}$ (in the
two-channel case $E_i^{\text{app}} = B_{i,DA}/(B_{i,DD}+B_{i,DA})$); with the
$AA$ channel present the per-state stoichiometry $S_i$ follows as well, so
states separate FRET dynamics from photophysics (acceptor blinking/bleaching)
on the E–S map.

## Why binning loses information — and H2MM does not

Classical HMM as used on TIRF/camera smFRET trajectories assumes a **constant
data rate**: one intensity frame every fixed interval, so each time step
carries a comparable observation. Confocal single-photon data breaks that
assumption completely. Photons arrive **sparsely and irregularly** — the
inter-photon time varies over orders of magnitude within a burst, and between
bursts there are long dark gaps. Forcing such data onto a fixed time grid to
apply ordinary HMM is lossy in both directions:

- **Coarse bins average out fast transitions.** A bin wide enough to hold
  several photons blurs any state change that happens inside it; sub-bin
  kinetics is simply gone.
- **Fine bins are mostly empty and mis-weighted.** A bin narrow enough to
  isolate single photons is empty most of the time; the empty bins carry no
  FRET information yet still enter the likelihood, and the arbitrary bin edge
  injects a timescale the physics never had.

H2MM removes the bin entirely. It models the **actual inter-photon time** as
the observable's timing: between two consecutive photons separated by $\Delta t$
clock ticks the hidden chain makes $\Delta t$ *unobserved* Markov steps, so the
propagator over that gap is the matrix power $\mathbf{A}^{\Delta t}$ rather than
a single $\mathbf{A}$. Every photon contributes its channel *and* its arrival
gap; nothing is thrown away and no external time bin is imposed. The likelihood
is therefore computed directly on the raw $(\text{index}, \text{time})$
sequence — the defining move of Gopich & Szabo's estimator and the reason H2MM
resolves dynamics faster than the mean burst duration.

(Implementation note: because only the *distinct* gap values matter, the powers
$\mathbf{A}^{\Delta t}$ and the associated transition-count tensors are computed
once per unique $\Delta t$ and cached, so the cost scales with the number of
photons, not the number of clock ticks. ChiSurf's plugin README calls this the
`A^Δt` trick. $\Delta t = 0$ is one of those distinct values, not a special
case: coarse macro-time scaling makes coincident arrival times common, and such
a pair propagates with $\mathbf{A}^0 = \mathbf{I}$ and contributes no transition
counts.)

## Optimization — forward-backward and Baum-Welch

For a fixed number of states $K$, fitting means finding the $(\boldsymbol\pi,
\mathbf{A}, \mathbf{B})$ that **maximize the likelihood** of the observed photon
stream. This is done by the **Baum-Welch algorithm**, the expectation-
maximization (EM) specialization for HMMs:

1. **E-step (forward-backward).** With the current model, a *forward* pass
   accumulates the probability of the photon sequence up to each photon ending
   in each state, and a *backward* pass the probability of the remainder given
   each state; combining them gives, for every photon, the posterior
   probability of each hidden state and, for every gap, the posterior of each
   state-to-state transition. To avoid numerical underflow over thousands of
   photons the passes are run **scaled** (renormalized per photon), and the
   log-likelihood is accumulated from the scaling factors.
2. **M-step (re-estimation).** The posteriors are turned into new parameter
   estimates: $\boldsymbol\pi$ from the first-photon state posteriors,
   $\mathbf{A}$ from the summed transition posteriors, $\mathbf{B}$ from the
   channel-weighted state posteriors — each a closed-form weighted average.

Iterating E and M **monotonically increases** the likelihood until it plateaus.
Pirchi & Tsukanov et al. 2016 supplied exactly the Baum-Welch reformulation of
Gopich & Szabo's equations that guarantees this per-iteration improvement,
which is what turned H2MM from an intractable search into a routine
optimization. Because EM finds a *local* optimum, the fit is repeated from
several random starting models (random restarts) and the best converged
likelihood is kept.

## Model selection — how many states?

The optimizer needs $K$ fixed in advance, so the number of states is itself a
question to be answered: run the optimization at $K = 1, 2, 3, \dots$ and choose
between the converged models. Raw likelihood always rises with more states
(more parameters fit the data better), so it cannot decide $K$ on its own — an
overfit model invents states the data does not support, an underfit one merges
distinct conformations. Two penalized criteria are used:

- **BIC — Bayesian Information Criterion.** Penalizes the maximized
  log-likelihood by the parameter count,
  $\mathrm{BIC} = -2\ln\mathcal{L} + p\ln n$, with $p$ free parameters and $n$
  photons; the model with the lowest BIC wins. Lerner et al. 2018 introduced
  the H2MM-adapted (modified) BIC as the first systematic over/under-fit
  discriminator.
- **ICL — Integrated Complete Likelihood.** Adds to a BIC-like penalty a term
  for the **entropy of the state assignment**: it rewards models whose states
  are *cleanly separable* (each photon confidently assigned) and penalizes
  models whose states overlap so much that the Viterbi assignment is
  ambiguous. Harris et al. 2022 showed ICL to be the more reliable
  discriminator for smFRET H2MM, precisely because it distrusts extra states
  that do not actually separate the data.

In practice one plots BIC and ICL against $K$ and takes the minimum; the two
usually agree, and where they disagree ICL's separability penalty makes it the
safer default.

## Outputs — reading a fitted model

Once the best $K$-state model is chosen, two families of results follow.

**From the model parameters directly:**

- **Per-state FRET efficiency** $E_i$ (and stoichiometry $S_i$ with $AA$) from
  the emission matrix $\mathbf{B}$ — the conformations themselves.
- **Transition rates** from the transition matrix. $\mathbf{A}$ is a
  *per-clock-tick* one-step matrix; dividing its off-diagonal entries by the
  clock period converts them to physical rate constants $k_{ij}$ (s⁻¹), so H2MM
  yields an interpretable kinetic scheme, not just static states. Correcting
  the model $E_i$ with the usual γ/leakage/direct-excitation factors turns
  apparent into accurate FRET — see [fret-calibration.md](fret-calibration.md).

**From decoding the hidden path (Viterbi):**

The **Viterbi algorithm** finds, given the fitted model, the single
most-probable state sequence underlying the photon stream — a per-photon state
assignment. Segmenting it into maximal same-state runs gives **dwells**, and
each dwell carries:

- its **dwell time** (duration), whose per-state distribution is (for a true
  two-state Markov process) exponential with the state's exit rate — a direct
  cross-check on the fitted $\mathbf{A}$;
- the **measured** E/S of the photons in that dwell (distinct from the model
  $E_i$): histogramming these per state gives the dwell-E histogram / dwell E–S
  scatter, and plotting E-before against E-after at each transition gives the
  **transition-density plot** that visualizes which interconversions occur;
- optionally a per-state **fluorescence-decay** (nanotime) histogram, tying the
  conformational state to a donor lifetime.

Dwell-level filtering (drop burst-edge dwells, require a minimum photon count,
select by state or duration) then cleans the kinetic statistics downstream.

**Decoding is a second choice, and Viterbi answers a different question.**
Viterbi maximizes $P(\mathbf{s}\mid\mathbf{y},\lambda)$ over whole
*sequences*. Most downstream products — an occupancy, a per-state decay, a
per-state spectrum, a state-labelled photon stream — instead ask how the photons
*distribute* over the states, and the argmax answers that with a bias that does
not average out: every photon of an ambiguous burst is resolved the same way, so
$\gamma = (0.7, 0.3)$ is reported as 100/0. Well-separated states are inflated;
ambiguous and short-lived ones are erased.

The unbiased quantity is the per-photon posterior
$\gamma_t(i) = \alpha_t(i)\beta_t(i) / \sum_j \alpha_t(j)\beta_t(j)$, which
the forward-backward E-step already forms. Its column means are the state
occupancy. Where the output must be one integer per photon, $\gamma$-weighting
is unavailable and the choice is argmax versus a **draw** from $\gamma$; the
draw reproduces the marginal by construction.

| decoder | draws from | photon distribution | dwell structure |
|---|---|---|---|
| `viterbi` | — (argmax) | biased | consistent (it *is* the ML path) |
| `jitter` | marginal $\gamma$, per photon | faithful | fragmented — unusable |
| `ffbs` | joint posterior, whole path | faithful | valid |

`jitter`'s draws are independent, so the sampled path keeps none of $\gamma$'s
temporal correlation and a solid dwell shatters into single photons — it is for
photon-level products only. `ffbs` (forward filtering, backward sampling) draws
a whole trajectory from $P(\mathbf{s}\mid\mathbf{y})$ and keeps both. Averaging
over draws is multiple imputation: the spread is the decoding uncertainty a
single Viterbi path reports as zero.

## Mapping to ChiSurf

The `chisurf/plugins/burst/burst_h2mm/` plugin implements all of the above on
`.bur` burst files read through `tttrlib`:

- **Engine.** The numeric core (`core/h2mm.py`) is a Numba re-implementation of
  the Pirchi/Harris algorithm — scaled forward-backward, Baum-Welch EM, Viterbi,
  BIC/ICL, the `A^Δt`/ρ caches — with an optional drop-in **`tttrlib.H2MM`**
  C++ backend (`core/h2mm_tttrlib.py`) that reaches the same optimum
  several-fold faster. The Numba and C++ engines are A/B-verified numerically
  equivalent against the reference `H2MM_C` library
  (`tests/test_ab_vs_h2mm_c.py`).
- **Photon streams.** `core/photons.py` maps detector channels (plus optional
  PIE/ALEX micro-time windows) to the H2MM channel indices; the first two
  streams are donor/acceptor for apparent-FRET, an optional third ($AA$/"yellow")
  enables per-state stoichiometry. Micro-time **divisors** can split a stream
  into finer nanotime-based indices for multiparameter H2MM.
- **Analysis.** `core/analysis.py` runs the state scan, applies BIC/ICL
  selection, and derives the Viterbi state paths, dwells, and transition tables.
- **The 6-panel dashboard.** The GUI (`gui/tool.py`) renders the burstH2MM-style
  result panels in one pyqtgraph dashboard: the dwell **E histogram** (or **E–S
  scatter** for ALEX/PIE), the **transition-density plot**, the **BIC/ICL
  model-selection** curve, per-state **dwell-time distributions**, per-state
  **fluorescence-decay** (nanotime) histograms, and an interactive per-burst
  **Viterbi state-path** viewer.
- The **decoder** (`viterbi` / `jitter` / `ffbs`) is selectable beside the
  fitting engine; `posterior_populations` reports the unbiased occupancy
  whichever ran, and dwell statistics are taken from a Viterbi path even under
  `jitter`. The decoders live in the `tttrlib.H2MM` C++ engine
  (`posterior` / `sample_states` / `sample_paths`).
- A run can write its assignment **back into the photon stream**: a PTU whose
  routing channels encode `(stream, state)`, and a msgpack state sidecar
  carrying the per-photon states with the model, decoder, seed and channel map.
  Either makes a per-state decay or FCS an ordinary channel/mask selection.
- **Exports.** Per-photon, per-burst, and per-dwell tables are written for
  ndxplorer; the per-burst table carries the state summary (dominant state,
  number of transitions, mean micro-time proxy) so it opens straight onto ndX's
  FRET-line plots, and the per-dwell table is the unit that dwell-filtering acts
  on.

The plugin is marked **experimental** — validated against `H2MM_C` on simulated
data, not yet on experimental measurements.

## Pointers

- Plugin: `chisurf/plugins/burst/burst_h2mm/` (README for the implementation
  detail; `core/h2mm.py`, `core/h2mm_tttrlib.py`, `core/analysis.py`,
  `core/photons.py`; `gui/tool.py` for the dashboard).
- Engine: `tttrlib.H2MM` / `tttrlib.H2mmModel` (C++), Numba fallback in
  `core/h2mm.py`.
- FRET corrections applied to the per-state E/S:
  [fret-calibration.md](fret-calibration.md).
- User-facing rendering of this theory: `docs/concepts/h2mm.md`.
- Key literature: Gopich & Szabo 2009 (J. Phys. Chem. B 113:10965; ML
  estimator); Pirchi, Tsukanov et al. 2016 (J. Phys. Chem. B 120:13065;
  Baum-Welch H2MM); Lerner et al. 2018 (J. Chem. Phys. 148:123315; modified
  BIC); Schrimpf, Barth, Hendrix & Lamb 2018 (Biophys. J. 114:1518; the PAM
  smFRET-analysis platform); Harris et al. 2022 (Nat. Commun. 13:1000; ICL,
  multiparameter/ALEX H2MM, `H2MM_C` and burstH2MM).
