---
type: Guide
title: 'Pair correlation and flow maps: measuring where molecules go'
description: RICS gives you a diffusion coefficient. This guide is about the two questions it cannot answer — which way is the sample moving, and is this place connected to that one…
tags: [guides, correlation, diffusion]
---

# Pair correlation and flow maps: measuring where molecules go

RICS gives you a diffusion coefficient. This guide is about the two questions it
cannot answer — *which way* is the sample moving, and *is this place connected
to that one* — and the two analyses that do: the pair correlation function
(pCF), and the velocity field that turns a stack into a quiver plot of arrows.

For the theory — what the peak time means, why a barrier deletes it, and what
limits the arrows — see {ref}`concept-pair-correlation`.

## The tool

Velocity fields have their own tool: **Spectroscopy → Image Tools → Flow**, or
standalone as **Imaging → Flow Maps**. It maps a TIFF stack or a photon stream
into one arrow per tile, with no model and no fit — the velocity is read off
where a correlation peak *is*.

If you have never run one, press **Guide** in its toolbar. The tour simulates a
scan whose flow profile is known — laminar flow through a channel, fastest in
the middle and zero at the walls — and walks you through checking the answer
against it. It points at the real buttons and waits for you to press them.

```{figure} figures/flow_tool.png
:name: fig-flow-tool
:width: 100%

The flow-map tool on its own demo. Left: the settings, in workflow order. Right:
the headline numbers, the arrows over the time-averaged image, and the profile
across the frame with the simulated truth drawn beside it — which is how the
20 % shear bias becomes visible rather than theoretical.
```

Headless, the same thing:

```bash
img-flow demo                  # simulate a scan whose flow profile is known
img-flow map scan.ptu --tile 24 --lags 5 --pixel-size 100 --json
```

The rest of this guide is the Python API the tool, the CLI and the RPC service
all sit on. The region-averaged pair correlation needs none of it — it is
already reachable from any carpet the
{doc}`image-correlation reader </concepts/image_correlation>` produces, through
`IcsCarpet.pcf_curve`.

## Which route to use

| you want | use | resolution |
| --- | --- | --- |
| one pCF curve from a region you already correlated | `IcsCarpet.pcf_curve(δ)` | none (region-averaged), lags quantized to the frame time |
| pCF resolved by position — barriers, compartments | `pcf_from_stack` / `pcf_from_kymograph` | one pixel; lags down to the line time |
| a 2-D velocity field, arrows on the image | `stics_flow_map` | the tile size |
| a 1-D velocity profile along the fast axis | `pcf_flow_map` | one pixel, but `vx` only |

## The cheap reading: a pCF curve from a carpet you already have

`IcsCarpet` exposes the pair correlation as a fifth reading beside `rics_map`,
`stics_map` and `tics_curve` — the carpet column a distance away instead of the
one at zero:

```python
from chisurf.core.experiments.ics import (
    IcsSettings, IcsTiming, compute_ics_carpet,
)

timing = IcsTiming(pixel_duration_us=10.0, line_duration_ms=0.32,
                   frame_duration_ms=10.24, pixel_size_nm=100.0)
carpet = compute_ics_carpet(
    stack, IcsSettings(frame_lags=tuple(range(8)), timing=timing)
)

tau, g = carpet.pcf_curve(+4)          # 4 pixels downstream
tau, g_back = carpet.pcf_curve(-4)     # 4 pixels upstream
```

`pcf_curve(0)` is exactly `tics_curve()`. Two limits come with it, and both are
why the position-resolved route below exists: the carpet is built by an FFT over
space, so every position in the region has been averaged together, and its time
axis only takes values that are multiples of the frame time.

## The real thing: position-resolved pCF

```python
from chisurf.core.experiments.ics import pcf_from_stack

carpet = pcf_from_stack(
    stack,
    deltas=(0, +6, -6),      # include both signs — the sign *is* the direction
    timing=timing,
    n_segments=8,            # the scatter between segments is the error bar
    detrend=True,            # bleaching correction, amplitude included
)

carpet.map(+6)               # (n_positions, n_tau) — the classic pCF carpet
carpet.curve(+6, position=20)          # (tau, g, error) at one position
carpet.transit_time(+6)                # seconds per position, NaN where no peak
carpet.velocity(6)                     # signed µm/s per position, from ±6
```

Read the carpet as an image with position running down and $\log\tau$ across. A
barrier is a **horizontal band where the arrival ridge is missing** while the
rows above and below it are unremarkable:

```{figure} figures/pcf_barrier.png
:name: fig-pcf-barrier
:width: 100%

A simulated line with an impermeable wall at pixel 32, drifting at 0.25 px per
line on the left and 0.125 on the right. The pair correlation reads 23.9 ms and
47.9 ms against a truth of 24 and 48, and reports neither across the wall — while
the mean intensity (grey, right panel) is flat and the local autocorrelation
(dashed, third panel) is normal.
```

### Choosing δ

