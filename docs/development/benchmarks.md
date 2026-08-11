---
type: Development Note
title: Benchmarks
description: Performance numbers for the compute cores ChiSurf owns.
tags: [development, benchmarks]
audience: developer
---

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

## WGSL compute on wgpu

**Work unit:** one element of `sqrt(x)*sin(x) + cos(x/2)` in float32, over an
array. Transcendental-heavy on purpose -- a kernel that only copies memory
measures the bus rather than the processor.

ChiSurf can and does run compute shaders (`chimol.renderer.compute`), and every
kernel there is guarded by a work-item floor (`MIN_WORK_ITEMS`) below which the
CPU route is taken. This table exists to justify that floor rather than assert
it, by separating the two numbers that get conflated:

- **kernel** -- dispatch and execute with the data already on the device. The
  honest number for a pipeline that keeps its buffers between passes.
- **round trip** -- allocate, upload, dispatch, read back. The honest number for
  anything called from numpy and returning to numpy.

```bash
pixi run python test/benchmarks/benchmark_wgpu_compute.py
```

Apple M1 Pro (Metal), wgpu 0.32.0. Limits: 1024 invocations per workgroup,
65535 workgroups per dimension, 32 kB workgroup storage.

| elements | kernel [ms] | round trip [ms] | numpy [ms] | kernel vs numpy | round trip vs numpy |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4,096 | 0.122 | 1.598 | 0.021 | 0.2x | 0.0x |
| 16,384 | 0.129 | 1.606 | 0.079 | 0.6x | 0.0x |
| 65,536 | 0.125 | 1.726 | 0.308 | 2.5x | 0.2x |
| 262,144 | 0.134 | 2.043 | 1.512 | 11.3x | 0.7x |
| 1,048,576 | 0.162 | 3.748 | 6.606 | 40.8x | 1.8x |
| 2,097,152 | 0.261 | 5.240 | 14.021 | 53.7x | 2.7x |

**What this says.** The kernel is flat to within a factor of two across three
orders of magnitude -- below about a million elements this GPU is not working,
it is being launched. Crossover against numpy is near **65k elements** with the
data resident, which is where `MIN_WORK_ITEMS = 20_000` comes from and is
roughly the right order for it.

**The round trip is a different question, and the answer is much less
flattering.** It carries about **1.6 ms of fixed cost** at every size -- buffer
allocation, submission, and the readback latency -- so a kernel that is handed
numpy and must return numpy does not break even until around a million
elements, and is still only 2.7x at two million. A guard tuned on the kernel
column will happily accept work that the round trip makes *twenty times
slower*. Anything designed around this has to either keep its buffers on the
device across several passes, or be doing far more arithmetic per byte than
this kernel does.

**A limit worth knowing before designing around it:** WebGPU allows at most
**65535 workgroups per dimension**, so a 1-D dispatch at 64 invocations each
tops out at 4.19 M elements. Past that a kernel must dispatch in 2-D. It is a
validation error, not a silent truncation -- but it is discovered at the first
large input rather than in development.

## ADPCM decode: numpy against a compute kernel

**Work unit:** one decoded sample of block-aligned IMA ADPCM
(`chisurf/gui/chigame/adpcm.py`), the codec the games' audio ships in.

The codec is sequential by construction -- every sample needs the predictor the
one before it left -- which looks like the worst possible fit for a GPU. It is
not, because the stream is cut into *independent* blocks: the sequential part is
the 505 steps inside one block, and thousands of blocks run at once. Both routes
are kept, and they are asserted **bit-identical**; a lossy codec that decoded
differently depending on which route ran would change the audio behind the
caller's back.

```bash
pixi run python test/benchmarks/benchmark_adpcm.py
```

Apple M1 Pro (Metal), wgpu 0.32.0.

| seconds | samples | blocks | numpy [ms] | wgsl [ms] | speedup | identical |
| ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 0.05 | 1,102 | 3 | 10.27 | 2.12 | 4.8x | yes |
| 0.2 | 4,410 | 9 | 9.94 | 1.67 | 6.0x | yes |
| 1.0 | 22,050 | 44 | 10.18 | 1.78 | 5.7x | yes |
| 5.0 | 110,250 | 219 | 10.90 | 2.08 | 5.2x | yes |
| 20.0 | 441,000 | 874 | 15.13 | 3.02 | 5.0x | yes |
| 80.0 | 1,764,000 | 3,494 | 28.31 | 6.38 | 4.4x | yes |

