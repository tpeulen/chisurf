---
type: Guide
title: 'Checking a burst folder before an MFD fit'
description: What MFD Prepare checks in a burst-analysis folder — photon sources, the photon-index convention, each detector's channel definition against the burst table's counts, and where the mean micro time comes from — and how to run it from Python, the CLI or its window.
tags: [guides, bursts, mfd, fret, tcspc]
---

# Checking a burst folder before an MFD fit

**What you get:** a report that says, for one burst-analysis folder, whether
the photons behind every burst can be found and read, which photon-index
convention the `.bur` tables use, how each detector is defined in terms of
routing channels and micro-time windows, and whether that definition
reproduces the tables' own photon counts. It moves and rewrites nothing.

This is the reading step of the 2D MFD fit, run on its own.
{doc}`57_mfd_fitting` loads a folder through the same
`chisurf.core.fluorescence.mfd.prepare.prepare_burst_folder`; when that load
refuses a detector, MFD Prepare shows why. The model the result feeds is
{ref}`concept-mfd-fitting`.

## 1. Where it is

MFD Prepare is **not reachable from any menu or hub**. Its manifest is
`menu_hidden`, and no hub tool embeds it (the burst hubs do not list it). It
is reached from:

* the CLI, `csc mfd-prepare`;
* Python, `chisurf.plugins.burst.mfd_prepare.api.prepare_folder`, or the core
  function directly;
* the RPC service `mfd_prepare.prepare`;
* its window, opened from the ChiSurf console:
  ```python
  from chisurf.plugins.burst.mfd_prepare.gui.tool import MfdPrepareTool
  w = MfdPrepareTool(); w.show()
  ```

The window is **Browse…** (pick the analysis folder), **Prepare**, and a text
box with the report. Without an RPC client it runs in the GUI thread, so the
window is unresponsive for the few seconds the photons take to read.

```{figure} figures/mfd_prepare_report.png
:name: fig-mfd-prepare-report
:width: 100%

MFD Prepare on the shipped `bh_spc132_sm_dna` burst folder: 2980 bursts,
three detectors, exclusive photon indices, ten `.spc` sources resolved through
the `.mti` sidecars, and every detector's count agreement 1.0000.
```

## 2. What it checks

The folder is the analysis folder (holding `bi4_bur/` and `Info/`), the
`bi4_bur` directory, or one `.bur` file. Every row of a `.bur` table points
back into a photon file as `(First Photon, Last Photon)`.

| line of the report | what was done |
|---|---|
| `bursts: N (M interleaved sentinel rows removed)` | the all-zero rows the `.bur` format places between bursts, so that companion folders align by position, are dropped |
| `detectors:` | detector names from the `Number of Photons (<name>)` columns |
| `photon index: inclusive/exclusive (agreement …)` | whether `Number of Photons = Last − First + 1` (current writer) or `Last − First` (older folders). Read off the table and honoured; slicing an old folder with the new convention adds one photon to every burst |
| `mean micro time from: bur column / photons` | the per-detector ⟨t⟩ is taken from `Mean Microtime (<name>) (ns)` when the table has it, otherwise recomputed from the photons |
| `m000.spc -> … [mti]` | each `First File` resolved to a file: the recorded manifest (`Info/analysis.json`), then the legacy `Info/*.mti` sidecar, then a file of that name beside the folder. A read that yields zero photons raises `UnresolvedPhotonSource` instead of returning an empty stream |
| `<name>: k bursts with no photons` | per detector |
| `<name>: count agreement a [ok/UNVERIFIED]` | the fraction of bursts for which the detector's photon count, recomputed from the photons with the channel definition in use, equals the table's column. **ok** needs ≥ 0.98 |

The channel definition comes from the folder's manifest when it records one,
otherwise it is **inferred**: candidate routing channels and micro-time
windows are tried on 250 bursts and accepted only if they reproduce the count
column exactly. On the shipped folder (no manifest):

| detector | channels | micro-time window |
|---|---|---|
| green | 0, 8 | all |
| red | 1, 9 | all |
| yellow | 1, 9 | 2048–4094 |

"yellow" is the acceptor under acceptor excitation: the same channels as red,
delayed. That is why no detector name can define it. If inference fails, the
last resort is the conventional green = (0, 8), red = (1, 9), and a detector
that then disagrees with its counts is reported `UNVERIFIED` and refused by
the MFD fit.

