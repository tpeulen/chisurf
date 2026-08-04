# Benchmarks

Performance numbers for the compute cores ChiSurf owns. Every table here is
produced by a script under `test/benchmarks/`, so the numbers can be
regenerated on any machine rather than trusted on faith.

The point of this page is not to advertise speed. It is to make regressions
visible and to record *why* a component is written the way it is: each section
states the work unit being measured, so that a later change can be judged
against it.

## Running them

Each script prints a markdown table on stdout, ready to paste back into this
page:

```bash
pixi run python test/benchmarks/benchmark_hmm.py         # Gaussian HMM
pixi run python test/benchmarks/benchmark_sampling.py    # ensemble samplers
```

Several also carry a `slow`-marked regression test that asserts the property the
benchmark exists to protect (that acceleration does not cost likelihood, that
the covariance move beats the stretch move on a correlated target):

```bash
pixi run pytest test/benchmarks -q -m slow
```

## Updating this page

**Re-run the affected section and update its table in the same change that
touches the component.** A benchmark page nobody refreshes is worse than none:
it turns into a claim about code that no longer exists. When a number moves,
say why in the notes under the table, and append the change to `okf/log.md`
like any other material change.

Timings depend on the machine, so always restate the environment line with the
table. Numbers from different machines must not be mixed within one table.

**Environment for the tables below** — Apple M1 Pro, macOS 26.5.1 (arm64),
Python 3.12.13, NumPy 2.4.6, SciPy 1.18.0, numba 0.66.0. Measured 2026-07-28.

---

## Gaussian HMM

`chisurf.core.math.hmm.GaussianHMM` — Baum-Welch fitting of a hidden Markov
model with multivariate normal emissions, used for binned single-molecule
traces. This replaced the external `hmmlearn` dependency, which is included
below as the reference it has to beat. See the
[concept page](../concepts/hidden_markov_models.md) for the method itself.

Two quantities matter, and they must be read together:

* **s / E-step** — the cost of one Baum-Welch map (forward-backward plus
  M-step) at a fixed iteration count. This is the honest implementation
  comparison: it does not depend on which optimum a run happens to walk into.
* **E-steps** and **log L** — how many maps convergence took, and the
  likelihood actually reached. Two implementations that stop at *different*
  optima cannot be compared on time alone, which is why the likelihood is in
  the table. A faster run that ends at a worse likelihood has not won.

`T` is the number of time bins, `K` the number of states, `F` the number of
detection channels, and `sep` the separation of the state means (1.0 = cleanly
resolved states, 0.1 = states overlapping within the shot noise, where EM
crawls and acceleration earns its keep).

