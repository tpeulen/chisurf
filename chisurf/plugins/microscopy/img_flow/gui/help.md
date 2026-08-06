# Flow maps — where the sample is moving

This tool produces **one velocity vector per place in the image**. There is no
model and no fit: the velocity is read off *where a correlation peak is*, not
off a parameter released in a transport model. That is what makes it a
measurement of transport rather than an interpretation of one.

If you have never run one, press **🧭** in the toolbar. The guided tour
simulates a scan whose flow profile is known and walks you through checking the
answer against it.

## The two estimators

**STICS** correlates each tile against itself a few frames later. Directed
transport carries the correlation peak away from zero lag by the distance the
sample travelled, so a straight line through the tracked peaks is the velocity
vector. Two-dimensional, direct, and blind to a flow too slow to shift the peak
at all.

**Pair correlation** asks a different question: correlate a position with the
position δ away and see *when* molecules arrive. The peak time is a transit
time, so the speed is δ/τ. One-dimensional along the fast scan axis, but
resolved down to the pixel — and it is the only one that can report **no
transport** rather than slow transport, which is what a barrier looks like.

They share no kernel. Agreement between them is real evidence.

## The three settings that decide the answer

**Tile size** is the spatial resolution of the map. Smaller localizes the flow
but holds fewer molecules and leaves the peak less room to travel; larger
averages distinct flows into one arrow. Several focus waists across is the usual
compromise.

**The lag range must keep the peak inside the tile.** Its displacement is
`v × lag × frame_time ÷ pixel_size` pixels. Overshoot and the correlation map,
being periodic, wraps the peak round to the opposite side — where the tracker
follows it happily and fits a straight line through a displacement that has
*changed sign*. Measured on a phantom flowing at 2 pixels per frame through a
16-pixel tile: the right magnitude, the wrong direction, and a respectable
R² of 0.7. Tiles where that happened are refused and counted; the summary says
how many.

**The scanner clock is the measurement.** The frame time and the pixel size are
what turn a peak displacement into µm/s. An inter-frame dead time that is not
accounted for, or a pixel size taken from the wrong objective, scales every
arrow by the same factor with nothing looking wrong.

## What the numbers mean

| number | reading |
| --- | --- |
| mean speed | over the tiles that passed the quality threshold |
| coherence | 1 = one direction everywhere, 0 = arrows at random |
| quality | goodness of the straight line fitted through the tracked peaks |
| refused tiles | the peak left the tile; shorten the lag range |

A **low coherence with a high mean speed** is a structured flow — a channel
profile, counter-rotating cells — not a failed measurement. Both low together
means there is no flow.

## What a flow map does not tell you accurately

**Where the flow shears inside a tile, the magnitude reads low.** Measured on a
simulated cellular flow: direction correct to ±3°, correlation r = 0.996, and
the speed **20 % low**. On a uniform flow the same estimator is accurate to a
few percent, and shrinking the tile does *not* remove the bias — the correlation
peak of a deforming pattern is smeared as well as displaced.

Read a flow map as a reliable picture of **where the sample is going** and a
conservative estimate of **how fast**. The demo makes this concrete: its
simulated channel has a peak speed of 2 µm/s and the tool reports about 1.5.

**Sub-pixel drift needs the Gaussian estimator**, which is the default. A centre
of mass over a window narrower than the peak locks to whole pixels and
overstated the velocity by 19 % at 0.2 pixels per frame.

## Before you believe a real map

1. **Did any tile escape?** The summary says so. Shorten the lag range.
2. **Does a region you know is static go blank** when you raise the quality
   threshold? Peak jitter fitted to a line is always *some* velocity, so an
   unfiltered map paints a convincing flow field onto a sample that has none.
3. **Does the other estimator agree?** They share no kernel.
4. **Does reversing the flow reverse the arrows?** Nothing else catches a
   mirrored axis, and a mirrored axis inverts the physics while every number
   stays plausible.

## Headless

```bash
img-flow demo                       # simulate a scan with a known flow profile
img-flow map scan.ptu --tile 24 --lags 5 --pixel-size 100 --json
img-flow methods                    # what each estimator can and cannot see
```

The GUI, the CLI and the RPC service (`img_flow.map.compute`) all take the same
path through `chisurf.plugins.microscopy.img_flow.core`.

## Further reading

Documentation links open in the ChiSurf documentation browser; the references
open in your web browser.

* [Pair correlation and flow maps — the theory](docs/concepts/pair_correlation.md)
* [Image correlation: RICS, STICS, TICS and iMSD](docs/concepts/image_correlation.md)
* [Pair correlation and flow maps — the workflow](docs/guides/55_pair_correlation.md)
* [Planning a scan: which dwell time measures D best?](docs/guides/45_scan_precision.md)
* {cite}`hebert2005`
* {cite}`digman2009`