**The threshold this decided was the opposite of the guess.** `MIN_BLOCKS_FOR_GPU`
was set to 600 on the reasoning from the table above -- a dispatch costs ~1.7 ms
of fixed overhead, so short effects should surely stay on the CPU. The
measurement says **zero**: the GPU is ahead at every size, including a clip
three blocks long.

The reason is that *the numpy route has the larger floor*. It runs exactly
`BLOCK` vectorised steps regardless of the clip's length -- 505 of them -- and at
roughly 20 us of numpy call overhead per step that is ~10 ms even when the
arrays being operated on have three elements each. Its cost is set by the block
size, not by the audio:

| clip | blocks | numpy [ms] | per vectorised step |
| ---: | ---: | ---: | ---: |
| 0.05 s | 3 | 9.85 | 19.5 us |
| 80 s | 3,494 | 69.96 | 138.5 us |

A twenty-six-hundred-fold increase in work costs seven times the wall clock,
because most of the small case is Python-to-numpy overhead. This is the general
trap with "vectorise the inner loop": the vectorised axis has to be *wide* for
it to mean anything, and here its width is the number of blocks, which for a
sound effect is single digits.

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

## Density-based clustering (HDBSCAN)

`chisurf.core.ml.cluster.HDBSCAN` — density-based clustering of a burst or pixel
table. This replaced two external packages, `hdbscan` and `scikit-learn`, both
of which are the references it has to beat. See the
[concept page](../concepts/density_clustering.md) for the method and the
[OKF concept](../../okf/subsystems/machine-learning.md) for the implementation.

The work unit is a **complete clustering**: core distances, the
mutual-reachability spanning tree, the condensed tree and the excess-of-mass
selection. Three things move the number and only one of them is the sample
count:

* **`d`, the number of features**, decides how well the k-d tree prunes. A
  bounding box overlaps the query ball in more and more directions as `d` grows,
  so the search degrades towards a scan — gracefully, but it degrades.
* **`min_samples`**, the neighbour rank for the core distance, sets how loose the
  pruning bound is. Larger core distances prune less, so a more conservative
  clustering is also a slower one.
* **Whether the compiled kernel is present.** The in-tree numba fallback is
  `O(n²)` Prim and single-threaded by design (a `parallel=True` numba kernel
  would launch numba's thread pool and lock `NUMBA_NUM_THREADS` for the
  process). It is a row of the table so the gap is visible rather than assumed.

The cluster count is next to every time, because a clustering that disagrees is
not a comparison. Note the convention difference: `min_samples` counts the point
itself here and in scikit-learn, and does not in the standalone `hdbscan`
package, so the reference is called with one fewer.

**Environment for this table** — Apple M1 Pro, macOS 26.5.1 (arm64), Python
3.12.13, `min_cluster_size=15`, `min_samples=5`. Measured 2026-08-10 on a
machine that was **not idle** (load average ~30 from unrelated work), so read the
*ratios*, which are stable across runs, rather than the absolute seconds, which
are inflated by roughly a factor of three across every row alike.

| case | implementation | fit [s] | clusters |
| --- | --- | ---: | ---: |
| n=5,000 d=2 | chisurf | 0.019 | 20 |
| n=5,000 d=2 | hdbscan | 0.138 | 20 |
| n=5,000 d=2 | scikit-learn | 0.138 | 20 |
| n=5,000 d=2 | chisurf (no compiled kernel) | 0.152 | 20 |
| n=20,000 d=2 | chisurf | 0.097 | 82 |
| n=20,000 d=2 | hdbscan | 25.445 | 83 |
| n=20,000 d=2 | scikit-learn | 4.763 | 84 |
| n=20,000 d=2 | chisurf (no compiled kernel) | 5.979 | 82 |
| n=100,000 d=2 | chisurf | 1.018 | 1186 |
| n=100,000 d=2 | hdbscan | 2.772 | 1186 |
| n=100,000 d=2 | scikit-learn | 73.998 | 1188 |
| n=20,000 d=3 | chisurf | 0.061 | 60 |
| n=20,000 d=3 | hdbscan | 0.731 | 57 |
| n=20,000 d=3 | scikit-learn | 2.360 | 58 |
| n=20,000 d=3 | chisurf (no compiled kernel) | 3.120 | 60 |
| n=100,000 d=3 | chisurf | 0.634 | 275 |
| n=100,000 d=3 | hdbscan | 6.379 | 271 |
| n=100,000 d=3 | scikit-learn | 83.684 | 274 |
| n=20,000 d=8 | chisurf | 1.656 | 7 |
| n=20,000 d=8 | hdbscan | 5.056 | 8 |
| n=20,000 d=8 | scikit-learn | 8.942 | 7 |
| n=20,000 d=8 | chisurf (no compiled kernel) | 8.475 | 7 |
| n=20,000 d=16 | chisurf | 8.644 | 4 |
| n=20,000 d=16 | hdbscan | 8.679 | 4 |
| n=20,000 d=16 | scikit-learn | 25.952 | 4 |
| n=20,000 d=16 | chisurf (no compiled kernel) | 24.010 | 4 |

