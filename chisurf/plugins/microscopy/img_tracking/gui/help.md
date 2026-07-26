# Particle tracking

Follows individual particles through a movie and turns their trajectories into a
**diffusion coefficient**. Three stages, each of which fails in its own way, so
each is exposed separately: **detect**, **link**, **transport**.

## What it answers

* How fast do the particles move — `D`, with an error bar.
* Is the motion ordinary diffusion, confined, or directed — the anomalous
  exponent `α`.
* How precisely is a single particle localised — `σ`, which comes out of the fit
  for free.

## The three stages

### 1. Detect

Particles are found in every frame independently. The **wavelet** detector is a
multiscale product: it suppresses the background and rejects single hot pixels
without any intensity threshold, and holds up at low signal-to-noise. The
**quantile** detector thresholds the raw frame and is cheaper, but needs bright,
well-separated spots on a flat background.

**Check the detections per frame** in the report against what you expect. This is
the cheapest diagnostic in the whole tool and it catches most problems:

| symptom | cause |
| --- | --- |
| far more detections than particles | threshold too low; noise is being tracked |
| markers flicker on and off | threshold too high |
| detections on empty background | threshold too low, or `Min area` = 1 |

Scrub the frame slider on the **Movie** view: markers that follow the particles
mean detection is working.

### 2. Link

Which detection in the next frame is the same particle? Solved as a global
assignment rather than nearest-neighbour, because when two particles approach
each other both can claim the same neighbour and the answer would depend on
iteration order.

**`Max step` is the whole safety margin.** Set it from the physics — a Brownian
particle moves about `sqrt(4·D·dt)` per frame — never from what makes the tracks
look longest. Too large and distinct particles get joined; too small and every
trajectory shatters.

**Crowding is what breaks tracking**, not the algorithm. When particles come
within the linking distance of one another the assignment is genuinely
ambiguous. In simulations where 10 % of particles had a neighbour inside the
linking distance, up to a quarter of the tracks merged two different particles
and `D` scattered by a factor of two. On a sparse field the same code recovers
identity exactly. If you cannot make the field sparser, image faster: the linking
distance shrinks with the frame interval.

Look at the **Trajectories** view. A track that jumps abruptly across the field
is an identity swap, and each one invents a displacement that never happened.

### 3. Transport

The mean squared displacement is fitted with

```
MSD(τ) = 4·D·τ^α + 4·σ²
```

Three things about that formula are worth knowing:

**The offset is not optional.** `σ` is the localisation uncertainty and adds a
constant to every lag. Fit without it and that constant lands in `D`, inflating
it — badly for slow particles.

**Only short lags are used.** The MSD at lag *n* of a track of length *N*
averages just *N−n* overlapping displacements, so the tail is noisy and
correlated. A quarter of the lags is the default.

**`D` and `α` are nearly degenerate.** A fit too high in one is too low in the
other and the curve still passes through the points. Fitting both roughly
quadruples the spread of `D`. Leave **Fit anomalous exponent** off unless the
question genuinely is whether the motion is anomalous — and then read `α`'s error
bar before concluding anything from it.

## The error bars

They come from **resampling whole tracks**, not from the fit covariance. That is
not a refinement: `curve_fit`'s covariance assumes independent residuals, and MSD
points at different lags are built from overlapping displacements of the same
trajectories. Measured against simulations with a known `D`, the covariance error
bar covered the truth in 4 runs out of 20. Resampling tracks gives 20 out of 20.

The report lists **"Read with care"** notes whenever the numbers should not be
taken at face value — too few tracks, a large relative error, an unresolved `α`.
They are worth reading before quoting anything.

## Simulate first

Tick **Simulate** and the tool generates a movie of Brownian particles with a `D`
you choose. This is the honest way to find out what your frame rate, particle
density and signal level can actually resolve, and the only way to know the right
answer while you learn to read the output. If the tracker cannot recover a known
`D` from a simulation resembling your data, it will not recover an unknown one
from the real thing.

## Units

Leave **Pixel size** and **Frame interval** at 1 to work in pixels and frames.
Set them and `D` comes out in µm²/s and `σ` in µm. Nothing else changes.

## Caveats

* Tracking runs on **one channel**. Combining channels first would blur the spots
  it has to localise; colocalisation between channels is a different question.
* **Short tracks are biased, not merely noisy.** A particle is likelier to be
  found twice in a row if it happened to stay put, so the shortest tracks
  over-represent the slowest motion. That is what `Min track length` is for.
* **Gap closing asserts that nothing else could have been there.** Keep
  `Max gap` small and check what changing it does to `D`.
* A **drifting sample** looks like directed motion. Correct drift first
  (Image Tools → Drift) — this tool cannot tell the two apart.
