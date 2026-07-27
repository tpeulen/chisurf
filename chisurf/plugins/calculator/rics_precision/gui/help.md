# RICS precision

How well will this scan measure a diffusion coefficient? Answered before the
microscope time is spent, rather than after.

## Why the question is awkward

Choosing a scan speed is a trade-off with a minimum in the middle:

* **Too fast** — the molecule has barely moved between neighbouring pixels, so
  the correlation carries almost no information about D, and few photons land in
  each pixel.
* **Too slow** — it has already decorrelated by the time the next pixel is read,
  so the correlation has decayed before you sample it.

Where that minimum lies depends on the D you are trying to measure — which is
the number you do not have yet. Hence a planner: put in the D you expect, and
see which settings can resolve it.

## Reading the curve

The plot is the predicted relative error against pixel dwell time, with your own
setting marked in orange. Both ends rise; the useful region is the trough.

The status line turns that into a sentence — how good your setting is, and how
much better the best dwell would be.

Rough guide to the numbers:

| predicted error | meaning |
| --- | --- |
| below 5 % | good; differences between conditions will be measurable |
| 5–20 % | usable for a large effect |
| 20–50 % | poor; only order-of-magnitude statements |
| above 50 % | the acquisition cannot measure this D |

**Read the position of the minimum as an order of magnitude, not a setting to
dial in.** The prediction is a Monte-Carlo estimate and carries roughly
1/sqrt(2 × repeats) of its own uncertainty — about 11 % at the default. On a
flat stretch of the curve, neighbouring points swap places from noise alone.

## What actually moves the answer

* **Frames** — precision improves as the square root, so halving the error costs
  four times the acquisition. This is usually the cheapest lever.
* **Brightness** — the dominant lever after that. A dim label cannot be rescued
  by scanning cleverly.
* **Molecules in view** — too few is noisy; too many sinks the correlation
  amplitude (which goes as 1/N) into the background.
* **Image size** — a larger frame averages more pixel pairs, at the cost of a
  longer frame time.
* **Beam waist** — measure it with the waist calibration rather than guessing.
  Every predicted error scales with it.

## Cost

The estimator computes the full covariance of the correlation estimator, which
grows as the **fourth power** of the number of lags fitted. Raising *Lags fitted*
from 4 to 8 costs sixteen times as much. The default is deliberately below the
reference implementation's 15.