Read three things out of it:

1. **In the range a burst feature space actually occupies — two to eight columns
   — the compiled path is 3× to 262× ahead of `hdbscan`** and 5× to 130× ahead
   of scikit-learn. The extreme entries are where the reference implementations
   change strategy rather than where this one is clever: `hdbscan` switches
   algorithm somewhere between 20,000 and 100,000 points, which is why its
   20,000-point two-dimensional case is *slower in absolute terms* than its
   100,000-point one; and scikit-learn's Prim is `O(n²)` throughout, which is
   what the 84 s at 100,000 points is.
2. **At sixteen features it is a dead heat** (8.64 s against 8.68 s), where an
   earlier version of this kernel was 1.7× *behind*. What closed it was not the
   dual-tree traversal `hdbscan` uses — that was implemented and turned out
   slower here, because its shared candidate state confines it to one core — but
   moving the candidate comparison out of squared-distance space. That removed a
   square root per candidate from the inner loop and, incidentally, fixed a
   tie-break bug; see the [OKF concept](../../okf/subsystems/machine-learning.md).
3. **The compiled kernel is worth 3× to 60×** over the in-tree fallback, and the
   fallback is what runs when the photon library is not importable. Both produce
   identical labels; only the time differs.

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

{src}`test/benchmarks/benchmark_mfd_engines.py`. The work unit is **one fit**, and the
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

## TCSPC fitting: where a fit spends its time

**Work unit:** one complete fit from the default seed, via
`chisurf.core.fluorescence.decay_fit_model.build_lifetime_fit` /
`build_fret_fit` on a Poisson-sampled synthetic decay. Best of three, after a
throwaway fit so JIT compilation and first-call cache fills land outside the
measurement. Re-derive with
`PYTHONPATH=. python test/benchmarks/benchmark_fit_hot_path.py`.

Measured 2026-08-10.

| Channels | Model | Fit [s] | Evaluations | Per evaluation [µs] |
| ---: | --- | ---: | ---: | ---: |
| 1 024 | LifetimeModel | 0.013 | 109 | 117.7 |
| 1 024 | GaussianModel | 0.031 | 47 | 656.7 |
| 4 096 | LifetimeModel | 0.035 | 201 | 174.5 |
| 4 096 | GaussianModel | 0.204 | 118 | 1 725.5 |
| 16 384 | LifetimeModel | 0.082 | 187 | 439.5 |
| 16 384 | GaussianModel | 0.610 | 99 | 6 160.3 |

