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

Before running, a step fingerprints four things:

* **its input files** — the burst tables *and* the raw measurements they point
  into, named in the folder's `Info/analysis.json`. Each is identified by path,
  size and modification time, so the check costs one `stat` per file rather than
  re-reading gigabytes of photon data.
* **every setting the computation is given** — including the ones you did not
  type: the detector definitions, the micro-time ranges, the per-detector IRF
  and background arrays sent over from *IRF & Background*.
* **the reading correction in force** — the per-channel TAC linearisation LUTs
  and micro-time shifts of the active setup. These belong to no step's settings
  and are applied inside the reader, so without this a LUT you edited would
  change every micro-time an analysis sees while every step reported its old
  result as current.
* **the code that does the computing** — each step's own version number plus the
  build of the library that holds the estimator (`fit2x`, `tttrlib`). A
  correction to a fit is a reason to refit, and it is the one reason you cannot
  see by looking at your own files.

If all four are identical to what produced the result the step is holding, the
run is skipped and the status bar says so:

```
Unchanged — kept the previous BVA result (🔁 Restart recomputes it)
```

Anything else recomputes: a changed τ or window length, a different donor
channel, one more `.bur` file in the folder, a re-recorded measurement, a new
IRF. You never have to remember to invalidate anything.

| Step | Reuses when | Recomputes when |
|---|---|---|
| 2. Burst Selection | the same raw files and the same search settings produced the displayed search | any file or setting differs |
| 3. BVA | the plot on screen is the answer *and*, for a Run, the `bv4/` files are current | settings, detectors or burst files differ |
| 4. 2CDE | the `2c4/` companions on disk match the current settings | variant, kernel, τ, channels or burst files differ |
| 5. MLE-Burstwise | the `bg4/`, `br4`, `by4/` exports on disk match | model, start values, min photons, per-detector settings or IRF differ |
| 6. H2MM | the fitted model on screen matches the request | state range, criterion, engine, seed, streams or burst files differ |
| 7. MLE-Statewise | the per-state `b?4_s*` folders on disk match | the H2MM run, the burst-wise settings or the experiment's IRF differ |

…and, for every row, when the raw measurements change, when the setup's reading
correction changes, or when the code that computes it does.

Steps 5 and 6 differ in *where* they keep the answer, which is why step 5 can
reuse across sessions and step 6 cannot: the MLE batch's product is the exported
files, while an H2MM fit lives only in the panel.

## Steps that start themselves

Two steps do not wait for a Run click at all: **2CDE (4)** and **H2MM (6)**
compute as soon as you open them, because by then everything they need has been
decided upstream. Both run off the GUI thread and both carry a **Stop** button
in their toolbar — BVA, which has always recomputed on its own when the folder
or a setting changes, has one now too.

Stopping is not a pause: a stopped run computed part of an answer, not an
answer, so nothing is remembered and the next run starts over. It is also not
undone by walking away — a computation you stopped does **not** start itself
again when you come back to the step, or Stop would only postpone the work until
the next *Next*. Change a file or a setting, or press **Run**, and the step
computes again; the suppression is exactly as narrow as the stop was.

Arriving at a step whose result is already there costs nothing — that is the
rule above doing its job, and it is what makes starting on arrival reasonable in
the first place.

## Everything downstream is handed the same files

The steps below the separator do not ask you to find the analysis again — the
workflow gives each of them what it needs from the run you just did:

| Panel | Receives |
|---|---|
| Browser | the burst folder, loaded as a table |
| Accurate FRET | the first `.bur` as its burst table, channel columns auto-mapped |
| Burst FCS | the burst folder (its list expands the folder itself) |
| Kinetics (GS) | every `.bur` the search produced |
| Background, IRF & Background | the raw TTTR files and the channel setup |

A panel where you already chose files yourself is left alone — the hand-off
fills an empty panel, it does not overwrite your selection.

## The stamp files

Each step that writes results writes a small JSON file next to them —
`bv4/bva.stamp.json`, `2c4/2cde.stamp.json`, `burst_mle.stamp.json`. They record
the fingerprint, the settings and the files involved:

```json
{
  "tool": "bva",
  "version": 2,
  "entries": [
    {
      "fingerprint": "3eae4503e38f2d32",
      "params": {"minimum_window_length": 0.01, "number_of_photons_per_slice": 10},
      "inputs": ["…/bi4_bur/m000.bur", "…/Info/analysis.json", "…/m000.spc"],
      "outputs": [
        {"path": "…/bv4/m000.bv4", "size": 20416, "mtime_ns": 1769606400000000000}
      ]
    }
  ]
}
```

They answer, on their own, "what settings is this output folder the result of?"
— useful long after the session that produced it. Deleting one costs nothing but
a recomputation.

Two details are worth knowing. A stamp records each output's **size and
modification time**, not only its name, so a result that was truncated or
rewritten underneath is not reused merely because a file of that name still
exists. And a stamp holds **several entries**, one per fingerprint, so analysing
one folder with two different selections of burst files remembers both instead
of making each recompute the other.

## Forcing a recomputation

You rarely need to: change any setting and the step runs. When you do want the
same computation again, press **🔁 Restart** — every analysis step has one
beside its Run button, and it is outlined the moment a run was skipped, which is
exactly when it is the thing you want. Deleting the stamp file works too.

```python
tool._run_analysis(force=True)      # BVA / H2MM
tool.run(force=True)                # 2CDE
wizard.process_bursts(force=True)   # burst-wise MLE export
```

Note that recomputing an H2MM fit reproduces the same answer rather than drawing
a new one: the restarts are seeded, and the seed is a field in the fit options.
That is deliberate — a reported state count is only reproducible if the seed
travels with it, and the status line reports which seed produced the fit. To draw
a genuinely independent sample, change the seed.

## What this does not do

The fingerprint trusts modification times. A file restored from a backup with an
old timestamp and different content will not be noticed — the one case where you
should delete the stamp. Content hashing is available in
`chisurf.core.analysis_cache.fingerprint(..., content=True)` and is not used by
default because hashing a burst folder costs more than the analysis it would
save.

It also cannot know about a change made outside chisurf to something that is
neither a file nor a setting — an environment variable that switches a numerical
backend, say. The version of the fitting library is covered; the way it was
configured at run time is not.

## Related

* [13 — Photon burst identification](13_burst_identification.md)
* [08 — Burst Variance Analysis (BVA)](08_burst_variance_analysis.md)
* [01 — FRET-2CDE / ALEX-2CDE burst dynamics](01_fret_2cde.md)
* [21 — Lifetime from photon bursts (MLE)](21_lifetime_from_bursts.md)
* [19 — Photon-by-photon HMM (H2MM)](19_h2mm_hidden_markov.md)
