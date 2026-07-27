# 53 — Reusing results: when a step recomputes, and when it does not

The burst workflow asks each step to run more often than you press its Run
button. Pressing **Next** runs the current step; walking back to look at a plot
hands the panel its burst folder again, which a panel reads as "something
changed". Every one of those used to be a full recomputation — BVA over every
burst, 2CDE over every photon pair, a burst-wise MLE fit of every burst, an
H2MM state scan with restarts — producing exactly the numbers that were already
on the screen.

A step now recomputes only when the answer could differ.

## What counts as a change

Before running, a step fingerprints two things:

* **its input files** — identified by path, size and modification time, so the
  check costs one `stat` per file rather than re-reading gigabytes of photon
  data, and
* **every setting the computation is given** — including the ones you did not
  type: the detector definitions, the micro-time ranges, the per-detector IRF
  and background arrays sent over from *IRF & Background*.

If both are identical to what produced the result the step is holding, the run
is skipped and the status bar says so:

```
Unchanged — kept the previous BVA result
```

Anything else recomputes: a changed τ or window length, a different donor
channel, one more `.bur` file in the folder, a re-recorded measurement, a new
IRF. You never have to remember to invalidate anything.

| Step | Reuses when | Recomputes when |
|---|---|---|
| 2. Burst Selection | the same raw files and the same search settings produced the displayed search | any file or setting differs |
| 3. BVA | the plot on screen is the answer *and*, for a Run, the `bv4/` files are current | settings, detectors or burst files differ |
| 4. 2CDE | the `2c4/` companions on disk match the current settings | variant, kernel, τ, channels or burst files differ |
| 5. MLE-Lifetime | the `bg4/`, `br4`, `by4/` exports on disk match | model, start values, min photons, per-detector settings or IRF differ |
| 6. H2MM | the fitted model on screen matches the request | state range, criterion, engine, streams or burst files differ |

Steps 5 and 6 differ in *where* they keep the answer, which is why step 5 can
reuse across sessions and step 6 cannot: the MLE batch's product is the exported
files, while an H2MM fit lives only in the panel.

## The stamp files

Each step that writes results writes a small JSON file next to them —
`bv4/bva.stamp.json`, `2c4/2cde.stamp.json`, `burst_mle.stamp.json`. They record
the fingerprint, the settings and the files involved:

```json
{
  "tool": "bva",
  "fingerprint": "3eae4503e38f2d32",
  "params": {"minimum_window_length": 0.01, "number_of_photons_per_slice": 10},
  "inputs": ["…/bi4_bur/m000.bur", "…"],
  "outputs": ["…/bv4/m000.bv4", "…"]
}
```

They answer, on their own, "what settings is this output folder the result of?"
— useful long after the session that produced it. Deleting one costs nothing but
a recomputation.

## Forcing a recomputation

You rarely need to: change any setting and the step runs. When you do want the
same computation again — an H2MM fit is stochastic, so a second fit is a genuine
second sample — either delete the stamp file or call the step from Python:

```python
tool._run_analysis(force=True)      # BVA / H2MM
tool.run(force=True)                # 2CDE
wizard.process_bursts(force=True)   # burst-wise MLE export
```

## What this does not do

The fingerprint trusts modification times. A file restored from a backup with an
old timestamp and different content will not be noticed — the one case where you
should delete the stamp. Content hashing is available in
`chisurf.core.analysis_cache.fingerprint(..., content=True)` and is not used by
default because hashing a burst folder costs more than the analysis it would
save.

## Related

* [13 — Photon burst identification](13_burst_identification.md)
* [08 — Burst Variance Analysis (BVA)](08_burst_variance_analysis.md)
* [01 — FRET-2CDE / ALEX-2CDE burst dynamics](01_fret_2cde.md)
* [21 — Lifetime from photon bursts (MLE)](21_lifetime_from_bursts.md)
* [19 — Photon-by-photon HMM (H2MM)](19_h2mm_hidden_markov.md)