**Discard the first run in a fresh process — all of it, not just the first
row.** The table above replaces one taken from a cold process, in which *every*
cell was slow and the 16 384-channel `GaussianModel` read **2.983 s** against the
0.61 s it actually costs — a fivefold error, large enough to credit a later
change with a speedup it did not produce. The per-case warm-up inside the script
does not cover it: the contamination is process-wide (numba's on-disk cache and
the loader's own page cache), not per case. Take numbers from a second or third
run of the script in a warmed checkout, and if a change appears to move a fit by
more than a few percent, re-measure the *old* code in the same session before
believing it.

**Time a fit costs, and what to conclude from it.** The convolution is 40–60% of
a fit and is already the photon library's compiled SIMD kernel — `per` is the
default mode. Reading `Parameter.value` is the next largest item: 27 340 reads in
a 1 024-channel lifetime fit, more total time than the convolution's own body.
Everything else is small.

**Count the evaluations, not the iterations.** The optimiser's iteration count
treats a whole Jacobian sweep as one step, so it understates the work by roughly
the number of free parameters; `Convolve.convolve` is called once per model
evaluation and is the honest counter. Re-running an already-converged `Fit`
starts at the optimum and exits after a couple of dozen evaluations — about a
fortieth of a real fit — so a benchmark that reuses the fit object measures the
exit condition rather than the fitting.

### Is it numba?

No — and here that is not a small effect but the whole picture. A 1 024-channel
two-component `LifetimeModel` fit calls **no numba kernel at all**, which
`test_a_lifetime_fit_calls_no_numba_kernel` now pins. In a `GaussianModel` fit
the numba-backed kernels (`distribution2rates`, `rates2lifetimes_new`,
`combine_distributions`) come to about **4%** of the fit, while numba's own
dispatcher type-resolution (`numba/core/types/abstract.py:__hash__`, 1 470
calls) profiles *above* them.

That inversion is the argument: those kernels operate on arrays of
`2 * n_components` elements, and at that size the JIT dispatch costs more than
the arithmetic it dispatches to. Removing the decorator makes them faster.
Contrast [Reading a PDB](#is-it-numba) below, where the JIT premium is a real
but one-off 0.076 s — the cost of numba is per-call on small arrays and
per-process on large ones, and only the first kind is worth acting on.

## ChiMOL ray tracing

**Work unit:** one `ray` render — the call a user waits on after typing the
command. The scene build is excluded and measured separately by
`benchmark_chimol_representations.py`; what is timed here is turning an already
built scene into pixels.

The model is T4 lysozyme (**148L**, 1 314 atoms), which ships in the test data.
It is small as structures go, and that is the point: a molecule this ordinary
has to be fast, or nothing larger is usable.

```bash
pixi run python test/benchmarks/benchmark_chimol_ray.py
```

320×240 with 2×2 samples per pixel, before and after the tracer gained a
bounding-volume hierarchy:

| Representation | Geometry handed to the tracer | Exhaustive | BVH | Speedup |
| --- | --- | --- | --- | --- |
| cartoon | 39 252 triangles | 19.12 s | 0.126 s | 151× |
| sticks | 33 216 triangles | 8.96 s | 0.062 s | 144× |
| surface | 51 748 triangles | 35.00 s | 0.198 s | 177× |
| lines | 5 536 caps + tessellated shafts | 51.11 s | 0.152 s | 337× |
| spheres | 1 314 spheres | 0.32 s | 0.058 s | 5.6× |

A publication-sized cartoon — 1024×768 with 2×2 samples — went from **195 s to
0.30 s (651×)**.

**Why the numbers differ so much between rows.** The cost of a ray tracer
without an acceleration structure is the sample count times the *primitive*
count, so the ranking above is a ranking of triangle counts and nothing else.
`spheres` gains least because it is the one representation whose primitives were
already few: a space-filling model is drawn as one merged mesh, and the tracer
had previously been taught to recover the 1 314 spheres it was built from rather
than intersect its 210 240 triangles. That fix bought 380× for one
representation and could not generalise, because the triangles of a cartoon are
not secretly spheres. The tree makes the geometry irrelevant.

**Quality is unchanged, and that is the property the benchmark protects.** An
acceleration structure is the one optimisation that fails silently — a ray that
never visits the box holding a triangle draws whatever is behind it. Rendering
each representation through both tracers and differencing: cartoon, sticks and
surface come out **bit-identical**. `spheres` and `lines` differ in 3.6 % and
0.03 % of pixels, from a shadow defect the tree exposed rather than caused (the
nearest occluder is now taken, as PyMOL does when the shadow decay is on).

The scaling table the script prints second is the one to read after any change
here: the same picture at four resolutions, in microseconds per sample. With a
tree that figure is roughly flat; without one it climbs with the scene.

## ChiMOL interactive frames

**Work unit:** one `paintGL`, drained with `glFinish` so the number is the frame
and not the queue. Same model (148L), a real GL context, 1280×860.

| Representation | Vertices | Before | After |
| --- | --- | --- | --- |
| cartoon | 20 022 | 28.34 ms | 4.12 ms |
| sticks | 33 216 | 11.61 ms | 3.91 ms |
| spheres | 210 240 | 17.34 ms | 4.94 ms |
| lines | 5 536 | 4.75 ms | 4.04 ms |
| surface | 25 876 | **82.12 ms** | **4.25 ms** |

Surface went from 12 fps to 235 fps. The cause was not the geometry: every
frame, `paintGL` re-entered the scene builder — through a *colour* query the
sequence strip makes once per object — and rebuilt every representation, which
for a surface means a density grid, marching cubes, gradients and ambient
occlusion, sixty times a second.

**The measurement that found it is worth copying.** Frame time was **flat
against pixel count**: 8× the pixels cost the same milliseconds. That rules out
both fill and vertex work in one experiment and says the cost is fixed CPU work
per frame, which is what sent the search to the profiler rather than to the
shaders. Ask a frame to scale before assuming what it is spending on.

This also settles a question that looked open: **impostor geometry would not
help here.** With the rebuild gone, 210 240 vertices (spheres) cost 0.9 ms more
than 5 536 (lines), so trading vertices for fragment work — what a sphere or
cylinder impostor does — has about a millisecond to win at this scale. Impostors
remain the right answer for the models they were added for, where the count is
in the hundreds of thousands. The remaining ~3.9 ms floor is the 2-D sequence
strip's text, not the molecule.

## ChiMOL chrome: the panel that was a picture

**Work unit:** building one frame of in-viewport chrome — the object panel, the
sequence strip, the mouse-mode block — ready for the GPU. Median of 20, same
panel contents at every size, so the only variable is the viewport.

The old path rasterised the whole thing into a viewport-sized premultiplied RGBA
image with `QPainter` and uploaded it as a texture. The new one appends quads
that `wgsl/ui.wgsl` draws.

| Viewport | `QPainter` + image | Bytes uploaded | Quads | Bytes uploaded | Speed-up |
| --- | --- | --- | --- | --- | --- |
| 1280×860 | 2.94 ms | 4.4 MB | 1.31 ms | 107 KB | 2.3× |
| 1920×1080 | 4.10 ms | 8.3 MB | 1.40 ms | 107 KB | 2.9× |
| 2560×1720 | 6.71 ms | 17.6 MB | 1.37 ms | 107 KB | 4.9× |
| 3840×2160 | 10.06 ms | 33.2 MB | 1.42 ms | 107 KB | 7.1× |

**The speed-up column is the least interesting one.** What the table actually
says is that the two paths scale differently: the old cost tracks *viewport
area* — it is rasterising every pixel of a mostly-empty image — while the new
one tracks *content*, and the content does not change when the window does. At
4K that is 7× less CPU and **318× fewer bytes** across the bus per repaint.

That difference is why the old path could not simply be made faster. Painting it
cost 9.6 ms of a 21 ms frame on a quarter-million beads, so the panel was
repainted on a **timer** and allowed to lag rather than redrawn when it changed
— and the timer was bypassed entirely for any scene carrying labels, because
labels move with the camera and forced a repaint every frame. Once a frame of
chrome is ~1.4 ms and 107 KB, deciding whether to rebuild costs more than
rebuilding, so the cache, the staleness and the invalidation calls are gone and
the panel is simply always current.

A whole frame of chrome is 313–608 quads, measured across the four captured
states. The remaining ~1.4 ms is Python building them; it is flat in the
viewport and would fall again if it ever mattered, since the geometry for a
panel that has not changed is the same geometry.

## Reading a PDB

Measured 2026-08-06 on an M-series Mac, best of five after a warm-up, through
`chisurf.core.fio.structure.coordinates.read_coordinates` with `keep_water=True`
and `only_standard_residues=False` (what the viewer asks for).

| File | Atoms | IMP, before | IMP, after | Native (`radii="vdw"`) |
| --- | ---: | ---: | ---: | ---: |
| `148l.pdb` | 1 363 | 0.195 s | 0.151 s | **0.008 s** |
| `hGBP1_closed.pdb` | 9 315 | 1.393 s | 0.957 s | **0.025 s** |
| `1rtd.pdb` | 17 784 | 3.658 s | 1.566 s | **0.048 s** |

The native reader is **49x** faster than the improved IMP path and **50x** the
original. It is selected by `radii="vdw"`, which is a *policy* rather than a
default: see below.

**The parser was never the slow part.** A profile of the 1.39 s read attributes
**0.079 s** to `IMP.atom.read_pdb` — the actual file parsing — and the rest to
`convert_atoms`, the Python loop that turns IMP's hierarchy into ChiSurf's
structured array. Per atom it built *twelve* SWIG `ParticleAdaptor`s (a separate
`Atom`, `Residue`, `Chain`, `Mass` and **two** `XYZR` decorators), looked the
chain id and element name up again for every atom of the same chain, and
assigned a `Vector3D` straight into a numpy field — which falls back to the
**iteration protocol**, 37 260 calls into `Vector3D___getitem__` for 9 315
atoms, 0.548 s of the total. That last one is the same trap that cost 17 s of a
19.7 s RMF load the same week: it is a property of every SWIG sequence, not of
one binding.

Building each decorator once, caching the chain and element lookups, and
subscripting the vector three times gives the "After" column. The remaining cost
is still per-atom SWIG traffic, which is why the third column matters: a
fixed-column numpy parser reads the same file **110×** faster again, and needs
no IMP at all.

### Is it numba?

No, and it is worth having the number: over a plain `load` of `148l.pdb`, eight
`njit` kernels compile and the **JIT premium is 0.076 s of a 0.70 s load**.
Seven of the eight already wrote their machine code to disk (`cache=True`), so a
second run of the application pays nothing for them; the eighth,
`protein.atom_dist`, did not and now does. Re-derive with the dispatcher walk in
`build_tools/dev_utils` or by comparing a first and second load in one process.

## Burst diagnostics: what a repaint costs

The window a burst-selection session lives in was taking **0.29 s per repaint**
while the burst search behind it took 0.04 s — so the analysis was never the
thing anyone was waiting for. The work unit here is one repaint of one plot
widget (1500x400) holding a raw per-photon series, because that is what the
window pays on every settings change, tab switch and resize.

```bash
QT_QPA_PLATFORM=offscreen pixi run python test/benchmarks/benchmark_burst_plots.py
```

**Environment** — Apple M1 Pro, macOS 26.5.1 (arm64), Python 3.12.13,
pyqtgraph on Qt5. Measured 2026-08-07.

| points | pen width | antialias | viewport decimation | log y | s/repaint |
|---:|---:|:---:|:---:|:---:|---:|
| 66,000 | 1 | no | no | no | 0.014 |
| 66,000 | 2 | no | no | no | 0.062 |
| 66,000 | 1 | yes | no | no | 0.023 |
| 66,000 | 1 | no | yes | no | 0.007 |
| 66,000 | 2 | no | yes | no | 0.024 |
| 66,000 | 1 | no | yes | yes | 0.006 |
| 660,000 | 1 | no | no | no | 0.136 |
| 660,000 | 1 | no | yes | no | 0.010 |
| 660,000 | 2 | no | yes | no | 0.044 |

Three things the table says, in order of how much they matter:

**Viewport decimation is the whole game.** `setDownsampling(auto=True,
mode="peak")` with `setClipToView(True)` takes 660k points from 0.136 s to
0.010 s — **13x** — and, more usefully, makes the cost nearly independent of the
array: 66k and 660k differ by 40% once it is on, and by 10x when it is off. Qt
then lays out what is *visible* rather than everything, which is also what makes
zooming into 1% of a trace stop costing what drawing all of it costs. `peak`
keeps each bin's extremes, for the same reason
`chisurf.core.fio.decimate.thin_for_plot` is min/max-per-bin rather than a
stride: a stride aliases the bursts away, which is worse than slow.

**A pen one pixel wider costs 3-4x.** 0.014 -> 0.062 s undecimated, 0.010 ->
0.044 s decimated. A Qt pen wider than a pixel is not cosmetic — it strokes an
outline around the polyline — so a "selected photons" layer drawn at width 2 was
paying more than the layer beneath it. Colour already distinguishes the layers.

**Thinning the data is the smallest of the three**, which is the trap: it is the
obvious lever and it moves 0.136 -> 0.014 s (10x) only when the viewport
decimation is *off*. With it on there is almost nothing left to win. Both are
still worth having — `thin_for_plot` bounds what is handed to Qt at all (memory,
and the JSON that crosses an RPC boundary), the viewport bounds what Qt lays out
— but a session that decimates the arrays and leaves the viewport alone has
fixed the wrong half.

End to end on the bundled ten-file `.spc` measurement (1.79 M photons, 1099
bursts), with all three applied: a whole-window repaint went **0.293 s -> 0.023
s**, five repaints 1.75 s -> 0.11 s, and "analyze then display" 2.23 s ->
0.77 s.

## Adding a component

A benchmark belongs here when a component is (a) on a path a user waits for, and
(b) something ChiSurf implements rather than calls. Write the script under
`test/benchmarks/benchmark_<component>.py` following the two above:

* a `run(...)` returning records **and** printing a markdown table,
* a fixed, seeded synthetic input so the numbers are reproducible,
* a `slow`-marked test asserting the property the benchmark protects,
* a module docstring that names the work unit and says why it is the fair one.

Then add a section here, and link it from the component's own documentation.
