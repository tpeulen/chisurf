---
type: Guide
title: 'Planning a scan: which dwell time measures D best?'
description: 'Before you record an image-correlation measurement, this tool answers two questions from the settings alone: how precisely will this acquisition measure $D$, and which pixel dwell time would measure it better.'
tags: [guides, scan, precision]
---

# Planning a scan: which dwell time measures D best?

Before you record an image-correlation measurement, this tool answers two
questions from the settings alone: **how precisely will this acquisition measure
$D$**, and **which pixel dwell time would measure it better**. It needs no data.

For why an optimum exists at all — and how far it can honestly be predicted —
see {ref}`concept-scan-precision`.

## Open the tool

It lives in **Main → Tools → Calculators**, as the **📐 RICS precision** entry
in the calculator list (or standalone as *Main → Tools → RICS-Precision*). It
sits with the calculators rather than in the imaging pipeline because it is one:
it consumes no dataset, opens no file and produces no analysis — it turns the
settings you type in into a predicted error, exactly like the FRET and FCS
calculators beside it.

```{figure} figures/precision_workspace.png
:name: fig-precision-workspace
:width: 100%

The RICS-precision calculator. Left: what you are measuring and how you intend to
scan it. Right: predicted relative error against pixel dwell time, on log axes,
with your own setting marked as a diamond. Here the default 8 µs sits just left
of the minimum near 16 µs — about 1.4× worse, which is not worth changing the
protocol for.
```

## Describe the measurement

**Sample.**

* **D** — the diffusion coefficient you expect. This is the awkward part of
  planning: the best settings depend on the answer you do not have yet. Use a
  literature value or an order-of-magnitude guess. A free dye is a few hundred
  µm²/s, a labelled protein a few tens, a membrane protein below one.
* **Molecules in view** — too few and the correlation is noisy; too many and its
  amplitude (which goes as $1/N$) sinks into the background.
* **Brightness** — photons per second from a single molecule at the focus
  centre. After frame count this is the dominant lever, and a dim label cannot
  be rescued by scanning cleverly.

**Optics.** Beam waists `w_r` and `w_z`, and the pixel size. Measure the waists
with the waist calibration rather than guessing: every predicted error scales
with `w_r`. The pixel size should sample the waist several times over — roughly
4 to 6 pixels across `w_r` — or the spatial shape of the correlation is
undersampled. Tick **Membrane (2-D)** for a surface measurement, which has
different shape factors from a 3-D focus.

**Scan.** The dwell time you plan to use, the pixels per line and lines per
frame, the frame count, and the **line overhead** — how much longer a line takes
than the sum of its pixels, from flyback and settling (1.2 means 20 %). The
sweep scales the line time with the dwell, because a line cannot stay short as
its pixels grow.

**Estimator** (collapsed; the defaults are fine). *Lags fitted* costs as the
fourth power, so raising it is expensive, and it must stay below half the
smaller image dimension — each lag is averaged over the pixel pairs that
realise it, and a small image holds too few, so the prediction is refused with
a message rather than computed from nothing. *Repeats* sets how many Monte-Carlo
realisations stand behind each point. *Seed* makes a quoted prediction
reproducible.

Press **▶ Predict**.

## Read the result

The **status line** is the summary: the error at your own setting, a verdict,
and how far you are from the best dwell — for example *"At 8 µs: 3.3 % error
(good) — about 1.4× worse than the best dwell (15.8 µs)."*

The verdicts are

| Predicted error | Verdict | What to do |
| --- | --- | --- |
| below 5 % | good | record it |
| 5–20 % | usable | fine for comparing conditions, thin for absolute values |
| 20–50 % | poor | change something before spending the beam time |
| above 50 % | unusable | the acquisition cannot answer the question |

The **curve** shows why. It rises at both ends: scan too fast and the molecule
has not moved between neighbouring pixels; scan too slowly and it has already
decorrelated. Both axes are logarithmic, because a badly-matched dwell is wrong
by orders of magnitude and would otherwise flatten the interesting range into a
line.

Three things are worth knowing before acting on the minimum:

* **Read it as an order of magnitude.** Each point is itself a Monte-Carlo
  estimate carrying roughly 10 % uncertainty at the default repeat count, so
  along a flat stretch the argmin wanders between neighbouring points from noise
  alone. Compare error values; do not chase the exact position.
* **Being 1.5× off the optimum is usually not worth a protocol change.** Being
  5× off is.
* **Slower is also longer.** The frame count is held fixed while the dwell is
  swept, so the right-hand side of the curve is a *longer* acquisition. The
  **Numbers** tab gives the implied line and frame time next to each error, so
  you can weigh precision against beam time yourself.

The **Numbers** tab lists the sweep as a table; **💾 Export CSV** writes it out
for a methods section or a lab-book entry. A dwell time the estimator cannot
evaluate shows as `—` rather than taking the rest of the curve down with it.

## Headless

The same prediction runs from the command line, which is the practical way to
sweep $D$ rather than the dwell time:

```bash
rics-precision 10 --pixel-time 8 --nx 64 --ny 64 --frames 100 \
               --pixel-size 50 --w-r 0.25 --w-z 1.25 \
               --brightness 100 --n-particles 50 \
               --out-csv sweep.csv
```

It prints the swept table, the best dwell and where your own setting sits;
`--json` emits the whole sweep for a script to consume. All of the compute is
Qt-free, so it needs no display.

A dwell time the estimator cannot evaluate is a `null` in the JSON (and an empty
field in the CSV) rather than a `NaN`, so the payload parses under a strict
reader. If *no* dwell time is realisable — the usual cause is a waist or pixel
size that cannot be right — the command exits non-zero in both modes, with
`--json` reporting `{"error": …}` instead of a curve of nulls.

## Using it well

Sweep **D**, not just the dwell. Since $D$ is an input, the honest procedure is
to try the plausible range — say a factor of three either side of your guess —
and pick a dwell that is tolerable across all of it, rather than optimising
against one guessed number.

If two species in the sample differ by orders of magnitude in $D$, no single
dwell serves both. The planner shows the cost of the compromise directly, which
usually makes the case for two acquisitions instead of one.

Finally, this is precision, not accuracy. It tells you how much your fitted $D$
would scatter, and nothing about bias: a wrong beam waist, an uncorrected drift
({doc}`43_drift_correction`) or an unmodelled immobile fraction will move the
answer in ways no amount of averaging removes.

## Runnable example

`examples/notebooks/RICS_Simulation_And_Recovery.ipynb` is the other half of this
page: rather than *predicting* the precision of a scan, it simulates one with a
known diffusion coefficient and measures what comes back — including the slow
end of the working range this planner exists to keep you out of.

## See also

- Tool: **RICS-Precision** (`chisurf/plugins/calculator/rics_precision/`).
