# Particle tracking: from spots to a diffusion coefficient

This tool follows individual particles through a movie and turns their
trajectories into a **diffusion coefficient**. It runs in three stages — detect,
link, analyse — each of which fails in its own way, which is why each is exposed
separately.

For the theory, and for what tracking genuinely cannot tell you, see
{ref}`concept-particle-tracking`.

## Open the tool

**Microscopy → Imaging → Particle Tracking**, or as the **Tracking** panel of
{doc}`Image Tools <24_scan_images>`, where it sits after *Drift* — a drifting
sample looks exactly like directed motion, and no amount of tracking separates
the two afterwards.

```{figure} figures/tracking_workspace.png
:name: fig-tracking-workspace
:width: 100%

Tracked on a simulated movie with known kinetics: 8 particles at
D = 0.5 px²/frame. The tool recovers 8 tracks of the full 60 frames and
D = 0.504 ± 0.1 — and still prints a *"Read with care"* note, because eight
tracks is not many. The Movie view marks every detection; scrub the frame slider
and they should follow the particles.
```

## Start with a simulation

Before touching real data, tick **Simulate** and set the diffusion coefficient,
particle count and signal level to resemble what you expect. This is the only way
to know the right answer, and the fastest way to learn what your frame rate and
particle density can actually resolve.

If the tracker cannot recover a known D from a simulation resembling your data,
it will not recover an unknown one from the real thing — and you will find that
out in minutes instead of after a week of imaging.

## 1. Detect

Choose the detector and threshold, then read **detections per frame** in the
report. This is the cheapest diagnostic in the tool and it catches most problems:

| what you see | what it means |
| --- | --- |
| far more detections than particles | threshold too low — you are tracking noise |
| markers flicker on and off between frames | threshold too high |
| markers sitting on empty background | threshold too low, or **Min area** = 1 |

Then scrub the frame slider on the **Movie** view and watch. Markers that travel
with the particles mean detection is working; nothing else needs checking.

**Wavelet** is the default and the right choice almost always: a multiscale
product that removes the background and rejects single hot pixels without any
intensity threshold. **Quantile** is cheaper but needs bright, well-separated
spots on a flat background.

**Min separation** collapses two detections closer than the point-spread function
to the brighter one. Spots that close cannot be told apart anyway, and admitting
both invents a particle for the linker to mis-assign.

## 2. Link

**Max step** is the whole safety margin. Set it from the physics — a Brownian
particle moves about `sqrt(4·D·dt)` per frame — not from what makes the tracks
look longest. That temptation is exactly the failure mode: a generous linking
distance produces long, beautiful, wrong tracks.

**Max gap** lets a track bridge frames where the particle was missed. Every
closed gap asserts that no other particle could have been there, so keep it at 1
or 2 and check what changing it does to D.

```{figure} figures/tracking_trajectories.png
:name: fig-tracking-trajectories
:width: 100%

The Trajectories view, drawn in image coordinates so it overlays the Movie view.
Eight compact random walks, none jumping across the field — that is what correct
linking looks like. **A track that leaps abruptly from one region to another is
an identity swap**, and each one invents a displacement that never happened and
inflates D.
```

:::{warning}
**Crowding breaks tracking, not the algorithm.** When two particles come within
the linking distance of one another, the assignment is genuinely ambiguous and
no method can resolve it from positions alone. In simulations where 10 % of
particles had a neighbour that close, up to a quarter of the tracks merged two
different particles and D scattered over a factor of two.

The remedy is experimental: label more sparsely, or image faster so the linking
distance shrinks. Check the **Track lengths** view — a distribution piled up at
the shortest lengths means linking is shattering trajectories.
:::

## 3. Analyse

Set **Pixel size** and **Frame interval** and D comes out in µm²/s; leave them at
1 and it is in pixels² per frame. Nothing else changes.

**Min track length** is a bias correction, not tidiness. A particle is likelier
to be found twice in a row if it happened to stay put, so the shortest tracks
over-represent the slowest motion.

**Leave "Fit anomalous exponent" off** unless the question genuinely is whether
the motion is anomalous. D and α are nearly degenerate — a fit too high in one is
too low in the other and the curve still fits — and fitting both roughly
quadruples the spread of D. When you do fit it, read α's error bar before
concluding anything: α = 1.17 ± 0.12 does not distinguish normal diffusion from
mild superdiffusion.

Read the **MSD** view. On log axes free diffusion is a straight line of slope 1;
a flattening tail is confinement, an upward curve is directed motion, and a
constant floor at short lag is the localisation error.

### The error bars, and why they are bootstrapped

They come from resampling whole tracks, not from the fit covariance — and that is
not a refinement. Least-squares covariance assumes independent residuals, and MSD
points at different lags are built from overlapping displacements of the same
trajectories. Measured against simulations with a known D, the covariance error
bar covered the truth in 4 runs out of 20. Resampling tracks gives 20 out of 20.

The report ends with **"Read with care"** notes whenever the numbers should not
be taken at face value — too few tracks, a large relative error, an unresolved α.
Read them before quoting anything.

## Headless

```bash
img-tracking movie.tif --channel 0 \
             --pixel-size 0.107 --frame-interval 0.05 \
             --max-distance 5 --max-gap 1 --min-track-length 10 \
             --tracks-csv tracks.csv --output transport.json
```

and, to find out what a photon budget can resolve before spending beam time:

```bash
img-tracking --simulate --sim-diffusion 0.5 --sim-particles 8 \
             --sim-frames 60 --max-distance 4
```

`--as-json` prints the whole result for a script to consume, and the command
**exits non-zero when no transport fit was possible**, so it can gate a pipeline
rather than silently emitting nothing. The same operations are available as RPC
methods (`img_tracking.jobs.track`, `img_tracking.jobs.simulate`).

`--tracks-csv` writes one row per linked detection (`track, frame, y, x,
intensity`), which is the form to take into your own analysis.

## Using it well

* **Correct drift first** ({doc}`43_drift_correction`). Drift is
  indistinguishable from directed motion.
* **Sweep the linking distance.** If D changes materially between two plausible
  values, the linking is doing the deciding, not the data.
* **Look at the trajectories before believing the number.** One swapped identity
  is invisible in the report and obvious in the plot.
* **A single D from a heterogeneous sample is a weighted average**, and the
  weighting depends on track lengths. Two populations need to be separated before
  they mean anything.