## 3. Reading it

* **All `ok`**: the folder can be fitted. Everything the 2D MFD reader will use
  was checked.
* **A detector `UNVERIFIED`**: its photons would be counted under the wrong
  colour. Record the detectors in the analysis manifest, or pass `streams=`
  explicitly (below). Do not fit with it.
* **`UnresolvedPhotonSource`**: a photon file moved or never existed. The
  bursts can be displayed, but ⟨t⟩, the IRF and the background, which the MFD
  fit takes from the photons, cannot be computed.
* **Many bursts with no photons in one detector** (here 1231 of 2980 in
  yellow): donor-only bursts, or an acceptor that bleached. Expected in PIE
  data, and it becomes the donor-only population in the fit.

## 4. Headless

```bash
csc mfd-prepare prepare "path/to/burstwise_All 0.1000#15" --report-only   # the report above
csc mfd-prepare prepare FOLDER                                         # full JSON result
csc mfd-prepare prepare FOLDER --no-photons                            # skip photon loading when possible
csc mfd-prepare contract                                               # the RPC contract
```

`--no-photons` only skips the photons when the table carries its mean micro
times *and* a manifest defines the detectors; the shipped folder has neither,
so the photons are read anyway and the counts still checked.

```python
from chisurf.core.fluorescence.mfd.prepare import prepare_burst_folder

folder = "path/to/burstwise_All 0.1000#15"
prep = prepare_burst_folder(folder, with_photons=True)
print(prep.report())
print(len(prep), prep.channels, prep.verified_channels)
# 2980 ('green', 'red', 'yellow') ('green', 'red', 'yellow')
prep.require_verified(["green", "red"])      # raises, naming the fix, if either is not

# an explicit channel definition instead of inference: one entry per detector
prep = prepare_burst_folder(folder, streams=[
    {"name": "green", "channels": [0, 8]},
    {"name": "red", "channels": [1, 9]},
    {"name": "yellow", "channels": [1, 9], "micro_time_ranges": [[2048, 4094]]},
])
print(prep.summary["stream_origin"], prep.summary["count_agreement"])
# caller {'green': 1.0, 'red': 1.0, 'yellow': 1.0}
```

`prep.counts`, `prep.spans` (per-detector first-to-last photon span, s),
`prep.mean_micro_time` (ns), `prep.duration`, `prep.first_photon`/`last_photon`
(always inclusive) and `prep.rows` (positions in the concatenated table, for
writing a result back beside the `.bur` files) are the arrays the MFD fit
consumes; `prep.summary` holds the diagnostics.

## Using it well

* **Run it once per folder, before the first MFD session**, and whenever the
  folder was copied or the raw files moved.
* **Record the detectors** in the analysis manifest when you write the
  folder. Inference works on clean data; a manifest works always.
* **Read the photon-index line** for folders written by older software: an
  `exclusive` folder is fine, provided everything downstream reads it through
  this function.

## Known defects

* **The JSON result is not JSON.** With photons loaded (the default),
  `PrepareResult.summary` carries the open TTTR objects under `_tttrs`, so
  `json.dumps(result.to_dict())` raises `Object of type TTTR is not JSON
  serializable`. The CLI hides it with `default=str`; the RPC method
  `mfd_prepare.prepare` returns the same dict and cannot be serialised by the
  transport. Fix: drop `_tttrs` in `prepare_folder` (or in `_jsonable`).
* **`csc mfd-prepare fit` does not run.** On the shipped folder it fails with
  `MfdReader object has no attribute 'experiment'`. Fit with
  {doc}`57_mfd_fitting` instead.
* **A partial `streams=` crashes.** Passing definitions for green and red
  only, on a folder with three detectors, raises `IndexError: index 2 is out
  of bounds` in `prepare_burst_folder` (`mfd/prepare.py`, count-agreement
  loop) instead of saying which detector has no definition. Pass one entry per
  detector.
* **Not reachable from the GUI** (see §1).

## See also

- {doc}`57_mfd_fitting` — the fit this prepares for.
- {ref}`concept-mfd-fitting` — why ⟨t⟩, the spans and raw observable space.
- {ref}`concept-smfret-bursts` — bursts, detectors and PIE.