$\delta$ is the one setting that matters. Too small and the transit time falls
below the sampling period; too large and molecules do not survive the trip, so
the peak drowns. Start from the transport you expect:

- **flow**: $\tau_\mathrm{max} = \delta a / v$ — pick $\delta$ so this is 10–100
  sampling periods;
- **diffusion**: $\tau_\mathrm{max} = (\delta a)^2/4D$ — the same target, but it
  grows as $\delta^2$, so the usable window is narrower than it looks.

Then confirm the physics by running **two or three distances**: a flow peak
moves as $\delta$, a diffusive one as $\delta^2$. That comparison is worth more
than any single fitted number.

### A line scan

`pcf_from_stack` flattens a raster stack into one time series per pixel sampled
once per line. For a genuine line scan, feed the kymograph directly:

```python
from chisurf.core.experiments.ics import pcf_from_kymograph

carpet = pcf_from_kymograph(intensity, deltas=(0, 4, -4), timing=timing,
                            time_unit="line")
```

`intensity` is `(n_time, n_positions)`. Set `time_unit` to whatever one row
actually is — `"line"`, `"frame"` or `"pixel"` — because that is what every lag
is measured in, and getting it wrong rescales every transit time silently.

## The arrows: a velocity field

```python
from chisurf.core.experiments.ics import stics_flow_map

field = stics_flow_map(stack, tile=16, step=8, frame_lags=range(0, 5),
                       timing=timing)

x, y, vx, vy = field.quiver(min_quality=0.6)   # µm and µm/s, ready to plot
field.summary(min_quality=0.6)                 # mean speed, direction, coherence
```

```{figure} figures/pcf_flow_arrows.png
:name: fig-pcf-flow-arrows
:width: 100%

Four counter-rotating cells: the simulated field, the field recovered one tile at
a time, and every tile's two velocity components against the truth. Direction is
right to ±3°; magnitude reads 20 % low because the flow shears within a tile.
```

Plot it with any quiver:

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.imshow(stack.mean(axis=0), cmap="gray",
          extent=(0, nx * pixel_um, ny * pixel_um, 0))
ax.quiver(x, y, vx, vy, np.hypot(vx, vy), cmap="autumn")
```

### Settings that decide the answer

**`tile`** — several waists across. Smaller localizes the flow better but has
fewer molecules in it and less room for the peak to travel; larger averages
distinct flows into one arrow.

**`frame_lags`** — the peak has to stay inside the tile. Its displacement is
`v · lag · frame_time / pixel_size` pixels, so pick the largest lag to keep that
under about a third of the tile. If you overshoot, ChiSurf will tell you rather
than guess: rejected tiles come back as `NaN` and `field.meta["n_escaped"]`
counts them. A tile whose peak wrapped around the edge produces a confident,
well-fitted, *backwards* velocity, so this check is not optional.

**`min_quality`** — the threshold on `quiver`, and the one to raise when a map
looks too good. Peak jitter fitted to a straight line is always *some* velocity,
so an unfiltered map paints a convincing flow field onto a sample that has none.
0.5–0.7 is a reasonable working range; a still sample should lose most of its
arrows.

**`subtract_average`** — `"frame"` removes each frame's own mean, `"stack"` also
removes the time-averaged image, i.e. the immobile fraction. On a shearing flow
the difference was under 2 %, but on a sample with genuinely stuck material it
matters much more.

### The second route, for a cross-check

`pcf_flow_map` gets the same arrows from transit times rather than peak
positions. It shares no kernel with `stics_flow_map` — one goes through the
spatial correlator, the other through an FFT along time — so agreement between
them is real evidence:

```python
from chisurf.core.experiments.ics import pcf_flow_map

profile = pcf_flow_map(stack, distance=4, tile=16, timing=timing)
profile.vx      # (n_bands, n_pixels), µm/s; vy is identically zero
```

It is one-dimensional and per-pixel, which makes it the route for a flow profile
*across* a channel, and the only one that distinguishes "no transport" from
"slow transport".

## Sanity checks before you believe a map

1. **Does the sign survive a reversal?** If you can, acquire or simulate the
   same field flowing the other way; the arrows must turn round and nothing else
   should change.
2. **Do two distances agree on the physics?** Flow scales as $\delta$,
   diffusion as $\delta^2$.
3. **Does a still region lose its arrows?** Raise `min_quality` until an area you
   know is static goes blank; if it never does, the field is jitter.
4. **Did any tile escape?** `field.meta["n_escaped"]` should be 0. If not, shorten
   the lag range.
5. **Is the intensity flat where the pCF says "barrier"?** A dark line is an
   absent sample, not a wall.

## Regenerating the figures

```bash
pixi run -e docs python docs/guides/make_figures.py
```

The two figures on this page come from `fig_pcf_flow_arrows` and
`fig_pcf_barrier` there, which run the very functions described above on
phantoms whose velocity is known.

## See also

- Tool: **Flow Maps** (`chisurf/plugins/microscopy/img_flow/`).
