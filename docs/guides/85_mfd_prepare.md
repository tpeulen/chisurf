---
type: Guide
title: Checking a burst folder before an MFD fit
description: What MFD Prepare checks in a burst-analysis folder — photon sources, the photon-index convention, each detector's channel definition against the burst table's counts, and where the mean micro time comes from — and how to run it from Python, the CLI or its window.
tags: [guides, bursts, fitting, photons, python, cli, headless]
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

**File → Data → MFD Prepare** opens the window (or
`python -m chisurf.emtk --plugin mfd_prepare`). Without a window it is
reached from:

* the CLI, `csc mfd-prepare`;
* Python, `chisurf.plugins.burst.mfd_prepare.api.prepare_folder(PrepareRequest(folder=…))`
  (`PrepareRequest` from `…mfd_prepare.api.models`), or the core function
  directly;
* the RPC service `mfd_prepare.prepare`.

The window opens at 1100 × 720 (a saved size takes precedence). Top to bottom:

| control | what it does |
|---|---|
| folder line | the burst-analysis folder that **Prepare** will read, or "No folder selected" |
| **Browse...** | opens the drawn folder chooser (starts in the folder already chosen); **Choose** takes the highlighted folder, or the folder being browsed when none is highlighted; **Cancel** changes nothing. Dropping the folder (or one `.bur` file) on the window does the same |
| **Prepare** | greyed until a folder is chosen; reads the photons in the background (the window stays responsive, and Browse and Prepare are greyed while it runs) |
| **Guide**, **Help** | the step-by-step tour (it waits for you to press Browse... and Prepare) and the help window |
| status line | what was done last: the bursts and the verdict, or the error |
| **Detectors** | one row per detector: channels, micro-time window, bursts without photons, count agreement and the verdict `ok` / `UNVERIFIED` |
| **Photon sources** | each photon file the bursts point into, where it was found and how many photons it holds |
| **Folder summary** | bursts, photon-index convention, where the mean micro time comes from, duration, photons in the bursts |
| **Report** | the report text, scrollable with the mouse wheel (section 2 explains each line) |

The three tables appear after **Prepare**; they are the same facts as the report, one row per detector or file. Without an RPC
client the preparation runs in this process, otherwise through `mfd_prepare.prepare`.

```{figure} figures/mfd_prepare_report.png
:name: fig-mfd-prepare-report
:width: 100%

MFD Prepare on the measured `bh_spc132_sm_dna` burst folder shipped with the burst-selection tests: 2980 bursts
(2990 interleaved sentinel rows removed), three detectors, exclusive photon indices, ten `m00N.spc` files resolved
through their `.mti` sidecars, 225 358 photons in the bursts, every detector's count agreement 1.0000.
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
csc mfd-prepare fit FOLDER --n-states 1                                # read, then fit the 2D MFD model
csc mfd-prepare contract                                               # the RPC contract
```

`--no-photons` only skips the photons when the table carries its mean micro
times *and* a manifest defines the detectors; the shipped folder has neither,
so the photons are read anyway and the counts still checked.

`fit` reads the folder through the MFD reader, fits the {doc}`57_mfd_fitting`
model with the Poisson score and prints JSON. On the shipped folder, one state
on the default 41 × 41 grid (about 20 s) gives `tauD0` 2.81 ns, `alpha` 0.026,
`R1` 54.0 Å, `donorOnly` 0.39 at χ²ᵣ 1.44; `--n-states 2` (about 90 s) splits
off a minor 31 Å state. `uncertainties` is always `null`: the histogram score
has no valid curvature, so use the model's `bootstrap()` or `burstwise_score()`.

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

Explicit definitions are matched to the detector columns by name, in any
order. Every detector needs one: leaving `yellow` out raises
`ValueError: streams= must define every detector of … (green, red, yellow): no
definition for 'yellow'`, and a name the folder does not have is refused the
same way. A detector is never completed from a guess, because its name does
not determine its definition.

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

## See also

- {doc}`57_mfd_fitting` — the fit this prepares for.
- {ref}`concept-mfd-fitting` — why ⟨t⟩, the spans and raw observable space.
- {ref}`concept-smfret-bursts` — bursts, detectors and PIE.
- Tool: MFD Prepare (`chisurf/plugins/burst/mfd_prepare/`).

```{figure} figures/mfd_prepare_native_primary_window.png
:width: 100%

MFD Prepare at its initial 1100 × 720 on a single-file excerpt of the same
BH SPC-132 measurement (`burst_analysis_handoff`, inclusive photon indices):
152 bursts, 17 282 burst photons, every detector's count agreement 1.0000. The
folder is not remembered: choose it and press **Prepare** again after
reopening. On a narrow window, scroll the **Report** to its last lines.
```