| case | implementation | s / E-step | E-steps | fit [s] | log L |
| --- | --- | ---: | ---: | ---: | ---: |
| T=5,000 K=2 F=1 sep=1.0 diag | chisurf (SQUAREM) | 0.0002 | 6 | 0.01 | -14,487.5 |
| T=5,000 K=2 F=1 sep=1.0 diag | chisurf (plain EM) | 0.0002 | 3 | 0.00 | -14,487.5 |
| T=5,000 K=2 F=1 sep=1.0 diag | hmmlearn | 0.0037 | 7 | 0.02 | -14,487.5 |
| T=50,000 K=3 F=2 sep=1.0 diag | chisurf (SQUAREM) | 0.0050 | 6 | 0.12 | -286,360.1 |
| T=50,000 K=3 F=2 sep=1.0 diag | chisurf (plain EM) | 0.0049 | 4 | 0.10 | -286,360.1 |
| T=50,000 K=3 F=2 sep=1.0 diag | hmmlearn | 0.0186 | 16 | 0.37 | -385,601.4 |
| T=50,000 K=3 F=2 sep=1.0 full | chisurf (SQUAREM) | 0.0051 | 6 | 0.13 | -286,358.9 |
| T=50,000 K=3 F=2 sep=1.0 full | chisurf (plain EM) | 0.0052 | 4 | 0.10 | -286,358.9 |
| T=50,000 K=3 F=2 sep=1.0 full | hmmlearn | 0.0275 | 20 | 0.57 | -385,559.5 |
| T=200,000 K=4 F=2 sep=1.0 diag | chisurf (SQUAREM) | 0.0216 | 6 | 0.59 | -1,146,086.0 |
| T=200,000 K=4 F=2 sep=1.0 diag | chisurf (plain EM) | 0.0217 | 4 | 0.43 | -1,146,086.0 |
| T=200,000 K=4 F=2 sep=1.0 diag | hmmlearn | 0.0628 | 9 | 1.27 | -1,146,086.0 |
| T=50,000 K=8 F=3 sep=1.0 diag | chisurf (SQUAREM) | 0.0355 | 9 | 0.90 | -427,530.9 |
| T=50,000 K=8 F=3 sep=1.0 diag | chisurf (plain EM) | 0.0352 | 6 | 0.71 | -427,530.9 |
| T=50,000 K=8 F=3 sep=1.0 diag | hmmlearn | 0.0855 | 116 | 8.84 | -478,681.8 |
| T=50,000 K=3 F=2 sep=0.15 full | chisurf (SQUAREM) | 0.0312 | 48 | 1.04 | -283,384.0 |
| T=50,000 K=3 F=2 sep=0.15 full | chisurf (plain EM) | 0.0299 | 55 | 1.17 | -283,384.0 |
| T=50,000 K=3 F=2 sep=0.15 full | hmmlearn | 0.0358 | 60 | 1.81 | -288,853.5 |
| T=20,000 K=4 F=1 sep=0.1 full | chisurf (SQUAREM) | 0.0107 | 75 | 0.70 | -56,783.9 |
| T=20,000 K=4 F=1 sep=0.1 full | chisurf (plain EM) | 0.0105 | 158 | 1.40 | -56,784.3 |
| T=20,000 K=4 F=1 sep=0.1 full | hmmlearn | 0.0160 | 115 | 1.60 | -56,781.4 |

**Reading the table.** Per E-step, ChiSurf is **1.1× to 18× faster**, and the
end-to-end fit is **2× to 10× faster**. Three effects are behind that, and each
is worth keeping:

1. **One fused backward sweep.** The backward lattice, the state posteriors and
   the expected transition counts all need the same quantity, so the compiled
   kernel computes and exponentiates it once instead of making three passes
   (`_backward_posteriors_xi`). Only two rows of the backward lattice are ever
   live, instead of the whole `(T, K)` array.
2. **Data-driven initialisation.** All parameters start from one k-means
   clustering read as a hard-assignment state path — centres as means,
   per-cluster scatter as covariance, label transitions as the transition
   matrix. The usual random Dirichlet draw ignores the data, and on the
   `K=8` and `K=3 F=2` rows above that is exactly why the reference needs 16 to
   116 maps and still lands on a **worse** likelihood: it merged states.
3. **SQUAREM acceleration** (on by default), which pays for itself only where EM
   crawls — the `sep=0.15` and `sep=0.1` rows, where it halves the work. On
   easy targets it costs a few extra maps (a cycle is three of them), which is
   why the plain-EM row is there for comparison.

## Ensemble samplers

`chisurf.core.fitting.ensemble` — the affine-invariant ensemble samplers behind
parameter-uncertainty estimation.

Steps per second is meaningless here: a slice step costs several
log-probability evaluations but travels much further than a stretch step. The
comparable units are **effective samples per second** and **per
log-probability evaluation** (the latter is what matters once the target is a
real fit rather than an analytic density, because then one evaluation is one
model computation).

The target is a Gaussian whose condition number κ sets how correlated it is.

| target | sampler | ESS/s | ESS/eval | ESS (min) | wall [s] |
| --- | --- | ---: | ---: | ---: | ---: |
| 4-D Gaussian, κ=1 | stretch | 2,290 | 0.0115 | 367 | 0.16 |
| 4-D Gaussian, κ=1 | slice (differential) | 2,438 | 0.0178 | 2,798 | 1.15 |
| 4-D Gaussian, κ=1 | slice (adaptive covariance) | 2,678 | 0.0197 | 3,106 | 1.16 |
| 8-D Gaussian, κ=100 | stretch | 1,094 | 0.0036 | 228 | 0.21 |
| 8-D Gaussian, κ=100 | slice (differential) | 1,507 | 0.0085 | 2,606 | 1.73 |
| 8-D Gaussian, κ=100 | slice (adaptive covariance) | 2,169 | 0.0109 | 3,358 | 1.55 |
| 16-D Gaussian, κ=100 | stretch | 620 | 0.0017 | 213 | 0.34 |
| 16-D Gaussian, κ=100 | slice (differential) | 1,206 | 0.0044 | 2,700 | 2.24 |
| 16-D Gaussian, κ=100 | slice (adaptive covariance) | 1,409 | 0.0052 | 3,201 | 2.52 |

