---
type: Guide
title: More samples, processed the same way
description: Burst Analysis step 4 — further measurements processed with exactly the pipeline tuned on the first one (setup, calibration, burst search, Burst MLE IRF, shifts and fit window, the optional steps), in the window and headless with BurstWorkflow.process_more.
tags: [guides, smfret, bursts, lifetime, batch]
---

# More samples, processed the same way

**Spectroscopy › Single-Molecule › Burst Analysis**, step **4. More samples**
(`chisurf/plugins/burst/burst_analysis/more_samples.py`, window
`gui/more_samples_app.py`). The pipeline steps are in [Lifetime from photon
bursts](21_lifetime_from_bursts.md) and [Photon burst identification](13_burst_identification.md).

A measurement series — the same construct at several conditions, repeats of one sample, a
titration — is only comparable if every measurement went through the **same** analysis. You tune
the pipeline on one measurement, then hand it the rest: step 4 runs each of them through exactly
that pipeline, one short row per sample.

## The recipe

What every sample goes through is one **recipe**, captured from the steps as they are set when
you press **Run** (`Recipe.capture`, from what the steps already export — the workflow context,
Burst Selection's settings, Burst MLE's settings payload):

| Part | From | Applied to each sample |
|---|---|---|
| Setup | step 0 | the same detectors, windows and G factors |
| Calibration | step 1 | the same buffer, IRF and reference-dye files, the calibration report |
| Burst search | step 2 | the same algorithm, parameters and filter |
| Burst MLE | step 3 | per detector the same model, start values, fixed parameters, **fit window**, IRF and calibrated time shifts |
| Optional steps | 2.1–3.1 | Fusion, BVA, 2CDE, H2MM — each only if it ran on the first data |

The **background** is the rule, not the number: the buffer's when step 1 has a buffer, else the
strict background selection of each sample's **own** photons (background belongs to the
measurement). New calibration files are added in step 1; the recipe follows them.

## In the window

1. Run steps 0–3 on the first measurement. Step 4 opens once Burst MLE has fitted it.
2. Drop further measurements on step 4: drag them from its *Workspace data* table into
   *Samples* (a group brings all its files), or drop files on the ChiSurf window while the step
   is open.
3. Press **Run** (or **Next**). The window waits behind the progress card; **Stop** stops after
   the step each sample is in. Samples run one at a time, or several at once when the files are
   large enough for the burst search to use more processes (the same limit, `CHISURF_BURST_WORKERS`).

![Step 4 in Simple mode after a run: two samples done, a third (not a photon file) failed](figures/116_more_samples_simple.png)

Each row is short — sample, bursts, mean τ of the first detector, mean E (two colours), status
(*queued*, *running*, *done*, *failed*). The tooltip has the rest: the run, τ per detector, the
recipe and calibration-report ids, or why the sample failed. A failed sample never stops the
others; **Run** again processes the failed and queued ones.

**Advanced** adds the recipe, one short row per part with its details in the tooltip, and
**Re-run** of the selected sample with the recipe as it is now:

![Step 4 in Advanced: the recipe part by part](figures/116_more_samples_advanced.png)

## Where the results go

Where the first data's went: each sample's burst run into its `.pto` analysis container (shown
under its photon stream in the workspace), its Burst MLE lifetimes and its BVA / 2CDE / H2MM
results as tables of that run, and beside them the calibration report (`burst_calibration`) and
the recipe (`burst_recipe`, with `recipe_id` and `calibration_report_id`), so every number names
what made it (`more_samples.read_recipe(container)`).

## Headless

```python
import json

from chisurf.plugins.burst.burst_analysis.api import BurstWorkflow, Recipe

if __name__ == "__main__":          # the burst fit runs in worker processes
    recipe = Recipe.from_payload(json.load(open("recipe.json")))
    rows = BurstWorkflow.offline().process_more(["m2.ptu", "m3.ptu"], recipe)
    for row in rows:
        print(row["name"], row["status"], row["bursts"], row["tau"], row["error"])
```

The recipe is what the window keeps in its settings (`state["children"]["more"]["recipe"]`) and
what `hub.capture_recipe().to_payload()` returns; save it as JSON once and every later batch uses
it. Processing a measurement with `process_more` and running steps 2–3 on it by hand with the
same settings give the same bursts and the same lifetimes (tested,
`burst_analysis/tests/test_more_samples.py`).

Figures: `docs/guides/screenshots/guide_116_more_samples.py`.
