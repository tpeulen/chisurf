# Number & Brightness

Number & Brightness (N&B) measures, pixel by pixel, **how many molecules** are in
the observation volume and **how bright each one is**, from the frame-to-frame
fluctuations of an image stack (Digman et al. 2008). It needs many frames of the
same field, recorded fast enough that molecules move between frames and slow
enough that they do not move within one pixel dwell.

## What is computed

For every pixel, over the frames, the mean ⟨k⟩ and variance σ² give

| map | formula | meaning |
| --- | --- | --- |
| B | σ²/⟨k⟩ | apparent brightness; 1 for immobile or Poisson-only pixels |
| N | ⟨k⟩²/σ² | apparent number |
| ε | (B − 1)/γ | molecular brightness, counts per pixel dwell per molecule |
| n | γ⟨k⟩/(B − 1) | molecule number |

An **analog** detector with gain S, offset k₀ and read-noise variance σ₀² uses
I = ⟨k⟩ − k₀ and V = σ² − σ₀²: B = V/I, ε = (V − S·I)/(S·I)/γ, n = γ·I²/(V − S·I).
γ is the observation-volume shape factor: 1 reports the values as Digman et al.
define them, 1/√8 = 0.3536 (3-D Gaussian) gives the γ-corrected values.

**Cross N&B** between two detector windows uses the covariance C:
B_cross = C/√(⟨a⟩⟨b⟩) — without −1, because shot noise does not correlate
between detectors — and N_cross = ⟨a⟩⟨b⟩/C.

## Workflow

1. **Load a file** (or press **🧪 Load demo**). The step-0 detector setup decides
   which windows are analysed; every window is computed.
2. **Correct the stack.** Bleaching and immobile structure add variance that is
   not number fluctuation: use *Detrend segments* for bleaching, *Subtract* /
   *Add back* for immobile structure and drifts. Always add a mean back after
   subtracting one — B divides by it.
3. **Set the detector.** Dead time (with the pixel dwell) for bright samples; for
   an analog detector, image a static gradient, Run, and press
   **📐 Calibrate analog**.
4. **Run**, then read the ε and n maps.
5. **Gate.** Draw regions on the *Parameter plane* (default intensity versus B);
   *Gated pixels* shows where that population is in the image.
6. **Add N&B to HDF5** to keep the maps beside other per-pixel results.

## Settings worth knowing

* **Moment smoothing** smooths the mean and standard-deviation maps before the
  ratios are formed (box, disk or Gaussian of the given radius). It trades
  resolution for precision.
* **Detrending** divides the variance by K − 2·segments rather than K − 1: each
  fitted line removes two degrees of freedom, and ignoring it biases B low.
* The variance is the unbiased sample variance (K − 1); the population variance
  would bias B low by (K − 1)/K.

## Further reading

* [Number & Brightness — theory](docs/concepts/number_and_brightness.md)
* [Number & Brightness — guide](docs/guides/67_number_and_brightness.md)
* Digman, Dalal, Horwitz, Gratton (2008) Biophys. J. 94, 2320 —
  [10.1529/biophysj.107.114645](https://doi.org/10.1529/biophysj.107.114645)
* Dalal, Digman, Horwitz, Vetri, Gratton (2008) Microsc. Res. Tech. 71, 69 —
  [10.1002/jemt.20526](https://doi.org/10.1002/jemt.20526)
