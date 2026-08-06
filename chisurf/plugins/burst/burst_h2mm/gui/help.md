# Photon-by-photon HMM (H2MM)

BVA and 2CDE tell you that a burst changed. H2MM tells you into **how many
states**, at **what efficiencies**, and with **what rate constants** — fitted to
the raw photon record, with no bin anywhere.

Press **Guide** for the walk-through.

## Why there is no bin

A classical HMM assumes a constant data rate: one frame every fixed interval.
Confocal photons break that assumption — they arrive sparsely and irregularly,
with gaps spanning orders of magnitude. Forcing them onto a time grid is lossy
either way: coarse bins average out fast transitions, fine bins are mostly empty
yet still enter the likelihood and inject an arbitrary timescale.

H2MM removes the bin and makes the **inter-photon time itself** the timing
observable. Across a gap of Δt clock ticks the hidden chain takes Δt *unobserved*
Markov steps, so the propagator is the matrix power **A^Δt**, not a single **A**.
Every photon contributes its channel *and* its gap; nothing is discarded. (Only
the distinct gap values matter, so each A^Δt is computed once and cached — cost
scales with the photon count, not with the number of clock ticks.)

Fitting is Baum-Welch (EM), which monotonically increases the likelihood to a
**local** optimum. Random restarts are run and the best converged fit kept.

## How many states

Raw likelihood always rises with K, so the state count is decided by a penalised
criterion: **BIC** = −2·lnL + p·ln n, or **ICL**, which adds the entropy of the
state assignment and so rewards models whose states are *cleanly separable*. Plot
both against K and take the minimum; where they disagree, ICL is the safer
default.

The penalty grows fast, because the parameter count is quadratic — for K states
and P streams, k = K² + (P−1)K − 1:

| K | k (DD/DA) | k (with AA) |
|---|---|---|
| 2 | 5 | 7 |
| 3 | 11 | 14 |
| 4 | 19 | 23 |
| 5 | 29 | 34 |

At 10⁵ photons, ln N ≈ 11.5, so 3 → 4 states adds 8 parameters and ≈ 92 to the
BIC penalty: the 4-state model must improve lnL by more than ~46 just to break
even. State counts above 3–4 need genuinely large photon budgets, and **a BIC
curve that keeps falling is more often unmodelled heterogeneity — photophysics,
bleaching, aggregates — than real extra conformations.**

## Decoding: "most likely path" is not "how the photons distribute"

Viterbi maximises the probability of a *whole sequence*. That is the right answer
for a single trajectory and the wrong one for an occupancy, a per-state decay or
a per-state spectrum, which all ask how many photons belong to each state. If
every photon in a burst has posterior γ = (0.7, 0.3), Viterbi assigns all of them
to state 0 and the 30 % is erased. Well-separated states come out inflated;
ambiguous or short-lived ones can vanish.

| decoder | photon distribution | dwell structure |
|---|---|---|
| `viterbi` | biased, winner-takes-all | consistent — it *is* the ML path |
| `jitter` | faithful | fragmented — do not use for dwells |
| `ffbs` | faithful | valid |

`jitter` draws each photon independently, so it keeps none of the posterior's
temporal correlation: at γ = (0.9, 0.1) one photon in ten flips and a single
dwell becomes dozens. ChiSurf therefore derives dwells and transitions from a
Viterbi path even when `jitter` is selected, and records that it did. `ffbs`
draws a whole trajectory, so it reproduces the marginal *and* keeps the dwells.
The unbiased occupancy (`posterior_populations`) is reported whatever decoder
ran.

## What the run leaves behind

Per-photon, per-burst and per-dwell tables, and — optionally — the state
assignment written **back into the photon stream**: a PTU whose routing channels
encode `(stream, state)`, and a msgpack sidecar carrying the per-photon states
with the model, decoder, seed and channel map. A per-state decay or per-state FCS
then becomes an ordinary channel or mask selection in any tool, with no H2MM-aware
plumbing. The per-dwell table opens directly in ndX.

## Before believing the result

**The kinetic window is bounded at both ends, by photons and by bursts.** A
transition is located to within about one inter-photon gap and can only be seen
if it happens *during* a burst. At 50 kHz the mean gap is 20 µs and a 1 ms burst
carries ~50 photons, so the accessible range is roughly 10³–10⁵ s⁻¹. Faster
exchange is averaged inside the photon spacing and appears as one state at
intermediate E; slower exchange never happens inside a burst and the molecule
looks static. More power widens the top edge and costs photobleaching, which
shortens bursts and closes the bottom one.

**The efficiencies are apparent, not accurate.** The per-state E read off the
emission matrix is an uncorrected proximity ratio — no leakage, no direct
excitation, no γ. Apply the corrections to the per-state values afterwards; never
compare raw ones against corrected histogram values.

**Baum-Welch finds a local optimum, and the likelihood is multimodal.** The
answer depends on the starting model. Reproducibility across restarts and seeds
is the check that the fit worked — not something to assume. Label permutation is
expected: state 1 and state 2 may swap between runs, so match states by E, never
by index.

**Dwell times are truncated by the burst.** Any dwell longer than the remaining
burst is cut short, biasing the distribution toward short times and the exit
rates upward. The first and last dwell of every burst are censored by
construction; exclude them (the per-dwell table carries an *Is Edge* flag) or
account for the censoring before reading rate constants off dwell histograms
rather than off the transition matrix.

**A flat likelihood profile means an unidentifiable state.** The **LL scan**
button profiles the log-likelihood in each state's E and S; a flat curve or a
window-wide confidence interval says the data do not determine that state, and no
amount of restarting will change it. The bootstrap (**±**) answers the same
question a different way, and the two diverge exactly on the poorly identified
states.

## Further reading

- [Photon-by-photon HMM](docs/concepts/h2mm.md) — the derivation, in full.
- [H2MM, step by step](docs/guides/19_h2mm_hidden_markov.md)
- [Reading H2MM results](docs/guides/30_h2mm_workflow_results.md)
- [Validating H2MM on simulated data](docs/guides/31_h2mm_simulation_validation.md)
- [Binned HMM](docs/guides/20_ebfret_binned_hmm.md) — the right tool when the data
  are already binned (TIRF/camera trajectories at a constant frame rate).
- [Burst variance analysis](docs/concepts/bva.md) and
  [FRET-2CDE](docs/concepts/burst_2cde.md) — the model-free screens that say
  *whether* to run this.
- {cite}`pirchi2016`
- {cite}`harris2022`
