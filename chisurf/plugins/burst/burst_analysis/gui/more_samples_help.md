# 4. More samples

You tuned the pipeline on one measurement: the setup, the calibration files, the burst search, the
IRF, background, model and fit window of Burst MLE, and perhaps BVA, 2CDE, Fusion or H2MM. This
step processes **further measurements exactly the same way**, so their numbers can be compared
with the first one's and with each other.

## What you do

1. **Drop the measurements on the step.** Drag them from the *Workspace data* table into the
   *Samples* table (a group is one row and brings all its files), right-click a row › *Add to this
   tool*, or drop files on the window while this step is open.
2. Press **Run** (or **Next**). The samples are processed one after another, or several at once when
   the files are large enough for the burst search to use more processes. The window waits behind
   the progress card; its **Stop** stops after the step each sample is in. A sample that fails is
   marked *failed* and the others go on; **Run** again processes the failed and the queued ones.

Each row is short: the sample, how many bursts were found, the mean lifetime τ of the first
detector, the mean proximity ratio E (two colours) and the status (*queued*, *running*, *done*,
*failed*). Hover a row for the rest: the run, τ of every detector, the recipe and calibration
report it was made with, or why it failed.

## The recipe

Every sample goes through one **recipe**, captured from the steps as they are set when you press
Run:

| Part | Taken from |
|---|---|
| Setup | step 0: detectors, windows, G factors |
| Calibration | step 1: the buffer, the IRF and reference-dye files already assigned, what they gave (G, V_eff) and the calibration report |
| Search | step 2: the algorithm, its parameters and the filter |
| Fit | step 3: per detector the model, start values and fixed parameters, the **fit window**, the IRF the fit used and its calibrated time shifts |
| Optional steps | Fusion, BVA, 2CDE and H2MM, each only if it ran on the first data, with its settings |

The background is the one rule that is applied, not copied: it is the buffer's when step 1 has a
buffer, else the strict background selection of **each sample's own** photons — background is a
property of the measurement. New calibration files are added in step 1; the recipe follows.

*Advanced* shows the recipe part by part (details in each row's tooltip) and lets you **Re-run** the
selected sample with the recipe as it is now.

## Where the results go

Where the first data's went: the burst run into the sample's `.pto` analysis container, shown
under its photon stream in the workspace; the lifetimes as the run's tables; and beside them the
calibration report (`burst_calibration`) and the recipe (`burst_recipe`, with its id and the
report's id), so every number names what made it.

## From a script

```python
import json
from chisurf.plugins.burst.burst_analysis.api import BurstWorkflow, Recipe

recipe = Recipe.from_payload(json.load(open("recipe.json")))   # or hub.capture_recipe()
rows = BurstWorkflow.offline().process_more(["m2.ptu", "m3.ptu"], recipe)
```

See [More samples, processed the same way](docs/guides/116_more_samples.md) and [Lifetimes from bursts](docs/guides/21_lifetime_from_bursts.md).