**Reading the table.** The gap grows with the correlation: on the isotropic
4-D target the covariance move buys 1.7× over the stretch move per evaluation,
on the correlated 16-D target 3.1×. That is the whole argument for learning the
covariance — and the reason the adaptive move is the default for
higher-dimensional posteriors.

## 2D-MFD: recovering a known exchange rate

`test/benchmarks/benchmark_mfd_engines.py`. The work unit is **one fit**, and the
quality reported next to it is the **bias and RMSE of the recovered exchange
rate** against the rate that generated the photons — not a deviance, which every
setting can lower by explaining the data differently.

The arbiter is neither implementation. Photons come from tttrlib's confocal
simulator and go through the same burst tables, reader and response estimation a
measurement does. Everything but the rate is pinned at truth, so whatever the
model gets wrong has nowhere to hide but the one free parameter.

| rate (Hz) | bias | RMSE | s/fit |
|---|---|---|---|
| 200 | +0.4% | 7.1% | 13.3 |
| 1000 | −7.8% | 8.6% | 19.0 |
| 5000 | −2.6% | 3.3% | 20.2 |

Three seeds per cell, so differences of a few percent in RMSE are not resolvable
and should not be read as ordering.

**Reading the table.**

* **The window assumption is the big one.** Taking a burst's span as the window
  over which its state averaged costs 18–33%, growing with the rate, and it is
  the only row that is wrong in the same direction everywhere. Correcting it is
  free or better in time, because a shorter window needs fewer transfer-matrix
  slices.
* **The Monte Carlo does not supersede the analytic path.** It is faster where
  exchange is slow (7.3 s against 13.3 at 200 Hz) and both slower and more biased
  where it is fast (45.8 s, +15.3% at 5 kHz), so it does not dominate the
  RMSE-vs-time front. It stays as the independent second opinion it was written
  to be, and nothing is retired.
* **Occupancy weighting looks competitive and is not.** It wins at 1 kHz (−0.5%
  against −7.8%) and ties at 5 kHz, then fails at 200 Hz (+19.9%). Green
  weighting is *provably* exact — conditioned on being a donor photon, a state's
  share is `f_s(1 − p_s)` normalised, not `f_s` — so this is compensation between
  two errors rather than a better model, and compensation that holds at one
  timescale is worth less than correctness at all of them.

The residual −7.8% at 1 kHz is a known limitation, not noise: the effective
window uses one scale for the whole measurement, while the ratio has a spread of
0.15 and tracks burst brightness (0.85 dim, 0.76 bright). Per nuisance cell would
capture it, and the measure is already binned by signal.

**How much the window correction is worth depends on the measurement**, and the
table above is not an upper bound on how little it can matter. It is computed
from the bursts' own arrival times, so a measurement whose bursts are evenly lit
gets a scale near 1 and is barely touched. The table uses truth-defined bursts;
repeating the 5 kHz cell with bursts found by the real search gives a scale of
0.729 against 0.694 and −28.0% → −2.1% against −34.1% → −3.5%, so the search does
not undo it. But on the real BH SPC-132 DNA measurement the scale is 0.95 at
5 kHz and 0.99 at 1 kHz — its bursts are far more uniformly lit than the
simulator's — and there the correction is a small one. Read the scale on your own
data rather than expecting the table's shift.

## Adding a component

A benchmark belongs here when a component is (a) on a path a user waits for, and
(b) something ChiSurf implements rather than calls. Write the script under
`test/benchmarks/benchmark_<component>.py` following the two above:

* a `run(...)` returning records **and** printing a markdown table,
* a fixed, seeded synthetic input so the numbers are reproducible,
* a `slow`-marked test asserting the property the benchmark protects,
* a module docstring that names the work unit and says why it is the fair one.

Then add a section here, and link it from the component's own documentation.
