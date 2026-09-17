---
type: Guide
title: Number & Brightness
description: Map molecule number and brightness per pixel from a confocal image stack with the Number & Brightness step of Image Tools — corrections, analog calibration, gating a brightness population back onto the image, cross N&B, and the same analysis from the command line and Python.
tags: [guides, imaging, brightness, oligomerization]
---

# Number & Brightness

:::{admonition} Theory
:class: seealso
The moments, the $-1$, analog detectors, cross N&B and what bleaching does are in
{ref}`concept-number-and-brightness`.
:::

## What it is

**Spectroscopy → Image Tools → 2. Number & Brightness** computes, for every
detector window of the imaging setup, the per-pixel apparent brightness $B$ and
number $N$, the molecular brightness $\varepsilon$ and the molecule number $n$
of a confocal photon stream with many frames. The maps go to the imaging HDF5
beside the other per-pixel results; a parameter plane with gate regions picks
out a brightness population and shows where it sits in the image.

## Try it on data whose answer is known

Press **🧪 Load demo**. It writes a simulated scan as an ordinary PTU file —
monomers ($\varepsilon = 0.5$ counts per dwell, $n = 6$) on the left half, dimers
($\varepsilon = 1.0$, $n = 3$) on the right, both halves equally bright — and
runs the analysis. The **Guide** button walks through the same steps.

The intensity map is uniform. The **Brightness ε** map is not:

```{figure} figures/nb_brightness_map.png
:alt: Number & Brightness tool showing the molecular-brightness map of the demo, dim left half and bright right half
:width: 100%

Molecular brightness of the demo: about 0.5 on the monomer half, 1.0 on the dimer half, at the same intensity.
```

On the **Parameter plane** (intensity horizontally, $B$ vertically) the two
species are two clouds at the same intensity, $B \approx 1.5$ and $B \approx 2.0$.
Draw a rectangle round the upper cloud with the rectangle button of **Gate
regions**; **Gated pixels** then shows the right half, and the status box reports
the gated pixels' median $\varepsilon \approx 1.0$ and $n \approx 3$.

```{figure} figures/nb_parameter_plane.png
:alt: Parameter plane of intensity versus apparent brightness with a gate rectangle over the dimer population
:width: 100%

The parameter plane with a gate over the brighter population.
```

## Settings, in the order they matter

1. **Stack corrections.** Anything that fluctuates besides the molecule number
   inflates $\varepsilon$. *Detrend segments* removes photobleaching (a line per
   pixel per segment, the mean put back, the lost degrees of freedom accounted
   for). *Subtract* / *Add back* remove immobile structure and slow drifts —
   subtract the pixel mean or a moving average, then add the total or pixel mean
   back, because $B$ divides by it.
2. **Detector.** For bright samples set the *dead time* and the *pixel dwell*.
   For an analog detector load a static-gradient calibration file, **Run**, press
   **📐 Calibrate analog** (it fills *Gain S* and *Offset*), then load the
   measurement. *Read variance* comes from a dark measurement.
3. **Estimator.** *Shape factor γ* is 1 for the values as Digman et al. define
   them and 0.3536 for the γ-corrected values other packages report. *Moment
   smoothing* (average, disk or Gaussian of *Radius*) trades resolution for a
   less noisy map; *Median filter* removes single hot pixels from ε and n.
4. **Cross N&B.** Pick a second window in *Cross with* to get the cross
   brightness and number maps; $B_\text{cross} \approx 0$ means the two labels
   move independently.

**➕ Add N&B to HDF5** writes `N`, `B`, `epsilon`, `n`, `mean` and `variance`
per window; **🧭 ndX** explores them together with the other per-pixel columns.

## Headless

```bash
img-pixel-nb scan.ptu -c 0 --detrend 5 --gamma 0.3536 --smoothing average --radius 3 -o scan.imaging.h5
```

```python
import tttrlib
from chisurf.core.fluorescence.imaging import (
    build_clsm, nb_pipeline, ccnb_maps, nb_gate_mask, analog_calibration,
)
from chisurf.core.roi import RectangleROI

stack = build_clsm(tttrlib.TTTR("scan.ptu"), channels=(0,)).get_intensity()
maps = nb_pipeline(stack, {"detrend_segments": 5, "gamma": 1.0})
dimers = nb_gate_mask(maps["mean"], maps["B"], RectangleROI(0, 1.75, 100, 3))
```

`nb_maps` takes the detector (`gain`, `offset`, `read_variance`, `dead_time`,
`pixel_dwell`) and estimator (`gamma`, `smoothing`, `radius`, `median`, `ddof`)
settings directly; `ccnb_maps(stack_a, stack_b)` is cross N&B;
`analog_calibration(mean, variance)` fits the gain and offset.
