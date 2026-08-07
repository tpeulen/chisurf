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
